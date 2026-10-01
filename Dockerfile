# Imagen del motor de inferencia: Python + Radare2 + GCC.
# Ollama NO va aquí: corre en la máquina anfitriona para usar la GPU.
FROM python:3.11-slim

ARG R2_VERSION=6.2.2
# amd64 (PC/laptop normal) o arm64 (Mac M1/M2, Raspberry): lo pone Docker solo
ARG TARGETARCH

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OLLAMA_HOST=http://host.docker.internal:11434

# gcc + binutils (strip) para compilar el dataset; curl para bajar radare2
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev binutils make curl ca-certificates file \
 && ARCH="${TARGETARCH:-amd64}" \
 && curl -fsSL -o /tmp/r2.deb \
      "https://github.com/radareorg/radare2/releases/download/${R2_VERSION}/radare2_${R2_VERSION}_${ARCH}.deb" \
 && apt-get install -y /tmp/r2.deb \
 && rm -rf /tmp/r2.deb /var/lib/apt/lists/*

WORKDIR /app

# Primero dependencias (se cachean aunque cambies el código)
COPY pyproject.toml ./
COPY src ./src
RUN pip install -e ".[dev]"

COPY . .

ENTRYPOINT ["elfinfer"]
CMD ["--help"]
