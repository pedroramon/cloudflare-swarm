#!/bin/bash

# Script de deploy do Cloudflare DNS Manager para Docker Swarm

set -e

echo "🚀 Deploy do Cloudflare DNS Manager"
echo "=================================="

# Variáveis
IMAGE_NAME="cloudflare-dns-manager"
SERVICE_NAME="cloudflare-dns-manager"
NETWORK_NAME="traefik-network"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funções auxiliares
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verifica se está rodando em um nó manager
check_swarm_manager() {
    if ! docker node ls &>/dev/null; then
        log_error "Este script deve ser executado em um nó manager do Docker Swarm"
        exit 1
    fi
    log_info "✅ Executando em nó manager do Swarm"
}

# Verifica se a rede do Traefik existe
check_traefik_network() {
    if ! docker network inspect $NETWORK_NAME &>/dev/null; then
        log_warn "Rede $NETWORK_NAME não encontrada. Criando..."
        docker network create --driver overlay $NETWORK_NAME
        log_info "✅ Rede $NETWORK_NAME criada"
    else
        log_info "✅ Rede $NETWORK_NAME já existe"
    fi
}

# Constrói a imagem Docker
build_image() {
    log_info "🔨 Construindo imagem Docker..."
    
    if [ ! -f "Dockerfile" ]; then
        log_error "Dockerfile não encontrado!"
        exit 1
    fi
    
    docker build -t $IMAGE_NAME:latest .
    log_info "✅ Imagem construída com sucesso"
}

# Verifica variáveis de ambiente necessárias
check_environment() {
    log_info "🔍 Verificando configuração..."
    
    if [ -z "$CLOUDFLARE_DOMAINS" ]; then
        log_error "Variável CLOUDFLARE_DOMAINS não definida!"
        echo "Exemplo:"
        echo 'export CLOUDFLARE_DOMAINS={"meudominio.com": {"zone_id": "xxx", "api_key": "yyy"}}'
        exit 1
    fi
    
    if [ -z "$SWARM_PUBLIC_IP" ]; then
        log_warn "SWARM_PUBLIC_IP não definida. Usando IP padrão."
        export SWARM_PUBLIC_IP="0.0.0.0"
    fi
    
    log_info "✅ Configuração verificada"
}

# Deploy do serviço
deploy_service() {
    log_info "🚀 Fazendo deploy do serviço..."
    
    # Remove serviço existente se houver
    if docker service inspect $SERVICE_NAME &>/dev/null; then
        log_info "Removendo serviço existente..."
        docker service rm $SERVICE_NAME
        sleep 5
    fi
    
    # Cria o serviço
    docker service create \
        --name $SERVICE_NAME \
        --network $NETWORK_NAME \
        --constraint 'node.role==manager' \
        --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock,readonly \
        --env CLOUDFLARE_DOMAINS="$CLOUDFLARE_DOMAINS" \
        --env SWARM_PUBLIC_IP="$SWARM_PUBLIC_IP" \
        --env PUBLIC_IP="${PUBLIC_IP:-$SWARM_PUBLIC_IP}" \
        --env CHECK_INTERVAL="${CHECK_INTERVAL:-30}" \
        --restart-condition on-failure \
        --restart-max-attempts 3 \
        $IMAGE_NAME:latest
    
    log_info "✅ Serviço deployado com sucesso"
}

# Verifica status do serviço
check_service_status() {
    log_info "📊 Verificando status do serviço..."
    
    sleep 5
    
    # Mostra status do serviço
    docker service ps $SERVICE_NAME
    
    echo ""
    log_info "📋 Logs do serviço:"
    echo "docker service logs -f $SERVICE_NAME"
}

# Menu de opções
show_menu() {
    echo ""
    echo "Opções disponíveis:"
    echo "1. build   - Construir imagem"
    echo "2. deploy  - Deploy completo"
    echo "3. logs    - Ver logs"
    echo "4. status  - Ver status"
    echo "5. remove  - Remover serviço"
    echo "6. help    - Mostrar ajuda"
}

# Funções de gerenciamento
show_logs() {
    docker service logs -f $SERVICE_NAME
}

show_status() {
    echo "📊 Status do serviço:"
    docker service ps $SERVICE_NAME
    echo ""
    echo "📈 Estatísticas:"
    docker service inspect $SERVICE_NAME --pretty
}

remove_service() {
    log_info "🗑️  Removendo serviço..."
    docker service rm $SERVICE_NAME
    log_info "✅ Serviço removido"
}

show_help() {
    cat << EOF
🔧 Cloudflare DNS Manager - Deploy Script

Este script gerencia o deploy do Cloudflare DNS Manager no Docker Swarm.

VARIÁVEIS DE AMBIENTE NECESSÁRIAS:

CLOUDFLARE_DOMAINS (obrigatório):
  JSON com configuração dos domínios
  Exemplo: export CLOUDFLARE_DOMAINS='{"example.com": {"zone_id": "xxx", "api_key": "yyy"}}'

SWARM_PUBLIC_IP (recomendado):
  IP público do seu cluster Swarm
  Exemplo: export SWARM_PUBLIC_IP="203.0.113.1"

CHECK_INTERVAL (opcional):
  Intervalo de verificação em segundos (padrão: 30)
  Exemplo: export CHECK_INTERVAL="60"

EXEMPLOS DE USO:

# Configurar variáveis
export CLOUDFLARE_DOMAINS='{"meusite.com": {"zone_id": "abc123", "api_key": "def456"}}'
export SWARM_PUBLIC_IP="203.0.113.1"

# Deploy completo
./deploy.sh deploy

# Ver logs
./deploy.sh logs

# Ver status
./deploy.sh status

LABELS SUPORTADAS:

O serviço monitora as seguintes labels nos serviços:
- traefik.http.routers.<nome>.rule=Host(\`dominio.com\`) 
- traefik.http.routers.<nome>.cloudflare.proxied=true|false

EOF
}

# Função principal
main() {
    case "${1:-menu}" in
        build)
            check_swarm_manager
            build_image
            ;;
        deploy)
            check_swarm_manager
            check_environment
            check_traefik_network
            build_image
            deploy_service
            check_service_status
            ;;
        logs)
            show_logs
            ;;
        status)
            show_status
            ;;
        remove)
            remove_service
            ;;
        help)
            show_help
            ;;
        menu|*)
            show_menu
            ;;
    esac
}

# Executa função principal
main "$@"