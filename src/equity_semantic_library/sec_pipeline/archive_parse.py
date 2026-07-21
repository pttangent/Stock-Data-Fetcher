from __future__ import annotations

import base64
import binascii
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from .archive_source import sha256_bytes


def tag_value(block: bytes, tag: bytes) -> str:
    match = re.search(rb"<" + tag + rb">([^\r\n<]*)", block, re.I)
    return match.group(1).decode("latin-1", "replace").strip() if match else ""


def unwrap_payload(block: bytes) -> tuple[str, bytes]:
    match = re.search(br"<TEXT>\s*(.*?)\s*</TEXT>", block, re.I | re.S)
    payload = match.group(1) if match else block
    for wrapper in (b"XBRL", b"XML", b"HTML", b"PDF", b"GRAPHIC", b"ZIP"):
        wrapped = re.fullmatch(rb"\s*<" + wrapper + rb">\s*(.*?)\s*</" + wrapper + rb">\s*", payload, re.I | re.S)
        if wrapped:
            return wrapper.decode(), wrapped.group(1)
    return "TEXT", payload.strip()


def decode_binary(payload: bytes) -> bytes:
    stripped = payload.strip()
    if stripped.startswith(b"begin "):
        out = bytearray()
        for line in stripped.splitlines()[1:]:
            if line.strip() == b"end":
                break
            try:
                out.extend(binascii.a2b_uu(line))
            except binascii.Error:
                return payload
        return bytes(out)
    compact = re.sub(br"\s+", b"", stripped)
    if len(compact) > 64 and re.fullmatch(br"[A-Za-z0-9+/=]+", compact):
        try:
            decoded = base64.b64decode(compact, validate=False)
            if decoded.startswith((b"%PDF", b"PK\x03\x04", b"\x89PNG", b"GIF8", b"\xff\xd8\xff")):
                return decoded
        except Exception:
            pass
    return payload


def classify_document(filename: str, document_type: str, wrapper: str, payload: bytes) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()
    head = payload[:1024].lstrip().lower()
    if wrapper in {"PDF", "GRAPHIC", "ZIP"} or ext in {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".xlsx", ".xls"}:
        return "binary", {".pdf": "application/pdf", ".zip": "application/zip", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}.get(ext, "application/octet-stream")
    if ext in {".htm", ".html"} or b"<html" in head or wrapper in {"HTML", "XBRL"}:
        return ("inline_xbrl" if b"<ix:" in payload.lower() or wrapper == "XBRL" else "html", "text/html")
    if ext in {".xml", ".xsd"} or wrapper == "XML" or head.startswith(b"<?xml"):
        return ("xbrl_xml" if document_type.upper().startswith("EX-101") or b"<xbrl" in head else "xml", "application/xml")
    if ext == ".json":
        return "json", "application/json"
    return "text", "text/plain"


def parse_documents(raw: bytes) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for index, match in enumerate(re.finditer(br"<DOCUMENT>(.*?)</DOCUMENT>", raw, re.I | re.S), 1):
        block = match.group(1)
        wrapper, payload = unwrap_payload(block)
        filename = tag_value(block, b"FILENAME")
        document_type = tag_value(block, b"TYPE")
        kind, mime = classify_document(filename, document_type, wrapper, payload)
        decoded = decode_binary(payload) if kind == "binary" else payload
        docs.append({
            "index": index,
            "sequence": tag_value(block, b"SEQUENCE") or str(index),
            "document_type": document_type,
            "filename": filename,
            "description": tag_value(block, b"DESCRIPTION"),
            "wrapper": wrapper,
            "payload": decoded,
            "content_kind": kind,
            "mime_type": mime,
            "source_start_byte": match.start(),
            "source_end_byte": match.end(),
            "block_sha256": sha256_bytes(block),
        })
    return docs


class VisibleTextParser(HTMLParser):
    BLOCKS = {"address","article","aside","blockquote","br","caption","dd","div","dl","dt","figcaption","figure","footer","h1","h2","h3","h4","h5","h6","header","hr","li","main","nav","ol","p","pre","section","table","td","th","tr","ul"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style"} or tag.endswith(":hidden"):
            self.skip += 1
        if not self.skip and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style"} or tag.endswith(":hidden"):
            self.skip = max(0, self.skip - 1)
        if not self.skip and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        value = "".join(self.parts).replace("\xa0", " ")
        value = re.sub(r"[ \t\f\v]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        return re.sub(r"\n{3,}", "\n\n", value).strip()


def html_to_text(payload: bytes) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(payload.decode("utf-8", "replace"), "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
        lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
        return "\n".join(x for x in lines if x)
    except Exception:
        parser = VisibleTextParser()
        parser.feed(payload.decode("utf-8", "replace"))
        parser.close()
        return parser.text()


ANNUAL_ITEMS = ["1", "1A", "1B", "1C", "2", "3", "4", "5", "6", "7", "7A", "8", "9", "9A", "9B", "9C", "10", "11", "12", "13", "14", "15", "16"]
QUARTER_ITEMS = ["I:1", "I:2", "I:3", "I:4", "II:1", "II:1A", "II:2", "II:3", "II:4", "II:5", "II:6"]


def extract_sections(text: str, form: str, group: str) -> list[dict[str, Any]]:
    if not text:
        return []
    lines = text.splitlines(keepends=True)
    candidates: list[dict[str, Any]] = []
    part = ""
    offset = 0
    if group == "event":
        item_re = re.compile(r"^\s*ITEM\s+(\d\.\d{2})\s*[:.\-–—]?\s*(.*)$", re.I)
    elif group in {"annual", "quarterly"}:
        item_re = re.compile(r"^\s*ITEM\s+(\d{1,2}[A-Z]?)\s*[:.\-–—]?\s*(.*)$", re.I)
    else:
        item_re = None
    for line in lines:
        compact = re.sub(r"\s+", " ", line).strip()
        pm = re.match(r"^PART\s+([IVX]+)\b", compact, re.I)
        if pm and len(compact) < 100:
            part = pm.group(1).upper()
        if item_re:
            im = item_re.match(compact)
            if im and len(compact) < 280:
                candidates.append({"part": part, "item": im.group(1).upper(), "title": im.group(2).strip(" .:-–—"), "start": offset + len(line) - len(line.lstrip())})
        offset += len(line)
    selected: list[dict[str, Any]] = []
    if group == "event":
        seen: set[str] = set()
        for candidate in candidates:
            if candidate["item"] not in seen:
                selected.append(candidate)
                seen.add(candidate["item"])
    elif group == "annual":
        limit = len(text) + 1
        for expected in reversed(ANNUAL_ITEMS):
            choices = [c for c in candidates if c["item"] == expected and c["start"] < limit]
            if choices:
                selected.append(choices[-1])
                limit = choices[-1]["start"]
        selected.reverse()
    elif group == "quarterly":
        limit = len(text) + 1
        for expected in reversed(QUARTER_ITEMS):
            choices = [c for c in candidates if f"{c['part']}:{c['item']}" == expected and c["start"] < limit]
            if choices:
                selected.append(choices[-1])
                limit = choices[-1]["start"]
        selected.reverse()
    else:
        headings = {
            "proxy": [r"proposal\s+(?:no\.?\s*)?\d+", r"executive compensation", r"security ownership", r"related person transactions?", r"audit committee"],
            "regulatory": [r"conflict minerals", r"reasonable country of origin inquiry", r"due diligence", r"response to the staff", r"comment letter"],
            "offering": [r"prospectus summary", r"risk factors", r"use of proceeds", r"dilution", r"plan of distribution", r"description of securities"],
        }.get(group, [])
        for pattern in headings:
            for match in re.finditer(rf"(?im)^\s*({pattern})\s*$", text):
                selected.append({"part": "", "item": "", "title": match.group(1).strip(), "start": match.start()})
        selected = sorted({(x["start"], x["title"]): x for x in selected}.values(), key=lambda x: x["start"])
    if not selected:
        return [{"section_key": "full_text", "part": "", "item": "", "title": "Full filing text", "ordinal": 1, "char_start": 0, "char_end": len(text), "text": text}]
    sections: list[dict[str, Any]] = []
    for index, heading in enumerate(selected, 1):
        end = selected[index]["start"] if index < len(selected) else len(text)
        body = text[heading["start"]:end].strip()
        if len(body) < 20:
            continue
        start = text.find(body, heading["start"], end)
        key = f"item_{heading['item']}" if heading["item"] else re.sub(r"[^a-z0-9]+", "_", heading["title"].lower()).strip("_")[:80]
        sections.append({"section_key": key or f"section_{index}", "part": heading["part"], "item": heading["item"], "title": heading["title"], "ordinal": index, "char_start": start, "char_end": start + len(body), "text": body})
    return sections


def extract_tables(payload: bytes, max_rows: int = 50, max_cols: int = 30) -> list[dict[str, Any]]:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(payload.decode("utf-8", "replace"), "html.parser")
        out = []
        for table in soup.find_all("table"):
            all_rows = []
            for tr in table.find_all("tr"):
                cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"], recursive=False)]
                if cells:
                    all_rows.append(cells)
            caption = table.find("caption")
            out.append({"rows": [r[:max_cols] for r in all_rows[:max_rows]], "row_count": len(all_rows), "column_count": max((len(r) for r in all_rows), default=0), "caption": caption.get_text(" ", strip=True) if caption else "", "truncated": len(all_rows) > max_rows or any(len(r) > max_cols for r in all_rows)})
        return out
    except Exception:
        return []


ATTR_RE = re.compile(r"([:\w.-]+)\s*=\s*([\"'])(.*?)\2", re.S)
INLINE_FACT_RE = re.compile(r"<ix:(nonNumeric|nonFraction|fraction)\b([^>]*)>(.*?)</ix:\1\s*>", re.I | re.S)
KEY_XBRL_CONCEPTS = re.compile(r"(?i)(Revenue|SalesRevenue|NetIncomeLoss|OperatingIncomeLoss|GrossProfit|Assets$|Liabilities$|StockholdersEquity|CashAndCashEquivalents|ResearchAndDevelopmentExpense|PaymentsToAcquirePropertyPlantAndEquipment|EarningsPerShare|CommonStocksOutstanding|LongTermDebt)")


def _attrs(raw: str) -> dict[str, str]:
    return {m.group(1): html.unescape(m.group(3)) for m in ATTR_RE.finditer(raw)}


def extract_inline_xbrl(payload: bytes, mode: str = "key_facts") -> list[dict[str, Any]]:
    if mode == "none":
        return []
    source = payload.decode("utf-8", "replace")
    facts = []
    for match in INLINE_FACT_RE.finditer(source):
        attrs = _attrs(match.group(2))
        concept = attrs.get("name", "")
        if mode == "key_facts" and not KEY_XBRL_CONCEPTS.search(concept):
            continue
        parser = VisibleTextParser()
        parser.feed(match.group(3))
        parser.close()
        facts.append({"concept": concept, "context_ref": attrs.get("contextRef", ""), "unit_ref": attrs.get("unitRef", ""), "decimals": attrs.get("decimals", ""), "scale": attrs.get("scale", ""), "sign": attrs.get("sign", ""), "is_nil": attrs.get("xsi:nil", "false"), "value": parser.text(), "source_kind": "inline_xbrl"})
    return facts


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def parse_xml(payload: bytes) -> ET.Element | None:
    try:
        return ET.fromstring(payload.decode("utf-8", "replace"))
    except ET.ParseError:
        return None


def descendants(root: ET.Element, name: str) -> list[ET.Element]:
    return [x for x in root.iter() if local_name(x.tag) == name]


def value_of(root: ET.Element | None, name: str) -> str:
    if root is None:
        return ""
    node = next((x for x in root.iter() if local_name(x.tag) == name), None)
    if node is None:
        return ""
    value = next((x for x in list(node) if local_name(x.tag) == "value"), None)
    return "".join((value or node).itertext()).strip()


def parse_13f(root: ET.Element) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(descendants(root, "infoTable"), 1):
        rows.append({
            "issuer_name": value_of(item, "nameOfIssuer"), "class_title": value_of(item, "titleOfClass"),
            "cusip": value_of(item, "cusip"), "figi": value_of(item, "figi"), "value_usd": value_of(item, "value"),
            "shares_or_principal": value_of(item, "sshPrnamt"), "share_type": value_of(item, "sshPrnamtType"),
            "put_call": value_of(item, "putCall"), "investment_discretion": value_of(item, "investmentDiscretion"),
            "voting_sole": value_of(item, "Sole"), "voting_shared": value_of(item, "Shared"), "voting_none": value_of(item, "None"),
            "row_index": index,
        })
    return rows
