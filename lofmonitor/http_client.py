"""HTTP session helpers."""

from __future__ import annotations

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class HttpClient:
    """Shared requests session that ignores system proxy settings."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            }
        )

    @retry(
        retry=retry_if_exception_type(
            (requests.RequestException, ValueError, KeyError)
        ),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def get_json(self, url: str, *, params: dict | None = None, referer: str = "") -> dict:
        headers = {}
        if referer:
            headers["Referer"] = referer
        response = self.session.get(
            url, params=params, headers=headers, timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected JSON payload from {url}")
        return payload

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=6),
        reraise=True,
    )
    def get_text(self, url: str, *, referer: str = "") -> str:
        headers = {}
        if referer:
            headers["Referer"] = referer
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.text
