import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

from app.db import connect_db, disconnect_db
from app.worker.scheduler import (
    job_generate_customer_invoices,
    job_remind_unpaid_invoices,
    job_suspend_overdue_users,
    job_generate_reseller_invoices,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan():
    # Startup
    await connect_db()
    logger.info("✅ Database connected (Worker)")

    scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")

    # Jadwal sesuai requirement
    scheduler.add_job(job_generate_customer_invoices, "cron", hour=9, minute=0)       # H-3 cek invoice
    scheduler.add_job(job_remind_unpaid_invoices, "cron", hour=9, minute=10)          # reminder unpaid
    scheduler.add_job(job_suspend_overdue_users, "cron", day=1, hour=6, minute=0)     # suspend overdue
    scheduler.add_job(job_generate_reseller_invoices, "cron", day=1, hour=0, minute=10)  # reseller invoice

    scheduler.start()
    logger.info("🚀 Worker scheduler started")

    try:
        yield
    finally:
        # Shutdown
        await disconnect_db()
        logger.info("🛑 Database disconnected (Worker)")


async def main():
    async with lifespan():
        # keep alive
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
