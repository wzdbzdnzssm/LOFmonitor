"""Notification channels."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import requests

from lofmonitor.config import PushConfig
from lofmonitor.http_client import HttpClient

logger = logging.getLogger(__name__)


class Notifier(ABC):
    @abstractmethod
    def send(self, title: str, content: str) -> None:
        raise NotImplementedError


class ConsoleNotifier(Notifier):
    def send(self, title: str, content: str) -> None:
        print(f"\n===== {title} =====\n{content}\n")


class PushPlusNotifier(Notifier):
    def __init__(self, token: str, client: HttpClient | None = None) -> None:
        self.token = token
        self.client = client or HttpClient()

    def send(self, title: str, content: str) -> None:
        if not self.token:
            raise ValueError("PushPlus token is empty")
        payload = {
            "token": self.token,
            "title": title,
            "content": content.replace("\n", "<br/>"),
            "template": "html",
        }
        response = self.client.session.post(
            "https://www.pushplus.plus/send",
            json=payload,
            timeout=self.client.timeout,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 200:
            raise RuntimeError(f"PushPlus failed: {body}")


class ServerChanNotifier(Notifier):
    def __init__(self, sendkey: str, client: HttpClient | None = None) -> None:
        self.sendkey = sendkey
        self.client = client or HttpClient()

    def send(self, title: str, content: str) -> None:
        if not self.sendkey:
            raise ValueError("ServerChan sendkey is empty")
        url = f"https://sctapi.ftqq.com/{self.sendkey}.send"
        response = self.client.session.post(
            url,
            data={"title": title, "desp": content},
            timeout=self.client.timeout,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("code") not in (0, 200):
            raise RuntimeError(f"ServerChan failed: {body}")


class WebhookNotifier(Notifier):
    def __init__(self, url: str, client: HttpClient | None = None) -> None:
        self.url = url
        self.client = client or HttpClient()

    def send(self, title: str, content: str) -> None:
        if not self.url:
            raise ValueError("Webhook url is empty")
        response = self.client.session.post(
            self.url,
            json={"title": title, "content": content},
            timeout=self.client.timeout,
        )
        response.raise_for_status()


def build_notifier(config: PushConfig) -> Notifier:
    channel = (config.channel or "console").lower()
    if channel == "pushplus":
        return PushPlusNotifier(config.pushplus.get("token", ""))
    if channel == "serverchan":
        return ServerChanNotifier(config.serverchan.get("sendkey", ""))
    if channel == "webhook":
        return WebhookNotifier(config.webhook.get("url", ""))
    return ConsoleNotifier()
