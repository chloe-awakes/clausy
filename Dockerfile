# Optional Docker image for running the Flask API.
# Note: Running a real browser with CDP from inside Docker is possible but more advanced.
# This image is mainly for packaging the server; you still need a reachable CDP endpoint.

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt &&     python -m playwright install --with-deps chromium

COPY . /app

ENV CLAUSY_BIND=0.0.0.0
ENV CLAUSY_PORT=3108

EXPOSE 3108

CMD ["python", "-m", "clausy.server"]
