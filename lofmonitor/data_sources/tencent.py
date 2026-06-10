"""Tencent finance data source (spot quotes, no IP block)."""

from __future__ import annotations

import time
import urllib.request
from typing import Iterable

from lofmonitor.data_sources.eastmoney import FundQuote
from lofmonitor.http_client import HttpClient


class TencentSource:
    name = "tencent"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def fetch_spot_quotes(self, codes: Iterable[str]) -> list[FundQuote]:
        codes = list(dict.fromkeys(codes))
        quotes: list[FundQuote] = []
        for chunk in _chunked(codes, 60):
            quotes.extend(_fetch_tencent_batch(chunk))
            time.sleep(0.1)
        return quotes


def _to_symbol(code: str) -> str:
    prefix = "sh" if code.startswith(("5", "6")) else "sz"
    return f"{prefix}{code}"


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _fetch_tencent_batch(codes: list[str]) -> list[FundQuote]:
    symbols = ",".join(_to_symbol(code) for code in codes)
    url = f"https://qt.gtimg.cn/q={symbols}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")

    quotes: list[FundQuote] = []
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]
        price = _to_float(vals[3])
        if price is None or price <= 0:
            continue
        amount = _to_float(vals[37])
        quotes.append(
            FundQuote(
                code=code,
                name=vals[1],
                price=price,
                amount=(amount * 10000) if amount else 0.0,
                market="SH" if code.startswith(("5", "6")) else "SZ",
            )
        )
    return quotes


def _to_float(value: str) -> float | None:
    if value in (None, "", "-", "--", "---"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
