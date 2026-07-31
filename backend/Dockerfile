FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ---------------------------------------------------------------------------
# System dependencies
#   ffmpeg          -> rendering + probing (ffprobe ships in the same package)
#   fonts-*         -> Latin + Arabic capable fonts for text layers
#   libraqm0        -> HarfBuzz/FriBidi text shaping backend used by Pillow
#   fontconfig      -> font discovery (fc-match) fallback
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        fontconfig \
        libraqm0 \
        fonts-dejavu-core \
        fonts-noto-core \
        fonts-hosny-amiri \
        curl \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /data/storage /data/tmp

EXPOSE 8000

ENTRYPOINT []
CMD ["/app/entrypoint.sh", "api"]
