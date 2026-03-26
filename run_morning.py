"""
Entry point for the 8am morning report workflow.
"""

from kalshi_api import KalshiAPI
from morning_report import run
from logger import log

if __name__ == "__main__":
    log("Morning report job starting")
    api = KalshiAPI()
    api.login()
    run(api)
    log("Morning report job complete")
