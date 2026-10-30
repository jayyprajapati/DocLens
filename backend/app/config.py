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

    # Retrieval breadth handed to Brain: vector candidates reranked (top_k) and how many of
    # the reranked chunks come back for DocLens' own selection step (top_n, Brain caps at 30).
    retrieve_top_k: int = int(os.getenv("RETRIEVE_TOP_K", "40"))
    retrieve_top_n: int = int(os.getenv("RETRIEVE_TOP_N", "20"))

    # Context selection (see retrieval.select). Rerank scores are raw cross-encoder logits.
    context_max_chunks: int = int(os.getenv("CONTEXT_MAX_CHUNKS", "6"))
    context_min_chunks: int = int(os.getenv("CONTEXT_MIN_CHUNKS", "3"))
    context_score_margin: float = float(os.getenv("CONTEXT_SCORE_MARGIN", "7.0"))
    # Below this best-chunk rerank score nothing in the user's documents is on topic: answer
    # "not found" without spending an LLM call.
    evidence_gate_score: float = float(os.getenv("EVIDENCE_GATE_SCORE", "-9.5"))

    # Generation defaults (the user's BYOK provider does the work). Low temperature: this is
    # extraction + synthesis from sources, not creative writing.
    answer_max_tokens: int = int(os.getenv("ANSWER_MAX_TOKENS", "2000"))
    answer_temperature: float = float(os.getenv("ANSWER_TEMPERATURE", "0.1"))
    # Reasoning effort for Ollama reasoning models ("" = provider default).
    answer_reasoning: str = _clean(os.getenv("ANSWER_REASONING", ""))
    rewrite_reasoning: str = _clean(os.getenv("REWRITE_REASONING", "low"))
    # Second-opinion "does the evidence really answer this?" check: auto | always | off.
    answer_verify: str = _clean(os.getenv("ANSWER_VERIFY", "auto")).lower()
    verify_reasoning: str = _clean(os.getenv("VERIFY_REASONING", "medium"))

    # Attach the raw model output + prompt sources to response meta (eval/debug only).
    debug_trace: bool = _clean(os.getenv("DEBUG_TRACE", "")).lower() in ("1", "true", "yes")

    # Abuse limits. These are the *defaults*: the live values are runtime settings the admin
    # panel edits (see runtime.py) — env only seeds them.
    max_query_chars: int = int(os.getenv("MAX_QUERY_CHARS", "4000"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    chat_rate_per_min: int = int(os.getenv("CHAT_RATE_PER_MIN", "30"))
    upload_rate_per_10min: int = int(os.getenv("UPLOAD_RATE_PER_10MIN", "30"))

    # Sandboxed extraction (extraction.py). Hard ceilings, not admin-editable: they protect the
    # shared server, so changing them is a deploy.
    extract_concurrency: int = int(os.getenv("EXTRACT_CONCURRENCY", "1"))
    extract_timeout_s: int = int(os.getenv("EXTRACT_TIMEOUT_S", "90"))
    extract_mem_mb: int = int(os.getenv("EXTRACT_MEM_MB", "512"))
    docx_max_entries: int = int(os.getenv("DOCX_MAX_ENTRIES", "2000"))
    docx_max_uncompressed_mb: int = int(os.getenv("DOCX_MAX_UNCOMPRESSED_MB", "150"))
    hard_max_pages: int = int(os.getenv("HARD_MAX_PAGES", "500"))
    hard_max_chars: int = int(os.getenv("HARD_MAX_CHARS", "2000000"))

    # Signed browser sessions (auth.py). Required in production: without it any client could
    # claim any user id. Rotating it signs everyone out (their documents stay, unreachable).
    session_secret: str = _clean(os.getenv("SESSION_SECRET", ""))
    # Admin panel → DocLens internal API (/internal/admin/*). Unset = the internal API is off.
    admin_api_token: str = _clean(os.getenv("ADMIN_API_TOKEN", ""))
    # Hosted ("free") mode: the server's own Ollama Cloud key, used only when the admin enables
    # hosted mode. Never stored in Mongo, never sent to the browser or the admin panel.
    hosted_ollama_api_key: str = _clean(os.getenv("HOSTED_OLLAMA_API_KEY", ""))
    # Usage analytics retention (doclens_events, TTL index).
    events_retention_days: int = int(os.getenv("EVENTS_RETENTION_DAYS", "180"))

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
