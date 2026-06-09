import React, { useState, useMemo, useCallback } from "react";
import { useBatchStockSummary, SymbolSummaryItem } from "@workspace/api-client-react";
import { Input } from "@/components/ui/input";
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
  const [dateInput, setDateInput] = useState("");
  const [copyStatus, setCopyStatus] = useState<"idle" | "success" | "error">("idle");
  const [sortConfig, setSortConfig] = useState<SortConfig>({ key: "dayReturnPct", direction: "desc" });

  const { mutate, isPending, data, error } = useBatchStockSummary();

  const handleQuery = () => {
    const symbolList = symbolsText
      .split(/[,\n]+/)
      .map(s => s.trim().toUpperCase())
      .filter(Boolean);
    
    if (symbolList.length === 0) return;

    mutate({ data: { symbols: symbolList, date: dateInput || null } });
  };

  const copyToCSV = useCallback(async () => {
    if (!data?.results || data.results.length === 0) return;

    try {
      const headers = [
        "symbol", "shortName", "dayOpen", "dayHigh", "dayLow", "dayClose", 
        "dayReturnPct", "dayVolume", "intradayVwapLast", "pctRegularMinutesAboveVwap", 
        "latestPrice", "isAfterHours", "afterHoursPrice", "afterHoursVsDayClosePct", 
        "currentVsVwapPct", "latestBarTimeEt"
      ];

      const csvRows = data.results.map(row => {
        return headers.map(header => {
          const val = row[header as keyof SymbolSummaryItem];
          if (val === null || val === undefined) return "";
          // Escape strings containing commas just in case
          if (typeof val === "string" && val.includes(",")) return `"${val}"`;
          return val;
        }).join(",");
      });

      const csv = [headers.join(","), ...csvRows].join("\n");
      await navigator.clipboard.writeText(csv);
      setCopyStatus("success");
      setTimeout(() => setCopyStatus("idle"), 3000);
    } catch (err) {
      console.error("Copy failed", err);
      setCopyStatus("error");
      setTimeout(() => setCopyStatus("idle"), 3000);
    }
  }, [data]);

  const handleSort = (key: keyof SymbolSummaryItem) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === "desc" ? "asc" : "desc"
    }));
  };

  const sortedResults = useMemo(() => {
    if (!data?.results) return [];
    
    const sorted = [...data.results].sort((a, b) => {
      if (!sortConfig.key) return 0;
      
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];

      if (aVal === null || aVal === undefined) return 1; // nulls last
      if (bVal === null || bVal === undefined) return -1;

      if (aVal < bVal) return sortConfig.direction === "asc" ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === "asc" ? 1 : -1;
      return 0;
    });

    return sorted;
  }, [data?.results, sortConfig]);

  const formatVol = (v: number | null | undefined) => {
    if (v == null) return "—";
    if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
    if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
    return v.toString();
  };

  const formatNum = (v: number | null | undefined, dp: number) => {
    if (v == null) return "—";
    return v.toFixed(dp);
  };

  const formatPct = (v: number | null | undefined) => {
    if (v == null) return "—";
    const sign = v >= 0 ? "+" : "";
    return `${sign}${v.toFixed(2)}%`;
  };

  const getPctColor = (v: number | null | undefined) => {
    if (v == null) return "text-muted-foreground";
    if (v > 0) return "text-success font-bold";
    if (v < 0) return "text-destructive font-bold";
    return "text-foreground";
  };

  const getVwapPctColor = (v: number | null | undefined) => {
    if (v == null) return "text-muted-foreground";
    if (v >= 60) return "text-success font-bold";
    if (v >= 40) return "text-yellow-500 font-bold";
    return "text-destructive font-bold";
  };

  const renderSortIcon = (key: keyof SymbolSummaryItem) => {
    if (sortConfig.key !== key) return <ArrowUpDown className="w-3 h-3 ml-1 inline opacity-30" />;
    return sortConfig.direction === "asc" ? <ArrowUp className="w-3 h-3 ml-1 inline" /> : <ArrowDown className="w-3 h-3 ml-1 inline" />;
  };

  return (
    <div className="bg-background text-foreground font-mono p-4 md:p-8 selection:bg-primary selection:text-primary-foreground">
      <div className="max-w-[1600px] mx-auto space-y-8">
        
        <header className="border-b border-border pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight uppercase">BATCH_SUMMARY</h1>
            <p className="text-muted-foreground text-sm mt-1 uppercase">Bulk query for daily summary & VWAP</p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <div className="flex flex-col items-end">
              <span className="text-muted-foreground uppercase text-xs">Status</span>
              <span className="text-success flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-success"></div> ONLINE</span>
            </div>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Controls Sidebar */}
          <div className="lg:col-span-3 space-y-6">
            <div className="space-y-4 bg-muted/20 p-4 border border-border">
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">股票代號列表 / Symbols</label>
                <Textarea 
                  value={symbolsText}
                  onChange={(e) => setSymbolsText(e.target.value)}
                  className="font-mono text-sm bg-transparent border-border h-32 uppercase resize-y"
                  placeholder="AAPL&#10;TSLA&#10;NVDA"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">交易日期 / Date (ET)</label>
                <Input 
                  type="date"
                  value={dateInput}
                  onChange={(e) => setDateInput(e.target.value)}
                  className="font-mono bg-transparent border-border"
                />
                <p className="text-[10px] text-muted-foreground opacity-70">Leave empty for today</p>
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
                {copyStatus === "success" ? "已複製 / Copied to clipboard" : "複製失敗 / Copy failed"}
              </div>
            )}

            {error && (
              <div className="p-3 bg-destructive/10 border border-destructive/30 text-destructive text-sm font-mono break-all">
                ERR: {error.message || "Query failed"}
              </div>
            )}

          </div>

          {/* Results Area */}
          <div className="lg:col-span-9 space-y-6 overflow-hidden">
            {!isPending && !data && !error && (
              <div className="h-full min-h-[400px] flex items-center justify-center border border-dashed border-border bg-muted/5">
                <div className="text-center space-y-2 text-muted-foreground">
                  <p className="uppercase text-sm tracking-widest">Awaiting Command</p>
                  <p className="text-xs opacity-50">Enter symbols to fetch batch summary.</p>
                </div>
              </div>
            )}

            {isPending && (
              <div className="h-full min-h-[400px] flex items-center justify-center border border-border bg-muted/10">
                <div className="flex flex-col items-center gap-4 text-primary">
                  <Loader2 className="h-8 w-8 animate-spin" />
                  <span className="uppercase text-xs font-bold tracking-widest animate-pulse">Fetching Data...</span>
                </div>
              </div>
            )}

            {!isPending && data && (
              <div className="border border-border bg-card overflow-hidden flex flex-col">
                <div className="bg-muted/30 px-4 py-3 border-b border-border flex flex-wrap items-center justify-between gap-4">
                  <div className="flex items-center gap-4 text-xs uppercase tracking-wider">
                     <span>Trade Date: <span className="font-bold text-foreground">{data.tradeDate}</span></span>
                     <span>Count: <span className="font-bold text-foreground">{data.results.length}</span></span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Fetched: {new Date(data.fetchedAt).toLocaleString()}
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <Table className="font-mono text-xs whitespace-nowrap">
                    <TableHeader className="bg-muted/10">
                      <TableRow className="border-border hover:bg-transparent">
                        <TableHead className="py-3 px-2 text-left cursor-pointer hover:text-foreground" onClick={() => handleSort("symbol")}>Symbol {renderSortIcon("symbol")}</TableHead>
                        <TableHead className="py-3 px-2 text-left cursor-pointer hover:text-foreground" onClick={() => handleSort("shortName")}>Name {renderSortIcon("shortName")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("dayOpen")}>Open {renderSortIcon("dayOpen")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("dayHigh")}>High {renderSortIcon("dayHigh")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("dayLow")}>Low {renderSortIcon("dayLow")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("dayClose")}>Close {renderSortIcon("dayClose")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("dayReturnPct")}>Chg% {renderSortIcon("dayReturnPct")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("dayVolume")}>Vol {renderSortIcon("dayVolume")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("intradayVwapLast")}>VWAP {renderSortIcon("intradayVwapLast")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("pctRegularMinutesAboveVwap")}>&gt;VWAP% {renderSortIcon("pctRegularMinutesAboveVwap")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("latestPrice")}>Latest {renderSortIcon("latestPrice")}</TableHead>
                        <TableHead className="py-3 px-2 text-center">Session</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("afterHoursPrice")}>AH Price {renderSortIcon("afterHoursPrice")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("afterHoursVsDayClosePct")}>AH Chg% {renderSortIcon("afterHoursVsDayClosePct")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("currentVsVwapPct")}>vs VWAP% {renderSortIcon("currentVsVwapPct")}</TableHead>
                        <TableHead className="py-3 px-2 text-right cursor-pointer hover:text-foreground" onClick={() => handleSort("latestBarTimeEt")}>Last Bar ET {renderSortIcon("latestBarTimeEt")}</TableHead>
                        <TableHead className="py-3 px-2 text-left">Error</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {sortedResults.map((row, i) => (
                        <TableRow key={row.symbol || i} className="border-border hover:bg-muted/10">
                          <TableCell className="px-2 font-bold">{row.symbol}</TableCell>
                          <TableCell className="px-2 max-w-[120px] truncate" title={row.shortName || ""}>{row.shortName || "—"}</TableCell>
                          <TableCell className="px-2 text-right">{formatNum(row.dayOpen, 2)}</TableCell>
                          <TableCell className="px-2 text-right">{formatNum(row.dayHigh, 2)}</TableCell>
                          <TableCell className="px-2 text-right">{formatNum(row.dayLow, 2)}</TableCell>
                          <TableCell className="px-2 text-right">{formatNum(row.dayClose, 2)}</TableCell>
                          <TableCell className={`px-2 text-right ${getPctColor(row.dayReturnPct)}`}>{formatPct(row.dayReturnPct)}</TableCell>
                          <TableCell className="px-2 text-right text-muted-foreground">{formatVol(row.dayVolume)}</TableCell>
                          <TableCell className="px-2 text-right">{formatNum(row.intradayVwapLast, 4)}</TableCell>
                          <TableCell className={`px-2 text-right ${getVwapPctColor(row.pctRegularMinutesAboveVwap)}`}>
                            {row.pctRegularMinutesAboveVwap != null ? `${row.pctRegularMinutesAboveVwap.toFixed(1)}%` : "—"}
                          </TableCell>
                          <TableCell className="px-2 text-right font-bold">{formatNum(row.latestPrice, 2)}</TableCell>
                          <TableCell className="px-2 text-center">
                            {row.isAfterHours ? (
                              <Badge variant="outline" className="text-amber-500 border-amber-500/30 bg-amber-500/10 px-1 py-0 h-5 text-[10px]">AH</Badge>
                            ) : row.isPremarket ? (
                              <Badge variant="outline" className="text-blue-500 border-blue-500/30 bg-blue-500/10 px-1 py-0 h-5 text-[10px]">PM</Badge>
                            ) : (
                              <Badge variant="outline" className="text-muted-foreground border-border bg-transparent px-1 py-0 h-5 text-[10px]">REG</Badge>
                            )}
                          </TableCell>
                          <TableCell className="px-2 text-right">{row.afterHoursPrice != null ? formatNum(row.afterHoursPrice, 2) : "—"}</TableCell>
                          <TableCell className={`px-2 text-right ${getPctColor(row.afterHoursVsDayClosePct)}`}>{formatPct(row.afterHoursVsDayClosePct)}</TableCell>
                          <TableCell className={`px-2 text-right ${getPctColor(row.currentVsVwapPct)}`}>{formatPct(row.currentVsVwapPct)}</TableCell>
                          <TableCell className="px-2 text-right text-[10px] text-muted-foreground">{row.latestBarTimeEt || "—"}</TableCell>
                          <TableCell className="px-2 text-left">
                            {row.fetchError ? <span className="text-destructive max-w-[100px] truncate inline-block" title={row.fetchError}>{row.fetchError}</span> : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                      {sortedResults.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={17} className="text-center py-8 text-muted-foreground">
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
