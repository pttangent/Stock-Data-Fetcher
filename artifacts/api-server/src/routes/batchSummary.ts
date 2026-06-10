import { Router, type IRouter } from "express";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
import YahooFinanceClass from "yahoo-finance2";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const yf = new (YahooFinanceClass as any)({ suppressNotices: ["yahooSurvey"] });

const router: IRouter = Router();

// ─── Timezone helpers (US/Eastern) ───────────────────────────────────────────

function getETDateString(date: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function getETMinutes(date: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).formatToParts(date);
  const hour = parseInt(parts.find((p) => p.type === "hour")?.value ?? "0", 10);
  const minute = parseInt(parts.find((p) => p.type === "minute")?.value ?? "0", 10);
  return hour * 60 + minute;
}

function formatET(date: Date): string {
  return (
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date) + " ET"
  );
}

const MARKET_OPEN_MINS = 9 * 60 + 30;   // 09:30 ET
const MARKET_CLOSE_MINS = 16 * 60;       // 16:00 ET

// ─── Types ───────────────────────────────────────────────────────────────────

type Bar = {
  date: Date;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

type SessionType = "premarket" | "regular" | "afterhours";

function getBarSession(date: Date): SessionType {
  const mins = getETMinutes(date);
  if (mins < MARKET_OPEN_MINS) return "premarket";
  if (mins > MARKET_CLOSE_MINS) return "afterhours";
  return "regular";
}

// ─── VWAP on a set of bars (regular-session only) ────────────────────────────

function computeVwap(bars: Bar[]): {
  intradayVwapLast: number | null;
  pctRegularMinutesAboveVwap: number | null;
  regularBarCount: number;
} {
  const regularBars = bars.filter((b) => getBarSession(b.date) === "regular");

  let cumPV = 0;
  let cumVol = 0;
  let lastVwap: number | null = null;
  let aboveCount = 0;
  let validCount = 0;

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

  return {
    intradayVwapLast: lastVwap != null ? Math.round(lastVwap * 10000) / 10000 : null,
    pctRegularMinutesAboveVwap:
      validCount > 0 ? Math.round((aboveCount / validCount) * 10000) / 100 : null,
    regularBarCount: regularBars.length,
  };
}

// ─── Rate-limit helpers ──────────────────────────────────────────────────────

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

// Yahoo expects hyphens for symbols that contain dots (e.g. BRK-B instead of BRK.B)
function normalizeYahooSymbol(sym: string): string {
  return sym.trim().toUpperCase().replace(/\./g, "-");
}

async function fetchQuotesBatch(
  symbols: string[],
): Promise<Record<string, Record<string, unknown>>> {
  const map: Record<string, Record<string, unknown>> = {};
  const chunkSize = 100;
  for (let i = 0; i < symbols.length; i += chunkSize) {
    const originals = symbols.slice(i, i + chunkSize);
    const normalized = originals.map(normalizeYahooSymbol);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const quotesObj = (await yf.quote(
        normalized,
        { return: "object" } as any,
        { validateResult: false },
      )) as Record<string, Record<string, unknown>>;
      for (let j = 0; j < originals.length; j++) {
        const orig = originals[j].trim().toUpperCase();
        const norm = normalized[j];
        const q = quotesObj[norm];
        if (q) map[orig] = q;
      }
    } catch {
      // Batch failed — fall back to individual quotes with delay
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

// ─── Per-symbol fetch ─────────────────────────────────────────────────────────

async function fetchSymbolSummary(
  symbol: string,
  prefetchedQuote?: Record<string, unknown>,
) {
  const sym = symbol.toUpperCase();
  const yahooSym = normalizeYahooSymbol(sym);

  try {
    // ── 1. Quote: name, price fields, prev close ──────────────────────────
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

    // ── 2. 1m intraday bars: fetch last 3 days, find most recent trading day ─
    const period1 = new Date(Date.now() - 3 * 86_400_000);
    period1.setUTCHours(8, 0, 0, 0);
    const period2 = new Date();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let chartResult: any = null;
    try {
      chartResult = await yf.chart(
        yahooSym,
        { period1, period2, interval: "1m" },
        { validateResult: false },
      );
    } catch {
      // silently continue — VWAP fields will be null
    }

    const rawQuotes: Array<Record<string, unknown>> = chartResult?.quotes ?? [];
    const allBars: Bar[] = rawQuotes.map((r) => ({
      date: r.date instanceof Date ? (r.date as Date) : new Date(String(r.date)),
      open: (r.open as number | null) ?? null,
      high: (r.high as number | null) ?? null,
      low: (r.low as number | null) ?? null,
      close: (r.close as number | null) ?? null,
      volume: (r.volume as number | null) ?? null,
    }));

    // ── 3. Group bars by ET date ──────────────────────────────────────────
    const barsByDate = new Map<string, Bar[]>();
    for (const bar of allBars) {
      const etDate = getETDateString(bar.date);
      const arr = barsByDate.get(etDate) ?? [];
      arr.push(bar);
      barsByDate.set(etDate, arr);
    }

    // ── 4. Find most recent ET date that has regular-session bars (VWAP day) ─
    const sortedDates = Array.from(barsByDate.keys()).sort().reverse(); // newest first
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

    // ── 5. Compute VWAP from that day's bars ─────────────────────────────
    let { intradayVwapLast, pctRegularMinutesAboveVwap, regularBarCount } =
      computeVwap(vwapBars);

    // Fallback: if no bars had valid volume but quote OHLC is available,
    // approximate VWAP from the day's typical price so the field is never null.
    if (intradayVwapLast == null && dayHigh != null && dayLow != null && dayClose != null) {
      const typical = (dayHigh + dayLow + dayClose) / 3;
      intradayVwapLast = Math.round(typical * 10000) / 10000;
      // pctRegularMinutesAboveVwap stays null — we don't have intraday bars to judge.
    }

    // ── 6. Latest bar across ALL fetched bars ────────────────────────────
    const latestBar = allBars.length > 0 ? allBars[allBars.length - 1] : null;
    const latestPrice = latestBar?.close ?? null;
    const latestBarTimeEt = latestBar ? formatET(latestBar.date) : null;
    const latestSession: SessionType | null = latestBar
      ? getBarSession(latestBar.date)
      : null;

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
      regularBarCount,
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

// ─── Route ───────────────────────────────────────────────────────────────────

router.post("/stocks/batch-summary", async (req, res): Promise<void> => {
  const body = req.body as Record<string, unknown>;
  const symbols = body.symbols;

  if (
    !Array.isArray(symbols) ||
    symbols.length === 0 ||
    symbols.some((s) => typeof s !== "string" || s.trim() === "")
  ) {
    res
      .status(400)
      .json({ error: "symbols must be a non-empty array of ticker strings" });
    return;
  }

  const tradeDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());

  req.log.info({ symbols: symbols.length, tradeDate }, "batch-summary request");

  try {
    // 1. Batch-fetch all quotes first (drastically reduces Yahoo API calls)
    const quotesMap = await fetchQuotesBatch(symbols);

    // 2. Fetch 1m chart data sequentially with delay to avoid rate limits
    const results = [];
    for (let i = 0; i < symbols.length; i++) {
      const symbol = symbols[i].trim();
      const item = await fetchSymbolSummary(symbol, quotesMap[symbol.toUpperCase()]);
      results.push(item);
      if (i < symbols.length - 1) {
        await sleep(120);
      }
    }

    res.json({
      results,
      tradeDate,
      fetchedAt: new Date().toISOString(),
    });
  } catch (err) {
    req.log.error({ err }, "batch-summary error");
    const message =
      err instanceof Error ? err.message : "Failed to fetch batch summary";
    res.status(500).json({ error: message });
  }
});

export default router;
