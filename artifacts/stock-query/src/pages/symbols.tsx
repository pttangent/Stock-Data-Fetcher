import React, { useState, useMemo, useCallback } from "react";
import { useBatchStockSummary, SymbolSummaryItem } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2, Copy, CheckCircle2, XCircle, ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

type SortConfig = {
  key: keyof SymbolSummaryItem | null;
  direction: "asc" | "desc";
};

export default function Symbols() {
  const [symbolsText, setSymbolsText] = useState("");
  const [copyStatus, setCopyStatus] = useState<"idle" | "success" | "error">("idle");
  const [sortConfig, setSortConfig] = useState<SortConfig>({ key: "vsPreClosePct", direction: "desc" });

  const { mutate, isPending, data, error } = useBatchStockSummary();

  const handleQuery = () => {
    const symbolList = symbolsText
      .split(/[,\n\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (symbolList.length === 0) return;
    mutate({ data: { symbols: symbolList } });
  };

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
          if (v === null || v === undefined) return "";
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

  const handleSort = (key: keyof SymbolSummaryItem) => {
    setSortConfig((prev) => ({
      key,
      direction: prev.key === key && prev.direction === "desc" ? "asc" : "desc",
    }));
  };

  const sortedResults = useMemo(() => {
    if (!data?.results) return [];
    return [...data.results].sort((a, b) => {
      if (!sortConfig.key) return 0;
      const av = a[sortConfig.key];
      const bv = b[sortConfig.key];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (av < bv) return sortConfig.direction === "asc" ? -1 : 1;
      if (av > bv) return sortConfig.direction === "asc" ? 1 : -1;
      return 0;
    });
  }, [data?.results, sortConfig]);

  const fmt = (v: number | null | undefined, dp = 2) =>
    v == null ? "—" : v.toFixed(dp);

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

  const SortIcon = ({ col }: { col: keyof SymbolSummaryItem }) => {
    if (sortConfig.key !== col) return <ArrowUpDown className="w-3 h-3 ml-1 inline opacity-30" />;
    return sortConfig.direction === "asc"
      ? <ArrowUp className="w-3 h-3 ml-1 inline" />
      : <ArrowDown className="w-3 h-3 ml-1 inline" />;
  };

  const Th = ({
    col,
    children,
    right,
  }: {
    col: keyof SymbolSummaryItem;
    children: React.ReactNode;
    right?: boolean;
  }) => (
    <TableHead
      className={`py-3 px-2 cursor-pointer hover:text-foreground select-none ${right ? "text-right" : "text-left"}`}
      onClick={() => handleSort(col)}
    >
      {children}
      <SortIcon col={col} />
    </TableHead>
  );

  const sessionBadge = (s: string | null | undefined) => {
    if (s === "afterhours")
      return <Badge variant="outline" className="text-amber-500 border-amber-500/30 bg-amber-500/10 px-1 py-0 h-5 text-[10px]">AH</Badge>;
    if (s === "premarket")
      return <Badge variant="outline" className="text-blue-500 border-blue-500/30 bg-blue-500/10 px-1 py-0 h-5 text-[10px]">PM</Badge>;
    if (s === "regular")
      return <Badge variant="outline" className="text-success border-success/30 bg-success/10 px-1 py-0 h-5 text-[10px]">REG</Badge>;
    return <span className="text-muted-foreground">—</span>;
  };

  return (
    <div className="bg-background text-foreground font-mono p-4 md:p-8 selection:bg-primary selection:text-primary-foreground">
      <div className="max-w-[1800px] mx-auto space-y-8">

        <header className="border-b border-border pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight uppercase">BATCH_SUMMARY</h1>
            <p className="text-muted-foreground text-sm mt-1 uppercase">Bulk query — OHLCV · VWAP · Latest price</p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <div className="w-2 h-2 rounded-full bg-success"></div>
            <span className="text-success uppercase text-xs font-bold">Online</span>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

          {/* Controls */}
          <div className="lg:col-span-3 space-y-4">
            <div className="space-y-4 bg-muted/20 p-4 border border-border">
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  股票代號列表 / Symbols
                </label>
                <Textarea
                  value={symbolsText}
                  onChange={(e) => setSymbolsText(e.target.value)}
                  className="font-mono text-sm bg-transparent border-border h-36 uppercase resize-y"
                  placeholder={"AAPL\nTSLA\nNVDA"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleQuery();
                  }}
                />
                <p className="text-[10px] text-muted-foreground opacity-60">每行或逗號分隔 · Ctrl+Enter 查詢</p>
              </div>

              <Button
                onClick={handleQuery}
                disabled={isPending || !symbolsText.trim()}
                className="w-full font-mono font-bold uppercase tracking-widest h-12"
              >
                {isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "查詢 / Query"}
              </Button>

              {data?.results && data.results.length > 0 && (
                <Button
                  onClick={copyToCSV}
                  variant="outline"
                  className="w-full font-mono font-bold uppercase tracking-widest"
                >
                  <Copy className="mr-2 h-4 w-4" /> 複製 CSV
                </Button>
              )}
            </div>

            {copyStatus !== "idle" && (
              <div className={`p-3 border flex items-center gap-3 text-sm font-bold uppercase ${
                copyStatus === "success"
                  ? "bg-success/10 border-success/30 text-success"
                  : "bg-destructive/10 border-destructive/30 text-destructive"
              }`}>
                {copyStatus === "success" ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                {copyStatus === "success" ? "已複製 / Copied" : "複製失敗 / Failed"}
              </div>
            )}

            {error && (
              <div className="p-3 bg-destructive/10 border border-destructive/30 text-destructive text-sm font-mono break-all">
                ERR: {error.message || "Query failed"}
              </div>
            )}

            {data && (
              <div className="text-[10px] text-muted-foreground space-y-1 border border-border p-3 bg-muted/10">
                <div>Trade date: <span className="text-foreground font-bold">{data.tradeDate}</span></div>
                <div>Fetched: {new Date(data.fetchedAt).toLocaleTimeString()}</div>
                <div>Count: {data.results.length}</div>
              </div>
            )}
          </div>

          {/* Table */}
          <div className="lg:col-span-9 overflow-hidden">
            {!isPending && !data && !error && (
              <div className="min-h-[400px] flex items-center justify-center border border-dashed border-border bg-muted/5">
                <div className="text-center space-y-2 text-muted-foreground">
                  <p className="uppercase text-sm tracking-widest">Awaiting Command</p>
                  <p className="text-xs opacity-50">Enter symbols and press Query.</p>
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

            {!isPending && data && (
              <div className="border border-border bg-card overflow-hidden">
                <div className="overflow-x-auto">
                  <Table className="font-mono text-xs whitespace-nowrap">
                    <TableHeader className="bg-muted/10">
                      <TableRow className="border-border hover:bg-transparent">
                        <Th col="symbol">Symbol</Th>
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
                        <TableHead className="py-3 px-2 text-center">Session</TableHead>
                        <Th col="latestBarTimeEt" right>Last Bar ET</Th>
                        <TableHead className="py-3 px-2 text-left text-muted-foreground text-[10px]">Err</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {sortedResults.map((row, i) => (
                        <TableRow key={row.symbol || i} className="border-border hover:bg-muted/10">
                          <TableCell className="px-2 font-bold">{row.symbol}</TableCell>
                          <TableCell className="px-2 max-w-[110px] truncate text-muted-foreground" title={row.shortName ?? ""}>{row.shortName ?? "—"}</TableCell>
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
                          <TableCell className="px-2 text-left">
                            {row.fetchError
                              ? <span className="text-destructive max-w-[80px] truncate inline-block" title={row.fetchError}>{row.fetchError}</span>
                              : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                      {sortedResults.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={17} className="text-center py-12 text-muted-foreground">
                            No data returned
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
