# Stufe 1: Oberfläche bauen
FROM node:22-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stufe 2: Laufzeit (Debian statt Alpine, damit später die Gesichtserkennung mit onnxruntime läuft)
FROM python:3.12-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libvips + HEIC-Decoder, exiftool zum Lesen/Schreiben der Metadaten,
# jpegtran für verlustfreies Drehen, ffmpeg für Video-Vorschaubilder, libgomp für onnxruntime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libvips42t64 \
        libheif-plugin-libde265 \
        libimage-exiftool-perl \
        libjpeg-turbo-progs \
        ffmpeg \
        tzdata \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/fotoarchiv ./fotoarchiv
COPY --from=frontend /src/dist ./static

CMD ["python", "-m", "fotoarchiv"]
