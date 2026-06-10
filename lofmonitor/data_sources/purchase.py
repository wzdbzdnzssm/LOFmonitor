"""Fund purchase status and daily limit (Eastmoney primary)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from lofmonitor.http_client import HttpClient

PURCHASE_CACHE_TTL = timedelta(hours=24)
UNLIMITED_THRESHOLD = 1_000_000_000


@dataclass
class FundPurchaseInfo:
    code: str
    name: str
    purchase_status: str
    redeem_status: str
    daily_limit_raw: float | None
    purchase_label: str


class EastmoneyPurchaseSource:
    name = "eastmoney_purchase"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()
        self.cache_path = (
            Path(__file__).resolve().parent.parent.parent
            / "data"
            / "purchase_status.json"
        )

    def fetch_purchase_map(self) -> dict[str, FundPurchaseInfo]:
        cached = self._load_cache()
        if cached is not None:
            return cached

        response = self.client.session.get(
            "https://fund.eastmoney.com/Data/Fund_JJJZ_Data.aspx",
            params={
                "t": "8",
                "page": "1,50000",
                "js": "reData",
                "sort": "fcode,asc",
            },
            headers={
                "User-Agent": self.client.session.headers.get("User-Agent", ""),
                "Referer": "https://fund.eastmoney.com/Fund_sgzt_bzdm.html",
            },
            timeout=self.client.timeout,
        )
        response.raise_for_status()
        text = response.text

        pattern = re.compile(
            r'\["(\d{6})","([^"]*)","([^"]*)","([^"]*)","([^"]*)",'
            r'"([^"]*)","([^"]*)","([^"]*)","([^"]*)","([^"]*)",'
            r'"([^"]*)","([^"]*)","([^"]*)"\]'
        )
        result: dict[str, FundPurchaseInfo] = {}
        for match in pattern.finditer(text):
            code = match.group(1)
            purchase_status = match.group(6) or "未知"
            redeem_status = match.group(7) or "未知"
            daily_limit_raw = _to_float(match.group(10))
            result[code] = FundPurchaseInfo(
                code=code,
                name=match.group(2),
                purchase_status=purchase_status,
                redeem_status=redeem_status,
                daily_limit_raw=daily_limit_raw,
                purchase_label=format_purchase_label(daily_limit_raw, purchase_status),
            )

        if not result:
            raise RuntimeError("Failed to parse Eastmoney purchase status data")

        self._save_cache(result)
        return result

    def _load_cache(self) -> dict[str, FundPurchaseInfo] | None:
        if not self.cache_path.exists():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            updated_at = datetime.fromisoformat(payload["updated_at"])
            if datetime.now() - updated_at > PURCHASE_CACHE_TTL:
                return None
            return {
                code: FundPurchaseInfo(
                    code=code,
                    name=item.get("name", ""),
                    purchase_status=item.get("purchase_status", "未知"),
                    redeem_status=item.get("redeem_status", "未知"),
                    daily_limit_raw=item.get("daily_limit_raw"),
                    purchase_label=item.get(
                        "purchase_label",
                        format_purchase_label(
                            item.get("daily_limit_raw"),
                            item.get("purchase_status", ""),
                        ),
                    ),
                )
                for code, item in payload["records"].items()
            }
        except (ValueError, KeyError, json.JSONDecodeError, TypeError):
            return None

    def _save_cache(self, records: dict[str, FundPurchaseInfo]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(records),
            "records": {
                code: {
                    "name": info.name,
                    "purchase_status": info.purchase_status,
                    "redeem_status": info.redeem_status,
                    "daily_limit_raw": info.daily_limit_raw,
                    "purchase_label": info.purchase_label,
                }
                for code, info in records.items()
            },
        }
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def format_purchase_label(
    daily_limit: float | None, purchase_status: str = ""
) -> str:
    """申购展示：暂停申购 / 限购xx元 / 不限购。"""
    status = purchase_status or ""
    if "暂停" in status and "申购" in status:
        return "暂停申购"

    if daily_limit is not None and 0 < daily_limit < UNLIMITED_THRESHOLD:
        if daily_limit == int(daily_limit):
            return f"限购{int(daily_limit)}元"
        return f"限购{daily_limit:g}元"

    return "不限购"


def _to_float(value) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
