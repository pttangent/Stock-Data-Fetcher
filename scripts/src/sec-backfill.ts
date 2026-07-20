import { createHash } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { access, appendFile, mkdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { extname, join, resolve } from "node:path";
import { once } from "node:events";

const TICKERS_URL = "https://www.sec.gov/files/company_tickers.json";
const SUBMISSIONS = "https://data.sec.gov/submissions";
const ARCHIVES = "https://www.sec.gov/Archives/edgar/data";
const CORE = new Set(["10-K", "10-Q", "8-K", "20-F", "40-F", "6-K"]);
const MiB = 1024 * 1024;

type DocumentMode = "none" | "complete" | "primary" | "both";
type Order = "oldest" | "newest";
interface Options {
  tickers: string[]; cik?: string; tickerFile?: string; tickerCikFile?: string;
  output: string; forms: Set<string> | null; formMode: "all" | "core" | "list";
  amendments: boolean; documents: DocumentMode; from?: string; to?: string;
  limit?: number; order: Order; gapMs: number; maxBytes: number;
  verify: boolean; refresh: boolean; dryRun: boolean;
}
interface Identity { ticker: string; cik: string; title: string | null; }
interface Filing {
  accessionNumber: string; filingDate: string | null; reportDate: string | null;
  acceptanceDateTime: string | null; form: string; act: string | null;
  fileNumber: string | null; filmNumber: string | null; items: string | null;
  size: number | null; isXbrl: number | null; isInlineXbrl: number | null;
  primaryDocument: string | null; primaryDocumentDescription: string | null;
  sourceShard: string;
}
interface Evidence {
  url: string; status: number; contentType: string | null; etag: string | null;
  lastModified: string | null; fetchedAt: string; bytes: number; sha256: string; path: string;
}
interface FetchMeta { url: string; status: number; contentType: string | null; etag: string | null; lastModified: string | null; fetchedAt: string; }

let nextRequestAt = 0;
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const ticker = (v: string) => v.trim().toUpperCase().replace(/\./g, "-");
const cik = (v: string | number) => {
  const n = String(v).replace(/\D/g, "");
  if (!n || n.length > 10) throw new Error(`Invalid CIK: ${v}`);
  return n.padStart(10, "0");
};
const exists = async (p: string) => { try { await access(p); return true; } catch { return false; } };
const safe = (v: string) => v.replace(/[^A-Za-z0-9._-]/g, "_");
const bytesText = (n: number) => n >= 1024 ** 4 ? `${(n / 1024 ** 4).toFixed(2)} TiB` : n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(2)} GiB` : n >= 1024 ** 2 ? `${(n / 1024 ** 2).toFixed(2)} MiB` : n >= 1024 ? `${(n / 1024).toFixed(2)} KiB` : `${n} B`;

function help(): void {
  console.log(`SEC full-history backfill — strictly sequential by ticker

pnpm --filter @workspace/scripts sec:backfill -- --ticker AAPL

--ticker AAPL,MSFT       ticker(s), processed sequentially
--cik 320193             bypass online mapping for one ticker
--ticker-file PATH       TXT/CSV, first column ticker
--ticker-cik-file PATH   local JSON/CSV mapping
--output PATH            default warehouse/sec
--forms all|core|LIST    default all; core=10-K,10-Q,8-K,20-F,40-F,6-K
--no-amendments          exclude /A
--documents MODE         none|complete|primary|both; default complete
--from/--to YYYY-MM-DD   filing-date bounds
--limit N                smoke-test limit per ticker
--order oldest|newest    default oldest
--request-gap-ms N       default 350, minimum 100
--max-document-mb N      default 512
--verify-existing        re-hash before skip
--refresh-metadata       ignore cached metadata
--dry-run                inventory and disk estimate only

SEC_USER_AGENT="Stock-Data-Fetcher contact@example.com" is required.`);
}
function int(v: string, name: string): number { const n = Number.parseInt(v, 10); if (!Number.isFinite(n) || n <= 0) throw new Error(`${name} must be positive`); return n; }
function date(v: string, name: string): string { if (!/^\d{4}-\d{2}-\d{2}$/.test(v) || Number.isNaN(Date.parse(`${v}T00:00:00Z`))) throw new Error(`${name} must be YYYY-MM-DD`); return v; }
function parse(argv: string[]): Options {
  const o: Options = { tickers: [], output: "warehouse/sec", forms: null, formMode: "all", amendments: true, documents: "complete", order: "oldest", gapMs: Number(process.env.SEC_REQUEST_GAP_MS ?? 350), maxBytes: 512 * MiB, verify: false, refresh: false, dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]; const next = () => { const v = argv[++i]; if (!v) throw new Error(`Missing value after ${a}`); return v; };
    if (a === "--ticker" || a === "--tickers") o.tickers.push(...next().split(",").map(ticker).filter(Boolean));
    else if (a === "--cik") o.cik = cik(next());
    else if (a === "--ticker-file") o.tickerFile = next();
    else if (a === "--ticker-cik-file") o.tickerCikFile = next();
    else if (a === "--output") o.output = next();
    else if (a === "--forms") { const v = next(); if (v.toLowerCase() === "all") { o.forms = null; o.formMode = "all"; } else if (v.toLowerCase() === "core") { o.forms = new Set(CORE); o.formMode = "core"; } else { o.forms = new Set(v.split(",").map(x => x.trim().toUpperCase()).filter(Boolean)); o.formMode = "list"; } }
    else if (a === "--no-amendments") o.amendments = false;
    else if (a === "--documents") { const v = next() as DocumentMode; if (!["none", "complete", "primary", "both"].includes(v)) throw new Error("Invalid --documents"); o.documents = v; }
    else if (a === "--from") o.from = date(next(), a);
    else if (a === "--to") o.to = date(next(), a);
    else if (a === "--limit") o.limit = int(next(), a);
    else if (a === "--order") { const v = next(); if (v !== "oldest" && v !== "newest") throw new Error("Invalid --order"); o.order = v; }
    else if (a === "--request-gap-ms") o.gapMs = int(next(), a);
    else if (a === "--max-document-mb") o.maxBytes = int(next(), a) * MiB;
    else if (a === "--verify-existing") o.verify = true;
    else if (a === "--refresh-metadata") o.refresh = true;
    else if (a === "--dry-run") o.dryRun = true;
    else if (a === "-h" || a === "--help") { help(); process.exit(0); }
    else throw new Error(`Unknown argument: ${a}`);
  }
  o.tickers = [...new Set(o.tickers)];
  if (o.gapMs < 100) throw new Error("Request gap must be at least 100ms");
  if (o.cik && o.tickers.length > 1) throw new Error("--cik supports one ticker only");
  return o;
}
function userAgent(): string { const v = process.env.SEC_USER_AGENT?.trim(); if (!v || !v.includes("@")) throw new Error("SEC_USER_AGENT with contact email is required"); return v; }
async function parent(p: string): Promise<void> { const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\")); await mkdir(i >= 0 ? p.slice(0, i) : ".", { recursive: true }); }
async function jsonWrite(p: string, value: unknown): Promise<void> { await parent(p); const tmp = `${p}.part`; await writeFile(tmp, `${JSON.stringify(value, null, 2)}\n`, "utf8"); await rename(tmp, p); }
async function jsonRead<T>(p: string): Promise<T | null> { try { return JSON.parse(String(await readFile(p, "utf8"))) as T; } catch { return null; } }
async function jsonFresh<T>(p: string, age: number): Promise<T | null> { try { if (Date.now() - (await stat(p)).mtimeMs > age) return null; return await jsonRead<T>(p); } catch { return null; } }
async function jsonl(p: string, value: unknown): Promise<void> { await parent(p); await appendFile(p, `${JSON.stringify(value)}\n`, "utf8"); }

async function secFetch(url: string, o: Options): Promise<Response> {
  let error: Error | null = null;
  for (let attempt = 0; attempt < 6; attempt++) {
    const wait = Math.max(0, nextRequestAt - Date.now()); if (wait) await sleep(wait); nextRequestAt = Date.now() + o.gapMs;
    const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 60_000);
    try {
      const r = await fetch(url, { headers: { "User-Agent": userAgent(), "Accept-Encoding": "gzip, deflate", Accept: "application/json,text/html,text/plain;q=0.9,*/*;q=0.8" }, signal: controller.signal });
      if (r.ok) return r;
      error = new Error(`SEC HTTP ${r.status} for ${url}`);
      if (![403, 408, 429, 500, 502, 503, 504].includes(r.status)) break;
    } catch (e) { error = e instanceof Error ? e : new Error(String(e)); }
    finally { clearTimeout(timeout); }
    const delay = Math.min(30_000, 1_000 * 2 ** attempt) + Math.floor(Math.random() * 500);
    console.warn(`[SEC] retry ${attempt + 1}/6 in ${delay}ms: ${error.message}`); await sleep(delay);
  }
  throw error ?? new Error(`SEC fetch failed: ${url}`);
}
async function fetchJson<T>(url: string, o: Options): Promise<{ data: T; source: FetchMeta }> {
  const r = await secFetch(url, o); const text = await r.text();
  let data: T; try { data = JSON.parse(text) as T; } catch { throw new Error(`Invalid SEC JSON: ${url}`); }
  return { data, source: { url, status: r.status, contentType: r.headers.get("content-type"), etag: r.headers.get("etag"), lastModified: r.headers.get("last-modified"), fetchedAt: new Date().toISOString() } };
}

async function tickerList(p: string): Promise<string[]> {
  return [...new Set(String(await readFile(p, "utf8")).split(/\r?\n/).map(l => l.trim()).filter(l => l && !l.startsWith("#")).map(l => ticker(l.split(/[\t,;]/)[0] ?? "")).filter(t => t && t !== "TICKER" && /^[A-Z0-9-]+$/.test(t)))];
}
async function localMap(p?: string): Promise<Map<string, Identity>> {
  const out = new Map<string, Identity>(); if (!p) return out; const text = String(await readFile(p, "utf8"));
  if (p.toLowerCase().endsWith(".json")) {
    const v = JSON.parse(text) as unknown;
    if (Array.isArray(v)) for (const x of v) { if (!x || typeof x !== "object") continue; const r = x as Record<string, unknown>; const t = ticker(String(r.ticker ?? r.symbol ?? "")); const c = r.cik ?? r.cik_str; if (t && c != null) out.set(t, { ticker: t, cik: cik(String(c)), title: String(r.title ?? r.name ?? "") || null }); }
    else if (v && typeof v === "object") for (const [k, x] of Object.entries(v as Record<string, unknown>)) { const t = ticker(k); if (x && typeof x === "object") { const r = x as Record<string, unknown>; out.set(t, { ticker: t, cik: cik(String(r.cik ?? r.cik_str)), title: String(r.title ?? r.name ?? "") || null }); } else out.set(t, { ticker: t, cik: cik(String(x)), title: null }); }
  } else for (const l of text.split(/\r?\n/)) { const [t0, c0, title] = l.split(/[\t,;]/).map(x => x.trim()); const t = ticker(t0 ?? ""); if (t && t !== "TICKER" && c0) out.set(t, { ticker: t, cik: cik(c0), title: title || null }); }
  return out;
}
function rows(v: unknown): Record<string, { cik_str: number; ticker: string; title: string }> | null { if (!v || typeof v !== "object") return null; const r = v as Record<string, unknown>; return (r.rows && typeof r.rows === "object" ? r.rows : r) as Record<string, { cik_str: number; ticker: string; title: string }>; }
async function officialMap(o: Options, root: string): Promise<Map<string, Identity>> {
  const p = join(root, "_reference", "company_tickers.json"); let raw = o.refresh ? null : rows(await jsonFresh<unknown>(p, 86_400_000));
  if (!raw) try { const f = await fetchJson<Record<string, { cik_str: number; ticker: string; title: string }>>(TICKERS_URL, o); raw = f.data; await jsonWrite(p, { source: f.source, rows: f.data }); }
  catch (e) { raw = rows(await jsonRead<unknown>(p)); if (!raw) throw e; console.warn(`[SEC] using stale ticker map: ${e instanceof Error ? e.message : e}`); }
  const out = new Map<string, Identity>(); for (const r of Object.values(raw)) { const t = ticker(r.ticker); out.set(t, { ticker: t, cik: cik(r.cik_str), title: r.title }); } return out;
}
function unwrap(v: unknown): { data: Record<string, unknown>; source: FetchMeta | null } | null { if (!v || typeof v !== "object") return null; const r = v as Record<string, unknown>; return { data: r.data && typeof r.data === "object" ? r.data as Record<string, unknown> : r, source: r.source && typeof r.source === "object" ? r.source as FetchMeta : null }; }
function at<T>(r: Record<string, unknown>, k: string, i: number): T | null { const v = r[k]; return Array.isArray(v) ? ((v[i] as T | undefined) ?? null) : null; }
function filings(r: Record<string, unknown>, shard: string): Filing[] {
  const a = Array.isArray(r.accessionNumber) ? r.accessionNumber : []; const out: Filing[] = [];
  for (let i = 0; i < a.length; i++) { const acc = at<string>(r, "accessionNumber", i)?.trim(); if (!acc) continue; out.push({ accessionNumber: acc, filingDate: at(r, "filingDate", i), reportDate: at(r, "reportDate", i), acceptanceDateTime: at(r, "acceptanceDateTime", i), form: at<string>(r, "form", i)?.toUpperCase() ?? "UNKNOWN", act: at(r, "act", i), fileNumber: at(r, "fileNumber", i), filmNumber: at(r, "filmNumber", i), items: at(r, "items", i), size: at(r, "size", i), isXbrl: at(r, "isXBRL", i), isInlineXbrl: at(r, "isInlineXBRL", i), primaryDocument: at(r, "primaryDocument", i), primaryDocumentDescription: at(r, "primaryDocDescription", i), sourceShard: shard }); }
  return out;
}
async function metadata(id: Identity, o: Options, root: string): Promise<{ company: Record<string, unknown>; filings: Filing[]; sources: FetchMeta[] }> {
  const dir = join(root, "_reference", "submissions", `CIK${id.cik}`); await mkdir(dir, { recursive: true });
  const rootPath = join(dir, `CIK${id.cik}.json`); let env = o.refresh ? null : unwrap(await jsonFresh<unknown>(rootPath, 300_000));
  if (!env) try { const f = await fetchJson<Record<string, unknown>>(`${SUBMISSIONS}/CIK${id.cik}.json`, o); env = { data: f.data, source: f.source }; await jsonWrite(rootPath, { source: f.source, data: f.data }); }
  catch (e) { env = unwrap(await jsonRead<unknown>(rootPath)); if (!env) throw e; console.warn(`[${id.ticker}] using stale submissions root`); }
  const sources: FetchMeta[] = env.source ? [env.source] : []; const fr = env.data.filings as Record<string, unknown> | undefined; const all = filings((fr?.recent as Record<string, unknown>) ?? {}, `CIK${id.cik}.json:recent`);
  const files = Array.isArray(fr?.files) ? fr.files : [];
  for (let i = 0; i < files.length; i++) { const d = files[i] as Record<string, unknown>; const name = String(d?.name ?? ""); if (!name) continue; const p = join(dir, safe(name)); let e = o.refresh ? null : unwrap(await jsonRead<unknown>(p)); if (!e) { const f = await fetchJson<Record<string, unknown>>(`${SUBMISSIONS}/${name}`, o); e = { data: f.data, source: f.source }; await jsonWrite(p, { descriptor: d, source: f.source, data: f.data }); } if (e.source) sources.push(e.source); all.push(...filings(e.data, name)); console.log(`[${id.ticker}] shard ${i + 1}/${files.length}: ${name}`); }
  const unique = new Map<string, Filing>(); for (const f of all) unique.set(f.accessionNumber, f); return { company: env.data, filings: [...unique.values()], sources };
}
function selected(f: Filing, o: Options): boolean { if (!o.amendments && f.form.endsWith("/A")) return false; const base = f.form.endsWith("/A") ? f.form.slice(0, -2) : f.form; if (o.forms && !o.forms.has(f.form) && !(o.amendments && o.forms.has(base))) return false; if (o.from && f.filingDate && f.filingDate < o.from) return false; if (o.to && f.filingDate && f.filingDate > o.to) return false; return true; }
function urls(id: Identity, f: Filing) { const c = String(Number.parseInt(id.cik, 10)); const a = f.accessionNumber.replace(/-/g, ""); const dir = `${ARCHIVES}/${c}/${a}`; return { complete: `${ARCHIVES}/${c}/${f.accessionNumber}.txt`, fallback: `${dir}/${f.accessionNumber}.txt`, primary: f.primaryDocument ? `${dir}/${f.primaryDocument}` : null, index: `${dir}/${f.accessionNumber}-index.html` }; }
async function fileHash(p: string): Promise<{ bytes: number; sha256: string }> { const h = createHash("sha256"); let bytes = 0; const s = createReadStream(p); s.on("data", (x: Buffer) => { bytes += x.length; h.update(x); }); await once(s, "end"); return { bytes, sha256: h.digest("hex") }; }
async function download(url: string, p: string, o: Options): Promise<{ status: "downloaded" | "skipped"; evidence: Evidence }> {
  const ep = `${p}.evidence.json`; const old = await jsonRead<Evidence>(ep);
  if (await exists(p)) { if (!o.verify && old) return { status: "skipped", evidence: old }; const h = await fileHash(p); if (old && h.bytes === old.bytes && h.sha256 === old.sha256) return { status: "skipped", evidence: old }; }
  await parent(p); const tmp = `${p}.part`; await rm(tmp, { force: true }); const r = await secFetch(url, o); if (!r.body) throw new Error(`No body: ${url}`); const h = createHash("sha256"); let bytes = 0; const w = createWriteStream(tmp); const reader = r.body.getReader();
  try { while (true) { const x = await reader.read(); if (x.done) break; bytes += x.value.byteLength; if (bytes > o.maxBytes) throw new Error(`Document exceeds ${o.maxBytes} bytes: ${url}`); h.update(x.value); if (!w.write(x.value)) await once(w, "drain"); } w.end(); await once(w, "finish"); await rename(tmp, p); }
  catch (e) { w.destroy(); await rm(tmp, { force: true }); throw e; }
  const evidence: Evidence = { url, status: r.status, contentType: r.headers.get("content-type"), etag: r.headers.get("etag"), lastModified: r.headers.get("last-modified"), fetchedAt: new Date().toISOString(), bytes, sha256: h.digest("hex"), path: p }; await jsonWrite(ep, evidence); return { status: "downloaded", evidence };
}
async function complete(u: ReturnType<typeof urls>, p: string, o: Options) { try { return await download(u.complete, p, o); } catch (e) { if (!(e instanceof Error) || !e.message.includes("HTTP 404")) throw e; return download(u.fallback, p, o); } }
function sourceBytes(fs: Filing[]): number { return fs.reduce((n, f) => n + (f.size ?? 512 * 1024), 0); }
function diskBytes(fs: Filing[], mode: DocumentMode): number { const n = sourceBytes(fs); if (mode === "none") return Math.max(10 * MiB, fs.length * 4096); if (mode === "complete") return Math.ceil(n * 1.3 + fs.length * 8192); if (mode === "primary") return Math.ceil(n * .9 + fs.length * 8192); return Math.ceil(n * 1.9 + fs.length * 12288); }

async function runTicker(id: Identity, o: Options, root: string) {
  const startedAt = new Date().toISOString(); const dir = join(root, `ticker=${safe(id.ticker)}`, `cik=${id.cik}`); await mkdir(dir, { recursive: true });
  console.log(`\n=== ${id.ticker} / CIK ${id.cik} ===`); const m = await metadata(id, o, root); let list = m.filings.filter(f => selected(f, o));
  list.sort((a, b) => { const x = `${a.filingDate ?? ""}|${a.acceptanceDateTime ?? ""}|${a.accessionNumber}`; const y = `${b.filingDate ?? ""}|${b.acceptanceDateTime ?? ""}|${b.accessionNumber}`; return o.order === "oldest" ? x.localeCompare(y) : y.localeCompare(x); }); if (o.limit) list = list.slice(0, o.limit);
  const estimate = sourceBytes(list); const recommended = diskBytes(list, o.documents); const companyName = typeof m.company.name === "string" ? m.company.name : id.title;
  await jsonWrite(join(dir, "company.json"), m.company); await jsonWrite(join(dir, "inventory.json"), { schemaVersion: 1, generatedAt: new Date().toISOString(), ticker: id.ticker, cik: id.cik, companyName, options: { formMode: o.formMode, forms: o.forms ? [...o.forms] : null, amendments: o.amendments, documents: o.documents, from: o.from, to: o.to, order: o.order }, discoveredFilings: m.filings.length, selectedFilings: list.length, estimatedSubmissionBytes: estimate, estimatedSubmissionSize: bytesText(estimate), sizeMetadataMissingCount: list.filter(f => f.size == null).length, recommendedFreeBytes: recommended, recommendedFreeSize: bytesText(recommended), sources: m.sources, filings: list });
  console.log(`[${id.ticker}] discovered=${m.filings.length}, selected=${list.length}, recommended=${bytesText(recommended)}`);
  const summary = { ticker: id.ticker, cik: id.cik, companyName, discoveredFilings: m.filings.length, selectedFilings: list.length, estimatedSubmissionBytes: estimate, downloadedFiles: 0, skippedFiles: 0, failedFiles: 0, startedAt, completedAt: null as string | null };
  if (o.dryRun || o.documents === "none") { summary.completedAt = new Date().toISOString(); await jsonWrite(join(dir, "run-summary.json"), summary); return summary; }
  for (let i = 0; i < list.length; i++) { const f = list[i]; const ad = join(dir, `accession=${safe(f.accessionNumber)}`); await mkdir(ad, { recursive: true }); const u = urls(id, f); const manifest: Record<string, unknown> = { ...f, ticker: id.ticker, cik: id.cik, companyName, filingIndexUrl: u.index, completeSubmissionUrl: u.complete, primaryDocumentUrl: u.primary, documents: {}, updatedAt: new Date().toISOString() };
    try { const docs: Record<string, Evidence> = {}; if (o.documents === "complete" || o.documents === "both") { const r = await complete(u, join(ad, "complete-submission.txt"), o); docs.complete = r.evidence; r.status === "downloaded" ? summary.downloadedFiles++ : summary.skippedFiles++; } if ((o.documents === "primary" || o.documents === "both") && u.primary && f.primaryDocument) { const r = await download(u.primary, join(ad, `primary-document${(extname(f.primaryDocument) || ".html").toLowerCase()}`), o); docs.primary = r.evidence; r.status === "downloaded" ? summary.downloadedFiles++ : summary.skippedFiles++; } manifest.documents = docs; manifest.status = "complete"; await jsonWrite(join(ad, "filing.json"), manifest); console.log(`[${id.ticker}] ${i + 1}/${list.length} ${f.form} ${f.accessionNumber} OK`); }
    catch (e) { summary.failedFiles++; const failure = { ticker: id.ticker, cik: id.cik, accessionNumber: f.accessionNumber, form: f.form, filingDate: f.filingDate, error: e instanceof Error ? e.message : String(e), failedAt: new Date().toISOString() }; manifest.status = "failed"; manifest.error = failure.error; await jsonWrite(join(ad, "filing.json"), manifest); await jsonl(join(dir, "errors.jsonl"), failure); console.error(`[${id.ticker}] ${i + 1}/${list.length} FAILED: ${failure.error}`); }
    await jsonWrite(join(dir, "run-summary.json"), { ...summary, currentIndex: i + 1 });
  }
  summary.completedAt = new Date().toISOString(); await jsonWrite(join(dir, "run-summary.json"), summary); return summary;
}

async function main(): Promise<void> {
  const o = parse(process.argv.slice(2)); userAgent(); const root = resolve(o.output); await mkdir(root, { recursive: true }); if (o.tickerFile) o.tickers.push(...await tickerList(o.tickerFile)); o.tickers = [...new Set(o.tickers.map(ticker))]; if (!o.tickers.length && !o.cik) throw new Error("Provide --ticker, --ticker-file, or --cik"); if (o.cik && !o.tickers.length) o.tickers = [`CIK${o.cik}`];
  const local = await localMap(o.tickerCikFile); let official: Map<string, Identity> | null = null; const ids: Identity[] = [];
  for (const t of o.tickers) { if (o.cik && o.tickers.length === 1) ids.push({ ticker: t, cik: o.cik, title: null }); else if (local.has(t)) ids.push(local.get(t)!); else { official ??= await officialMap(o, root); const id = official.get(t); if (!id) throw new Error(`No CIK mapping for ${t}`); ids.push(id); } }
  const runId = new Date().toISOString().replace(/[:.]/g, "-"); const rd = join(root, "_runs", runId); const manifest = { schemaVersion: 1, runId, startedAt: new Date().toISOString(), command: process.argv, options: { ...o, forms: o.forms ? [...o.forms] : null }, identities: ids }; await jsonWrite(join(rd, "run-manifest.json"), manifest); const summaries: Awaited<ReturnType<typeof runTicker>>[] = [];
  for (let i = 0; i < ids.length; i++) { const id = ids[i]; console.log(`\nTicker ${i + 1}/${ids.length}: ${id.ticker}`); try { const s = await runTicker(id, o, root); summaries.push(s); await jsonl(join(rd, "ticker-results.jsonl"), { status: "complete", ...s }); } catch (e) { const f = { status: "failed", ticker: id.ticker, cik: id.cik, error: e instanceof Error ? e.message : String(e), failedAt: new Date().toISOString() }; await jsonl(join(rd, "ticker-results.jsonl"), f); console.error(`[${id.ticker}] ticker failed: ${f.error}`); } }
  const final = { ...manifest, completedAt: new Date().toISOString(), tickerCount: ids.length, completedTickerCount: summaries.length, failedTickerCount: ids.length - summaries.length, estimatedSubmissionBytes: summaries.reduce((n, s) => n + s.estimatedSubmissionBytes, 0), downloadedFiles: summaries.reduce((n, s) => n + s.downloadedFiles, 0), skippedFiles: summaries.reduce((n, s) => n + s.skippedFiles, 0), failedFiles: summaries.reduce((n, s) => n + s.failedFiles, 0), summaries }; await jsonWrite(join(rd, "run-summary.json"), final); console.log(`\nRun complete: ${summaries.length}/${ids.length} tickers`); if (final.failedTickerCount || final.failedFiles) process.exitCode = 2;
}
main().catch(e => { console.error(e instanceof Error ? e.stack ?? e.message : e); process.exitCode = 1; });
