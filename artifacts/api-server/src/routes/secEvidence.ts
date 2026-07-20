import { Router, type IRouter } from "express";
import { createHash } from "node:crypto";

const router: IRouter = Router();

const SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json";
const SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions";
const SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data";
const DEFAULT_FORMS = ["10-K", "10-Q", "8-K"];
const MAX_RESULTS = 50;
const MAX_DOCUMENTS = 3;
const MAX_DOCUMENT_BYTES = 8 * 1024 * 1024;
const MAX_RESPONSE_BYTES = 12 * 1024 * 1024;
const SEC_REQUEST_GAP_MS = 150;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

let nextSecRequestAt = 0;
let secQueue: Promise<void> = Promise.resolve();

interface CacheEntry<T> {
  expiresAt: number;
  value: T;
}

const cache = new Map<string, CacheEntry<unknown>>();

interface SecTickerRow {
  cik_str: number;
  ticker: string;
  title: string;
}

interface SecCompanyIdentity {
  cik: string;
  ticker: string | null;
  title: string;
}

interface SecFetchResult {
  url: string;
  status: number;
  contentType: string | null;
  etag: string | null;
  lastModified: string | null;
  fetchedAt: string;
  body: string;
}

function getUserAgent(): string | null {
  const value = process.env.SEC_USER_AGENT?.trim();
  return value && value.includes("@") ? value : null;
}

async function waitForSecSlot(): Promise<void> {
  const task = secQueue.then(async () => {
    const delay = Math.max(0, nextSecRequestAt - Date.now());
    if (delay > 0) await sleep(delay);
    nextSecRequestAt = Date.now() + SEC_REQUEST_GAP_MS;
  });
  secQueue = task.catch(() => undefined);
  await task;
}

function getCached<T>(key: string): T | null {
  const hit = cache.get(key);
  if (!hit || hit.expiresAt <= Date.now()) {
    cache.delete(key);
    return null;
  }
  return hit.value as T;
}

function setCached<T>(key: string, value: T, ttlMs: number): T {
  cache.set(key, { value, expiresAt: Date.now() + ttlMs });
  return value;
}

async function readBodyWithLimit(response: Response, maxBytes: number): Promise<string> {
  const declaredBytes = Number.parseInt(response.headers.get("content-length") ?? "0", 10);
  if (Number.isFinite(declaredBytes) && declaredBytes > maxBytes) {
    throw new Error(`SEC response exceeds ${maxBytes} bytes`);
  }

  if (!response.body) return "";
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    totalBytes += value.byteLength;
    if (totalBytes > maxBytes) {
      await reader.cancel();
      throw new Error(`SEC response exceeds ${maxBytes} bytes`);
    }
    chunks.push(value);
  }

  const combined = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder("utf-8").decode(combined);
}

async function fetchSecText(
  url: string,
  ttlMs: number,
  maxBytes = MAX_RESPONSE_BYTES,
): Promise<SecFetchResult> {
  const cached = getCached<SecFetchResult>(url);
  if (cached) return cached;

  const userAgent = getUserAgent();
  if (!userAgent) {
    throw new Error(
      'SEC_USER_AGENT is required and must contain a contact email, e.g. "Stock-Data-Fetcher admin@example.com"',
    );
  }

  let lastError: Error | null = null;
  for (let attempt = 0; attempt < 4; attempt++) {
    await waitForSecSlot();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20_000);

    try {
      const response = await fetch(url, {
        headers: {
          "User-Agent": userAgent,
          Accept: "application/json,text/html,text/plain;q=0.9,*/*;q=0.8",
        },
        signal: controller.signal,
      });
      const body = response.ok ? await readBodyWithLimit(response, maxBytes) : "";

      if (response.ok) {
        return setCached(
          url,
          {
            url,
            status: response.status,
            contentType: response.headers.get("content-type"),
            etag: response.headers.get("etag"),
            lastModified: response.headers.get("last-modified"),
            fetchedAt: new Date().toISOString(),
            body,
          },
          ttlMs,
        );
      }

      const retryable = response.status === 429 || response.status === 403 || response.status >= 500;
      lastError = new Error(`SEC request failed (${response.status}) for ${url}`);
      if (!retryable) break;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Unknown SEC request error");
    } finally {
      clearTimeout(timeout);
    }

    await sleep(500 * 2 ** attempt + Math.floor(Math.random() * 250));
  }

  throw lastError ?? new Error(`SEC request failed for ${url}`);
}

async function fetchSecJson<T>(url: string, ttlMs: number): Promise<{ data: T; evidence: SecFetchResult }> {
  const evidence = await fetchSecText(url, ttlMs);
  try {
    return { data: JSON.parse(evidence.body) as T, evidence };
  } catch {
    throw new Error(`SEC returned invalid JSON for ${url}`);
  }
}

function normalizeTicker(value: string): string {
  return value.trim().toUpperCase().replace(/\./g, "-");
}

async function resolveCompany(symbolOrCik: string): Promise<SecCompanyIdentity> {
  const raw = symbolOrCik.trim();
  if (/^\d{1,10}$/.test(raw)) {
    return {
      cik: raw.padStart(10, "0"),
      ticker: null,
      title: `CIK ${raw.padStart(10, "0")}`,
    };
  }

  const { data } = await fetchSecJson<Record<string, SecTickerRow>>(SEC_TICKER_URL, 6 * 60 * 60 * 1000);
  const requested = normalizeTicker(raw);
  const match = Object.values(data).find((row) => normalizeTicker(row.ticker) === requested);
  if (!match) throw new Error(`No SEC ticker mapping found for ${raw.toUpperCase()}`);

  return {
    cik: String(match.cik_str).padStart(10, "0"),
    ticker: match.ticker.toUpperCase(),
    title: match.title,
  };
}

function queryString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function queryBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value !== "string") return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function queryInteger(value: unknown, fallback: number, min: number, max: number): number {
  if (typeof value !== "string") return fallback;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function parseForms(value: unknown): string[] {
  const raw = queryString(value);
  if (!raw) return DEFAULT_FORMS;
  const forms = raw
    .split(",")
    .map((form) => form.trim().toUpperCase())
    .filter(Boolean);
  return forms.length > 0 ? [...new Set(forms)] : DEFAULT_FORMS;
}

function fieldAt<T>(record: Record<string, unknown>, key: string, index: number): T | null {
  const values = record[key];
  return Array.isArray(values) ? ((values[index] as T | undefined) ?? null) : null;
}

function formMatches(form: string, requested: string[], includeAmendments: boolean): boolean {
  if (requested.includes(form)) return true;
  return includeAmendments && form.endsWith("/A") && requested.includes(form.slice(0, -2));
}

function stripHtml(html: string): string {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/gi, '"')
    .replace(/\s+/g, " ")
    .trim();
}

router.get("/sec/filings", async (req, res): Promise<void> => {
  const symbol = queryString(req.query.symbol) ?? queryString(req.query.cik);
  if (!symbol) {
    res.status(400).json({ error: "symbol or cik is required" });
    return;
  }

  if (!getUserAgent()) {
    res.status(503).json({
      error: "SEC_USER_AGENT is not configured",
      requiredFormat: "Stock-Data-Fetcher contact@example.com",
    });
    return;
  }

  const forms = parseForms(req.query.forms);
  const limit = queryInteger(req.query.limit, 20, 1, MAX_RESULTS);
  const includeAmendments = queryBoolean(req.query.includeAmendments, true);
  const includeDocument = queryBoolean(req.query.includeDocument, false);
  const documentLimit = includeDocument
    ? queryInteger(req.query.documentLimit, 1, 1, MAX_DOCUMENTS)
    : 0;

  try {
    const identity = await resolveCompany(symbol);
    const submissionsUrl = `${SEC_SUBMISSIONS_BASE}/CIK${identity.cik}.json`;
    const { data: submissions, evidence: submissionsEvidence } = await fetchSecJson<Record<string, unknown>>(
      submissionsUrl,
      5 * 60 * 1000,
    );

    const filingsRoot = submissions.filings as Record<string, unknown> | undefined;
    const recent = (filingsRoot?.recent as Record<string, unknown> | undefined) ?? {};
    const accessionNumbers = Array.isArray(recent.accessionNumber) ? recent.accessionNumber : [];
    const cikPath = String(Number.parseInt(identity.cik, 10));
    const filings = [];

    for (let index = 0; index < accessionNumbers.length && filings.length < limit; index++) {
      const form = fieldAt<string>(recent, "form", index) ?? "";
      if (!formMatches(form, forms, includeAmendments)) continue;

      const accessionNumber = fieldAt<string>(recent, "accessionNumber", index) ?? "";
      const accessionPath = accessionNumber.replace(/-/g, "");
      const primaryDocument = fieldAt<string>(recent, "primaryDocument", index) ?? "";
      const filingDirectory = `${SEC_ARCHIVES_BASE}/${cikPath}/${accessionPath}`;
      const primaryDocumentUrl = primaryDocument ? `${filingDirectory}/${primaryDocument}` : null;
      const filingIndexUrl = accessionNumber
        ? `${filingDirectory}/${accessionNumber}-index.html`
        : null;

      filings.push({
        form,
        accessionNumber,
        filingDate: fieldAt<string>(recent, "filingDate", index),
        reportDate: fieldAt<string>(recent, "reportDate", index),
        acceptanceDateTime: fieldAt<string>(recent, "acceptanceDateTime", index),
        act: fieldAt<string>(recent, "act", index),
        fileNumber: fieldAt<string>(recent, "fileNumber", index),
        filmNumber: fieldAt<string>(recent, "filmNumber", index),
        items: fieldAt<string>(recent, "items", index),
        size: fieldAt<number>(recent, "size", index),
        isXbrl: fieldAt<number>(recent, "isXBRL", index),
        isInlineXbrl: fieldAt<number>(recent, "isInlineXBRL", index),
        primaryDocument,
        primaryDocumentDescription: fieldAt<string>(recent, "primaryDocDescription", index),
        filingIndexUrl,
        primaryDocumentUrl,
        documentEvidence: null as null | Record<string, unknown>,
      });
    }

    for (let index = 0; index < Math.min(documentLimit, filings.length); index++) {
      const filing = filings[index];
      if (!filing.primaryDocumentUrl) continue;
      try {
        const document = await fetchSecText(
          filing.primaryDocumentUrl,
          60 * 60 * 1000,
          MAX_DOCUMENT_BYTES,
        );
        const bytes = Buffer.byteLength(document.body, "utf8");

        filing.documentEvidence = {
          fetchedAt: document.fetchedAt,
          contentType: document.contentType,
          etag: document.etag,
          lastModified: document.lastModified,
          bytes,
          sha256: createHash("sha256").update(document.body, "utf8").digest("hex"),
          excerpt: stripHtml(document.body).slice(0, 1600),
        };
      } catch (error) {
        filing.documentEvidence = {
          error: error instanceof Error ? error.message : "Failed to fetch filing document",
        };
      }
    }

    const responseFetchedAt = new Date().toISOString();
    res.json({
      query: {
        symbol: identity.ticker ?? symbol.toUpperCase(),
        cik: identity.cik,
        forms,
        includeAmendments,
        includeDocument,
      },
      company: {
        cik: identity.cik,
        ticker: identity.ticker,
        name: (submissions.name as string | undefined) ?? identity.title,
        sic: (submissions.sic as string | undefined) ?? null,
        sicDescription: (submissions.sicDescription as string | undefined) ?? null,
        exchanges: Array.isArray(submissions.exchanges) ? submissions.exchanges : [],
        tickers: Array.isArray(submissions.tickers) ? submissions.tickers : [],
        fiscalYearEnd: (submissions.fiscalYearEnd as string | undefined) ?? null,
        entityType: (submissions.entityType as string | undefined) ?? null,
      },
      filings,
      evidenceChain: {
        authority: "U.S. Securities and Exchange Commission",
        tickerMapUrl: SEC_TICKER_URL,
        submissionsUrl,
        submissionsFetchedAt: submissionsEvidence.fetchedAt,
        submissionsEtag: submissionsEvidence.etag,
        submissionsLastModified: submissionsEvidence.lastModified,
        responseFetchedAt,
        availabilityField: "acceptanceDateTime",
        hashAlgorithm: includeDocument ? "SHA-256" : null,
        pointInTimeRule:
          "Use acceptanceDateTime as the earliest SEC availability timestamp; fetchedAt records local observation time.",
      },
    });
  } catch (error) {
    req.log.error({ err: error, symbol, forms }, "SEC filings query failed");
    const message = error instanceof Error ? error.message : "Failed to fetch SEC filings";
    const status = message.startsWith("No SEC ticker mapping") ? 404 : 502;
    res.status(status).json({ error: message });
  }
});

export default router;
