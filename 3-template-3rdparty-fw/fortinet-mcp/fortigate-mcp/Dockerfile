FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

ENV FORTIGATE_HOST=""
ENV FORTIGATE_API_TOKEN=""
ENV FORTIGATE_PORT="443"
ENV FORTIGATE_VERIFY_SSL="false"
ENV FORTIGATE_VDOM="root"
ENV LOG_LEVEL="INFO"

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8001/health')" || exit 1

CMD ["python", "-m", "src.server"]
