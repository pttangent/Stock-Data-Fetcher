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
  }).format(date); // e.g. "2026-06-09"
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
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date) + " ET";
}

// Regular session: 09:30 – 16:00 ET
const MARKET_OPEN_MINS = 9 * 60 + 30;
const MARKET_CLOSE_MINS = 16 * 60;

// ─── VWAP calculation ────────────────────────────────────────────────────────

type Bar = {
  date: Date;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

function computeSummary(bars: Bar[]) {
  if (bars.length === 0) {
    return {
      intradayBarCount: 0,
      regularBarCount: null,
      latestPrice: null,
      latestBarTimeEt: null,
      isAfterHours: null,
      isPremarket: null,
      intradayVwapLast: null,
      currentVsVwapPct: null,
      pctRegularMinutesAboveVwap: null,
      pctAfterHoursAboveVwap: null,
    };
  }

  const regularBars: Bar[] = [];
  const afterHoursBars: Bar[] = [];

  for (const bar of bars) {
    const mins = getETMinutes(bar.date);
    if (mins >= MARKET_OPEN_MINS && mins <= MARKET_CLOSE_MINS) {
      regularBars.push(bar);
    } else if (mins > MARKET_CLOSE_MINS) {
      afterHoursBars.push(bar);
    }
  }

  // Cumulative VWAP over regular session
  let cumPV = 0;
  let cumVol = 0;
  let lastVwap: number | null = null;
  let aboveVwapCount = 0;
  let validRegularCount = 0;

  for (const bar of regularBars) {
    const { high, low, close, volume } = bar;
    if (high == null || low == null || close == null || volume == null || volume === 0) continue;
    const typical = (high + low + close) / 3;
    cumPV += typical * volume;
    cumVol += volume;
    if (cumVol > 0) {
      lastVwap = cumPV / cumVol;
      if (close > lastVwap) aboveVwapCount++;
      validRegularCount++;
    }
  }

  const pctAboveVwap =
    validRegularCount > 0 ? Math.round((aboveVwapCount / validRegularCount) * 10000) / 100 : null;

  // After-hours bars vs VWAP
  let ahAboveCount = 0;
  let ahValidCount = 0;
  if (lastVwap !== null) {
    for (const bar of afterHoursBars) {
      if (bar.close == null) continue;
      ahValidCount++;
      if (bar.close > lastVwap) ahAboveCount++;
    }
  }
  const pctAfterHoursAboveVwap =
    ahValidCount > 0 ? Math.round((ahAboveCount / ahValidCount) * 10000) / 100 : null;

  // Latest bar
  const latestBar = bars[bars.length - 1];
  const latestMinutes = getETMinutes(latestBar.date);
  const isAfterHours = latestMinutes > MARKET_CLOSE_MINS;
  const isPremarket = latestMinutes < MARKET_OPEN_MINS;
  const latestPrice = latestBar.close ?? null;

  const currentVsVwapPct =
    latestPrice != null && lastVwap != null
      ? Math.round(((latestPrice / lastVwap - 1) * 100) * 100) / 100
      : null;

  return {
    intradayBarCount: bars.length,
    regularBarCount: regularBars.length,
    latestPrice,
    latestBarTimeEt: formatET(latestBar.date),
    isAfterHours,
    isPremarket,
    intradayVwapLast: lastVwap != null ? Math.round(lastVwap * 10000) / 10000 : null,
    currentVsVwapPct,
    pctRegularMinutesAboveVwap: pctAboveVwap,
    pctAfterHoursAboveVwap,
  };
}

// ─── Per-symbol fetch ─────────────────────────────────────────────────────────

async function fetchSymbolSummary(symbol: string, tradeDate: string) {
  const base = { symbol: symbol.toUpperCase() };

  try {
    // 1. Quote (price + after-hours + name)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const quote: Record<string, any> = await yf.quote(symbol);

    const shortName = (quote.shortName as string | null) ?? null;
    const exchange = (quote.exchange as string | null) ?? null;
    const currency = (quote.currency as string | null) ?? null;
    const regularMarketOpen = (quote.regularMarketOpen as number | null) ?? null;
    const regularMarketDayHigh = (quote.regularMarketDayHigh as number | null) ?? null;
    const regularMarketDayLow = (quote.regularMarketDayLow as number | null) ?? null;
    const regularMarketPrice = (quote.regularMarketPrice as number | null) ?? null;
    const regularMarketVolume = (quote.regularMarketVolume as number | null) ?? null;
    const regularMarketChangePercent =
      (quote.regularMarketChangePercent as number | null) ?? null;
    const preMarketPrice = (quote.preMarketPrice as number | null) ?? null;
    const postMarketPrice = (quote.postMarketPrice as number | null) ?? null;

    // day return pct from open
    const dayReturnPct =
      regularMarketOpen && regularMarketPrice
        ? Math.round(((regularMarketPrice / regularMarketOpen - 1) * 100) * 100) / 100
        : regularMarketChangePercent != null
          ? Math.round(regularMarketChangePercent * 100) / 100
          : null;

    // 2. 1m intraday bars for tradeDate (full day ET window)
    // Yahoo Finance only retains ~2 trading days of 1m data.
    // Use period1 = start of tradeDate (08:00 UTC ≈ 4 AM EDT, DST-safe) and period2 = now.
    // Yahoo returns whatever it has from period1 onwards; the ET date filter below trims to the target day.
    const dayStart = new Date(`${tradeDate}T08:00:00Z`);
    const dayEnd = new Date(); // always "now" — forces Yahoo to return available data

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let chartResult: any = null;
    try {
      chartResult = await yf.chart(symbol, {
        period1: dayStart,
        period2: dayEnd,
        interval: "1m",
      });
    } catch {
      // chart may fail if no data; continue with quote data only
    }

    const rawQuotes: Array<Record<string, unknown>> = chartResult?.quotes ?? [];
    const bars: Bar[] = rawQuotes
      .map((q) => ({
        date: q.date instanceof Date ? (q.date as Date) : new Date(String(q.date)),
        open: (q.open as number | null) ?? null,
        high: (q.high as number | null) ?? null,
        low: (q.low as number | null) ?? null,
        close: (q.close as number | null) ?? null,
        volume: (q.volume as number | null) ?? null,
      }))
      .filter((b) => {
        // Only keep bars that fall on the target ET date
        return getETDateString(b.date) === tradeDate;
      });

    const vwap = computeSummary(bars);

    // Best after-hours price: latest bar if after-hours, else postMarketPrice
    let afterHoursPrice: number | null = null;
    if (vwap.isAfterHours && vwap.latestPrice != null) {
      afterHoursPrice = vwap.latestPrice;
    } else if (postMarketPrice != null) {
      afterHoursPrice = postMarketPrice;
    }

    const afterHoursVsDayClosePct =
      afterHoursPrice != null && regularMarketPrice != null
        ? Math.round(((afterHoursPrice / regularMarketPrice - 1) * 100) * 100) / 100
        : null;

    return {
      ...base,
      shortName,
      exchange,
      currency,
      dayOpen: regularMarketOpen,
      dayHigh: regularMarketDayHigh,
      dayLow: regularMarketDayLow,
      dayClose: regularMarketPrice,
      dayVolume: regularMarketVolume,
      dayReturnPct,
      latestPrice: vwap.latestPrice,
      latestBarTimeEt: vwap.latestBarTimeEt,
      isAfterHours: vwap.isAfterHours,
      isPremarket: vwap.isPremarket,
      postMarketPrice,
      preMarketPrice,
      afterHoursPrice,
      afterHoursVsDayClosePct,
      regularBarCount: vwap.regularBarCount,
      intradayBarCount: vwap.intradayBarCount,
      intradayVwapLast: vwap.intradayVwapLast,
      currentVsVwapPct: vwap.currentVsVwapPct,
      pctRegularMinutesAboveVwap: vwap.pctRegularMinutesAboveVwap,
      pctAfterHoursAboveVwap: vwap.pctAfterHoursAboveVwap,
      fetchError: null,
    };
  } catch (err) {
    return {
      ...base,
      shortName: null,
      exchange: null,
      currency: null,
      dayOpen: null,
      dayHigh: null,
      dayLow: null,
      dayClose: null,
      dayVolume: null,
      dayReturnPct: null,
      latestPrice: null,
      latestBarTimeEt: null,
      isAfterHours: null,
      isPremarket: null,
      postMarketPrice: null,
      preMarketPrice: null,
      afterHoursPrice: null,
      afterHoursVsDayClosePct: null,
      regularBarCount: null,
      intradayBarCount: null,
      intradayVwapLast: null,
      currentVsVwapPct: null,
      pctRegularMinutesAboveVwap: null,
      pctAfterHoursAboveVwap: null,
      fetchError: err instanceof Error ? err.message : "Unknown error",
    };
  }
}

// ─── Route ───────────────────────────────────────────────────────────────────

router.post("/stocks/batch-summary", async (req, res): Promise<void> => {
  const body = req.body as Record<string, unknown>;
  const symbols = body.symbols;
  const date = body.date as string | null | undefined;

  if (
    !Array.isArray(symbols) ||
    symbols.length === 0 ||
    symbols.length > 100 ||
    symbols.some((s) => typeof s !== "string" || s.trim() === "")
  ) {
    res.status(400).json({ error: "symbols must be a non-empty array of up to 100 ticker strings" });
    return;
  }

  // Determine trade date in ET
  const tradeDate = date ?? getETDateString(new Date());

  req.log.info({ symbols, tradeDate }, "batch-summary request");

  try {
    // Fetch symbols sequentially to avoid rate-limiting
    const results = [];
    for (const symbol of symbols) {
      const item = await fetchSymbolSummary(symbol.trim().toUpperCase(), tradeDate);
      results.push(item);
    }

    res.json({
      results,
      tradeDate,
      fetchedAt: new Date().toISOString(),
    });
  } catch (err) {
    req.log.error({ err }, "batch-summary error");
    const message = err instanceof Error ? err.message : "Failed to fetch batch summary";
    res.status(500).json({ error: message });
  }
});

export default router;
