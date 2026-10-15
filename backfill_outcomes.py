"""
BACKFILL OUTCOMES
=================
One-shot catch-up for pending outcomes in outcomes.csv.
The regular `auto_resolve_outcomes` in run_scan.py only pulls 5 pages
of settled markets per 30-min scan (~1000 markets), which is plenty
for incremental catch-up but takes months to burn down a backlog.

This script pulls up to 100 pages (~20,000 settled markets) in one
run, matches against ALL pending outcomes.csv rows, and writes once.
Run via a one-off `workflow_dispatch` or locally with Kalshi API keys.

Usage:
  python backfill_outcomes.py --pages 100
"""
import argparse
import time

from kalshi_api import KalshiAPI
from outcomes import auto_resolve_outcomes, read_all
from logger import log


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pages", type=int, default=100,
                   help="pages of settled markets to pull (each = 200 markets)")
    p.add_argument("--limit", type=int, default=200,
                   help="markets per page")
    args = p.parse_args()

    log(f"Backfill: pulling up to {args.pages * args.limit} settled markets")
    api = KalshiAPI()
    api.login()

    before = sum(1 for r in read_all() if (r.get("outcome") or "").strip() == "")
    log(f"Before: {before} pending outcomes")

    t0 = time.time()
    resolved = auto_resolve_outcomes(api, pages=args.pages, limit=args.limit)
    elapsed = time.time() - t0

    after = sum(1 for r in read_all() if (r.get("outcome") or "").strip() == "")
    log(f"After:  {after} pending outcomes")
    log(f"Resolved {resolved} new outcomes in {elapsed:.1f}s "
        f"(reduction: {before - after} rows)")


if __name__ == "__main__":
    main()
