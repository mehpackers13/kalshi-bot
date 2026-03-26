"""
Entry point for the Sunday evening weekly review workflow.
"""

from kalshi_api import KalshiAPI
from morning_report import run_weekly_review
from logger import log

if __name__ == "__main__":
    log("Weekly review job starting")
    api = KalshiAPI()
    api.login()
    run_weekly_review(api)
    log("Weekly review job complete")
