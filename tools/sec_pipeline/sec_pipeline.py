#!/usr/bin/env python3
"""Deterministic SEC filing decomposition and structured table extraction.

The pipeline consumes the repository's SEC warehouse layout directly from ZIP files
or extracted directories. It never calls an LLM and uses only Python's standard
library so the evidence chain is reproducible and auditable.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import csv
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any, Iterator, Mapping, Sequence
import xml.etree.ElementTree as ET
from zipfile import ZipFile

PARSER_VERSION = "1.0.0"
SCHEMA_VERSION = "sec-evidence-chain-v1"
SUPPORTED_BASE_FORMS = {"10-K", "10-Q", "8-K", "4", "144", "13F-HR"}

TABLE_FIELDS: dict[str, list[str]] = {
    "filings": [
        "filing_id", "ticker", "cik", "company_name", "accession", "form", "base_form",
        "is_amendment", "filing_date", "report_date", "acceptance_datetime", "items",
        "primary_document", "source_container", "source_member", "source_sha256",
        "expected_sha256", "evidence_verified", "document_count", "section_count",
        "table_count", "xbrl_fact_count", "structured_row_count", "status",
    ],
    "documents": [
        "document_id", "filing_id", "ticker", "accession", "sequence", "document_type",
        "filename", "description", "content_kind", "mime_type", "is_primary", "is_attachment",
        "wrapper", "source_start_byte", "source_end_byte", "raw_sha256", "payload_sha256",
        "payload_bytes", "materialized_path",
    ],
    "sections": [
        "section_id", "filing_id", "document_id", "ticker", "accession", "form", "part",
        "item", "title", "ordinal", "start_char", "end_char", "text_sha256", "text",
    ],
    "tables": [
        "table_id", "filing_id", "document_id", "ticker", "accession", "form", "table_index",
        "section_hint", "caption", "row_count", "column_count", "rows_json", "text_sha256",
    ],
    "xbrl_facts": [
        "fact_id", "filing_id", "document_id", "ticker", "accession", "form", "concept",
        "context_ref", "unit_ref", "decimals", "scale", "sign", "format", "is_nil", "value",
        "source_kind",
    ],
    "form4_transactions": [
        "transaction_id", "filing_id", "ticker", "accession", "form", "issuer_cik", "issuer_name",
        "issuer_symbol", "owner_cik", "owner_name", "is_director", "is_officer",
        "is_ten_percent_owner", "officer_title", "aff10b5_one", "security_kind", "security_title",
        "transaction_date", "transaction_code", "shares", "price_per_share", "acquired_disposed",
        "shares_owned_after", "direct_or_indirect", "nature_of_ownership", "exercise_date",
        "expiration_date", "underlying_title", "underlying_shares",
    ],
    "form144_notices": [
        "notice_id", "filing_id", "ticker", "accession", "form", "issuer_cik", "issuer_name",
        "seller_name", "relationship_to_issuer", "security_title", "units_to_sell",
        "aggregate_market_value", "units_outstanding", "approx_sale_date", "exchange_name",
        "broker_name", "notice_date", "signature",
    ],
    "form13f_holdings": [
        "holding_id", "filing_id", "ticker", "accession", "form", "report_date", "issuer_name",
        "class_title", "cusip", "figi", "value_usd", "shares_or_principal", "share_type",
        "put_call", "investment_discretion", "other_manager", "voting_sole", "voting_shared",
        "voting_none",
    ],
    "processing_issues": [
        "issue_id", "filing_id", "ticker", "accession", "stage", "severity", "code", "message",
    ],
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(*parts: Any) -> str:
    raw = "\x1f".join("" if p is None else str(p) for p in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def clean_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value).strip()


def base_form(form: str) -> str:
    value = (form or "").strip().upper()
    return value[:-2] if value.endswith("/A") else value


class Source:
    label: str

    def filing_members(self) -> Iterator[str]:
        raise NotImplementedError

    def read(self, member: str) -> bytes:
        raise NotImplementedError

    def exists(self, member: str) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        pass


class ZipSource(Source):
    def __init__(self, path: Path):
        self.path = path
        self.label = str(path)
        self.zf = ZipFile(path)
        self._names = set(self.zf.namelist())

    def filing_members(self) -> Iterator[str]:
        yield from sorted(n for n in self._names if n.endswith("/filing.json"))

    def read(self, member: str) -> bytes:
        return self.zf.read(member)

    def exists(self, member: str) -> bool:
        return member in self._names

    def close(self) -> None:
        self.zf.close()


class DirectorySource(Source):
    def __init__(self, path: Path):
        self.path = path
        self.label = str(path)

    def filing_members(self) -> Iterator[str]:
        for p in sorted(self.path.rglob("filing.json")):
            yield p.relative_to(self.path).as_posix()

    def read(self, member: str) -> bytes:
        return (self.path / PurePosixPath(member)).read_bytes()

    def exists(self, member: str) -> bool:
        return (self.path / PurePosixPath(member)).exists()


def open_sources(paths: Sequence[Path]) -> list[Source]:
    sources: list[Source] = []
    for path in paths:
        if path.is_dir():
            sources.append(DirectorySource(path))
        elif path.is_file() and path.suffix.lower() == ".zip":
            sources.append(ZipSource(path))
        else:
            raise ValueError(f"Unsupported input: {path}")
    return sources


class TableWriter:
    def __init__(self, root: Path):
        self.root = root
        self.tables_dir = root / "tables"
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        self.handles: dict[str, Any] = {}
        self.writers: dict[str, csv.DictWriter] = {}
        self.counts = {name: 0 for name in TABLE_FIELDS}
        for name, fields in TABLE_FIELDS.items():
            fh = (self.tables_dir / f"{name}.csv").open("w", newline="", encoding="utf-8")
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            self.handles[name] = fh
            self.writers[name] = writer

    def write(self, table: str, row: Mapping[str, Any]) -> None:
        fields = TABLE_FIELDS[table]
        normalized = {key: clean_scalar(row.get(key, "")) for key in fields}
        self.writers[table].writerow(normalized)
        self.counts[table] += 1

    def close(self) -> None:
        for fh in self.handles.values():
            fh.close()


class VisibleTextParser(HTMLParser):
    BLOCKS = {
        "address", "article", "aside", "blockquote", "br", "caption", "dd", "div", "dl", "dt",
        "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
        "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in {"script", "style"} or t.endswith(":hidden"):
            self.skip_depth += 1
        if not self.skip_depth and t in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {"script", "style"} or t.endswith(":hidden"):
            self.skip_depth = max(0, self.skip_depth - 1)
        if not self.skip_depth and t in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        value = "".join(self.parts).replace("\xa0", " ")
        value = re.sub(r"[ \t\f\v]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def html_to_text(data: bytes) -> str:
    parser = VisibleTextParser()
    parser.feed(data.decode("utf-8", "replace"))
    parser.close()
    return parser.text()


class TableHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.tables: list[dict[str, Any]] = []
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell_parts: list[str] | None = None
        self.caption_parts: list[str] | None = None
        self.rolling: list[str] = []
        self.section_hint = ""
        self.current_hint = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "table":
            if self.depth == 0:
                self.rows = []
                self.current_hint = self.section_hint
            self.depth += 1
        elif self.depth == 1 and t == "tr":
            self.row = []
        elif self.depth == 1 and t in {"td", "th"}:
            self.cell_parts = []
        elif self.depth == 1 and t == "caption":
            self.caption_parts = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self.depth == 1 and t in {"td", "th"} and self.cell_parts is not None:
            cell = re.sub(r"\s+", " ", "".join(self.cell_parts)).strip()
            if self.row is not None:
                self.row.append(cell)
            self.cell_parts = None
        elif self.depth == 1 and t == "tr" and self.row is not None:
            if any(self.row):
                self.rows.append(self.row)
            self.row = None
        elif self.depth == 1 and t == "caption" and self.caption_parts is not None:
            self.caption_parts = [re.sub(r"\s+", " ", "".join(self.caption_parts)).strip()]
        elif t == "table" and self.depth:
            self.depth -= 1
            if self.depth == 0:
                caption = self.caption_parts[0] if self.caption_parts else ""
                self.tables.append({"rows": self.rows, "caption": caption, "section_hint": self.current_hint})
                self.caption_parts = None

    def handle_data(self, data: str) -> None:
        if self.cell_parts is not None:
            self.cell_parts.append(data)
        if self.caption_parts is not None:
            self.caption_parts.append(data)
        if self.depth == 0:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.rolling.append(text)
                self.rolling = self.rolling[-12:]
                probe = " ".join(self.rolling)
                matches = list(re.finditer(r"(?i)\bitem\s+((?:\d{1,2}[A-Z]?)|(?:\d\.\d{2}))\b", probe))
                if matches:
                    self.section_hint = "Item " + matches[-1].group(1).upper()


def extract_tables(data: bytes) -> list[dict[str, Any]]:
    parser = TableHTMLParser()
    parser.feed(data.decode("utf-8", "replace"))
    parser.close()
    return parser.tables


def tag_value(block: bytes, tag: bytes) -> str:
    m = re.search(rb"<" + tag + rb">([^\r\n<]*)", block, re.I)
    return m.group(1).decode("latin-1", "replace").strip() if m else ""


def unwrap_payload(block: bytes) -> tuple[str, bytes]:
    text_match = re.search(br"<TEXT>\s*(.*?)\s*</TEXT>", block, re.I | re.S)
    payload = text_match.group(1) if text_match else block
    for wrapper in (b"XBRL", b"XML", b"HTML", b"PDF", b"GRAPHIC", b"ZIP"):
        m = re.fullmatch(rb"\s*<" + wrapper + rb">\s*(.*?)\s*</" + wrapper + rb">\s*", payload, re.I | re.S)
        if m:
            return wrapper.decode("ascii"), m.group(1)
    return "TEXT", payload.strip()


def decode_binary_payload(payload: bytes) -> bytes:
    stripped = payload.strip()
    if stripped.startswith(b"begin "):
        out = bytearray()
        lines = stripped.splitlines()[1:]
        for line in lines:
            if line.strip() == b"end":
                break
            if not line:
                continue
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
    dt = document_type.upper()
    head = payload[:512].lstrip().lower()
    if wrapper in {"PDF", "GRAPHIC", "ZIP"} or ext in {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".xlsx", ".xls"}:
        mime = {
            ".pdf": "application/pdf", ".zip": "application/zip", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
        }.get(ext, "application/octet-stream")
        return "binary", mime
    if ext in {".htm", ".html"} or b"<html" in head or wrapper in {"HTML", "XBRL"}:
        return ("inline_xbrl" if b"<ix:" in payload.lower() or wrapper == "XBRL" else "html", "text/html")
    if ext in {".xml", ".xsd"} or wrapper == "XML" or head.startswith(b"<?xml"):
        if dt.startswith("EX-101") or b"<xbrl" in head:
            return "xbrl_xml", "application/xml"
        return "xml", "application/xml"
    if ext == ".json":
        return "json", "application/json"
    if ext == ".css":
        return "css", "text/css"
    if ext == ".js":
        return "javascript", "text/javascript"
    return "text", "text/plain"


def parse_documents(raw: bytes) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    pattern = re.compile(br"<DOCUMENT>(.*?)</DOCUMENT>", re.I | re.S)
    for match in pattern.finditer(raw):
        block = match.group(1)
        wrapper, payload = unwrap_payload(block)
        filename = tag_value(block, b"FILENAME")
        doc_type = tag_value(block, b"TYPE")
        kind, mime = classify_document(filename, doc_type, wrapper, payload)
        decoded = decode_binary_payload(payload) if kind == "binary" else payload
        results.append({
            "sequence": tag_value(block, b"SEQUENCE"),
            "document_type": doc_type,
            "filename": filename,
            "description": tag_value(block, b"DESCRIPTION"),
            "wrapper": wrapper,
            "payload": decoded,
            "content_kind": kind,
            "mime_type": mime,
            "start": match.start(),
            "end": match.end(),
            "block_sha256": sha256_bytes(block),
        })
    return results


def heading_candidates(text: str, form: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    current_part = ""
    lines = text.splitlines(keepends=True)
    offset = 0
    part_re = re.compile(r"^\s*PART\s+([IVX]+)\b", re.I)
    item_re = re.compile(r"^\s*ITEM\s+(\d\.\d{2})\s*[:.\-–—]?\s*(.*)$", re.I) if base_form(form) == "8-K" else re.compile(r"^\s*ITEM\s+((?:\d{1,2}[A-Z]?))\s*[:.\-–—]?\s*(.*)$", re.I)
    for line in lines:
        stripped = re.sub(r"\s+", " ", line).strip()
        pm = part_re.match(stripped)
        if pm and len(stripped) < 80:
            current_part = pm.group(1).upper()
        im = item_re.match(stripped)
        if im and len(stripped) < 240:
            results.append({
                "part": current_part,
                "item": im.group(1).upper(),
                "title": im.group(2).strip(" .:-–—"),
                "start": offset + line.find(line.lstrip()),
                "line": stripped,
            })
        offset += len(line)
    return results


def select_section_headings(text: str, form: str) -> list[dict[str, Any]]:
    candidates = heading_candidates(text, form)
    bf = base_form(form)
    if bf == "8-K":
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for c in candidates:
            if c["item"] not in seen:
                selected.append(c)
                seen.add(c["item"])
        return selected
    if bf == "10-K":
        expected = ["1", "1A", "1B", "1C", "2", "3", "4", "5", "6", "7", "7A", "8", "9", "9A", "9B", "9C", "10", "11", "12", "13", "14", "15", "16"]
        key = lambda c: c["item"]
    elif bf == "10-Q":
        expected = ["I:1", "I:2", "I:3", "I:4", "II:1", "II:1A", "II:2", "II:3", "II:4", "II:5", "II:6"]
        key = lambda c: f"{c['part']}:{c['item']}"
    else:
        return []
    picked: list[dict[str, Any]] = []
    limit = len(text) + 1
    for exp in reversed(expected):
        choices = [c for c in candidates if key(c) == exp and c["start"] < limit]
        if choices:
            chosen = choices[-1]
            picked.append(chosen)
            limit = chosen["start"]
    picked.reverse()
    return picked


def extract_sections(text: str, form: str) -> list[dict[str, Any]]:
    headings = select_section_headings(text, form)
    sections: list[dict[str, Any]] = []
    for i, heading in enumerate(headings):
        start = heading["start"]
        end = headings[i + 1]["start"] if i + 1 < len(headings) else len(text)
        body = text[start:end].strip()
        if len(body) >= 20:
            sections.append({**heading, "end": end, "text": body})
    return sections


ATTR_RE = re.compile(r"([:\w.-]+)\s*=\s*([\"'])(.*?)\2", re.S)
INLINE_FACT_RE = re.compile(r"<ix:(nonNumeric|nonFraction|fraction)\b([^>]*)>(.*?)</ix:\1\s*>", re.I | re.S)
INLINE_NIL_RE = re.compile(r"<ix:(nonNumeric|nonFraction|fraction)\b([^>]*)/\s*>", re.I | re.S)


def parse_attrs(raw: str) -> dict[str, str]:
    return {m.group(1): html.unescape(m.group(3)) for m in ATTR_RE.finditer(raw)}


def strip_markup(raw: str) -> str:
    parser = VisibleTextParser()
    parser.feed(raw)
    parser.close()
    return parser.text()


def extract_inline_xbrl(payload: bytes) -> list[dict[str, Any]]:
    source = payload.decode("utf-8", "replace")
    facts: list[dict[str, Any]] = []
    for m in INLINE_FACT_RE.finditer(source):
        attrs = parse_attrs(m.group(2))
        facts.append({
            "concept": attrs.get("name", ""), "context_ref": attrs.get("contextRef", ""),
            "unit_ref": attrs.get("unitRef", ""), "decimals": attrs.get("decimals", ""),
            "scale": attrs.get("scale", ""), "sign": attrs.get("sign", ""),
            "format": attrs.get("format", ""), "is_nil": attrs.get("xsi:nil", "false"),
            "value": strip_markup(m.group(3)), "source_kind": "inline_xbrl",
        })
    for m in INLINE_NIL_RE.finditer(source):
        attrs = parse_attrs(m.group(2))
        facts.append({
            "concept": attrs.get("name", ""), "context_ref": attrs.get("contextRef", ""),
            "unit_ref": attrs.get("unitRef", ""), "decimals": attrs.get("decimals", ""),
            "scale": attrs.get("scale", ""), "sign": attrs.get("sign", ""),
            "format": attrs.get("format", ""), "is_nil": attrs.get("xsi:nil", "true"),
            "value": "", "source_kind": "inline_xbrl",
        })
    return facts


def extract_instance_xbrl(payload: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(payload.decode("utf-8", "replace"))
    except ET.ParseError:
        return []
    if local_name(root.tag).lower() != "xbrl":
        return []
    facts: list[dict[str, Any]] = []
    for elem in root.iter():
        attrs = {local_name(k): v for k, v in elem.attrib.items()}
        context = attrs.get("contextRef", "")
        if not context:
            continue
        facts.append({
            "concept": local_name(elem.tag), "context_ref": context, "unit_ref": attrs.get("unitRef", ""),
            "decimals": attrs.get("decimals", ""), "scale": attrs.get("scale", ""),
            "sign": attrs.get("sign", ""), "format": attrs.get("format", ""),
            "is_nil": attrs.get("nil", "false"), "value": "".join(elem.itertext()).strip(),
            "source_kind": "xbrl_instance",
        })
    return facts


def xml_root(payload: bytes) -> ET.Element | None:
    try:
        return ET.fromstring(payload.decode("utf-8", "replace"))
    except ET.ParseError:
        return None


def descendants(root: ET.Element, name: str) -> list[ET.Element]:
    return [e for e in root.iter() if local_name(e.tag) == name]


def first_desc(root: ET.Element | None, name: str) -> ET.Element | None:
    return next((e for e in root.iter() if local_name(e.tag) == name), None) if root is not None else None


def value_of(root: ET.Element | None, path: Sequence[str] | str) -> str:
    if root is None:
        return ""
    names = [path] if isinstance(path, str) else list(path)
    cur = root
    for name in names:
        found = next((e for e in list(cur) if local_name(e.tag) == name), None)
        if found is None:
            found = first_desc(cur, name)
        if found is None:
            return ""
        cur = found
    value_node = next((e for e in list(cur) if local_name(e.tag) == "value"), None)
    node = value_node if value_node is not None else cur
    return "".join(node.itertext()).strip()


def parse_form4(root: ET.Element, filing: Mapping[str, Any]) -> list[dict[str, Any]]:
    issuer = first_desc(root, "issuer")
    owner = first_desc(root, "reportingOwner")
    rel = first_desc(owner, "reportingOwnerRelationship")
    common = {
        "issuer_cik": value_of(issuer, "issuerCik"), "issuer_name": value_of(issuer, "issuerName"),
        "issuer_symbol": value_of(issuer, "issuerTradingSymbol"), "owner_cik": value_of(owner, "rptOwnerCik"),
        "owner_name": value_of(owner, "rptOwnerName"), "is_director": value_of(rel, "isDirector"),
        "is_officer": value_of(rel, "isOfficer"), "is_ten_percent_owner": value_of(rel, "isTenPercentOwner"),
        "officer_title": value_of(rel, "officerTitle"), "aff10b5_one": value_of(root, "aff10b5One"),
    }
    rows: list[dict[str, Any]] = []
    for kind, element_name in (("non_derivative", "nonDerivativeTransaction"), ("derivative", "derivativeTransaction")):
        for idx, tx in enumerate(descendants(root, element_name), 1):
            row = {
                **common, "security_kind": kind, "security_title": value_of(tx, "securityTitle"),
                "transaction_date": value_of(tx, "transactionDate"), "transaction_code": value_of(tx, "transactionCode"),
                "shares": value_of(tx, "transactionShares"), "price_per_share": value_of(tx, "transactionPricePerShare"),
                "acquired_disposed": value_of(tx, "transactionAcquiredDisposedCode"),
                "shares_owned_after": value_of(tx, "sharesOwnedFollowingTransaction"),
                "direct_or_indirect": value_of(tx, "directOrIndirectOwnership"),
                "nature_of_ownership": value_of(tx, "natureOfOwnership"), "exercise_date": value_of(tx, "exerciseDate"),
                "expiration_date": value_of(tx, "expirationDate"), "underlying_title": value_of(tx, "underlyingSecurityTitle"),
                "underlying_shares": value_of(tx, "underlyingSecurityShares"),
            }
            row["transaction_id"] = stable_id(filing["filing_id"], kind, idx, row["transaction_date"], row["security_title"], row["shares"])
            rows.append(row)
    return rows


def parse_form144(root: ET.Element, filing: Mapping[str, Any]) -> list[dict[str, Any]]:
    form_data_node = first_desc(root, "formData")
    form_data = form_data_node if form_data_node is not None else root
    issuer = first_desc(form_data, "issuerInfo")
    seller = value_of(issuer, "nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold")
    relationship_root = issuer if issuer is not None else form_data
    relationships = ["".join(e.itertext()).strip() for e in descendants(relationship_root, "relationshipToIssuer")]
    notice = first_desc(form_data, "noticeSignature")
    rows: list[dict[str, Any]] = []
    for idx, sec in enumerate(descendants(form_data, "securitiesInformation"), 1):
        broker = first_desc(sec, "brokerOrMarketmakerDetails")
        row = {
            "issuer_cik": value_of(issuer, "issuerCik"), "issuer_name": value_of(issuer, "issuerName"),
            "seller_name": seller, "relationship_to_issuer": "|".join(x for x in relationships if x),
            "security_title": value_of(sec, "securitiesClassTitle"), "units_to_sell": value_of(sec, "noOfUnitsSold"),
            "aggregate_market_value": value_of(sec, "aggregateMarketValue"),
            "units_outstanding": value_of(sec, "noOfUnitsOutstanding"), "approx_sale_date": value_of(sec, "approxSaleDate"),
            "exchange_name": value_of(sec, "securitiesExchangeName"), "broker_name": value_of(broker, "name"),
            "notice_date": value_of(notice, "noticeDate"), "signature": value_of(notice, "signature"),
        }
        row["notice_id"] = stable_id(filing["filing_id"], idx, row["seller_name"], row["security_title"], row["units_to_sell"])
        rows.append(row)
    return rows


def parse_13f(root: ET.Element, filing: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(descendants(root, "infoTable"), 1):
        row = {
            "report_date": filing.get("report_date", ""), "issuer_name": value_of(item, "nameOfIssuer"),
            "class_title": value_of(item, "titleOfClass"), "cusip": value_of(item, "cusip"),
            "figi": value_of(item, "figi"), "value_usd": value_of(item, "value"),
            "shares_or_principal": value_of(item, "sshPrnamt"), "share_type": value_of(item, "sshPrnamtType"),
            "put_call": value_of(item, "putCall"), "investment_discretion": value_of(item, "investmentDiscretion"),
            "other_manager": value_of(item, "otherManager"), "voting_sole": value_of(item, "Sole"),
            "voting_shared": value_of(item, "Shared"), "voting_none": value_of(item, "None"),
        }
        row["holding_id"] = stable_id(filing["filing_id"], idx, row["cusip"], row["issuer_name"], row["class_title"])
        rows.append(row)
    return rows


def safe_filename(name: str, fallback: str) -> str:
    base = Path(name.replace("\\", "/")).name or fallback
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return base[:180] or fallback


def issue_row(filing: Mapping[str, Any], stage: str, severity: str, code: str, message: str) -> dict[str, Any]:
    return {
        "issue_id": stable_id(filing.get("filing_id"), stage, code, message), "filing_id": filing.get("filing_id", ""),
        "ticker": filing.get("ticker", ""), "accession": filing.get("accession", ""), "stage": stage,
        "severity": severity, "code": code, "message": message,
    }


def process_filing(source: Source, member: str, writer: TableWriter, output_root: Path, document_mode: str) -> None:
    base = member.rsplit("/", 1)[0]
    meta = json.loads(source.read(member).decode("utf-8"))
    form = clean_scalar(meta.get("form"))
    accession = clean_scalar(meta.get("accessionNumber")) or PurePosixPath(base).name.replace("accession=", "")
    ticker = clean_scalar(meta.get("ticker"))
    cik = clean_scalar(meta.get("cik"))
    filing_id = stable_id(ticker, cik, accession, form)
    filing: dict[str, Any] = {
        "filing_id": filing_id, "ticker": ticker, "cik": cik, "company_name": meta.get("companyName", ""),
        "accession": accession, "form": form, "base_form": base_form(form), "is_amendment": form.upper().endswith("/A"),
        "filing_date": meta.get("filingDate", ""), "report_date": meta.get("reportDate", ""),
        "acceptance_datetime": meta.get("acceptanceDateTime", ""), "items": meta.get("items", ""),
        "primary_document": meta.get("primaryDocument", ""), "source_container": source.label,
        "source_member": base + "/complete-submission.txt", "status": "complete",
    }
    raw_member = filing["source_member"]
    if not source.exists(raw_member):
        filing.update({"status": "missing_raw", "document_count": 0, "section_count": 0, "table_count": 0, "xbrl_fact_count": 0, "structured_row_count": 0})
        writer.write("processing_issues", issue_row(filing, "load", "error", "MISSING_COMPLETE_SUBMISSION", raw_member))
        writer.write("filings", filing)
        return
    raw = source.read(raw_member)
    source_sha = sha256_bytes(raw)
    filing["source_sha256"] = source_sha
    expected_sha = clean_scalar(meta.get("documents", {}).get("complete", {}).get("sha256", ""))
    evidence_member = raw_member + ".evidence.json"
    if source.exists(evidence_member):
        try:
            evidence = json.loads(source.read(evidence_member).decode("utf-8"))
            expected_sha = clean_scalar(evidence.get("sha256", expected_sha))
        except Exception as exc:
            writer.write("processing_issues", issue_row(filing, "evidence", "warning", "INVALID_EVIDENCE_JSON", str(exc)))
    filing["expected_sha256"] = expected_sha
    filing["evidence_verified"] = bool(expected_sha and expected_sha.lower() == source_sha.lower())
    if expected_sha and not filing["evidence_verified"]:
        filing["status"] = "evidence_mismatch"
        writer.write("processing_issues", issue_row(filing, "evidence", "error", "SHA256_MISMATCH", f"expected={expected_sha} actual={source_sha}"))

    docs = parse_documents(raw)
    filing["document_count"] = len(docs)
    primary_name = Path(clean_scalar(meta.get("primaryDocument", "")).replace("\\", "/")).name.lower()
    section_count = table_count = fact_count = structured_count = 0
    for doc_index, doc in enumerate(docs, 1):
        filename_base = Path(doc["filename"].replace("\\", "/")).name.lower()
        is_primary = bool(primary_name and filename_base == primary_name) or (not primary_name and doc_index == 1)
        payload: bytes = doc["payload"]
        payload_sha = sha256_bytes(payload)
        doc_id = stable_id(filing_id, doc.get("sequence"), doc.get("document_type"), doc.get("filename"), payload_sha)
        materialized = ""
        should_write = document_mode == "all" or (document_mode == "primary" and is_primary)
        if should_write:
            rel_dir = Path("documents") / f"ticker={ticker}" / f"cik={cik}" / f"accession={accession}"
            out_dir = output_root / rel_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            seq = re.sub(r"\D+", "", doc.get("sequence", "")) or str(doc_index)
            name = safe_filename(doc.get("filename", ""), f"document-{doc_index}.bin")
            out_path = out_dir / f"{int(seq):04d}-{name}"
            out_path.write_bytes(payload)
            materialized = out_path.relative_to(output_root).as_posix()
        writer.write("documents", {
            "document_id": doc_id, "filing_id": filing_id, "ticker": ticker, "accession": accession,
            "sequence": doc.get("sequence", ""), "document_type": doc.get("document_type", ""),
            "filename": doc.get("filename", ""), "description": doc.get("description", ""),
            "content_kind": doc.get("content_kind", ""), "mime_type": doc.get("mime_type", ""),
            "is_primary": is_primary, "is_attachment": not is_primary, "wrapper": doc.get("wrapper", ""),
            "source_start_byte": doc.get("start", ""), "source_end_byte": doc.get("end", ""),
            "raw_sha256": doc.get("block_sha256", ""), "payload_sha256": payload_sha,
            "payload_bytes": len(payload), "materialized_path": materialized,
        })

        kind = doc.get("content_kind")
        if is_primary and kind in {"html", "inline_xbrl"} and base_form(form) in {"10-K", "10-Q", "8-K"}:
            text = html_to_text(payload)
            for ordinal, sec in enumerate(extract_sections(text, form), 1):
                sec_id = stable_id(doc_id, sec.get("part"), sec.get("item"), sec.get("start"), sha256_bytes(sec["text"].encode("utf-8")))
                writer.write("sections", {
                    "section_id": sec_id, "filing_id": filing_id, "document_id": doc_id, "ticker": ticker,
                    "accession": accession, "form": form, "part": sec.get("part", ""), "item": sec.get("item", ""),
                    "title": sec.get("title", ""), "ordinal": ordinal, "start_char": sec.get("start", ""),
                    "end_char": sec.get("end", ""), "text_sha256": sha256_bytes(sec["text"].encode("utf-8")),
                    "text": sec["text"],
                })
                section_count += 1
            for table_index, table in enumerate(extract_tables(payload), 1):
                rows = table["rows"]
                rows_json = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
                writer.write("tables", {
                    "table_id": stable_id(doc_id, table_index, sha256_bytes(rows_json.encode("utf-8"))),
                    "filing_id": filing_id, "document_id": doc_id, "ticker": ticker, "accession": accession,
                    "form": form, "table_index": table_index, "section_hint": table.get("section_hint", ""),
                    "caption": table.get("caption", ""), "row_count": len(rows),
                    "column_count": max((len(r) for r in rows), default=0), "rows_json": rows_json,
                    "text_sha256": sha256_bytes(rows_json.encode("utf-8")),
                })
                table_count += 1

        facts: list[dict[str, Any]] = []
        if kind == "inline_xbrl":
            facts = extract_inline_xbrl(payload)
        elif kind == "xbrl_xml":
            facts = extract_instance_xbrl(payload)
        for fact_index, fact in enumerate(facts, 1):
            writer.write("xbrl_facts", {
                "fact_id": stable_id(doc_id, fact_index, fact.get("concept"), fact.get("context_ref"), fact.get("value")),
                "filing_id": filing_id, "document_id": doc_id, "ticker": ticker, "accession": accession,
                "form": form, **fact,
            })
            fact_count += 1

        root = xml_root(payload) if kind in {"xml", "xbrl_xml"} else None
        dt = doc.get("document_type", "").upper()
        if root is not None and base_form(form) == "4" and base_form(dt) == "4":
            for row in parse_form4(root, filing):
                writer.write("form4_transactions", {"filing_id": filing_id, "ticker": ticker, "accession": accession, "form": form, **row})
                structured_count += 1
        elif root is not None and base_form(form) == "144" and base_form(dt) == "144":
            for row in parse_form144(root, filing):
                writer.write("form144_notices", {"filing_id": filing_id, "ticker": ticker, "accession": accession, "form": form, **row})
                structured_count += 1
        elif root is not None and base_form(form) == "13F-HR" and dt in {"INFORMATION TABLE", "13F-HR"}:
            for row in parse_13f(root, filing):
                writer.write("form13f_holdings", {"filing_id": filing_id, "ticker": ticker, "accession": accession, "form": form, **row})
                structured_count += 1

    filing.update({
        "section_count": section_count, "table_count": table_count, "xbrl_fact_count": fact_count,
        "structured_row_count": structured_count,
    })
    writer.write("filings", filing)


def build_pipeline(args: argparse.Namespace) -> int:
    input_paths = [Path(p).resolve() for p in args.input]
    output = Path(args.output).resolve()
    if output.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output already exists: {output}; pass --overwrite to replace it")
        shutil.rmtree(output)
    temp_parent = output.parent
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=output.name + ".tmp-", dir=temp_parent))
    writer = TableWriter(temp_root)
    sources: list[Source] = []
    processed = 0
    selected_forms = {base_form(f) for f in args.forms.split(",") if f.strip()} if args.forms else SUPPORTED_BASE_FORMS
    source_manifest: list[dict[str, Any]] = []
    try:
        sources = open_sources(input_paths)
        for source in sources:
            source_manifest.append({"path": source.label, "kind": source.__class__.__name__})
            for member in source.filing_members():
                meta = json.loads(source.read(member).decode("utf-8"))
                if base_form(clean_scalar(meta.get("form"))) not in selected_forms:
                    continue
                if args.tickers and clean_scalar(meta.get("ticker")).upper() not in args.tickers:
                    continue
                if args.accessions and clean_scalar(meta.get("accessionNumber")) not in args.accessions:
                    continue
                try:
                    process_filing(source, member, writer, temp_root, args.document_mode)
                except Exception as exc:
                    ticker = clean_scalar(meta.get("ticker"))
                    accession = clean_scalar(meta.get("accessionNumber"))
                    filing_id = stable_id(ticker, meta.get("cik", ""), accession, meta.get("form", ""))
                    fallback = {"filing_id": filing_id, "ticker": ticker, "accession": accession}
                    writer.write("processing_issues", issue_row(fallback, "filing", "error", exc.__class__.__name__, str(exc)))
                    writer.write("filings", {
                        **fallback, "cik": meta.get("cik", ""), "company_name": meta.get("companyName", ""),
                        "form": meta.get("form", ""), "base_form": base_form(meta.get("form", "")),
                        "is_amendment": clean_scalar(meta.get("form")).upper().endswith("/A"),
                        "filing_date": meta.get("filingDate", ""), "report_date": meta.get("reportDate", ""),
                        "acceptance_datetime": meta.get("acceptanceDateTime", ""), "source_container": source.label,
                        "source_member": member.rsplit("/", 1)[0] + "/complete-submission.txt", "status": "failed",
                        "document_count": 0, "section_count": 0, "table_count": 0, "xbrl_fact_count": 0,
                        "structured_row_count": 0,
                    })
                    if args.fail_fast:
                        raise
                processed += 1
                if args.max_filings and processed >= args.max_filings:
                    break
            if args.max_filings and processed >= args.max_filings:
                break
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "inputs": source_manifest,
            "selected_forms": sorted(selected_forms),
            "document_mode": args.document_mode,
            "processed_filings": processed,
            "table_counts": writer.counts,
            "deterministic": True,
            "llm_used": False,
        }
        (temp_root / "schema.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION, "tables": TABLE_FIELDS}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["schema_file"] = "schema.json"
        (temp_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        writer.close()
        for source in sources:
            source.close()
    temp_root.replace(output)
    print(json.dumps({"output": str(output), "processed_filings": processed, "table_counts": writer.counts}, ensure_ascii=False))
    return 0


def parse_csv_set(value: str) -> set[str]:
    return {v.strip().upper() for v in value.split(",") if v.strip()}


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Deterministically split SEC submissions and emit normalized evidence tables.")
    p.add_argument("--input", action="append", required=True, help="ZIP archive or extracted SEC warehouse directory; repeatable")
    p.add_argument("--output", required=True, help="Output directory")
    p.add_argument("--forms", default=",".join(sorted(SUPPORTED_BASE_FORMS)), help="Comma-separated base forms")
    p.add_argument("--tickers", type=parse_csv_set, default=set(), help="Optional ticker filter")
    p.add_argument("--accessions", type=lambda s: {x.strip() for x in s.split(",") if x.strip()}, default=set(), help="Optional accession filter")
    p.add_argument("--document-mode", choices=("none", "primary", "all"), default="all", help="Materialize no documents, primary documents, or all split documents")
    p.add_argument("--max-filings", type=int, default=0, help="Development/smoke-test limit; 0 means unlimited")
    p.add_argument("--overwrite", action="store_true", help="Replace an existing output directory")
    p.add_argument("--fail-fast", action="store_true", help="Stop on first filing error")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    return build_pipeline(make_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
