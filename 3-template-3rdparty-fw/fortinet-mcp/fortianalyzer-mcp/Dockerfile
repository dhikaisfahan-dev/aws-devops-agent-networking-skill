FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

ENV FAZ_HOST=""
ENV FAZ_API_TOKEN=""
ENV FAZ_PORT="443"
ENV FAZ_VERIFY_SSL="false"
ENV FAZ_ADOM="root"
ENV LOG_LEVEL="INFO"

EXPOSE 8003

CMD ["python", "-m", "src.server"]
