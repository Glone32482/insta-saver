FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "yt-dlp[default]"
WORKDIR /app
COPY server.py .
COPY static ./static
ENV HOST=0.0.0.0 PORT=8777 PYTHONUNBUFFERED=1
EXPOSE 8777
# yt-dlp обновляется при каждом старте: Instagram часто меняет API
CMD pip install -q -U "yt-dlp[default]" ; python server.py
