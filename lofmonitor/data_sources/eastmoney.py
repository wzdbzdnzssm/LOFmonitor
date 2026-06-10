"""Eastmoney data source (primary)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from lofmonitor.http_client import HttpClient

LOF_CODE_PREFIXES = (
    "160",
    "161",
    "162",
    "163",
    "164",
    "165",
    "166",
    "167",
    "168",
    "169",
    "501",
    "502",
    "503",
)
GUZHI_TYPES = ("6", "8", "9")
UNIVERSE_CACHE_TTL = timedelta(hours=24)


@dataclass
class FundQuote:
    code: str
    name: str
    price: float
    amount: float
    market: str  # SH / SZ


@dataclass
class FundNavInfo:
    code: str
    name: str
    estimate: float | None
    nav: float | None
    estimate_date: str | None
    nav_date: str | None
    fund_type: str = ""
    is_qdii: bool = False


def market_prefix(code: str) -> str:
    return "1" if code.startswith(("5", "6")) else "0"


def to_secid(code: str) -> str:
    return f"{market_prefix(code)}.{code}"


def is_lof_exchange_code(code: str) -> bool:
    return code.startswith(LOF_CODE_PREFIXES)


class EastmoneySource:
    name = "eastmoney"

    def __init__(
        self,
        client: HttpClient | None = None,
        batch_size: int = 80,
        request_delay: float = 0.12,
    ) -> None:
        self.client = client or HttpClient()
        self.batch_size = batch_size
        self.request_delay = request_delay
        self.cache_path = (
            Path(__file__).resolve().parent.parent.parent / "data" / "lof_universe.json"
        )

    def fetch_listed_lof_codes(self) -> list[str]:
        """All A-share tradable LOF / QDII-LOF codes."""
        # Skip clist (push2.eastmoney.com is blocked on some servers)
        # Use candidate codes directly
        cached = self._load_universe_cache()
        if cached:
            return cached

        candidates = self._build_candidate_codes()
        self._save_universe_cache(candidates)
        return candidates

    def _build_candidate_codes(self) -> list[str]:
        codes: set[str] = set()

        # 场内 LOF 代码段：不能依赖 fundcode_search 名称含 LOF/QDII，
        # 例如 160644 登记为 PHGMHLGPRMB，场内简称才是「港美互联网」。
        for code, name in self._fetch_fundcode_search():
            if is_lof_exchange_code(code):
                codes.add(code)

        for fund_type in GUZHI_TYPES:
            for row in self._fetch_guzhi_rows(fund_type):
                code = row.get("bzdm")
                if not code:
                    continue
                name = (row.get("jjjc") or "").upper()
                ftype = (row.get("FType") or "").upper()
                listed = row.get("IsListTrade") == "1" or row.get("IsExchg") == "1"
                if not listed:
                    continue
                if (
                    "LOF" in name
                    or "LOF" in ftype
                    or "QDII" in ftype
                    or is_lof_exchange_code(code)
                ):
                    codes.add(code)

        return sorted(codes)

    def refresh_universe_cache(self, codes: list[str]) -> None:
        if not codes:
            return
        existing = self._load_universe_cache() or []
        merged = sorted(set(existing) | set(codes))
        self._save_universe_cache(merged)

    def _fetch_fundcode_search(self) -> list[tuple[str, str]]:
        text = self.client.get_text(
            "https://fund.eastmoney.com/js/fundcode_search.js",
            referer="https://fund.eastmoney.com/",
        )
        return re.findall(r'"(\d{6})","([^"]*?)"', text)

    def _load_universe_cache(self) -> list[str] | None:
        if not self.cache_path.exists():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            updated_at = datetime.fromisoformat(payload["updated_at"])
            if datetime.now() - updated_at > UNIVERSE_CACHE_TTL:
                return None
            codes = payload.get("codes") or []
            return sorted({str(code) for code in codes})
        except (ValueError, KeyError, json.JSONDecodeError):
            return None

    def _save_universe_cache(self, codes: list[str]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(codes),
            "codes": codes,
        }
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _fetch_guzhi_rows(self, fund_type: str) -> list[dict]:
        url = "https://api.fund.eastmoney.com/FundGuZhi/GetFundGZList"
        params = {
            "type": fund_type,
            "sort": "3",
            "orderType": "desc",
            "canbuy": "0",
            "pageIndex": "1",
            "pageSize": "20000",
            "_": int(time.time() * 1000),
        }
        payload = self.client.get_json(
            url, params=params, referer="https://fund.eastmoney.com/"
        )
        return payload["Data"]["list"]

    def fetch_nav_map(self) -> dict[str, FundNavInfo]:
        meta = self.client.get_json(
            "https://api.fund.eastmoney.com/FundGuZhi/GetFundGZList",
            params={
                "type": "8",
                "sort": "3",
                "orderType": "desc",
                "canbuy": "0",
                "pageIndex": "1",
                "pageSize": "1",
                "_": int(time.time() * 1000),
            },
            referer="https://fund.eastmoney.com/",
        )["Data"]
        estimate_date = meta.get("gxrq")
        nav_date = meta.get("gzrq")

        rows: list[dict] = []
        for fund_type in GUZHI_TYPES:
            rows.extend(self._fetch_guzhi_rows(fund_type))

        result: dict[str, FundNavInfo] = {}
        for row in rows:
            code = row.get("bzdm")
            if not code:
                continue
            estimate = _to_float(row.get("gsz"))
            nav = _to_float(row.get("gbdwjz")) or _to_float(row.get("dwjz"))
            ftype = str(row.get("FType") or "")
            is_qdii = "QDII" in ftype.upper()
            current = result.get(code)
            if current and current.nav and not nav:
                nav = current.nav
            result[code] = FundNavInfo(
                code=code,
                name=row.get("jjjc") or (current.name if current else ""),
                estimate=estimate or (current.estimate if current else None),
                nav=nav,
                estimate_date=estimate_date,
                nav_date=nav_date,
                fund_type=ftype or (current.fund_type if current else ""),
                is_qdii=is_qdii or (current.is_qdii if current else False),
            )
        return result

    def fetch_spot_quotes(
        self, codes: Iterable[str], *, sleep: bool = True
    ) -> list[FundQuote]:
        codes = list(dict.fromkeys(codes))
        if not codes:
            return []

        url = "http://push2.eastmoney.com/api/qt/ulist.np/get"
        quotes: list[FundQuote] = []
        for chunk in _chunked(codes, self.batch_size):
            secids = ",".join(to_secid(code) for code in chunk)
            params = {
                "fltt": "2",
                "fields": "f12,f14,f2,f6,f13",
                "secids": secids,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            }
            payload = None
            for attempt in range(4):
                try:
                    payload = self.client.get_json(
                        url, params=params, referer="http://quote.eastmoney.com/"
                    )
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.5 * (attempt + 1))
            if payload is None:
                continue
            diff = (payload.get("data") or {}).get("diff") or []
            for item in diff:
                price = _to_float(item.get("f2"))
                if price is None or price <= 0:
                    continue
                code = str(item.get("f12"))
                market_flag = item.get("f13")
                market = "SH" if market_flag == 1 else "SZ"
                quotes.append(
                    FundQuote(
                        code=code,
                        name=str(item.get("f14") or ""),
                        price=price,
                        amount=_to_float(item.get("f6")) or 0.0,
                        market=market,
                    )
                )
            if sleep:
                time.sleep(self.request_delay)
        return quotes

    def fetch_spot_via_clist(self) -> list[FundQuote]:
        """Authoritative LOF board list when push2 clist is reachable."""
        hosts = [
            "http://push2.eastmoney.com",
            "https://88.push2.eastmoney.com",
            "https://2.push2.eastmoney.com",
        ]
        fields = "f12,f14,f2,f6,f13"
        base_params = {
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "wbp2u": "|0|0|0|web",
            "fid": "f3",
            "fs": "b:MK0404,b:MK0405,b:MK0406,b:MK0407",
            "fields": fields,
            "pz": "100",
        }
        last_error: Exception | None = None
        for host in hosts:
            try:
                rows: list[dict] = []
                page = 1
                while True:
                    params = {**base_params, "pn": str(page)}
                    payload = self.client.get_json(
                        f"{host}/api/qt/clist/get",
                        params=params,
                        referer="https://quote.eastmoney.com/",
                    )
                    data = payload["data"]
                    diff = data.get("diff") or []
                    rows.extend(diff)
                    if len(rows) >= data["total"]:
                        break
                    page += 1
                quotes = []
                for item in rows:
                    price = _to_float(item.get("f2"))
                    if price is None or price <= 0:
                        continue
                    quotes.append(
                        FundQuote(
                            code=str(item.get("f12")),
                            name=str(item.get("f14") or ""),
                            price=price,
                            amount=_to_float(item.get("f6")) or 0.0,
                            market="SH" if item.get("f13") == 1 else "SZ",
                        )
                    )
                return quotes
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise RuntimeError("Eastmoney clist fallback failed") from last_error

    def fetch_nav_map_batch(self) -> dict[str, FundNavInfo]:
        """Fetch all fund NAVs in one request via Eastmoney batch API.

        Returns a dict mapping fund code -> FundNavInfo for LOF-relevant codes.
        """
        url = "https://fund.eastmoney.com/Data/Fund_JJJZ_Data.aspx"
        params = {"t": "1", "page": "1,50000", "js": "reData", "sort": "fcode,asc"}
        text = self.client.session.get(
            url, params=params, headers={"Referer": "https://fund.eastmoney.com/"}, timeout=self.client.timeout
        ).text
        if not text.startswith("var reData="):
            raise RuntimeError("Unexpected batch NAV response format")
        body = text[len("var reData=") :].rstrip(";")

        # Extract showday for nav_date
        showday_match = re.search(r'showday:(\[[^\]]*\])', body)
        showday = json.loads(showday_match.group(1)) if showday_match else []
        nav_date = showday[0] if showday else None

        datas_match = re.search(r'datas:(\[\[.*?\]\]),', body, re.DOTALL)
        if not datas_match:
            raise RuntimeError("Failed to extract datas from batch NAV response")
        rows = json.loads(datas_match.group(1))

        result: dict[str, FundNavInfo] = {}
        for row in rows:
            code = row[0]
            if not is_lof_exchange_code(code):
                continue
            name = row[1]
            nav = _to_float(row[5])
            estimate = _to_float(row[4])
            result[code] = FundNavInfo(
                code=code,
                name=name,
                estimate=estimate,
                nav=nav,
                estimate_date=None,
                nav_date=nav_date,
            )
        return result

    def fetch_missing_navs(self, codes: Iterable[str]) -> dict[str, FundNavInfo]:
        """Fetch latest published NAV for codes absent from bulk valuation list."""
        result: dict[str, FundNavInfo] = {}
        for code in dict.fromkeys(codes):
            try:
                payload = self.client.get_json(
                    "https://api.fund.eastmoney.com/f10/lsjz",
                    params={"fundCode": code, "pageIndex": "1", "pageSize": "1"},
                    referer="https://fund.eastmoney.com/",
                )
                rows = (payload.get("Data") or {}).get("LSJZList") or []
                if not rows:
                    continue
                nav = _to_float(rows[0].get("DWJZ"))
                if not nav:
                    continue
                result[code] = FundNavInfo(
                    code=code,
                    name="",
                    estimate=None,
                    nav=nav,
                    estimate_date=None,
                    nav_date=rows[0].get("FSRQ"),
                )
            except Exception:  # noqa: BLE001
                continue
            time.sleep(0.05)
        return result


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _to_float(value) -> float | None:
    if value in (None, "", "-", "--", "---"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
