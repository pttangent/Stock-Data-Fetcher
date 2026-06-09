import React, { useState, useCallback, useEffect } from "react";
import { getStockHistory, useGetStockInfo, StockHistoryResult, GetStockHistoryParams } from "@workspace/api-client-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { format } from "date-fns";
import { Loader2, Copy, CheckCircle2, XCircle } from "lucide-react";
import CandlestickChart from "@/components/CandlestickChart";

type Period = "1d" | "max";
type Interval = "1m" | "5m" | "15m" | "1h" | "1d";

type HomeProps = {
  pendingSymbolQuery?: string | null;
  onPendingQueryHandled?: () => void;
};

export default function Home({ pendingSymbolQuery, onPendingQueryHandled }: HomeProps = {}) {
  const [symbol, setSymbol] = useState("AAPL");
  const [period, setPeriod] = useState<Period>("1d");
  const [interval, setInterval] = useState<Interval>("1m");
  
  const [results, setResults] = useState<StockHistoryResult[]>([]);
  const [activeResultIdx, setActiveResultIdx] = useState(0);
  const [isFetching, setIsFetching] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: stockInfo } = useGetStockInfo(
    { symbol }, 
    { query: { enabled: !!symbol && symbol.length > 0, queryKey: [`/api/stocks/info`, { symbol }] } }
  );

  const copyToClipboard = useCallback(async (data: StockHistoryResult[], _fetchedSymbol: string) => {
    try {
      const blocks = data.map(r => {
        const header = `# ${r.symbol} | period=${r.period} | interval=${r.interval} | rows=${r.rowCount} | fetchedAt=${r.fetchedAt}`;
        const csv = [
          "date,open,high,low,close,volume",
          ...r.data.map(row =>
            [row.date, row.open ?? "", row.high ?? "", row.low ?? "", row.close ?? "", row.volume ?? ""].join(",")
          )
        ].join("\n");
        return `${header}\n${csv}`;
      });

      await navigator.clipboard.writeText(blocks.join("\n\n"));
      setCopyStatus("success");
      setTimeout(() => setCopyStatus("idle"), 3000);
    } catch (err) {
      console.error("Failed to copy", err);
      setCopyStatus("error");
      setTimeout(() => setCopyStatus("idle"), 3000);
    }
  }, []);

  const runQueries = async (
    queries: Omit<GetStockHistoryParams, "symbol">[],
    symbolOverride?: string
  ) => {
    const sym = symbolOverride ?? symbol;
    if (!sym) return;

    setIsFetching(true);
    setErrorMsg(null);
    try {
      const promises = queries.map(q => getStockHistory({ symbol: sym, ...q }));
      const res = await Promise.all(promises);
      setResults(res);
      setActiveResultIdx(0);
      await copyToClipboard(res, sym);
    } catch (err: any) {
      console.error("Query failed", err);
      setErrorMsg(err.message || "Query failed");
    } finally {
      setIsFetching(false);
    }
  };

  // Auto-query when navigated from Symbols tab via symbol click
  useEffect(() => {
    if (!pendingSymbolQuery) return;
    setSymbol(pendingSymbolQuery);
    setPeriod("1d");
    setInterval("1m");
    runQueries([{ period: "1d", interval: "1m" }], pendingSymbolQuery);
    onPendingQueryHandled?.();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingSymbolQuery]);

  const handleManualQuery = () => {
    runQueries([{ period, interval }]);
  };

  const handlePreset1 = () => {
    runQueries([{ period: "max", interval: "1m" }]);
  };

  const handlePreset2 = () => {
    runQueries([
      { period: "max", interval: "1m" },
      { period: "max", interval: "15m" }
    ]);
  };

  const handlePreset3 = () => {
    runQueries([
      { period: "max", interval: "1d" },
      { period: "max", interval: "1m" },
      { period: "max", interval: "15m" }
    ]);
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-mono p-4 md:p-8 selection:bg-primary selection:text-primary-foreground">
      <div className="max-w-7xl mx-auto space-y-8">
        
        <header className="border-b border-border pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight uppercase">STOCK_DATA_QUERY</h1>
            <p className="text-muted-foreground text-sm mt-1 uppercase">Terminal interface for OHLCV data</p>
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
          <div className="lg:col-span-4 space-y-6">
            <div className="space-y-4 bg-muted/20 p-4 border border-border">
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">股票代號 / Symbol</label>
                <div className="relative">
                  <Input 
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                    className="font-mono text-lg font-bold bg-transparent border-border uppercase h-12"
                    placeholder="AAPL"
                  />
                  {stockInfo && stockInfo.shortName && (
                    <div className="absolute right-3 top-3 text-xs text-muted-foreground text-right pointer-events-none">
                      <div className="truncate w-32">{stockInfo.shortName}</div>
                      {stockInfo.regularMarketPrice && (
                        <div className={
                          (stockInfo.regularMarketChangePercent || 0) >= 0 ? "text-success" : "text-destructive"
                        }>
                          {stockInfo.regularMarketPrice.toFixed(2)}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">查詢範圍 / Period</label>
                  <Select value={period} onValueChange={(v) => setPeriod(v as Period)}>
                    <SelectTrigger className="font-mono bg-transparent border-border h-10">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="font-mono">
                      <SelectItem value="1d">今日 (1d)</SelectItem>
                      <SelectItem value="max">全歷史 (max)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">資料尺度 / Interval</label>
                  <Select value={interval} onValueChange={(v) => setInterval(v as Interval)}>
                    <SelectTrigger className="font-mono bg-transparent border-border h-10">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="font-mono">
                      <SelectItem value="1m">1min</SelectItem>
                      <SelectItem value="5m">5min</SelectItem>
                      <SelectItem value="15m">15min</SelectItem>
                      <SelectItem value="1h">1h</SelectItem>
                      <SelectItem value="1d">1d</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Button 
                onClick={handleManualQuery}
                disabled={isFetching || !symbol}
                className="w-full font-mono font-bold uppercase tracking-widest h-12"
              >
                {isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "手動查詢 / Query"}
              </Button>
            </div>

            <div className="space-y-3 bg-muted/20 p-4 border border-border">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-4">快速設定 / Presets</label>
              
              <Button 
                variant="outline" 
                onClick={handlePreset1}
                disabled={isFetching || !symbol}
                className="w-full justify-start font-mono text-xs h-auto py-3 whitespace-normal text-left"
              >
                <div className="flex flex-col items-start gap-1">
                  <span className="font-bold">全歷史 1min K</span>
                  <span className="text-[10px] text-muted-foreground opacity-70">Exec: [max, 1m]</span>
                </div>
              </Button>
              
              <Button 
                variant="outline" 
                onClick={handlePreset2}
                disabled={isFetching || !symbol}
                className="w-full justify-start font-mono text-xs h-auto py-3 whitespace-normal text-left"
              >
                <div className="flex flex-col items-start gap-1">
                  <span className="font-bold">全歷史 1min K + 全歷史 15min K</span>
                  <span className="text-[10px] text-muted-foreground opacity-70">Exec: [max, 1m] & [max, 15m]</span>
                </div>
              </Button>
              
              <Button 
                variant="outline" 
                onClick={handlePreset3}
                disabled={isFetching || !symbol}
                className="w-full justify-start font-mono text-xs h-auto py-3 whitespace-normal text-left"
              >
                <div className="flex flex-col items-start gap-1">
                  <span className="font-bold">全歷史 1d K + 1min K + 15min K</span>
                  <span className="text-[10px] text-muted-foreground opacity-70">Exec: [max, 1d] & [max, 1m] & [max, 15m]</span>
                </div>
              </Button>
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

            {errorMsg && (
              <div className="p-3 bg-destructive/10 border border-destructive/30 text-destructive text-sm font-mono break-all">
                ERR: {errorMsg}
              </div>
            )}

          </div>

          {/* Results Area */}
          <div className="lg:col-span-8 space-y-6">
            {!isFetching && results.length === 0 && !errorMsg && (
              <div className="h-full min-h-[400px] flex items-center justify-center border border-dashed border-border bg-muted/5">
                <div className="text-center space-y-2 text-muted-foreground">
                  <p className="uppercase text-sm tracking-widest">Awaiting Command</p>
                  <p className="text-xs opacity-50">Select parameters and execute query.</p>
                </div>
              </div>
            )}

            {isFetching && (
              <div className="h-full min-h-[400px] flex items-center justify-center border border-border bg-muted/10">
                <div className="flex flex-col items-center gap-4 text-primary">
                  <Loader2 className="h-8 w-8 animate-spin" />
                  <span className="uppercase text-xs font-bold tracking-widest animate-pulse">Fetching Data...</span>
                </div>
              </div>
            )}

            {!isFetching && results.length > 0 && (
              <div className="space-y-4">
                {results.length > 1 && (
                  <div className="flex items-center gap-2 border-b border-border">
                    {results.map((result, idx) => (
                      <button
                        key={`${result.period}-${result.interval}-${idx}`}
                        onClick={() => setActiveResultIdx(idx)}
                        className={`px-4 py-2 text-sm font-mono uppercase tracking-widest border-b-2 transition-colors ${
                          activeResultIdx === idx
                            ? "border-primary text-primary"
                            : "border-transparent text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {result.interval}
                      </button>
                    ))}
                  </div>
                )}

                {(() => {
                  const result = results[activeResultIdx] || results[0];
                  return (
                    <div key={`${result.period}-${result.interval}-${activeResultIdx}`} className="border border-border bg-card overflow-hidden">
                      <div className="p-4 border-b border-border bg-muted/10">
                        <CandlestickChart data={result.data} interval={result.interval} />
                      </div>

                      <div className="bg-muted/30 px-4 py-3 border-b border-border flex flex-wrap items-center justify-between gap-4">
                        <div className="flex items-center gap-4">
                          <Badge variant="outline" className="font-mono bg-background text-foreground rounded-none border-border">
                            {result.symbol}
                          </Badge>
                          <div className="flex items-center gap-2 text-xs uppercase text-muted-foreground tracking-wider">
                            <span>P:<span className="text-foreground font-bold">{result.period}</span></span>
                            <span>I:<span className="text-foreground font-bold">{result.interval}</span></span>
                            <span>Rows:<span className="text-foreground font-bold">{result.rowCount.toLocaleString()}</span></span>
                          </div>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {format(new Date(result.fetchedAt), "yyyy-MM-dd HH:mm:ss")}
                        </div>
                      </div>
                      
                      <div className="overflow-x-auto">
                        <Table className="font-mono text-xs">
                          <TableHeader className="bg-muted/10">
                            <TableRow className="border-border">
                              <TableHead className="text-muted-foreground uppercase py-2">Date (ISO)</TableHead>
                              <TableHead className="text-muted-foreground uppercase py-2 text-right">Open</TableHead>
                              <TableHead className="text-muted-foreground uppercase py-2 text-right">High</TableHead>
                              <TableHead className="text-muted-foreground uppercase py-2 text-right">Low</TableHead>
                              <TableHead className="text-muted-foreground uppercase py-2 text-right">Close</TableHead>
                              <TableHead className="text-muted-foreground uppercase py-2 text-right">Volume</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {result.data.slice(0, 5).map((row, i) => (
                              <TableRow key={i} className="border-border">
                                <TableCell className="whitespace-nowrap text-muted-foreground">{row.date}</TableCell>
                                <TableCell className="text-right">{row.open?.toFixed(4) || "N/A"}</TableCell>
                                <TableCell className="text-right">{row.high?.toFixed(4) || "N/A"}</TableCell>
                                <TableCell className="text-right">{row.low?.toFixed(4) || "N/A"}</TableCell>
                                <TableCell className="text-right font-bold text-primary">{row.close?.toFixed(4) || "N/A"}</TableCell>
                                <TableCell className="text-right text-muted-foreground">{row.volume?.toLocaleString() || "N/A"}</TableCell>
                              </TableRow>
                            ))}
                            {result.data.length > 5 && (
                              <TableRow className="border-none hover:bg-transparent">
                                <TableCell colSpan={6} className="text-center py-4 text-muted-foreground opacity-50 italic">
                                  ... {result.data.length - 5} more rows fetched
                                </TableCell>
                              </TableRow>
                            )}
                            {result.data.length === 0 && (
                              <TableRow>
                                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                                  No data returned
                                </TableCell>
                              </TableRow>
                            )}
                          </TableBody>
                        </Table>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
