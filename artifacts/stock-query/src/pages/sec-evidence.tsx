import React, { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileSearch,
  Loader2,
  ShieldCheck,
} from "lucide-react";

interface DocumentEvidence {
  fetchedAt?: string;
  contentType?: string | null;
  etag?: string | null;
  lastModified?: string | null;
  bytes?: number;
  sha256?: string;
  excerpt?: string;
  skipped?: boolean;
  reason?: string;
  error?: string;
}

interface Filing {
  form: string;
  accessionNumber: string;
  filingDate: string | null;
  reportDate: string | null;
  acceptanceDateTime: string | null;
  size: number | null;
  isXbrl: number | null;
  isInlineXbrl: number | null;
  primaryDocument: string;
  primaryDocumentDescription: string | null;
  filingIndexUrl: string | null;
  primaryDocumentUrl: string | null;
  documentEvidence: DocumentEvidence | null;
}

interface SecResponse {
  query: {
    symbol: string;
    cik: string;
    forms: string[];
    includeAmendments: boolean;
    includeDocument: boolean;
  };
  company: {
    cik: string;
    ticker: string | null;
    name: string;
    sic: string | null;
    sicDescription: string | null;
    exchanges: string[];
    tickers: string[];
    fiscalYearEnd: string | null;
    entityType: string | null;
  };
  filings: Filing[];
  evidenceChain: {
    authority: string;
    tickerMapUrl: string;
    submissionsUrl: string;
    submissionsFetchedAt: string;
    submissionsEtag: string | null;
    submissionsLastModified: string | null;
    responseFetchedAt: string;
    availabilityField: string;
    hashAlgorithm: string | null;
    pointInTimeRule: string;
  };
}

interface YahooSnapshot {
  symbol: string;
  shortName: string | null;
  longName: string | null;
  exchange: string | null;
  currency: string | null;
  regularMarketPrice: number | null;
  regularMarketChangePercent: number | null;
  marketCap: number | null;
  provider?: string;
  providerTimestamp?: string | null;
  fetchedAt?: string;
  pointInTimeGuarantee?: boolean;
}

const formatBytes = (value: number | null | undefined) => {
  if (value == null) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)} MB`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} KB`;
  return `${value} B`;
};

const formatDateTime = (value: string | null | undefined) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
};

const shortHash = (value: string | undefined) =>
  value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "—";

export default function SecEvidence() {
  const [symbol, setSymbol] = useState("AAPL");
  const [forms, setForms] = useState("10-K,10-Q,8-K");
  const [limit, setLimit] = useState("20");
  const [includeDocument, setIncludeDocument] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SecResponse | null>(null);
  const [yahoo, setYahoo] = useState<YahooSnapshot | null>(null);
  const [copied, setCopied] = useState(false);

  const latestEvidence = useMemo(
    () => data?.filings.find((filing) => filing.documentEvidence?.sha256) ?? null,
    [data],
  );

  const runQuery = async () => {
    const querySymbol = symbol.trim().toUpperCase();
    if (!querySymbol) return;

    setLoading(true);
    setError(null);
    setCopied(false);
    try {
      const params = new URLSearchParams({
        symbol: querySymbol,
        forms,
        limit,
        includeAmendments: "true",
        includeDocument: String(includeDocument),
        documentLimit: includeDocument ? "1" : "0",
      });

      const [secResult, yahooResult] = await Promise.allSettled([
        fetch(`/api/sec/filings?${params.toString()}`),
        fetch(`/api/stocks/info?symbol=${encodeURIComponent(querySymbol)}`),
      ]);

      if (secResult.status !== "fulfilled") throw secResult.reason;
      const secBody = await secResult.value.json();
      if (!secResult.value.ok) {
        throw new Error(secBody.error ?? "SEC query failed");
      }
      setData(secBody as SecResponse);

      if (yahooResult.status === "fulfilled" && yahooResult.value.ok) {
        setYahoo((await yahooResult.value.json()) as YahooSnapshot);
      } else {
        setYahoo(null);
      }
    } catch (queryError) {
      setData(null);
      setYahoo(null);
      setError(queryError instanceof Error ? queryError.message : "Query failed");
    } finally {
      setLoading(false);
    }
  };

  const copyEvidence = async () => {
    if (!data) return;
    const payload = {
      company: data.company,
      evidenceChain: data.evidenceChain,
      filings: data.filings.map((filing) => ({
        form: filing.form,
        accessionNumber: filing.accessionNumber,
        filingDate: filing.filingDate,
        reportDate: filing.reportDate,
        acceptanceDateTime: filing.acceptanceDateTime,
        filingIndexUrl: filing.filingIndexUrl,
        primaryDocumentUrl: filing.primaryDocumentUrl,
        documentEvidence: filing.documentEvidence,
      })),
      yahooObservation: yahoo,
    };
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-mono p-4 md:p-8 selection:bg-primary selection:text-primary-foreground">
      <div className="max-w-7xl mx-auto space-y-8">
        <header className="border-b border-border pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight uppercase">SEC_EVIDENCE_CHAIN</h1>
            <p className="text-muted-foreground text-sm mt-1 uppercase">
              Official filings · availability time · source hash
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs uppercase font-bold text-success">
            <ShieldCheck className="h-4 w-4" /> SEC authoritative source
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <aside className="lg:col-span-4 space-y-6">
            <div className="space-y-4 bg-muted/20 p-4 border border-border">
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  股票代号或 CIK / Symbol or CIK
                </label>
                <Input
                  value={symbol}
                  onChange={(event) => setSymbol(event.target.value.toUpperCase())}
                  onKeyDown={(event) => event.key === "Enter" && runQuery()}
                  className="font-mono text-lg font-bold bg-transparent border-border uppercase h-12"
                  placeholder="AAPL"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  文件类型 / Forms
                </label>
                <Input
                  value={forms}
                  onChange={(event) => setForms(event.target.value.toUpperCase())}
                  className="font-mono bg-transparent border-border"
                  placeholder="10-K,10-Q,8-K"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  返回数量 / Limit
                </label>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={limit}
                  onChange={(event) => setLimit(event.target.value)}
                  className="font-mono bg-transparent border-border"
                />
              </div>

              <div className="flex items-start gap-3 border border-border p-3 bg-muted/10">
                <Checkbox
                  id="include-document"
                  checked={includeDocument}
                  onCheckedChange={(checked) => setIncludeDocument(checked === true)}
                />
                <label htmlFor="include-document" className="text-xs leading-relaxed cursor-pointer">
                  下载最近一份主文档并生成 SHA-256；用于证明本次实际抓到的原文内容。
                </label>
              </div>

              <Button
                onClick={runQuery}
                disabled={loading || !symbol.trim()}
                className="w-full font-mono font-bold uppercase tracking-widest h-12"
              >
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileSearch className="mr-2 h-4 w-4" />}
                查询 / Query
              </Button>
            </div>

            <div className="border border-border p-4 bg-muted/10 space-y-3 text-xs">
              <div className="flex items-center gap-2 font-bold uppercase text-success">
                <CheckCircle2 className="h-4 w-4" /> SEC：正式证据
              </div>
              <p className="text-muted-foreground leading-relaxed">
                filing acceptance time 是公开可用时间；accession、官方 URL 与内容哈希共同构成可复核证据链。
              </p>
            </div>

            <div className="border border-amber-500/30 p-4 bg-amber-500/5 space-y-3 text-xs">
              <div className="flex items-center gap-2 font-bold uppercase text-amber-500">
                <AlertTriangle className="h-4 w-4" /> Yahoo：辅助观察
              </div>
              <p className="text-muted-foreground leading-relaxed">
                适合快速行情、交易所、名称与市值补充；不是 SEC 文件的替代来源，也不能仅凭 Yahoo 响应重建过去某时点看到的页面。
              </p>
            </div>
          </aside>

          <main className="lg:col-span-8 space-y-6">
            {!loading && !data && !error && (
              <div className="min-h-[420px] flex items-center justify-center border border-dashed border-border bg-muted/5">
                <div className="text-center space-y-2 text-muted-foreground">
                  <FileSearch className="h-8 w-8 mx-auto opacity-50" />
                  <p className="uppercase text-sm tracking-widest">Awaiting SEC Query</p>
                  <p className="text-xs opacity-60">Input a ticker or CIK to build the evidence chain.</p>
                </div>
              </div>
            )}

            {loading && (
              <div className="min-h-[420px] flex items-center justify-center border border-border bg-muted/10">
                <div className="flex flex-col items-center gap-4 text-primary">
                  <Loader2 className="h-8 w-8 animate-spin" />
                  <span className="uppercase text-xs font-bold tracking-widest animate-pulse">
                    Fetching SEC Data...
                  </span>
                </div>
              </div>
            )}

            {error && (
              <div className="p-4 bg-destructive/10 border border-destructive/30 text-destructive text-sm break-all">
                ERR: {error}
              </div>
            )}

            {!loading && data && (
              <>
                <section className="border border-border bg-muted/10 p-4 space-y-4">
                  <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-xl font-bold">{data.company.name}</h2>
                        {data.company.ticker && <Badge variant="outline">{data.company.ticker}</Badge>}
                        <Badge variant="outline">CIK {data.company.cik}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-2">
                        {data.company.sicDescription ?? "SIC unavailable"}
                        {data.company.exchanges.length > 0 ? ` · ${data.company.exchanges.join(", ")}` : ""}
                      </p>
                    </div>
                    <Button variant="outline" onClick={copyEvidence} className="font-mono text-xs">
                      {copied ? <CheckCircle2 className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
                      {copied ? "Copied" : "Copy Evidence JSON"}
                    </Button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                    <div className="border border-border p-3">
                      <div className="text-muted-foreground uppercase mb-1">SEC availability</div>
                      <div className="font-bold">
                        {formatDateTime(data.filings[0]?.acceptanceDateTime)}
                      </div>
                    </div>
                    <div className="border border-border p-3">
                      <div className="text-muted-foreground uppercase mb-1">Locally fetched</div>
                      <div className="font-bold">{formatDateTime(data.evidenceChain.responseFetchedAt)}</div>
                    </div>
                    <div className="border border-border p-3">
                      <div className="text-muted-foreground uppercase mb-1">Latest SHA-256</div>
                      <div className="font-bold break-all" title={latestEvidence?.documentEvidence?.sha256}>
                        {shortHash(latestEvidence?.documentEvidence?.sha256)}
                      </div>
                    </div>
                  </div>
                </section>

                {yahoo && (
                  <section className="border border-border p-4 bg-muted/5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-xs uppercase text-muted-foreground">Yahoo observation snapshot</div>
                        <div className="mt-1 font-bold">
                          {yahoo.shortName ?? yahoo.symbol} · {yahoo.exchange ?? "—"} · {yahoo.currency ?? "—"}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-bold">
                          {yahoo.regularMarketPrice == null ? "—" : yahoo.regularMarketPrice.toFixed(2)}
                        </div>
                        <div className="text-[10px] text-muted-foreground">
                          Provider time: {formatDateTime(yahoo.providerTimestamp)} · Fetched: {formatDateTime(yahoo.fetchedAt)}
                        </div>
                      </div>
                    </div>
                  </section>
                )}

                <section className="overflow-x-auto border border-border">
                  <Table className="font-mono text-xs whitespace-nowrap">
                    <TableHeader className="bg-muted/10">
                      <TableRow className="border-border hover:bg-transparent">
                        <TableHead>Form</TableHead>
                        <TableHead>Filed</TableHead>
                        <TableHead>Report period</TableHead>
                        <TableHead>Accepted / Available</TableHead>
                        <TableHead>Accession</TableHead>
                        <TableHead className="text-right">Size</TableHead>
                        <TableHead>Evidence</TableHead>
                        <TableHead>Source</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.filings.map((filing) => (
                        <TableRow key={filing.accessionNumber} className="border-border hover:bg-muted/10">
                          <TableCell className="font-bold">{filing.form}</TableCell>
                          <TableCell>{filing.filingDate ?? "—"}</TableCell>
                          <TableCell>{filing.reportDate ?? "—"}</TableCell>
                          <TableCell>{formatDateTime(filing.acceptanceDateTime)}</TableCell>
                          <TableCell className="text-muted-foreground">{filing.accessionNumber}</TableCell>
                          <TableCell className="text-right">{formatBytes(filing.size)}</TableCell>
                          <TableCell>
                            {filing.documentEvidence?.sha256 ? (
                              <Badge
                                variant="outline"
                                className="text-success border-success/30"
                                title={filing.documentEvidence.sha256}
                              >
                                SHA {shortHash(filing.documentEvidence.sha256)}
                              </Badge>
                            ) : filing.documentEvidence?.error ? (
                              <Badge variant="outline" className="text-destructive border-destructive/30">
                                HASH ERR
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">metadata only</span>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex gap-3">
                              {filing.filingIndexUrl && (
                                <a
                                  href={filing.filingIndexUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-primary hover:underline inline-flex items-center gap-1"
                                >
                                  Index <ExternalLink className="h-3 w-3" />
                                </a>
                              )}
                              {filing.primaryDocumentUrl && (
                                <a
                                  href={filing.primaryDocumentUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-primary hover:underline inline-flex items-center gap-1"
                                >
                                  Document <ExternalLink className="h-3 w-3" />
                                </a>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </section>

                {latestEvidence?.documentEvidence?.excerpt && (
                  <section className="border border-border bg-muted/5 p-4 space-y-3">
                    <div className="flex flex-wrap justify-between gap-3 text-xs">
                      <span className="font-bold uppercase">Fetched document excerpt</span>
                      <span className="text-muted-foreground">
                        {formatBytes(latestEvidence.documentEvidence.bytes)} · {latestEvidence.form} · {latestEvidence.accessionNumber}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">
                      {latestEvidence.documentEvidence.excerpt}
                    </p>
                  </section>
                )}

                <section className="border border-border p-3 bg-muted/10 text-[10px] text-muted-foreground space-y-1 break-all">
                  <div>Authority: {data.evidenceChain.authority}</div>
                  <div>Submissions source: {data.evidenceChain.submissionsUrl}</div>
                  <div>Submissions fetched: {formatDateTime(data.evidenceChain.submissionsFetchedAt)}</div>
                  <div>PIT rule: {data.evidenceChain.pointInTimeRule}</div>
                </section>
              </>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
