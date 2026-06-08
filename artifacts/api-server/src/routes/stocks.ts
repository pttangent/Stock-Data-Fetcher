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

const router: IRouter = Router();

router.get("/stocks/history", async (req, res): Promise<void> => {
  const parsed = GetStockHistoryQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const { symbol, period, interval } = parsed.data;

  try {
    const result = await yf.chart(symbol, {
      period1: period === "1d" ? new Date(Date.now() - 86400000) : "1970-01-01",
      interval,
    });

    const quotes: Array<Record<string, unknown>> = result?.quotes ?? [];
    const data = quotes.map((q) => ({
      date: q.date instanceof Date ? (q.date as Date).toISOString() : String(q.date),
      open: (q.open as number | null) ?? null,
      high: (q.high as number | null) ?? null,
      low: (q.low as number | null) ?? null,
      close: (q.close as number | null) ?? null,
      volume: (q.volume as number | null) ?? null,
    }));

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
      longName: (quote.longName as string | null) ?? null,
      currency: (quote.currency as string | null) ?? null,
      exchange: (quote.exchange as string | null) ?? null,
      regularMarketPrice: (quote.regularMarketPrice as number | null) ?? null,
      regularMarketChangePercent: (quote.regularMarketChangePercent as number | null) ?? null,
      marketCap: (quote.marketCap as number | null) ?? null,
      fiftyTwoWeekHigh: (quote.fiftyTwoWeekHigh as number | null) ?? null,
      fiftyTwoWeekLow: (quote.fiftyTwoWeekLow as number | null) ?? null,
    });
  } catch (err) {
    req.log.error({ err, symbol }, "Yahoo Finance quote error");
    const message = err instanceof Error ? err.message : "Failed to fetch stock info";
    res.status(500).json({ error: message });
  }
});

export default router;
