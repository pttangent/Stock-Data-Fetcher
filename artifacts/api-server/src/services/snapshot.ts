import { db, marketSnapshotsTable } from "@workspace/db";
import { eq, desc } from "drizzle-orm";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
import YahooFinanceClass from "yahoo-finance2";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const yf = new (YahooFinanceClass as any)({ suppressNotices: ["yahooSurvey"] });

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function normalizeYahooSymbol(sym: string): string {
  return sym.trim().toUpperCase().replace(/\./g, "-");
}

async function fetchQuotesBatch(symbols: string[]): Promise<Record<string, Record<string, unknown>>> {
  const map: Record<string, Record<string, unknown>> = {};
  const chunkSize = 100;
  for (let i = 0; i < symbols.length; i += chunkSize) {
    const originals = symbols.slice(i, i + chunkSize);
    const normalized = originals.map(normalizeYahooSymbol);
    try {
      const quotesObj = (await yf.quote(normalized, { return: "object" }, { validateResult: false })) as Record<
        string,
        Record<string, unknown>
      >;
      for (let j = 0; j < originals.length; j++) {
        const orig = originals[j].trim().toUpperCase();
        const norm = normalized[j];
        const q = quotesObj[norm];
        if (q) map[orig] = q;
      }
    } catch {
      for (const sym of originals) {
        const norm = normalizeYahooSymbol(sym);
        try {
          const q = (await yf.quote(norm, undefined, { validateResult: false })) as Record<string, unknown>;
          map[sym.trim().toUpperCase()] = q;
        } catch {
          // leave missing
        }
        await sleep(200);
      }
    }
    if (i + chunkSize < symbols.length) {
      await sleep(500);
    }
  }
  return map;
}

async function fetchSymbolSummary(symbol: string, prefetchedQuote?: Record<string, unknown>) {
  const sym = symbol.toUpperCase();
  const yahooSym = normalizeYahooSymbol(sym);

  try {
    let quote: Record<string, unknown>;
    if (prefetchedQuote) {
      quote = prefetchedQuote;
    } else {
      quote = (await yf.quote(yahooSym, undefined, { validateResult: false })) as Record<string, unknown>;
    }

    if (!quote || Object.keys(quote).length === 0) {
      throw new Error("No quote data");
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const q = quote as Record<string, any>;

    const shortName = (q.shortName as string | null) ?? null;
    const exchange = (q.exchange as string | null) ?? null;
    const currency = (q.currency as string | null) ?? null;

    const dayOpen = (q.regularMarketOpen as number | null) ?? null;
    const dayHigh = (q.regularMarketDayHigh as number | null) ?? null;
    const dayLow = (q.regularMarketDayLow as number | null) ?? null;
    const dayClose = (q.regularMarketPrice as number | null) ?? null;
    const dayVolume = (q.regularMarketVolume as number | null) ?? null;

    const prevClose =
      (q.regularMarketPreviousClose as number | null) ??
      (q.previousClose as number | null) ??
      null;

    const intradayReturnPct =
      dayOpen && dayClose
        ? Math.round(((dayClose / dayOpen - 1) * 100) * 100) / 100
        : null;

    const vsPreClosePct =
      prevClose && dayClose
        ? Math.round(((dayClose / prevClose - 1) * 100) * 100) / 100
        : null;

    const period1 = new Date(Date.now() - 3 * 86_400_000);
    period1.setUTCHours(8, 0, 0, 0);
    const period2 = new Date();

    let chartResult: any = null;
    try {
      chartResult = await yf.chart(
        yahooSym,
        { period1, period2, interval: "1m" },
        { validateResult: false },
      );
    } catch {
      // silently continue
    }

    const rawQuotes: Array<Record<string, unknown>> = chartResult?.quotes ?? [];
    type Bar = { date: Date; open: number | null; high: number | null; low: number | null; close: number | null; volume: number | null };
    const allBars: Bar[] = rawQuotes.map((r) => ({
      date: r.date instanceof Date ? (r.date as Date) : new Date(String(r.date)),
      open: (r.open as number | null) ?? null,
      high: (r.high as number | null) ?? null,
      low: (r.low as number | null) ?? null,
      close: (r.close as number | null) ?? null,
      volume: (r.volume as number | null) ?? null,
    }));

    const getETDateString = (date: Date) =>
      new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(date);

    const getETMinutes = (date: Date) => {
      const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "numeric", hour12: false }).formatToParts(date);
      const hour = parseInt(parts.find((p) => p.type === "hour")?.value ?? "0", 10);
      const minute = parseInt(parts.find((p) => p.type === "minute")?.value ?? "0", 10);
      return hour * 60 + minute;
    };

    const MARKET_OPEN_MINS = 9 * 60 + 30;
    const MARKET_CLOSE_MINS = 16 * 60;
    const getBarSession = (date: Date) => {
      const mins = getETMinutes(date);
      if (mins < MARKET_OPEN_MINS) return "premarket";
      if (mins > MARKET_CLOSE_MINS) return "afterhours";
      return "regular";
    };

    const barsByDate = new Map<string, Bar[]>();
    for (const bar of allBars) {
      const etDate = getETDateString(bar.date);
      const arr = barsByDate.get(etDate) ?? [];
      arr.push(bar);
      barsByDate.set(etDate, arr);
    }

    const sortedDates = Array.from(barsByDate.keys()).sort().reverse();
    let vwapDate: string | null = null;
    let vwapBars: Bar[] = [];
    for (const date of sortedDates) {
      const dateBars = barsByDate.get(date) ?? [];
      const hasRegular = dateBars.some((b) => getBarSession(b.date) === "regular");
      if (hasRegular) {
        vwapDate = date;
        vwapBars = dateBars;
        break;
      }
    }

    const regularBars = vwapBars.filter((b) => getBarSession(b.date) === "regular");
    let cumPV = 0, cumVol = 0, lastVwap: number | null = null, aboveCount = 0, validCount = 0;
    for (const b of regularBars) {
      const { high, low, close, volume } = b;
      if (high == null || low == null || close == null || volume == null || volume === 0) continue;
      const typical = (high + low + close) / 3;
      cumPV += typical * volume;
      cumVol += volume;
      if (cumVol > 0) {
        lastVwap = cumPV / cumVol;
        if (close > lastVwap) aboveCount++;
        validCount++;
      }
    }

    let intradayVwapLast = lastVwap != null ? Math.round(lastVwap * 10000) / 10000 : null;
    let pctRegularMinutesAboveVwap = validCount > 0 ? Math.round((aboveCount / validCount) * 10000) / 100 : null;

    if (intradayVwapLast == null && dayHigh != null && dayLow != null && dayClose != null) {
      const typical = (dayHigh + dayLow + dayClose) / 3;
      intradayVwapLast = Math.round(typical * 10000) / 10000;
    }

    const formatET = (date: Date) =>
      new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(date) + " ET";

    const latestBar = allBars.length > 0 ? allBars[allBars.length - 1] : null;
    const latestPrice = latestBar?.close ?? null;
    const latestBarTimeEt = latestBar ? formatET(latestBar.date) : null;
    const latestSession = latestBar ? getBarSession(latestBar.date) : null;

    const latestChgPct =
      latestPrice != null && dayClose
        ? Math.round(((latestPrice / dayClose - 1) * 100) * 100) / 100
        : null;

    return {
      symbol: sym,
      shortName,
      exchange,
      currency,
      prevClose,
      dayOpen,
      dayHigh,
      dayLow,
      dayClose,
      dayVolume,
      intradayReturnPct,
      vsPreClosePct,
      latestPrice,
      latestSession,
      latestChgPct,
      latestBarTimeEt,
      vwapDate,
      regularBarCount: regularBars.length,
      intradayBarCount: allBars.length,
      intradayVwapLast,
      pctRegularMinutesAboveVwap,
      fetchError: null,
    };
  } catch (err) {
    return {
      symbol: sym,
      shortName: null,
      exchange: null,
      currency: null,
      prevClose: null,
      dayOpen: null,
      dayHigh: null,
      dayLow: null,
      dayClose: null,
      dayVolume: null,
      intradayReturnPct: null,
      vsPreClosePct: null,
      latestPrice: null,
      latestSession: null,
      latestChgPct: null,
      latestBarTimeEt: null,
      vwapDate: null,
      regularBarCount: null,
      intradayBarCount: null,
      intradayVwapLast: null,
      pctRegularMinutesAboveVwap: null,
      fetchError: err instanceof Error ? err.message : "Unknown error",
    };
  }
}

async function runBatchSummary(symbols: string[]) {
  const quotesMap = await fetchQuotesBatch(symbols);
  const results = [];
  for (let i = 0; i < symbols.length; i++) {
    const symbol = symbols[i].trim();
    const item = await fetchSymbolSummary(symbol, quotesMap[symbol.toUpperCase()]);
    results.push(item);
    if (i < symbols.length - 1) {
      await sleep(120);
    }
  }
  return results;
}

async function loadTickersFromCsv(filename: string): Promise<string[]> {
  const fs = await import("node:fs/promises");
  const path = await import("node:path");
  const csvPath = path.resolve(process.cwd(), "artifacts", "stock-query", "public", "data", filename);
  const text = await fs.readFile(csvPath, "utf-8");
  const lines = text.split(/\r?\n/);
  let started = false;
  const tickers: string[] = [];
  for (const line of lines) {
    if (!started) {
      if (line.startsWith("Ticker")) started = true;
      continue;
    }
    const ticker = line.split(",")[0].trim().toUpperCase();
    if (ticker && /^[A-Z0-9.]+$/.test(ticker)) {
      tickers.push(ticker);
    }
  }
  return tickers;
}

let isRunning = false;

export async function captureSnapshot(type: "all-stocks" | "all-etfs" | "all-combined") {
  if (isRunning) {
    console.log("[snapshot] Previous capture still running, skipping.");
    return;
  }
  isRunning = true;
  console.log(`[snapshot] Starting capture: ${type}`);

  try {
    let symbols: string[] = [];
    if (type === "all-stocks") {
      symbols = await loadTickersFromCsv("P123_Screen_0_20260606.csv");
    } else if (type === "all-etfs") {
      symbols = await loadTickersFromCsv("P123_ETFCEF.csv");
    } else {
      const stocks = await loadTickersFromCsv("P123_Screen_0_20260606.csv");
      const etfs = await loadTickersFromCsv("P123_ETFCEF.csv");
      symbols = [...stocks, ...etfs];
    }

    const results = await runBatchSummary(symbols);
    const tradeDate = new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());

    await db.insert(marketSnapshotsTable).values({
      type,
      tradeDate,
      symbolCount: symbols.length,
      results: results as any,
    });

    console.log(`[snapshot] Captured ${type}: ${symbols.length} symbols.`);
  } catch (err) {
    console.error("[snapshot] Capture failed:", err);
  } finally {
    isRunning = false;
  }
}

export async function getLatestSnapshot(type: "all-stocks" | "all-etfs" | "all-combined") {
  const rows = await db
    .select()
    .from(marketSnapshotsTable)
    .where(eq(marketSnapshotsTable.type, type))
    .orderBy(desc(marketSnapshotsTable.fetchedAt))
    .limit(1);
  return rows[0] ?? null;
}

export async function getSnapshotById(id: number) {
  const rows = await db
    .select()
    .from(marketSnapshotsTable)
    .where(eq(marketSnapshotsTable.id, id))
    .limit(1);
  return rows[0] ?? null;
}

export async function listSnapshots(type?: "all-stocks" | "all-etfs" | "all-combined", limit = 50) {
  let query = db
    .select({ id: marketSnapshotsTable.id, type: marketSnapshotsTable.type, tradeDate: marketSnapshotsTable.tradeDate, fetchedAt: marketSnapshotsTable.fetchedAt, symbolCount: marketSnapshotsTable.symbolCount })
    .from(marketSnapshotsTable)
    .orderBy(desc(marketSnapshotsTable.fetchedAt))
    .limit(limit);

  if (type) {
    query = query.where(eq(marketSnapshotsTable.type, type));
  }

  return query;
}

export function startSnapshotScheduler() {
  const HALF_HOUR_MS = 30 * 60 * 1000;

  // Run immediately on startup, then every 30 minutes
  setTimeout(() => {
    captureSnapshot("all-stocks");
    captureSnapshot("all-etfs");
  }, 5000);

  setInterval(() => {
    captureSnapshot("all-stocks");
    captureSnapshot("all-etfs");
  }, HALF_HOUR_MS);

  console.log("[snapshot] Scheduler started (every 30 min).");
}
