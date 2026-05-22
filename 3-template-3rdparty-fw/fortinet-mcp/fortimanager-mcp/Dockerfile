FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

ENV FMG_HOST=""
ENV FMG_API_TOKEN=""
ENV FMG_PORT="443"
ENV FMG_VERIFY_SSL="false"
ENV FMG_ADOM="root"
ENV LOG_LEVEL="INFO"

EXPOSE 8002

CMD ["python", "-m", "src.server"]
