"""
Background worker: runs on a schedule to:
  - disable expired subscriptions
  - retry failed provisioning
"""
import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from billing.services.billing_service import BillingService

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

service = BillingService()


async def task_disable_expired():
    try:
        count = await service.disable_expired_subscriptions()
        if count:
            logger.info("[worker] Disabled %d expired subscriptions", count)
    except Exception as e:
        logger.error("[worker] disable_expired error: %s", e, exc_info=True)


async def task_retry_provisioning():
    try:
        count = await service.retry_pending_provisioning()
        if count:
            logger.info("[worker] Retried provisioning for %d subscriptions", count)
    except Exception as e:
        logger.error("[worker] retry_provisioning error: %s", e, exc_info=True)


def main():
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        task_disable_expired,
        trigger=IntervalTrigger(minutes=5),
        id="disable_expired",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        task_retry_provisioning,
        trigger=IntervalTrigger(minutes=3),
        id="retry_provisioning",
        replace_existing=True,
        misfire_grace_time=60,
    )

    scheduler.start()
    logger.info("Worker started. Jobs: %s", [j.id for j in scheduler.get_jobs()])

    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker shutting down")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
