FROM python:3.11-alpine

# Instala dependências do sistema
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    docker-cli

# Define diretório de trabalho
WORKDIR /app

# Copia requirements
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia código da aplicação
COPY app.py cloudflare_manager.py docker_manager.py .

# Cria usuário não-root e adiciona ao grupo docker
RUN addgroup -S docker && \
    adduser -D -s /bin/sh cloudflare && \
    adduser cloudflare docker

USER cloudflare

# Comando padrão
CMD ["python", "app.py"]

# Labels
LABEL maintainer="Pedro Ramon <pedroramon.dev@gmail.com>"
LABEL description="Cloudflare DNS Manager para Docker Swarm"
LABEL version="1.0.0"