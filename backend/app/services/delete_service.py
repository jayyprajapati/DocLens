from app.config import CORTEX_BASE_URL
from services.rag_client import delete_all_documents as rag_delete_all_documents
from services.rag_client import delete_document as rag_delete_document


def run_delete(user_id, doc_id, app_name="doclens"):
    return rag_delete_document(
        user_id=user_id,
        doc_id=doc_id,
        app_name=app_name,
        base_url=CORTEX_BASE_URL,
    )


def run_delete_all(user_id, app_name="doclens"):
    return rag_delete_all_documents(
        user_id=user_id,
        app_name=app_name,
        base_url=CORTEX_BASE_URL,
    )
