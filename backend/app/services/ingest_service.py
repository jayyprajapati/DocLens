from app.config import CORTEX_BASE_URL
from services.rag_client import ingest as rag_ingest


def run_ingest(file_path, user_id, app_name="doclens"):
    return rag_ingest(
        file_path=file_path,
        user_id=user_id,
        app_name=app_name,
        base_url=CORTEX_BASE_URL,
    )