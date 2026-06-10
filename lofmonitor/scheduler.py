"""Job runner and scheduler."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from lofmonitor.calculator import LofPremiumService, format_top_message
from lofmonitor.config import AppConfig, load_config
from lofmonitor.notifier import build_notifier
from lofmonitor.trading_calendar import is_trading_day

logger = logging.getLogger(__name__)


class LofMonitorJob:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.service = LofPremiumService(config)
        self.notifier = build_notifier(config.push)

    def run(self, force: bool = False) -> str | None:
        """Run monitor. Returns message if actionable records found, None otherwise."""
        if not force and not is_trading_day():
            message = "Today is not a trading day, skip push."
            logger.info(message)
            return None

        df = self.service.collect()
        top_df = self.service.top_premium(df)

        # Silent exit if no actionable records
        if top_df.empty:
            logger.info("No actionable LOF records (|premium|>10%% and purchasable).")
            return None

        message = format_top_message(top_df, total_count=len(df))
        self._save_snapshot(top_df, message)

        if self.config.push.enabled:
            title = f"LOF套利机会 | {len(top_df)}只"
            self.notifier.send(title, message)
        else:
            logger.info("Push disabled:\n%s", message)
        return message

    def _save_snapshot(self, df, message: str) -> None:
        output_dir = Path(__file__).resolve().parent.parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = output_dir / f"lof_premium_{stamp}.csv"
        txt_path = output_dir / f"lof_premium_{stamp}.txt"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        txt_path.write_text(message, encoding="utf-8")
        logger.info("Saved snapshot to %s", csv_path)


def run_once(config_path: str | None = None, force: bool = False) -> str | None:
    config = load_config(config_path)
    return LofMonitorJob(config).run(force=force)


def start_scheduler(config_path: str | None = None) -> None:
    config = load_config(config_path)
    hour, minute = map(int, config.schedule.push_time.split(":"))
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    job = LofMonitorJob(config)

    scheduler.add_job(
        job.run,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=hour,
            minute=minute,
            timezone="Asia/Shanghai",
        ),
        id="lof_premium_push",
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info(
        "Scheduler started. Push at %02d:%02d on weekdays (trading-day check inside job).",
        hour,
        minute,
    )
    scheduler.start()
