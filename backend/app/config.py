import os

from dotenv import load_dotenv

from backend.app.data import REPO_ROOT

load_dotenv(REPO_ROOT / ".env")

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_PRICING_MODEL = os.environ.get("LLM_PRICING_MODEL", "gpt-6-luna").strip()
LLM_REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT", "low").strip()
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "60"))
MAX_MODEL_CALLS = int(os.environ.get("MAX_MODEL_CALLS", "16"))
