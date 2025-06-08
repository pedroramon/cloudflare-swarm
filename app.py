#!/usr/bin/env python3
"""
Cloudflare DNS Manager para Docker Swarm
Monitora labels dos serviços e cria registros DNS automaticamente
"""

import docker
import requests
import json
import time
import logging
import os
from typing import Dict, List, Optional
from urllib.parse import urlparse

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CloudflareDNSManager:
    def __init__(self, domain_config: Dict[str, Dict[str, str]], check_interval: int = 30):
        """
        Inicializa o gerenciador DNS da Cloudflare
        
        Args:
            domain_config: Dicionário com configuração dos domínios
                          formato: {"dominio.com": {"zone_id": "xxx", "api_key": "yyy"}}
            check_interval: Intervalo em segundos para verificar mudanças
        """
        self.domain_config = domain_config
        self.check_interval = check_interval
        self.docker_client = docker.from_env()
        self.processed_services = set()
        
    def get_domain_config(self, hostname: str) -> Optional[Dict[str, str]]:
        """
        Obtém a configuração do domínio baseado no hostname
        """
        for domain, config in self.domain_config.items():
            if hostname.endswith(domain):
                return config
        return None
    
    def extract_hostname_from_rule(self, rule: str) -> Optional[str]:
        """
        Extrai o hostname da regra do Traefik
        Suporta formatos como: Host(`example.com`) ou Host(`sub.example.com`)
        """
        import re
        
        # Padrão para Host(`hostname`)
        host_pattern = r'Host\(`([^`]+)`\)'
        match = re.search(host_pattern, rule)
        
        if match:
            return match.group(1)
        
        # Padrão alternativo: Host("hostname")
        host_pattern_alt = r'Host\("([^"]+)"\)'
        match = re.search(host_pattern_alt, rule)
        
        if match:
            return match.group(1)
            
        return None
    
    def get_cloudflare_record(self, zone_id: str, api_key: str, name: str) -> Optional[Dict]:
        """
        Verifica se um registro DNS já existe na Cloudflare
        """
        url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        params = {"name": name, "type": "A"}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data["success"] and data["result"]:
                return data["result"][0]
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao verificar registro DNS para {name}: {e}")
            return None
    
    def create_cloudflare_record(self, zone_id: str, api_key: str, name: str, 
                               ip: str, proxied: bool = True) -> bool:
        """
        Cria um registro DNS na Cloudflare
        """
        url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "type": "A",
            "name": name,
            "content": ip,
            "proxied": proxied,
            "ttl": 1 if proxied else 300
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            
            if result["success"]:
                logger.info(f"Registro DNS criado: {name} -> {ip} (proxied: {proxied})")
                return True
            else:
                logger.error(f"Erro ao criar registro DNS: {result.get('errors', [])}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao criar registro DNS para {name}: {e}")
            return False
    
    def get_swarm_node_ip(self) -> str:
        """
        Obtém o IP do nó do Swarm (pode ser customizado conforme sua configuração)
        """
        # Opção 1: IP do líder do swarm
        try:
            swarm_info = self.docker_client.info()
            if 'Swarm' in swarm_info and swarm_info['Swarm']['LocalNodeState'] == 'active':
                # Por padrão, usa o IP público definido na variável de ambiente
                return os.getenv('SWARM_PUBLIC_IP', '0.0.0.0')
        except Exception as e:
            logger.warning(f"Erro ao obter IP do Swarm: {e}")
        
        # Fallback para IP definido em variável de ambiente
        return os.getenv('PUBLIC_IP', '0.0.0.0')
    
    def process_service_labels(self, service) -> None:
        """
        Processa as labels de um serviço e cria registros DNS se necessário
        """
        try:
            service_name = service.name
            labels = service.attrs.get('Spec', {}).get('Labels', {})
            
            if not labels:
                return
            
            # Procura por labels do Traefik relacionadas a rotas
            traefik_rules = []
            proxied_settings = {}
            
            for key, value in labels.items():
                # Labels do Traefik que definem regras de roteamento
                if '.rule' in key and 'Host(' in value:
                    traefik_rules.append(value)
                
                # Label customizada para controlar proxy da Cloudflare
                if key.endswith('.cloudflare.proxied'):
                    # Extrai o nome do router/serviço da label
                    router_name = key.split('.cloudflare.proxied')[0].split('.')[-1]
                    proxied_settings[router_name] = value.lower() == 'true'
            
            # Processa cada regra encontrada
            for rule in traefik_rules:
                hostname = self.extract_hostname_from_rule(rule)
                if not hostname:
                    continue
                
                # Verifica se já foi processado
                service_key = f"{service_name}:{hostname}"
                if service_key in self.processed_services:
                    continue
                
                # Obtém configuração do domínio
                domain_config = self.get_domain_config(hostname)
                if not domain_config:
                    logger.warning(f"Configuração não encontrada para domínio: {hostname}")
                    continue
                
                # Determina se deve usar proxy
                proxied = True  # Padrão
                for router_name, proxy_setting in proxied_settings.items():
                    if router_name in rule or router_name in service_name:
                        proxied = proxy_setting
                        break
                
                # Verifica se o registro já existe
                existing_record = self.get_cloudflare_record(
                    domain_config['zone_id'],
                    domain_config['api_key'],
                    hostname
                )
                
                if existing_record:
                    logger.info(f"Registro DNS já existe: {hostname}")
                    self.processed_services.add(service_key)
                    continue
                
                # Cria o registro DNS
                swarm_ip = self.get_swarm_node_ip()
                if swarm_ip != '0.0.0.0':
                    success = self.create_cloudflare_record(
                        domain_config['zone_id'],
                        domain_config['api_key'],
                        hostname,
                        swarm_ip,
                        proxied
                    )
                    
                    if success:
                        self.processed_services.add(service_key)
                else:
                    logger.error("IP público do Swarm não configurado")
                    
        except Exception as e:
            logger.error(f"Erro ao processar serviço {service.name}: {e}")
    
    def monitor_services(self) -> None:
        """
        Monitora continuamente os serviços do Docker Swarm
        """
        logger.info("Iniciando monitoramento de serviços...")
        
        while True:
            try:
                # Lista todos os serviços
                services = self.docker_client.services.list()
                
                for service in services:
                    self.process_service_labels(service)
                
                logger.debug(f"Verificação concluída. {len(services)} serviços analisados.")
                
            except Exception as e:
                logger.error(f"Erro durante monitoramento: {e}")
            
            time.sleep(self.check_interval)

def load_config_from_env() -> Dict[str, Dict[str, str]]:
    """
    Carrega configuração dos domínios a partir de variáveis de ambiente
    
    Formato esperado:
    CLOUDFLARE_DOMAINS={"example.com": {"zone_id": "xxx", "api_key": "yyy"}}
    """
    config_str = os.getenv('CLOUDFLARE_DOMAINS', '{}')
    try:
        return json.loads(config_str)
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao carregar configuração dos domínios: {e}")
        return {}

def main():
    """
    Função principal
    """
    # Carrega configuração
    domain_config = load_config_from_env()
    
    if not domain_config:
        logger.error("Nenhuma configuração de domínio encontrada. Configure a variável CLOUDFLARE_DOMAINS.")
        return
    
    # Intervalo de verificação (padrão: 30 segundos)
    check_interval = int(os.getenv('CHECK_INTERVAL', '30'))
    
    # Cria e inicia o gerenciador
    manager = CloudflareDNSManager(domain_config, check_interval)
    
    try:
        manager.monitor_services()
    except KeyboardInterrupt:
        logger.info("Parando o monitoramento...")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")

if __name__ == "__main__":
    main()