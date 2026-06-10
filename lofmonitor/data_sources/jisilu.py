"""Jisilu data source (premium backup)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from lofmonitor.http_client import HttpClient
from lofmonitor.data_sources.purchase import format_purchase_label


@dataclass
class JisiluRecord:
    code: str
    name: str
    price: float
    nav: float | None
    estimate: float | None
    premium_pct: float
    nav_premium_pct: float | None
    amount: float
    purchase_label: str = "不限购"


class JisiluSource:
    name = "jisilu"

    ENDPOINTS = (
        "index_lof_list",
        "stock_lof_list",
    )

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def fetch_records(self) -> list[JisiluRecord]:
        records: dict[str, JisiluRecord] = {}
        for endpoint in self.ENDPOINTS:
            rows = self._fetch_endpoint(endpoint)
            for row in rows:
                records[row.code] = row
        return list(records.values())

    def _fetch_endpoint(self, endpoint: str) -> list[JisiluRecord]:
        timestamp = int(time.time() * 1000)
        url = f"https://www.jisilu.cn/data/lof/{endpoint}/"
        params = {
            "_jsl": f"LST_t={timestamp}",
            "rp": "500",
            "only_owned": "",
        }
        payload = self.client.get_json(
            url, params=params, referer="https://www.jisilu.cn/data/lof/"
        )
        rows = payload.get("rows") or []
        records: list[JisiluRecord] = []
        for row in rows:
            cell = row.get("cell") or {}
            code = str(cell.get("fund_id") or "")
            if not code:
                continue
            price = _to_float(cell.get("price"))
            if price is None:
                continue
            estimate = _to_float(cell.get("estimate_value"))
            nav = _to_float(cell.get("fund_nav"))
            discount = _to_float(cell.get("discount_rt"))
            nav_discount = _to_float(cell.get("nav_discount_rt"))
            if nav_discount is not None:
                premium_pct = -nav_discount
            elif discount is not None:
                premium_pct = -discount
            elif nav and nav > 0:
                premium_pct = (price / nav - 1) * 100
            elif estimate and estimate > 0:
                premium_pct = (price / estimate - 1) * 100
            else:
                continue
            purchase_status = str(cell.get("apply_status") or "")
            purchase_label = format_purchase_label(
                _to_float(cell.get("amount_incr")),
                purchase_status,
            )
            if purchase_label == "不限购":
                tips = str(cell.get("amount_incr_tips") or "").strip()
                if "暂停" in purchase_status:
                    purchase_label = "暂停申购"
                elif tips.startswith("限购"):
                    purchase_label = tips.replace("/日", "")
            records.append(
                JisiluRecord(
                    code=code,
                    name=str(cell.get("fund_nm") or ""),
                    price=price,
                    nav=nav,
                    estimate=estimate,
                    premium_pct=premium_pct,
                    nav_premium_pct=-nav_discount if nav_discount is not None else None,
                    amount=_to_float(cell.get("amount")) or 0.0,
                    purchase_label=purchase_label,
                )
            )
        return records


def _to_float(value) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
