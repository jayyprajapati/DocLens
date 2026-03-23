from app.config import CORTEX_BASE_URL, DEFAULT_MODEL
from services.rag_client import generate as rag_generate


def run_generate(prompt):
    return rag_generate(
        prompt=prompt,
        model=DEFAULT_MODEL,
        base_url=CORTEX_BASE_URL,
    )