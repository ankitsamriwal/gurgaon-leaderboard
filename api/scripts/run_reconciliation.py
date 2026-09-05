#!/usr/bin/env python3
"""Entrypoint for the nightly reconciliation job (docs/03: run at ~2 AM
IST). Not wired to a scheduler in this build — doc00 lists Celery/RQ +
Redis or APScheduler as options; standing one up is an infra decision for
whoever deploys this. Point a cron/systemd timer/Celery-beat task at this
script, e.g.:

    0 20 * * * cd /path/to/api && .venv/bin/python scripts/run_reconciliation.py

(2 AM IST == 20:30 UTC the previous day, but cron here is illustrative —
match it to the deployment's actual timezone handling.)
"""

import asyncio
import sys

sys.path.insert(0, ".")

from app.db import async_session  # noqa: E402
from app.services.reconciliation import run_reconciliation  # noqa: E402


async def main() -> None:
    async with async_session() as session:
        report = await run_reconciliation(session)
    print(f"Reconciliation run {report['id']}: "
          f"{report['mismatch_count']} mismatch(es) out of {report['projects_checked']} project(s) checked.")
    if report["mismatch_count"] > 0:
        sys.exit(1)  # non-zero exit so cron/systemd surfaces this as a failure


if __name__ == "__main__":
    asyncio.run(main())
