"""Premium calculation and data aggregation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from lofmonitor.config import AppConfig
from lofmonitor.data_sources.eastmoney import EastmoneySource, FundNavInfo, FundQuote
from lofmonitor.data_sources.jisilu import JisiluSource
from lofmonitor.data_sources.purchase import EastmoneyPurchaseSource
from lofmonitor.data_sources.sina import SinaSource
from lofmonitor.data_sources.tencent import TencentSource
from lofmonitor.http_client import HttpClient

logger = logging.getLogger(__name__)


@dataclass
class PremiumRecord:
    code: str
    name: str
    price: float
    reference: float
    reference_type: str
    premium_pct: float
    amount: float
    market: str
    data_source: str
    purchase_label: str = "不限购"


class LofPremiumService:
    def __init__(self, config: AppConfig, client: HttpClient | None = None) -> None:
        self.config = config
        self.client = client or HttpClient()
        self.eastmoney = EastmoneySource(
            self.client,
            batch_size=config.data.batch_size,
            request_delay=config.data.request_delay,
        )
        self.sina = SinaSource(self.client)
        self.tencent = TencentSource(self.client)
        self.jisilu = JisiluSource(self.client)
        self.purchase = EastmoneyPurchaseSource(self.client)

    def collect(self) -> pd.DataFrame:
        try:
            records = self._collect_from_eastmoney()
            if records:
                return self._to_dataframe(records, "eastmoney+sina")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Eastmoney pipeline failed: %s", exc)

        logger.warning("Falling back to Jisilu data source")
        records = self._collect_from_jisilu()
        return self._to_dataframe(records, "jisilu")

    def top_premium(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter: |premium| > 10% and purchasable (not suspended)."""
        if df.empty:
            return df
        # Absolute premium > 10%
        df = df[df["premium_pct"].abs() > 10].copy()
        # Must be purchasable (not 暂停申购)
        df = df[df["purchase_label"] != "暂停申购"].copy()
        # Sort by absolute premium desc
        return df.sort_values("premium_pct", key=lambda s: s.abs(), ascending=False)

    def _collect_from_eastmoney(self) -> list[PremiumRecord]:
        nav_map = self.eastmoney.fetch_nav_map_batch()
        purchase_map = self._fetch_purchase_map()
        codes = self.eastmoney.fetch_listed_lof_codes()
        logger.info("LOF universe size: %s", len(codes))
        quotes = self._fetch_spot_quotes(codes)
        logger.info("Fetched spot quotes: %s", len(quotes))
        quote_map = {quote.code: quote for quote in quotes}

        missing_nav_codes = [
            quote.code
            for quote in quotes
            if not nav_map.get(quote.code) or not nav_map[quote.code].nav
        ]
        if missing_nav_codes:
            fallback_navs = self.eastmoney.fetch_missing_navs(missing_nav_codes)
            nav_map.update(fallback_navs)
            logger.info("Filled NAV via fallback API: %s", len(fallback_navs))

        records: list[PremiumRecord] = []
        for code, quote in quote_map.items():
            nav_info = nav_map.get(code)
            reference, ref_type = _pick_reference(nav_info)
            if reference is None or reference <= 0:
                continue
            if quote.price <= 0 or quote.amount <= 0:
                continue
            premium = (quote.price / reference - 1) * 100
            purchase_info = purchase_map.get(code)
            records.append(
                PremiumRecord(
                    code=code,
                    name=quote.name or (nav_info.name if nav_info else ""),
                    price=quote.price,
                    reference=reference,
                    reference_type=ref_type,
                    premium_pct=round(premium, 2),
                    amount=quote.amount,
                    market=quote.market,
                    data_source="eastmoney",
                    purchase_label=(
                        purchase_info.purchase_label if purchase_info else "不限购"
                    ),
                )
            )
        if not records:
            raise RuntimeError("No premium records matched from Eastmoney pipeline")
        self.eastmoney.refresh_universe_cache(list(quote_map.keys()))
        logger.info(
            "Premium matched %s/%s quotes (skipped %s without nav)",
            len(records),
            len(quote_map),
            len(quote_map) - len(records),
        )
        return records

    def _fetch_spot_quotes(self, codes: list[str]) -> list[FundQuote]:
        quotes: list[FundQuote] = []
        
        # Try Tencent first (no IP block, reliable)
        try:
            quotes = self.tencent.fetch_spot_quotes(codes)
            if len(quotes) >= max(20, len(codes) // 10):
                return quotes
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tencent quotes failed: %s", exc)
        
        # Fallback to Eastmoney
        try:
            quotes = self.eastmoney.fetch_spot_quotes(codes)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Eastmoney batch quotes failed: %s", exc)

        if len(quotes) < max(20, len(codes) // 10):
            try:
                clist_quotes = self.eastmoney.fetch_spot_via_clist()
                if clist_quotes:
                    return clist_quotes
            except Exception as exc:  # noqa: BLE001
                logger.warning("Eastmoney clist failed: %s", exc)

        quote_codes = {quote.code for quote in quotes}
        missing = [code for code in codes if code not in quote_codes]
        if missing:
            try:
                quotes.extend(self.sina.fetch_spot_quotes(missing))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Sina spot quotes failed: %s", exc)
        return quotes

    def _fetch_purchase_map(self):
        try:
            return self.purchase.fetch_purchase_map()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Eastmoney purchase map failed: %s", exc)
            return {}

    def _collect_from_jisilu(self) -> list[PremiumRecord]:
        rows = self.jisilu.fetch_records()
        records: list[PremiumRecord] = []
        for row in rows:
            reference = row.nav if row.nav and row.nav > 0 else row.estimate
            ref_type = "nav" if row.nav and row.nav > 0 else "estimate"
            premium_pct = (
                row.nav_premium_pct
                if row.nav_premium_pct is not None
                else row.premium_pct
            )
            if reference is None or reference <= 0:
                continue
            records.append(
                PremiumRecord(
                    code=row.code,
                    name=row.name,
                    price=row.price,
                    reference=reference,
                    reference_type=ref_type,
                    premium_pct=round(premium_pct, 2),
                    amount=row.amount,
                    market="SH" if row.code.startswith(("5", "6")) else "SZ",
                    data_source="jisilu",
                    purchase_label=row.purchase_label or "不限购",
                )
            )
        if not records:
            raise RuntimeError("Jisilu fallback returned no records")
        return records

    @staticmethod
    def _to_dataframe(records: list[PremiumRecord], source: str) -> pd.DataFrame:
        df = pd.DataFrame(
            [
                {
                    "code": item.code,
                    "name": item.name,
                    "price": item.price,
                    "reference": item.reference,
                    "reference_type": item.reference_type,
                    "premium_pct": item.premium_pct,
                    "amount": item.amount,
                    "market": item.market,
                    "data_source": item.data_source or source,
                    "purchase_label": item.purchase_label,
                }
                for item in records
            ]
        )
        return df


def _pick_reference(nav_info: FundNavInfo | None) -> tuple[float | None, str]:
    if nav_info is None:
        return None, ""
    # LOF 套利惯例：优先用最新公布单位净值（T-1），QDII 尤其不能用盘中估值。
    if nav_info.nav and nav_info.nav > 0:
        return nav_info.nav, "nav"
    if nav_info.estimate and nav_info.estimate > 0:
        return nav_info.estimate, "estimate"
    return None, ""


def format_top_message(
    df: pd.DataFrame,
    generated_at: datetime | None = None,
    total_count: int | None = None,
) -> str:
    now = generated_at or datetime.now()
    lines = [
        f"LOF套利机会 | {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "筛选条件: |溢价率| > 10% 且 可申购",
    ]
    if total_count is not None:
        lines.append(f"覆盖场内 LOF/QDII-LOF: {total_count} 只")
    lines.append("")
    if df.empty:
        lines.append("暂无符合条件的套利机会")
        return "\n".join(lines)

    for idx, row in enumerate(df.itertuples(index=False), start=1):
        amount_wan = row.amount / 10_000
        ref_label = "公布净值" if row.reference_type == "nav" else "估算"
        premium_sign = "溢价" if row.premium_pct >= 0 else "折价"
        lines.append(
            f"{idx}. {row.code} {row.name} | {premium_sign} {row.premium_pct:+.2f}% | "
            f"价 {row.price:.4f} | {ref_label} {row.reference:.4f} | "
            f"成交额 {amount_wan:.1f}万 | {row.market} | {row.purchase_label}"
        )
    source = df["data_source"].iloc[0] if "data_source" in df.columns else "unknown"
    lines.extend(["", f"数据源: {source}"])
    return "\n".join(lines)
