"""
Entry point for GitHub Actions scan workflow.
Logs in to Kalshi, runs one full scan cycle, exits.
"""

from kalshi_api import KalshiAPI
from scanner import run_scan
from logger import log

if __name__ == "__main__":
    log("Scan job starting")
    api = KalshiAPI()
    api.login()
    run_scan(api)
    log("Scan job complete")
