from app.config import CORTEX_BASE_URL, DEFAULT_MODEL
from main import run as run_cli_query


def run_query(query, user_id, app_name="doclens", llm_config=None):
    normalized_llm_config = dict(llm_config or {})
    normalized_llm_config.setdefault("model", DEFAULT_MODEL)

    return run_cli_query(
        query=query,
        user_id=user_id,
        app_name=app_name,
        llm_config=normalized_llm_config,
        base_url=CORTEX_BASE_URL,
    )