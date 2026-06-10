"""Sina finance data source (spot backup)."""

from __future__ import annotations

import re
import time
from typing import Iterable

from lofmonitor.data_sources.eastmoney import FundQuote
from lofmonitor.http_client import HttpClient


class SinaSource:
    name = "sina"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def fetch_spot_quotes(self, codes: Iterable[str]) -> list[FundQuote]:
        codes = list(dict.fromkeys(codes))
        quotes: list[FundQuote] = []
        for chunk in _chunked(codes, 60):
            symbols = ",".join(_to_symbol(code) for code in chunk)
            text = self.client.get_text(
                f"https://hq.sinajs.cn/list={symbols}",
                referer="https://finance.sina.com.cn/",
            )
            quotes.extend(_parse_sina_text(text))
            time.sleep(0.1)
        return quotes


def _to_symbol(code: str) -> str:
    prefix = "sh" if code.startswith(("5", "6")) else "sz"
    return f"{prefix}{code}"


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _parse_sina_text(text: str) -> list[FundQuote]:
    quotes: list[FundQuote] = []
    for line in text.splitlines():
        match = re.match(r'var hq_str_(sh|sz)(\d{6})="([^"]*)"', line.strip())
        if not match:
            continue
        market_prefix, code, body = match.groups()
        if not body:
            continue
        parts = body.split(",")
        if len(parts) < 10:
            continue
        name = parts[0]
        try:
            price = float(parts[3])
            amount = float(parts[9])
        except ValueError:
            continue
        quotes.append(
            FundQuote(
                code=code,
                name=name,
                price=price,
                amount=amount,
                market="SH" if market_prefix == "sh" else "SZ",
            )
        )
    return quotes
