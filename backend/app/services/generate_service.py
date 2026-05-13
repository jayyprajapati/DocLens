from app.config import CORTEX_BASE_URL
from services.rag_client import generate as rag_generate


def run_generate(query, user_id, app_name="doclens", llm=None):
    """
    Direct generation using Cortex /generate.
    llm: {"provider": "openai", "api_key": "...", "model": "gpt-4o-mini"}
    """
    return rag_generate(
        query=query,
        user_id=user_id,
        app_name=app_name,
        llm=llm,
        base_url=CORTEX_BASE_URL,
    )
