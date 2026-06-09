# evaluation/metrics.py
# DeepEval metric definitions for the AI E-Commerce Operations Manager.
#
# We use Azure OpenAI as the judge LLM (same deployment already configured).
# Three DeepEval metrics are used:
#
#   1. AnswerRelevancyMetric  — does the answer actually address the question?
#   2. FaithfulnessMetric     — are claims grounded in the retrieval context?
#   3. GEval (custom)         — is the severity / root-cause diagnosis correct?
#
# All three are LLM-as-judge metrics — they call your Azure endpoint.
# They run locally; no DeepEval cloud account needed.

import os
from dotenv import load_dotenv

load_dotenv()

# ── Configure DeepEval to use Azure OpenAI as the judge ──────────────────────
# DeepEval reads these env vars automatically when you import its metrics.
# We set them programmatically here so metrics.py is the single config point.

os.environ.setdefault("OPENAI_API_KEY",           os.getenv("OPENAI_API_KEY", ""))
os.environ.setdefault("AZURE_OPENAI_API_KEY",     os.getenv("OPENAI_API_KEY", ""))
os.environ.setdefault("AZURE_OPENAI_ENDPOINT",    os.getenv("AZURE_OPENAI_ENDPOINT", ""))
os.environ.setdefault("OPENAI_API_VERSION",       os.getenv("AZURE_OPENAI_API_VERSION", ""))
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"  # suppress login prompt

from deepeval.models import DeepEvalBaseLLM
from langchain_openai import AzureChatOpenAI
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval
from deepeval.test_case import LLMTestCaseParams


# ── Custom judge model — wraps our existing Azure deployment ─────────────────

class AzureJudge(DeepEvalBaseLLM):
    """
    Thin wrapper so DeepEval uses the same AzureChatOpenAI instance
    we already use everywhere else in the project.
    """

    def __init__(self):
        self._client = AzureChatOpenAI(
            azure_deployment   = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            azure_endpoint     = os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            api_key            = os.getenv("OPENAI_API_KEY", ""),
            api_version        = os.getenv("AZURE_OPENAI_API_VERSION", ""),
            temperature        = 0,
        )

    def load_model(self):
        return self._client

    def generate(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage
        response = self._client.invoke([HumanMessage(content=prompt)])
        return response.content

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self) -> str:
        return os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")


# Singleton — instantiated once, reused by all metrics
_judge = AzureJudge()


# ── Metric 1: Answer Relevancy ────────────────────────────────────────────────
# Measures: does the output actually answer what the user asked?
# Score:    0.0 – 1.0  |  threshold: 0.7
answer_relevancy = AnswerRelevancyMetric(
    threshold = 0.7,
    model     = _judge,
    verbose_mode = False,
)


# ── Metric 2: Faithfulness ────────────────────────────────────────────────────
# Measures: are factual claims in the output supported by the retrieved context?
# Context:  we pass agent analyses as the "retrieval context"
# Score:    0.0 – 1.0  |  threshold: 0.7
faithfulness = FaithfulnessMetric(
    threshold = 0.7,
    model     = _judge,
    verbose_mode = False,
)


# ── Metric 3: GEval — Ops Diagnosis Quality ───────────────────────────────────
# Custom rubric: does the answer identify root causes and recommend actions?
# Score:    0.0 – 1.0  |  threshold: 0.6
ops_diagnosis_quality = GEval(
    name       = "Ops Diagnosis Quality",
    model      = _judge,
    threshold  = 0.6,
    criteria   = (
        "Evaluate the output as an e-commerce operations diagnosis. "
        "A high-quality diagnosis should: "
        "(1) identify specific root causes with supporting evidence, "
        "(2) explain cross-domain connections (e.g. stock + campaign + complaints), "
        "(3) recommend concrete, prioritised actions, "
        "(4) reference historical context if similar past incidents exist. "
        "Penalise vague, generic answers that do not reference specific products, "
        "campaigns, or metrics from the data."
    ),
    evaluation_params = [
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ],
)


# Convenience list — run_eval.py iterates this
ALL_METRICS = [answer_relevancy, faithfulness, ops_diagnosis_quality]
