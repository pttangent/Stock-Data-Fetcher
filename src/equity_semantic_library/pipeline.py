from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .config import Settings
from .db import Database
from .providers.sec import SECTION_EXTRACTOR_VERSION, SecProvider, extract_sections
from .providers.yahoo import YahooProvider
from .util import normalize_symbol, utc_now, yahoo_symbol


class IngestionPipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        database: Database | None = None,
        sec_provider: SecProvider | None = None,
        yahoo_provider: YahooProvider | None = None,
    ):
        self.settings = settings
        self.db = database or Database(settings.db_path)
        self.sec = sec_provider
        self.yahoo = yahoo_provider or YahooProvider(settings)

    def initialize(self) -> None:
        self.db.initialize()

    def ingest(
        self,
        symbols: list[str],
        *,
        use_sec: bool = True,
        use_yahoo: bool = True,
        refresh: bool = False,
    ) -> str:
        if not use_sec and not use_yahoo:
            raise ValueError("At least one source must be enabled")
        normalized = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols))
        if use_sec and self.sec is None:
            self.sec = SecProvider(self.settings)
        config = {
            "use_sec": use_sec,
            "use_yahoo": use_yahoo,
            "refresh": refresh,
            "db_path": str(self.settings.db_path),
            "data_dir": str(self.settings.data_dir),
        }
        run_id = self.db.start_run(config, normalized)
        for symbol in normalized:
            self.ingest_symbol(
                run_id,
                symbol,
                use_sec=use_sec,
                use_yahoo=use_yahoo,
                refresh=refresh,
            )
        self.db.finish_run(run_id)
        return run_id

    def ingest_symbol(
        self,
        run_id: str,
        symbol: str,
        *,
        use_sec: bool = True,
        use_yahoo: bool = True,
        refresh: bool = False,
    ) -> None:
        self.db.set_queue_status(run_id, symbol, "running", increment_attempt=True)
        sec_identity_success = False
        sec_document_success = False
        yahoo_success = False
        issuer_id: str | None = None
        security_id: str | None = None
        sec_error: str | None = None
        yahoo_error: str | None = None

        if use_sec:
            assert self.sec is not None
            try:
                match = self.sec.lookup_cik(symbol)
                if match is None:
                    raise LookupError(f"No SEC ticker/CIK mapping for {symbol}")
                submissions = self.sec.get_submissions(match.cik, refresh=refresh)
                issuer_id = self.db.upsert_issuer(
                    cik=match.cik,
                    legal_name=submissions.get("name") or match.title,
                    identity_status="sec_resolved",
                    sic=submissions.get("sic"),
                    sic_description=submissions.get("sicDescription"),
                    state_of_incorporation=submissions.get("stateOfIncorporation"),
                )
                exchanges = submissions.get("exchanges") or []
                security_id = self.db.upsert_security(
                    issuer_id=issuer_id,
                    symbol=symbol,
                    yahoo_symbol=yahoo_symbol(symbol),
                    exchange=exchanges[0] if exchanges else None,
                    status="active",
                )
                self.db.insert_source_record(
                    security_id=security_id,
                    source="sec_submissions",
                    source_key=f"CIK{match.cik}",
                    observed_at=utc_now(),
                    payload=submissions,
                    status="ok",
                )
                sec_identity_success = True

                metadata = self.sec.select_latest_annual_filing(submissions)
                if metadata is None:
                    raise LookupError(f"No exact 10-K, 20-F, or 40-F found for {symbol}")
                self.db.upsert_source_document(
                    issuer_id=issuer_id,
                    metadata=metadata,
                    status="metadata_only",
                )
                try:
                    content = self.sec.fetch_filing_content(symbol, metadata)
                    path, content_hash, media_type = self.sec.persist_filing(content)
                    document_id = self.db.upsert_source_document(
                        issuer_id=issuer_id,
                        metadata=metadata,
                        local_path=str(path),
                        content_hash=content_hash,
                        media_type=media_type,
                        retrieval_method=content.retrieval_method,
                        status="downloaded",
                    )
                    self.db.replace_sections(
                        document_id,
                        extract_sections(content.text),
                        SECTION_EXTRACTOR_VERSION,
                    )
                    sec_document_success = True
                except Exception as filing_exc:
                    sec_error = str(filing_exc)
                    self.db.record_error(
                        run_id=run_id,
                        symbol=symbol,
                        stage="filing_content",
                        source="sec_edgar",
                        error=filing_exc,
                        retryable=True,
                        context={"metadata": asdict(metadata)},
                    )
            except Exception as exc:
                sec_error = str(exc)
                stage = "filing_metadata" if sec_identity_success else "sec_identity"
                self.db.record_error(
                    run_id=run_id,
                    symbol=symbol,
                    stage=stage,
                    source="sec_edgar",
                    error=exc,
                    retryable=True,
                )

        if use_yahoo:
            try:
                profile = self.yahoo.fetch_profile(symbol, refresh=refresh)
                data = profile.payload
                if issuer_id is None:
                    issuer_id = self.db.upsert_issuer(
                        cik=None,
                        legal_name=data.get("longName") or data.get("shortName"),
                        identity_status="provisional",
                        country=data.get("country"),
                        provisional_key=symbol,
                    )
                if security_id is None:
                    quote_type = data.get("quoteType")
                    security_id = self.db.upsert_security(
                        issuer_id=issuer_id,
                        symbol=symbol,
                        yahoo_symbol=profile.yahoo_symbol,
                        exchange=data.get("exchange"),
                        quote_type=quote_type,
                        security_type=quote_type,
                        currency=data.get("currency"),
                        is_etf=str(quote_type).upper() == "ETF",
                        status="provisional" if not sec_identity_success else "active",
                    )
                record_id = self.db.insert_source_record(
                    security_id=security_id,
                    source="yfinance",
                    source_key=profile.yahoo_symbol,
                    observed_at=profile.observed_at,
                    available_at=profile.observed_at,
                    payload=data,
                    status="ok",
                )
                self.db.insert_yahoo_profile(security_id, record_id, profile)
                yahoo_success = True
            except Exception as exc:
                yahoo_error = str(exc)
                self.db.record_error(
                    run_id=run_id,
                    symbol=symbol,
                    stage="company_profile",
                    source="yfinance",
                    error=exc,
                    retryable=True,
                )

        if use_sec and use_yahoo:
            if sec_document_success and yahoo_success:
                status = "completed"
            elif sec_identity_success or yahoo_success:
                status = "partial" if sec_identity_success else "review_required"
            else:
                status = "failed"
        elif use_sec:
            if sec_document_success:
                status = "completed"
            elif sec_identity_success:
                status = "partial"
            else:
                status = "failed"
        else:
            status = "review_required" if yahoo_success else "failed"

        error = "; ".join(filter(None, [sec_error, yahoo_error])) or None
        self.db.set_queue_status(run_id, symbol, status, error=error)


def load_symbols(path: str | Path, symbol_column: str = "symbol") -> list[str]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".txt", ".list"}:
        values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    elif suffix == ".csv":
        import csv

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return []
            lookup = {name.lower(): name for name in reader.fieldnames}
            actual = lookup.get(symbol_column.lower()) or lookup.get("ticker")
            if actual is None:
                raise ValueError(f"No {symbol_column!r} or 'ticker' column in {path}")
            values = [row.get(actual, "") for row in reader]
    elif suffix == ".json":
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            values = [item.get(symbol_column) if isinstance(item, dict) else item for item in raw]
        else:
            raise ValueError("JSON input must be an array")
    elif suffix in {".parquet", ".pq"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("Install the parquet extra: pip install '.[parquet]'") from exc
        try:
            frame = pd.read_parquet(path)
        except ImportError as exc:
            raise RuntimeError("Install the parquet extra: pip install '.[parquet]'") from exc
        columns = {str(name).lower(): name for name in frame.columns}
        actual = columns.get(symbol_column.lower()) or columns.get("ticker")
        if actual is None:
            raise ValueError(f"No {symbol_column!r} or 'ticker' column in {path}")
        values = frame[actual].tolist()
    else:
        raise ValueError(f"Unsupported input type: {path.suffix}")
    return [
        normalize_symbol(str(value)) for value in values if value is not None and str(value).strip()
    ]
