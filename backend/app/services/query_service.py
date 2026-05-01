from app.config import CORTEX_BASE_URL
from services.rag_client import query as rag_query


def run_query(query, user_id, app_name="doclens", llm=None, doc_ids=None):
    return rag_query(
        query=query,
        user_id=user_id,
        app_name=app_name,
        llm=llm,
        doc_ids=doc_ids,
        base_url=CORTEX_BASE_URL,
    )
