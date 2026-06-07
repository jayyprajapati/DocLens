"""DocLens backend configuration.

DocLens is a thin orchestration + state layer in front of Brain (the
application-agnostic RAG engine). Brain owns embeddings, vector search, and the
BYOK LLM call; DocLens owns *its own* state (chat sessions, messages, and which
document is global vs. scoped to a single chat) in MongoDB. Brain never sees any
DocLens application data — only vectors keyed by an opaque ``namespace`` (the
user id) and ``doc_id``.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _clean(value: str) -> str:
    return (value or "").strip()


class Settings:
    # Brain (the RAG engine)
    brain_base_url: str = _clean(os.getenv("BRAIN_BASE_URL", "http://localhost:8000")).rstrip("/")
    brain_api_key: str = _clean(os.getenv("BRAIN_API_KEY", ""))
    # Brain selects a dedicated Qdrant collection from this name. DocLens always
    # uses one collection; user isolation happens via namespace=user_id.
    brain_app_name: str = _clean(os.getenv("BRAIN_APP_NAME", "doclens")) or "doclens"
    brain_timeout: float = float(os.getenv("BRAIN_TIMEOUT", "180"))

    # MongoDB — DocLens application state only.
    mongo_uri: str = _clean(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    mongo_db: str = _clean(os.getenv("MONGO_DB", "doclens")) or "doclens"

    # Retrieval breadth handed to Brain (candidate pool before its rerank).
    retrieve_top_k: int = int(os.getenv("RETRIEVE_TOP_K", "40"))

    # Generation defaults (the user's BYOK provider does the work).
    answer_max_tokens: int = int(os.getenv("ANSWER_MAX_TOKENS", "1400"))
    answer_temperature: float = float(os.getenv("ANSWER_TEMPERATURE", "0.4"))

    env: str = _clean(os.getenv("ENV") or os.getenv("APP_ENV") or "development").lower()
    cors_allowed_origins: str = _clean(os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000"))

    @property
    def is_dev(self) -> bool:
        return self.env in ("dev", "development", "local")

    @property
    def allowed_origins(self) -> list[str]:
        raw = self.cors_allowed_origins
        if not raw:
            return ["http://localhost:3000"]
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()
