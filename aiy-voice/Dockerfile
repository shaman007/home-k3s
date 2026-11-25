FROM python:3.15.2-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libopus0 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && groupadd --gid 10001 aiy-voice \
    && useradd --uid 10001 --gid 10001 --create-home voice
COPY server.py web_search.py memory_search.py conversation_memory.py mcp_transport.py device_tools.py reminder_speech.py home_assistant.py homeassistant_tools.json prompts.py opus_audio.py .
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python", "/app/server.py"]
