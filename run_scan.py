"""
Entry point for GitHub Actions scan workflow.
Logs in to Kalshi, runs one full scan cycle, exits.
"""

from kalshi_api import KalshiAPI
from scanner import run_scan
from outcomes import auto_resolve_outcomes
from logger import log

if __name__ == "__main__":
    log("Scan job starting")
    api = KalshiAPI()
    api.login()

    # Resolve any newly-settled alerts BEFORE the scan so self_improve has
    # the freshest hit-rate data for category confidence tuning.
    # Pulls up to 1000 recently finalized markets (5 pages * 200).
    try:
        resolved = auto_resolve_outcomes(api, pages=5, limit=200)
        if resolved:
            log(f"Auto-resolve: scored {resolved} newly-settled alerts")
    except TypeError:
        # Older signature without pages/limit kwargs
        resolved = auto_resolve_outcomes(api)
        if resolved:
            log(f"Auto-resolve: scored {resolved} newly-settled alerts")
    except Exception as exc:
        log(f"Auto-resolve failed: {exc}", "WARN")

    run_scan(api)
    log("Scan job complete")
