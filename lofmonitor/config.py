"""Configuration loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ScheduleConfig:
    push_time: str = "14:30"


@dataclass
class DataConfig:
    batch_size: int = 80
    request_delay: float = 0.15


@dataclass
class PushConfig:
    enabled: bool = True
    channel: str = "console"
    pushplus: dict[str, str] = field(default_factory=dict)
    serverchan: dict[str, str] = field(default_factory=dict)
    webhook: dict[str, str] = field(default_factory=dict)


@dataclass
class FilterConfig:
    min_amount: float = 1_000_000
    top_n: int = 10


@dataclass
class AppConfig:
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    data: DataConfig = field(default_factory=DataConfig)
    push: PushConfig = field(default_factory=PushConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)


def _merge_dataclass(instance: Any, payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        if not hasattr(instance, key):
            continue
        current = getattr(instance, key)
        if isinstance(current, (ScheduleConfig, DataConfig, PushConfig, FilterConfig)):
            _merge_dataclass(current, value)
        else:
            setattr(instance, key, value)


def load_config(path: str | Path | None = None) -> AppConfig:
    config = AppConfig()
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config.yaml"
    else:
        path = Path(path)

    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        _merge_dataclass(config, raw)
    return config
