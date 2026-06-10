# Single place where the Azure OpenAI LLM is configured.
# All agents import `llm` from here — if you ever change the model,
# you only need to update this one file.

import os
from pathlib import Path
from dotenv import load_dotenv         # reads key=value pairs from the .env file into os.environ
from langchain_openai import AzureChatOpenAI  # LangChain wrapper for Azure OpenAI chat models
from langchain_core.globals import set_llm_cache
from langchain_core.caches import InMemoryCache

import warnings
# Suppress Pydantic serializer warnings from LangChain's with_structured_output —
# these are cosmetic and don't affect functionality
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Load .env from the project root (two levels up from this file: agents/ -> project root)
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True, encoding="utf-8-sig")

# Process-wide LLM cache. Identical prompts (e.g. repeated planner routing for the
# same follow-up question, or critic re-grading the same draft) skip the API
# round-trip entirely. Temperature is 0 across the board, so cached responses
# are exactly what a fresh call would have returned.
# In-memory cache lives only for the process lifetime — fine for a single-worker
# uvicorn; swap for SQLiteCache if multi-worker persistence is needed.
set_llm_cache(InMemoryCache())

# Two LLM tiers:
#   llm       — strong model used by ReAct agents and synthesis (quality matters)
#   llm_fast  — cheaper model used by planner and critic (short, structured calls)
#
# If AZURE_OPENAI_DEPLOYMENT_FAST is unset, llm_fast falls back to the strong
# deployment so behavior is unchanged out of the box.
_STRONG_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini-2025-04-14")
_FAST_DEPLOYMENT   = os.getenv("AZURE_OPENAI_DEPLOYMENT_FAST", _STRONG_DEPLOYMENT)

# Timeout/retry: synthesis calls may stream long responses, so cap at 120s.
# Let the SDK retry transient 429/5xx twice with backoff before surfacing the error.
_AZURE_COMMON = dict(
    api_key        = os.getenv("OPENAI_API_KEY"),
    api_version    = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "https://ai-proxy.lab.epam.com"),
    temperature     = 0,   # deterministic — best for analysis and structured tasks
    request_timeout = 120,  # seconds, increased for complex synthesis queries
    max_retries     = 2,   # retry transient failures (429, 5xx) with backoff
)

llm      = AzureChatOpenAI(azure_deployment=_STRONG_DEPLOYMENT, **_AZURE_COMMON)
llm_fast = AzureChatOpenAI(azure_deployment=_FAST_DEPLOYMENT,   **_AZURE_COMMON)