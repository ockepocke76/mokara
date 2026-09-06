"""
Background worker entrypoint.

Run locally (from api/):  .venv/bin/python worker.py
Processes BACKGROUND_JOBS (simulation_run, pdf_generation,
strategy_evaluation) until interrupted.
"""
from dotenv import load_dotenv

load_dotenv()

from services.background_worker import run_worker

if __name__ == "__main__":
    run_worker()
