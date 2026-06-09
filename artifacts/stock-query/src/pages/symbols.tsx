import React, { useState, useMemo, useCallback } from "react";
import { useBatchStockSummary, SymbolSummaryItem } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Loader2, Copy, CheckCircle2, XCircle, ArrowDown, ArrowUp, ArrowUpDown,
} from "lucide-react";

// ─── Category dict parser ─────────────────────────────────────────────────────
// Accepts Python-style or JSON dict:
//   "Category": ["SYM1", "SYM2"]
// Returns null if no valid categories found.
function parseCategorySymbols(text: string): Record<string, string[]> | null {
  const result: Record<string, string[]> = {};
  // Match "Category Name": [ ... ] blocks
  const blockRe = /["']([^"']+)["']\s*:\s*\[([^\]]*)\]/g;
  let m: RegExpExecArray | null;
  while ((m = blockRe.exec(text)) !== null) {
    const cat = m[1].trim();
    const inner = m[2];
    // Extract quoted or bare uppercase symbols from the value list
    const syms: string[] = [];
    const symRe = /["']([A-Za-z0-9.^-]{1,10})["']|([A-Z]{1,10})/g;
    let sm: RegExpExecArray | null;
    while ((sm = symRe.exec(inner)) !== null) {
      const s = (sm[1] ?? sm[2]).trim().toUpperCase();
      if (s) syms.push(s);
    }
    if (cat && syms.length > 0) result[cat] = syms;
  }
  return Object.keys(result).length > 0 ? result : null;
}

// ─── Sorting ──────────────────────────────────────────────────────────────────
type SortKey = keyof SymbolSummaryItem;
type SortConfig = { key: SortKey | null; direction: "asc" | "desc" };

function applySortFn(items: SymbolSummaryItem[], cfg: SortConfig): SymbolSummaryItem[] {
  if (!cfg.key) return items;
  return [...items].sort((a, b) => {
    const av = a[cfg.key!];
    const bv = b[cfg.key!];
    if (av == null) return 1;
    if (bv == null) return -1;
    if (av < bv) return cfg.direction === "asc" ? -1 : 1;
    if (av > bv) return cfg.direction === "asc" ? 1 : -1;
    return 0;
  });
}

// ─── Formatters ───────────────────────────────────────────────────────────────
const fmt = (v: number | null | undefined, dp = 2) => (v == null ? "—" : v.toFixed(dp));

const fmtVol = (v: number | null | undefined) => {
  if (v == null) return "—";
  if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return v.toString();
};

const fmtPct = (v: number | null | undefined) => {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
};

const pctColor = (v: number | null | undefined) => {
  if (v == null) return "text-muted-foreground";
  if (v > 0) return "text-success font-bold";
  if (v < 0) return "text-destructive font-bold";
  return "";
};

const vwapPctColor = (v: number | null | undefined) => {
  if (v == null) return "text-muted-foreground";
  if (v >= 60) return "text-success font-bold";
  if (v >= 40) return "text-yellow-500 font-bold";
  return "text-destructive font-bold";
};

const sessionBadge = (s: string | null | undefined) => {
  if (s === "afterhours")
    return <Badge variant="outline" className="text-amber-500 border-amber-500/30 bg-amber-500/10 px-1 py-0 h-5 text-[10px]">AH</Badge>;
  if (s === "premarket")
    return <Badge variant="outline" className="text-blue-500 border-blue-500/30 bg-blue-500/10 px-1 py-0 h-5 text-[10px]">PM</Badge>;
  if (s === "regular")
    return <Badge variant="outline" className="text-success border-success/30 bg-success/10 px-1 py-0 h-5 text-[10px]">REG</Badge>;
  return <span className="text-muted-foreground">—</span>;
};

// ─── Category table ───────────────────────────────────────────────────────────
function CategoryTable({
  category,
  rows,
  onSymbolClick,
}: {
  category: string;
  rows: SymbolSummaryItem[];
  onSymbolClick: (sym: string) => void;
}) {
  const [sort, setSort] = useState<SortConfig>({ key: "vsPreClosePct", direction: "desc" });

  const sorted = useMemo(() => applySortFn(rows, sort), [rows, sort]);

  const handleSort = (key: SortKey) => {
    setSort((prev) => ({
      key,
      direction: prev.key === key && prev.direction === "desc" ? "asc" : "desc",
    }));
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sort.key !== col)
      return <ArrowUpDown className="w-3 h-3 ml-1 inline opacity-30" />;
    return sort.direction === "asc"
      ? <ArrowUp className="w-3 h-3 ml-1 inline" />
      : <ArrowDown className="w-3 h-3 ml-1 inline" />;
  };

  const Th = ({
    col, children, right,
  }: { col: SortKey; children: React.ReactNode; right?: boolean }) => (
    <TableHead
      className={`py-2 px-2 cursor-pointer hover:text-foreground select-none whitespace-nowrap ${right ? "text-right" : "text-left"}`}
      onClick={() => handleSort(col)}
    >
      {children}<SortIcon col={col} />
    </TableHead>
  );

  // Category summary: count above 60% vwap
  const withVwap = rows.filter((r) => r.pctRegularMinutesAboveVwap != null);
  const above60 = withVwap.filter((r) => (r.pctRegularMinutesAboveVwap ?? 0) >= 60).length;

  return (
    <div className="border border-border bg-card overflow-hidden">
      {/* Category header */}
      <div className="bg-muted/20 px-4 py-2 border-b border-border flex items-center justify-between gap-4 flex-wrap">
        <span className="font-bold text-xs uppercase tracking-widest text-foreground">
          {category}
        </span>
        <div className="flex items-center gap-4 text-[10px] text-muted-foreground">
          <span>{rows.length} symbols</span>
          {withVwap.length > 0 && (
            <span className={above60 / withVwap.length >= 0.6 ? "text-success font-bold" : above60 / withVwap.length >= 0.4 ? "text-yellow-500" : "text-destructive"}>
              &gt;VWAP 60%: {above60}/{withVwap.length}
            </span>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <Table className="font-mono text-xs whitespace-nowrap">
          <TableHeader className="bg-muted/10">
            <TableRow className="border-border hover:bg-transparent">
              <TableHead
                className="py-2 px-2 cursor-pointer hover:text-foreground select-none whitespace-nowrap sticky left-0 z-20 bg-card border-r border-border shadow-[2px_0_4px_rgba(0,0,0,0.4)]"
                onClick={() => handleSort("symbol")}
              >
                Symbol<SortIcon col="symbol" />
              </TableHead>
              <Th col="shortName">Name</Th>
              <Th col="prevClose" right>Prev</Th>
              <Th col="dayOpen" right>Open</Th>
              <Th col="dayHigh" right>High</Th>
              <Th col="dayLow" right>Low</Th>
              <Th col="dayClose" right>Close</Th>
              <Th col="vsPreClosePct" right>vs Prev%</Th>
              <Th col="intradayReturnPct" right>Intraday%</Th>
              <Th col="dayVolume" right>Vol</Th>
              <Th col="intradayVwapLast" right>VWAP</Th>
              <Th col="pctRegularMinutesAboveVwap" right>&gt;VWAP%</Th>
              <Th col="latestPrice" right>Latest</Th>
              <Th col="latestChgPct" right>Latest Chg%</Th>
              <TableHead className="py-2 px-2 text-center">Session</TableHead>
              <Th col="latestBarTimeEt" right>Last Bar ET</Th>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((row, i) => (
              <TableRow key={row.symbol || i} className="border-border hover:bg-muted/10 group">
                <TableCell className="px-2 font-bold sticky left-0 z-10 bg-card group-hover:bg-muted/10 border-r border-border shadow-[2px_0_4px_rgba(0,0,0,0.4)] transition-colors">
                  {row.fetchError ? (
                    <span className="text-destructive" title={row.fetchError}>{row.symbol} ⚠</span>
                  ) : (
                    <button
                      onClick={() => onSymbolClick(row.symbol)}
                      className="font-bold hover:text-primary hover:underline cursor-pointer underline-offset-2 transition-colors"
                      title={`個股查詢: ${row.symbol} 1min intraday`}
                    >
                      {row.symbol}
                    </button>
                  )}
                </TableCell>
                <TableCell className="px-2 max-w-[100px] truncate text-muted-foreground" title={row.shortName ?? ""}>{row.shortName ?? "—"}</TableCell>
                <TableCell className="px-2 text-right text-muted-foreground">{fmt(row.prevClose)}</TableCell>
                <TableCell className="px-2 text-right">{fmt(row.dayOpen)}</TableCell>
                <TableCell className="px-2 text-right">{fmt(row.dayHigh)}</TableCell>
                <TableCell className="px-2 text-right">{fmt(row.dayLow)}</TableCell>
                <TableCell className="px-2 text-right font-bold">{fmt(row.dayClose)}</TableCell>
                <TableCell className={`px-2 text-right ${pctColor(row.vsPreClosePct)}`}>{fmtPct(row.vsPreClosePct)}</TableCell>
                <TableCell className={`px-2 text-right ${pctColor(row.intradayReturnPct)}`}>{fmtPct(row.intradayReturnPct)}</TableCell>
                <TableCell className="px-2 text-right text-muted-foreground">{fmtVol(row.dayVolume)}</TableCell>
                <TableCell className="px-2 text-right">{fmt(row.intradayVwapLast, 4)}</TableCell>
                <TableCell className={`px-2 text-right ${vwapPctColor(row.pctRegularMinutesAboveVwap)}`}>
                  {row.pctRegularMinutesAboveVwap != null ? `${row.pctRegularMinutesAboveVwap.toFixed(1)}%` : "—"}
                </TableCell>
                <TableCell className="px-2 text-right font-bold">{fmt(row.latestPrice)}</TableCell>
                <TableCell className={`px-2 text-right ${pctColor(row.latestChgPct)}`}>{fmtPct(row.latestChgPct)}</TableCell>
                <TableCell className="px-2 text-center">{sessionBadge(row.latestSession)}</TableCell>
                <TableCell className="px-2 text-right text-[10px] text-muted-foreground">{row.latestBarTimeEt ?? "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────────
const DEFAULT_INPUT = `CATEGORY_SYMBOLS = {
    "AI semicap / semiconductor equipment": [
        "AMD", "AVGO", "AMAT", "ASML", "ARM", "ADI", "AMKR", "AXTI", "APH"
    ],
    "AI networking / datacenter infrastructure": [
        "ANET", "ALAB", "APLD", "ASTS", "ASX", "BBAI", "AI", "BILL"
    ],
    "AI power / nuclear / uranium": [
        "SMR", "OKLO", "CCJ", "ASPI", "BE", "AMPX", "ABAT"
    ],
    "High beta / mobility / edge technology": [
        "ACHR", "AUR", "ASST"
    ],
    "AI megacap / platform anchors": [
        "NVDA", "TSM", "MU", "MRVL", "TSLA", "GOOGL", "MSFT", "META", "BABA"
    ],
    "Financial / defense / broad market overlap": [
        "JPM", "GS", "ADP", "APP", "LMT", "NOC", "BB"
    ],
    "ETF confirmation basket": [
        "NLR", "URA", "URNM", "URNJ", "XLU", "GRID", "PAVE"
    ],
}`;

export default function Symbols({ onSymbolClick }: { onSymbolClick: (sym: string) => void }) {
  const [inputText, setInputText] = useState(DEFAULT_INPUT);
  const [copyStatus, setCopyStatus] = useState<"idle" | "success" | "error">("idle");
  const [parseError, setParseError] = useState<string | null>(null);

  const { mutate, isPending, data, error } = useBatchStockSummary();

  // Parsed categories (live, from current inputText)
  const parsedCategories = useMemo<Record<string, string[]> | null>(() => {
    return parseCategorySymbols(inputText);
  }, [inputText]);

  const handleQuery = () => {
    const cats = parsedCategories;
    if (!cats) {
      setParseError("無法解析 — 請確認格式為 \"類別\": [\"SYM1\", \"SYM2\"]");
      return;
    }
    setParseError(null);
    const all = [...new Set(Object.values(cats).flat())];
    if (all.length === 0) return;
    mutate({ data: { symbols: all } });
  };

  // Build lookup: symbol → result
  const resultMap = useMemo<Record<string, SymbolSummaryItem>>(() => {
    if (!data?.results) return {};
    const m: Record<string, SymbolSummaryItem> = {};
    for (const r of data.results) m[r.symbol] = r;
    return m;
  }, [data]);

  const copyToCSV = useCallback(async () => {
    if (!data?.results || data.results.length === 0) return;
    try {
      const headers: (keyof SymbolSummaryItem)[] = [
        "symbol", "shortName", "prevClose",
        "dayOpen", "dayHigh", "dayLow", "dayClose", "dayVolume",
        "intradayReturnPct", "vsPreClosePct",
        "latestPrice", "latestSession", "latestChgPct",
        "vwapDate", "intradayVwapLast", "pctRegularMinutesAboveVwap",
        "latestBarTimeEt",
      ];
      const csvRows = data.results.map((row) =>
        headers.map((h) => {
          const v = row[h];
          if (v == null) return "";
          if (typeof v === "string" && v.includes(",")) return `"${v}"`;
          return v;
        }).join(",")
      );
      await navigator.clipboard.writeText([headers.join(","), ...csvRows].join("\n"));
      setCopyStatus("success");
      setTimeout(() => setCopyStatus("idle"), 3000);
    } catch {
      setCopyStatus("error");
      setTimeout(() => setCopyStatus("idle"), 3000);
    }
  }, [data]);

  const totalSymbols = parsedCategories
    ? [...new Set(Object.values(parsedCategories).flat())].length
    : 0;
  const categoryCount = parsedCategories ? Object.keys(parsedCategories).length : 0;

  return (
    <div className="bg-background text-foreground font-mono p-4 md:p-8">
      <div className="max-w-7xl mx-auto space-y-6">

        <header className="border-b border-border pb-4 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight uppercase">BATCH_SUMMARY</h1>
            <p className="text-muted-foreground text-sm mt-1 uppercase">Category dict → per-category OHLCV · VWAP tables</p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <div className="w-2 h-2 rounded-full bg-success"></div>
            <span className="text-success uppercase text-xs font-bold">Online</span>
          </div>
        </header>

        {/* Input section */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-4 space-y-4">
            <div className="space-y-3 bg-muted/20 p-4 border border-border">
              <div className="space-y-1">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  CATEGORY_SYMBOLS 字典
                </label>
                <p className="text-[10px] text-muted-foreground opacity-60">
                  格式：<code className="bg-muted px-1">"類別名": ["SYM1", "SYM2"]</code>
                </p>
              </div>
              <Textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                className="font-mono text-xs bg-transparent border-border resize-y"
                style={{ minHeight: "320px" }}
                spellCheck={false}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleQuery();
                }}
              />

              {/* Parse preview */}
              {parsedCategories ? (
                <div className="text-[10px] text-muted-foreground border border-border bg-muted/10 p-2 space-y-0.5">
                  <div className="text-success font-bold mb-1">✓ 解析成功 · {categoryCount} 類別 · {totalSymbols} 個代號</div>
                  {Object.entries(parsedCategories).map(([cat, syms]) => (
                    <div key={cat} className="truncate">
                      <span className="text-foreground">{cat}</span>
                      <span className="text-muted-foreground"> ({syms.length}): {syms.join(", ")}</span>
                    </div>
                  ))}
                </div>
              ) : inputText.trim() ? (
                <div className="text-[10px] text-destructive border border-destructive/30 bg-destructive/5 p-2">
                  未偵測到有效類別。確認包含 <code>"名稱": ["SYM"]</code> 格式。
                </div>
              ) : null}

              <Button
                onClick={handleQuery}
                disabled={isPending || !parsedCategories}
                className="w-full font-mono font-bold uppercase tracking-widest h-12"
              >
                {isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "查詢 / Query"}
              </Button>

              {data?.results && (
                <Button onClick={copyToCSV} variant="outline" className="w-full font-mono font-bold uppercase tracking-widest">
                  <Copy className="mr-2 h-4 w-4" /> 複製全部 CSV
                </Button>
              )}
            </div>

            {parseError && (
              <div className="p-3 bg-destructive/10 border border-destructive/30 text-destructive text-xs font-mono">
                {parseError}
              </div>
            )}
            {copyStatus !== "idle" && (
              <div className={`p-3 border flex items-center gap-3 text-sm font-bold uppercase ${copyStatus === "success" ? "bg-success/10 border-success/30 text-success" : "bg-destructive/10 border-destructive/30 text-destructive"}`}>
                {copyStatus === "success" ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                {copyStatus === "success" ? "已複製 / Copied" : "複製失敗 / Failed"}
              </div>
            )}
            {error && (
              <div className="p-3 bg-destructive/10 border border-destructive/30 text-destructive text-xs font-mono break-all">
                ERR: {error.message}
              </div>
            )}
            {data && (
              <div className="text-[10px] text-muted-foreground border border-border p-3 bg-muted/10 space-y-0.5">
                <div>Trade date: <span className="text-foreground font-bold">{data.tradeDate}</span></div>
                <div>Fetched: {new Date(data.fetchedAt).toLocaleTimeString()}</div>
                <div>Total symbols: {data.results.length}</div>
              </div>
            )}
          </div>

          {/* Results: one table per category */}
          <div className="lg:col-span-8 space-y-6">
            {!isPending && !data && !error && (
              <div className="min-h-[400px] flex items-center justify-center border border-dashed border-border bg-muted/5">
                <div className="text-center space-y-2 text-muted-foreground">
                  <p className="uppercase text-sm tracking-widest">Awaiting Command</p>
                  <p className="text-xs opacity-50">貼上類別字典，按 Query。</p>
                </div>
              </div>
            )}

            {isPending && (
              <div className="min-h-[400px] flex items-center justify-center border border-border bg-muted/10">
                <div className="flex flex-col items-center gap-4 text-primary">
                  <Loader2 className="h-8 w-8 animate-spin" />
                  <span className="uppercase text-xs font-bold tracking-widest animate-pulse">Fetching Data...</span>
                </div>
              </div>
            )}

            {!isPending && data && parsedCategories && Object.entries(parsedCategories).map(([cat, syms]) => {
              const rows = syms.map((s) => resultMap[s]).filter(Boolean) as SymbolSummaryItem[];
              return (
                <CategoryTable key={cat} category={cat} rows={rows} onSymbolClick={onSymbolClick} />
              );
            })}
          </div>
        </div>

      </div>
    </div>
  );
}
