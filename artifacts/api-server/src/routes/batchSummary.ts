import { Router, type IRouter } from "express";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
import YahooFinanceClass from "yahoo-finance2";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const yf = new (YahooFinanceClass as any)();

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

// ─── Per-symbol fetch ─────────────────────────────────────────────────────────

async function fetchSymbolSummary(symbol: string) {
  const sym = symbol.toUpperCase();

  try {
    // ── 1. Quote: name, price fields, prev close ──────────────────────────
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const quote: Record<string, any> = await yf.quote(sym);

    const shortName = (quote.shortName as string | null) ?? null;
    const exchange = (quote.exchange as string | null) ?? null;
    const currency = (quote.currency as string | null) ?? null;

    // Regular-session OHLCV from quote
    const dayOpen = (quote.regularMarketOpen as number | null) ?? null;
    const dayHigh = (quote.regularMarketDayHigh as number | null) ?? null;
    const dayLow = (quote.regularMarketDayLow as number | null) ?? null;
    const dayClose = (quote.regularMarketPrice as number | null) ?? null;
    const dayVolume = (quote.regularMarketVolume as number | null) ?? null;

    // Previous close — used for real daily return calculation
    const prevClose =
      (quote.regularMarketPreviousClose as number | null) ??
      (quote.previousClose as number | null) ??
      null;

    // Intraday change: close vs open (same day)
    const intradayReturnPct =
      dayOpen && dayClose
        ? Math.round(((dayClose / dayOpen - 1) * 100) * 100) / 100
        : null;

    // vs previous close: the actual overnight + intraday return shown in markets
    const vsPreClosePct =
      prevClose && dayClose
        ? Math.round(((dayClose / prevClose - 1) * 100) * 100) / 100
        : null;

    // ── 2. 1m intraday bars: fetch last 3 days, find most recent trading day ─
    // Yahoo Finance keeps ~2 trading days of 1m data.
    // period1 = 3 calendar days ago at 08:00 UTC (~4am EDT) to cover pre-market.
    // period2 = now — forcing Yahoo to return the available window.
    const period1 = new Date(Date.now() - 3 * 86_400_000);
    period1.setUTCHours(8, 0, 0, 0);
    const period2 = new Date();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let chartResult: any = null;
    try {
      chartResult = await yf.chart(sym, {
        period1,
        period2,
        interval: "1m",
      });
    } catch {
      // silently continue — VWAP fields will be null
    }

    const rawQuotes: Array<Record<string, unknown>> = chartResult?.quotes ?? [];
    const allBars: Bar[] = rawQuotes.map((q) => ({
      date: q.date instanceof Date ? (q.date as Date) : new Date(String(q.date)),
      open: (q.open as number | null) ?? null,
      high: (q.high as number | null) ?? null,
      low: (q.low as number | null) ?? null,
      close: (q.close as number | null) ?? null,
      volume: (q.volume as number | null) ?? null,
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
    const { intradayVwapLast, pctRegularMinutesAboveVwap, regularBarCount } =
      computeVwap(vwapBars);

    // ── 6. Latest bar across ALL fetched bars ────────────────────────────
    const latestBar = allBars.length > 0 ? allBars[allBars.length - 1] : null;
    const latestPrice = latestBar?.close ?? null;
    const latestBarTimeEt = latestBar ? formatET(latestBar.date) : null;
    const latestSession: SessionType | null = latestBar
      ? getBarSession(latestBar.date)
      : null;

    // Latest price vs previous close
    const latestChgPct =
      latestPrice != null && prevClose
        ? Math.round(((latestPrice / prevClose - 1) * 100) * 100) / 100
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
    symbols.length > 100 ||
    symbols.some((s) => typeof s !== "string" || s.trim() === "")
  ) {
    res
      .status(400)
      .json({ error: "symbols must be a non-empty array of up to 100 ticker strings" });
    return;
  }

  const tradeDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());

  req.log.info({ symbols, tradeDate }, "batch-summary request");

  try {
    const results = [];
    for (const symbol of symbols) {
      const item = await fetchSymbolSummary(symbol.trim());
      results.push(item);
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
