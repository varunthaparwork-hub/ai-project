# Single place where the Azure OpenAI LLM is configured.
# All agents import `llm` from here — if you ever change the model,
# you only need to update this one file.

import os
from pathlib import Path
from dotenv import load_dotenv         # reads key=value pairs from the .env file into os.environ
from langchain_openai import AzureChatOpenAI  # LangChain wrapper for Azure OpenAI chat models

import warnings
# Suppress Pydantic serializer warnings from LangChain's with_structured_output —
# these are cosmetic and don't affect functionality
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Load .env from the project root (two levels up from this file: agents/ -> project root)
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True, encoding="utf-8-sig")

# Create the shared LLM instance used by every agent and node in the project.
# os.getenv(KEY, DEFAULT) reads from .env — falls back to default if key is missing.
llm = AzureChatOpenAI(
    api_key          = os.getenv("OPENAI_API_KEY"),                              # your Azure OpenAI key
    api_version      = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"), # API version
    azure_endpoint   = os.getenv("AZURE_OPENAI_ENDPOINT",   "https://ai-proxy.lab.epam.com"), # endpoint URL
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT",  "gpt-4.1-mini-2025-04-14"),     # deployed model name
    temperature      = 0,  # 0 = deterministic output — best for analysis and structured tasks
)