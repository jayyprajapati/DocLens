import os

from dotenv import load_dotenv


load_dotenv()


CORTEX_BASE_URL = os.getenv("CORTEX_BASE_URL", os.getenv("RAG_API_BASE_URL", "http://localhost:8000"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")