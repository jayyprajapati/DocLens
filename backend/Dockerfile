# DocLens backend — built in CI (GitHub Actions → GHCR) and PULLED by the Hetzner server; the server
# never compiles. This is a thin orchestration layer (httpx + pymongo), so no system libraries are
# needed and the image stays small.
FROM python:3.12-slim

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
