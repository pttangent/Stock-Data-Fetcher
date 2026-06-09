import { Router, type IRouter } from "express";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
import YahooFinanceClass from "yahoo-finance2";
import {
  GetStockHistoryQueryParams,
  GetStockInfoQueryParams,
} from "@workspace/api-zod";

// yahoo-finance2 v3 requires explicit instantiation
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const yf = new (YahooFinanceClass as any)();

const DAY_MS = 86_400_000;

// Yahoo Finance per-interval constraints (approximate, conservative)
const INTERVAL_CONFIG: Record<string, { chunkDays: number; maxLookbackDays: number }> = {
  "1m":  { chunkDays: 7,   maxLookbackDays: 30  },
  "5m":  { chunkDays: 60,  maxLookbackDays: 60  },
  "15m": { chunkDays: 60,  maxLookbackDays: 60  },
  "1h":  { chunkDays: 730, maxLookbackDays: 730 },
  "1d":  { chunkDays: 36500, maxLookbackDays: 36500 },
};

type OHLCVBar = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

async function fetchChunked(
  symbol: string,
  interval: string,
  startMs: number,
  endMs: number
): Promise<OHLCVBar[]> {
  const cfg = INTERVAL_CONFIG[interval] ?? { chunkDays: 7, maxLookbackDays: 30 };
  const chunkMs = cfg.chunkDays * DAY_MS;

  const chunks: Array<[number, number]> = [];
  let cursor = startMs;
  while (cursor < endMs) {
    const chunkEnd = Math.min(cursor + chunkMs, endMs);
    chunks.push([cursor, chunkEnd]);
    cursor = chunkEnd;
  }

  const allBars: OHLCVBar[] = [];
  const seenDates = new Set<string>();

  for (const [p1, p2] of chunks) {
    try {
      const result = await yf.chart(symbol, {
        period1: new Date(p1),
        period2: new Date(p2),
        interval,
      });

      const quotes: Array<Record<string, unknown>> = result?.quotes ?? [];
      for (const q of quotes) {
        const date =
          q.date instanceof Date
            ? (q.date as Date).toISOString()
            : String(q.date);
        if (seenDates.has(date)) continue;
        seenDates.add(date);
        allBars.push({
          date,
          open:   (q.open   as number | null) ?? null,
          high:   (q.high   as number | null) ?? null,
          low:    (q.low    as number | null) ?? null,
          close:  (q.close  as number | null) ?? null,
          volume: (q.volume as number | null) ?? null,
        });
      }
    } catch {
      // Skip chunks that return no data (e.g. pre-IPO range)
    }
  }

  allBars.sort((a, b) => a.date.localeCompare(b.date));
  return allBars;
}

const router: IRouter = Router();

router.get("/stocks/history", async (req, res): Promise<void> => {
  const parsed = GetStockHistoryQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const { symbol, period, interval } = parsed.data;
  const cfg = INTERVAL_CONFIG[interval] ?? { chunkDays: 7, maxLookbackDays: 30 };

  const nowMs  = Date.now();
  const endMs  = nowMs;
  const startMs =
    period === "1d"
      ? nowMs - DAY_MS
      : nowMs - cfg.maxLookbackDays * DAY_MS;

  try {
    const data = await fetchChunked(symbol, interval, startMs, endMs);

    res.json({
      symbol: symbol.toUpperCase(),
      period,
      interval,
      rowCount: data.length,
      data,
      fetchedAt: new Date().toISOString(),
    });
  } catch (err) {
    req.log.error({ err, symbol, period, interval }, "Yahoo Finance chart error");
    const message = err instanceof Error ? err.message : "Failed to fetch stock data";
    res.status(500).json({ error: message });
  }
});

router.get("/stocks/info", async (req, res): Promise<void> => {
  const parsed = GetStockInfoQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const { symbol } = parsed.data;

  try {
    const quote: Record<string, unknown> = await yf.quote(symbol);

    res.json({
      symbol: symbol.toUpperCase(),
      shortName: (quote.shortName as string | null) ?? null,
      longName:  (quote.longName  as string | null) ?? null,
      currency:  (quote.currency  as string | null) ?? null,
      exchange:  (quote.exchange  as string | null) ?? null,
      regularMarketPrice:         (quote.regularMarketPrice         as number | null) ?? null,
      regularMarketChangePercent: (quote.regularMarketChangePercent as number | null) ?? null,
      marketCap:        (quote.marketCap        as number | null) ?? null,
      fiftyTwoWeekHigh: (quote.fiftyTwoWeekHigh as number | null) ?? null,
      fiftyTwoWeekLow:  (quote.fiftyTwoWeekLow  as number | null) ?? null,
    });
  } catch (err) {
    req.log.error({ err, symbol }, "Yahoo Finance quote error");
    const message = err instanceof Error ? err.message : "Failed to fetch stock info";
    res.status(500).json({ error: message });
  }
});

export default router;
