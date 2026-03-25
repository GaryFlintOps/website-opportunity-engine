# app.py — entry point shim
# The real application lives in src/dashboard.py.
# Both `uvicorn app:app` and `uvicorn src.dashboard:app` will work.
from src.dashboard import app  # noqa: F401
