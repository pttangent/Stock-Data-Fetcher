import React, { useState, useMemo, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Loader2, Copy, ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

interface SnapshotItem {
  symbol: string;
  shortName: string | null;
  prevClose: number | null;
  dayOpen: number | null;
  dayHigh: number | null;
  dayLow: number | null;
  dayClose: number | null;
  dayVolume: number | null;
  intradayReturnPct: number | null;
  vsPreClosePct: number | null;
  latestPrice: number | null;
  latestSession: string | null;
  latestChgPct: number | null;
  vwapDate: string | null;
  intradayVwapLast: number | null;
  pctRegularMinutesAboveVwap: number | null;
  latestBarTimeEt: string | null;
}

interface Snapshot {
  id: number;
  type: string;
  tradeDate: string;
  fetchedAt: string;
  symbolCount: number;
  results: SnapshotItem[];
}

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

type SortKey = keyof SnapshotItem;
type SortConfig = { key: SortKey | null; direction: "asc" | "desc" };

function applySort(items: SnapshotItem[], cfg: SortConfig): SnapshotItem[] {
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

function ResultsTable({ rows }: { rows: SnapshotItem[] }) {
  const [sort, setSort] = useState<SortConfig>({ key: "vsPreClosePct", direction: "desc" });

  const sorted = useMemo(() => applySort(rows, sort), [rows, sort]);

  const handleSort = (key: SortKey) => {
    setSort((prev) => ({
      key,
      direction: prev.key === key && prev.direction === "desc" ? "asc" : "desc",
    }));
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sort.key !== col) return <ArrowUpDown className="w-3 h-3 ml-1 inline opacity-30" />;
    return sort.direction === "asc"
      ? <ArrowUp className="w-3 h-3 ml-1 inline" />
      : <ArrowDown className="w-3 h-3 ml-1 inline" />;
  };

  const Th = ({ col, children, right }: { col: SortKey; children: React.ReactNode; right?: boolean }) => (
    <TableHead
      className={`py-2 px-2 cursor-pointer hover:text-foreground select-none whitespace-nowrap ${right ? "text-right" : "text-left"}`}
      onClick={() => handleSort(col)}
    >
      {children}<SortIcon col={col} />
    </TableHead>
  );

  return (
    <div className="overflow-x-auto border border-border">
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
            <TableHead className="py-2 px-2 text-center">Session</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((row, i) => (
            <TableRow key={row.symbol || i} className="border-border hover:bg-muted/10">
              <TableCell className="px-2 font-bold">{row.symbol}</TableCell>
              <TableCell className="px-2 max-w-[100px] truncate text-muted-foreground">{row.shortName ?? "—"}</TableCell>
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
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default function MarketSnapshot() {
  const [activeType, setActiveType] = useState<"all-stocks" | "all-etfs">("all-stocks");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [snapshots, setSnapshots] = useState<Array<{ id: number; type: string; tradeDate: string; fetchedAt: string; symbolCount: number }>>([]);
  const [loading, setLoading] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "success">("idle");

  const fetchLatest = useCallback(async (type: "all-stocks" | "all-etfs") => {
    setLoading(true);
    try {
      const res = await fetch(`/api/snapshots/latest?type=${type}`);
      if (res.ok) {
        const data = await res.json();
        setSnapshot(data);
      } else {
        setSnapshot(null);
      }
    } catch {
      setSnapshot(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSnapshots = useCallback(async () => {
    try {
      const res = await fetch("/api/snapshots");
      if (res.ok) {
        const data = await res.json();
        setSnapshots(data.snapshots || []);
      }
    } catch {
      // ignore
    }
  }, []);

  const fetchById = useCallback(async (id: number) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/snapshots/${id}`);
      if (res.ok) {
        const data = await res.json();
        setSnapshot(data);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchLatest(activeType);
    fetchSnapshots();
  }, [activeType, fetchLatest, fetchSnapshots]);

  const copyToCSV = useCallback(async () => {
    if (!snapshot?.results || snapshot.results.length === 0) return;
    try {
      const headers = [
        "symbol", "shortName", "prevClose", "dayOpen", "dayHigh", "dayLow", "dayClose", "dayVolume",
        "intradayReturnPct", "vsPreClosePct", "latestPrice", "latestSession", "latestChgPct",
        "vwapDate", "intradayVwapLast", "pctRegularMinutesAboveVwap", "latestBarTimeEt",
      ];
      const csvRows = snapshot.results.map((row: SnapshotItem) =>
        headers.map((h) => {
          const v = row[h as keyof SnapshotItem];
          if (v == null) return "";
          if (typeof v === "string" && v.includes(",")) return `"${v}"`;
          return v;
        }).join(",")
      );
      await navigator.clipboard.writeText([headers.join(","), ...csvRows].join("\n"));
      setCopyStatus("success");
      setTimeout(() => setCopyStatus("idle"), 3000);
    } catch {
      // ignore
    }
  }, [snapshot]);

  const typeSnapshots = snapshots.filter((s) => s.type === activeType);

  return (
    <div className="bg-background text-foreground font-mono p-4 md:p-8">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="border-b border-border pb-4 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight uppercase">MARKET_SNAPSHOT</h1>
            <p className="text-muted-foreground text-sm mt-1 uppercase">Scheduled market scan · 30 min interval</p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <div className="w-2 h-2 rounded-full bg-success"></div>
            <span className="text-success uppercase text-xs font-bold">Auto-Capturing</span>
          </div>
        </header>

        <div className="flex flex-wrap gap-2">
          <Button
            variant={activeType === "all-stocks" ? "default" : "outline"}
            onClick={() => setActiveType("all-stocks")}
            className="font-mono font-bold text-xs"
          >
            All Stocks
          </Button>
          <Button
            variant={activeType === "all-etfs" ? "default" : "outline"}
            onClick={() => setActiveType("all-etfs")}
            className="font-mono font-bold text-xs"
          >
            All ETF/CEF
          </Button>
        </div>

        {snapshot && (
          <div className="text-[10px] text-muted-foreground border border-border p-3 bg-muted/10 space-y-0.5">
            <div>Trade date: <span className="text-foreground font-bold">{snapshot.tradeDate}</span></div>
            <div>Fetched: {new Date(snapshot.fetchedAt).toLocaleString()}</div>
            <div>Symbols: <span className="text-foreground font-bold">{snapshot.symbolCount}</span></div>
            <div>Snapshot ID: {snapshot.id}</div>
          </div>
        )}

        <div className="flex flex-wrap gap-2 items-center">
          <Button onClick={() => fetchLatest(activeType)} variant="outline" className="font-mono text-xs">
            刷新 / Refresh
          </Button>
          {snapshot && (
            <Button onClick={copyToCSV} variant="outline" className="font-mono text-xs">
              {copyStatus === "success" ? "已複製 / Copied" : "複製 CSV / Copy CSV"}
            </Button>
          )}
        </div>

        {typeSnapshots.length > 0 && (
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">歷史快照 / History</label>
            <div className="flex flex-wrap gap-2">
              {typeSnapshots.map((s) => (
                <Button
                  key={s.id}
                  variant={snapshot?.id === s.id ? "default" : "outline"}
                  onClick={() => fetchById(s.id)}
                  className="font-mono text-[10px] h-8"
                >
                  #{s.id} {s.tradeDate} ({s.symbolCount})
                </Button>
              ))}
            </div>
          </div>
        )}

        {loading && (
          <div className="min-h-[400px] flex items-center justify-center border border-border bg-muted/10">
            <div className="flex flex-col items-center gap-4 text-primary">
              <Loader2 className="h-8 w-8 animate-spin" />
              <span className="uppercase text-xs font-bold tracking-widest animate-pulse">Loading Snapshot...</span>
            </div>
          </div>
        )}

        {!loading && !snapshot && (
          <div className="min-h-[400px] flex items-center justify-center border border-dashed border-border bg-muted/5">
            <div className="text-center space-y-2 text-muted-foreground">
              <p className="uppercase text-sm tracking-widest">No Snapshot Yet</p>
              <p className="text-xs opacity-50">首次快照會在伺服器啟動後自動生成，約需 25–30 分鐘。</p>
            </div>
          </div>
        )}

        {!loading && snapshot && <ResultsTable rows={snapshot.results} />}
      </div>
    </div>
  );
}
