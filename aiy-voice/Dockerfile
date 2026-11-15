FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && groupadd --gid 10001 aiy-voice \
    && useradd --uid 10001 --gid 10001 --create-home voice
COPY server.py web_search.py memory_search.py profile.txt .
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python", "/app/server.py"]
