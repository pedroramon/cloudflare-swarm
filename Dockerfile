FROM python:3.11-alpine

# Instala dependências do sistema
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev

# Define diretório de trabalho
WORKDIR /app

# Copia requirements
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia código da aplicação
COPY cloudflare_dns_manager.py .

# Cria usuário não-root
RUN adduser -D -s /bin/sh cloudflare
USER cloudflare

# Comando padrão
CMD ["python", "cloudflare_dns_manager.py"]

# Labels
LABEL maintainer="Seu Nome <seu@email.com>"
LABEL description="Cloudflare DNS Manager para Docker Swarm"
LABEL version="1.0.0"