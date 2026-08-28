import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://hft:hft@localhost:5432/hft")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
KRAKEN_SYMBOL = os.environ.get("KRAKEN_SYMBOL", "BTC/USD")

# --- Agentic layer ---------------------------------------------------------
# All optional: unset -> that piece of the agent layer degrades gracefully
# (see hft.agents.base / hft.data_plane.timeseries), deterministic terminal
# always works regardless.
# OpenAI-compatible LLM backend — defaults to OpenRouter, works with any
# OpenAI-compatible provider (DeepSeek direct, OpenRouter, etc) by swapping
# LLM_BASE_URL. LLM_MODEL is whatever model id that provider expects
# (OpenRouter: "deepseek/deepseek-chat", "openai/gpt-4o-mini", etc — see
# openrouter.ai/models).
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek/deepseek-chat")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

UPSTASH_REDIS_URL = os.environ.get("UPSTASH_REDIS_URL", REDIS_URL)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
# Local fallback store used when SUPABASE_URL is unset (dev / no provisioning).
LOCAL_TIMESERIES_DB = os.environ.get("LOCAL_TIMESERIES_DB", "timeseries.db")

QUOTE_CACHE_TTL_S = int(os.environ.get("QUOTE_CACHE_TTL_S", "5"))
AGENT_MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "6"))
AGENT_TIMEOUT_S = float(os.environ.get("AGENT_TIMEOUT_S", "20"))
AGENT_COST_CEILING_USD = float(os.environ.get("AGENT_COST_CEILING_USD", "0.05"))
AGENT_OUTPUT_CACHE_TTL_S = int(os.environ.get("AGENT_OUTPUT_CACHE_TTL_S", "60"))
