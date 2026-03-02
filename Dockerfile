FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    openbox \
    x11-utils \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY clausy ./clausy
COPY scripts ./scripts

RUN pip install -U pip && pip install .
RUN python -m playwright install --with-deps chromium

COPY . .

ENV CLAUSY_BIND=0.0.0.0
ENV CLAUSY_PORT=5000
ENV CLAUSY_PROVIDER=chatgpt
ENV CLAUSY_CDP_HOST=127.0.0.1
ENV CLAUSY_CDP_PORT=9200
ENV CLAUSY_BROWSER_BOOTSTRAP=auto
ENV DISPLAY=:99

EXPOSE 5000

CMD ["./scripts/docker-start.sh"]
