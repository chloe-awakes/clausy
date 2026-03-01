FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY clausy ./clausy
COPY scripts ./scripts

RUN pip install -U pip && pip install .
RUN python -m playwright install --with-deps chromium

COPY . .

ENV CLAUSY_BIND=0.0.0.0
ENV CLAUSY_PORT=5000
ENV CLAUSY_PROVIDER=chatgpt
ENV CLAUSY_CDP_HOST=host.docker.internal
ENV CLAUSY_CDP_PORT=9200

EXPOSE 5000

CMD ["python", "-m", "clausy"]
