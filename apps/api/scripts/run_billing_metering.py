#!/usr/bin/env python3
"""T-205 (SPEC-205): the nightly billing-metering job. NOT part of the product — a
real ops entrypoint, same standing as apps/orchestrator/scripts/run_pilot.py. No
scheduler daemon exists anywhere in this repo (provider_health_service.py's own
docstring already discloses this: "a future scheduler can call ...; nothing here
assumes one does") — this script is meant to be invoked by an external cron/CI
schedule, e.g. `make billing-meter DATE=2026-07-08`.

For each org: records the day's raw usage (idempotent — AC1), applies any deferred
plan downgrade whose period has ended, bills the elapsed period's overage as real
Razorpay addons, and expires any grace period that has run out (AC4's dunning path).

Usage:
    python scripts/run_billing_metering.py --date 2026-07-08   # a specific day (UTC)
    python scripts/run_billing_metering.py                     # defaults to yesterday
"""

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.db.session import SessionLocal  # noqa: E402
from api.services import billing_service  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="ISO date (YYYY-MM-DD, UTC) to meter. Defaults to yesterday.",
    )
    args = parser.parse_args()

    report_date: date = (
        date.fromisoformat(args.date)
        if args.date
        else (datetime.now(UTC) - timedelta(days=1)).date()
    )

    session = SessionLocal()
    try:
        reported = billing_service.run_metering_for_all_orgs(session, report_date=report_date)
        session.commit()
        for org_id, kinds in reported.items():
            if kinds:
                print(f"  {org_id}: reported {kinds}")

        applied = billing_service.apply_pending_plan_sweep(session)
        session.commit()
        for org in applied:
            print(f"  {org.id}: plan downgrade applied -> {org.plan}")

        paused = billing_service.expire_grace_periods(session)
        session.commit()
        for org in paused:
            print(f"  {org.id}: paused for nonpayment")

        print(f"billing metering for {report_date.isoformat()} complete")
    finally:
        session.close()


if __name__ == "__main__":
    main()
