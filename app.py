#!/usr/bin/env python3
"""
Cloudflare DNS Manager para Docker Swarm
Monitora labels dos serviços e cria registros DNS automaticamente
"""

import json
import logging
import os
from typing import Dict

from docker_manager import DockerManager
from cloudflare_manager import CloudflareManager

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CloudflareDNSManager:
    def __init__(self, domain_config: Dict[str, Dict[str, str]]):
        """
        Inicializa o gerenciador DNS da Cloudflare
        """
        self.docker_manager = DockerManager()
        self.cloudflare_manager = CloudflareManager(domain_config)
        self.processed_services = set()
    
    def process_service(self, service, action: str) -> None:
        """
        Processa um serviço e gerencia seus registros DNS
        """
        try:
            if action == 'remove':
                # TODO: Implementar remoção de registros DNS
                logger.info(f"Serviço removido: {service.name}")
                return
            
            service_info = self.docker_manager.get_service_info(service)
            
            for rule in service_info['rules']:
                hostname = self.docker_manager.extract_hostname_from_rule(rule)
                if not hostname:
                    continue
                
                # Verifica se já foi processado
                service_key = f"{service_info['name']}:{hostname}"
                if service_key in self.processed_services:
                    continue
                
                # Obtém configuração do domínio
                domain_config = self.cloudflare_manager.get_domain_config(hostname)
                if not domain_config:
                    logger.warning(f"Configuração não encontrada para domínio: {hostname}")
                    continue
                
                # Determina se deve usar proxy
                proxied = True  # Padrão
                for router_name, proxy_setting in service_info['proxied_settings'].items():
                    if router_name in rule or router_name in service_info['name']:
                        proxied = proxy_setting
                        break
                
                # Verifica se o registro já existe
                existing_record = self.cloudflare_manager.get_record(
                    domain_config['zone_id'],
                    domain_config['api_key'],
                    hostname
                )
                
                if existing_record:
                    logger.info(f"Registro DNS já existe: {hostname}")
                    self.processed_services.add(service_key)
                    continue
                
                # Cria o registro DNS
                swarm_ip = self.docker_manager.get_swarm_node_ip()
                if swarm_ip != '0.0.0.0':
                    success = self.cloudflare_manager.create_record(
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
    
    def start(self) -> None:
        """
        Inicia o monitoramento de serviços
        """
        self.docker_manager.monitor_services(self.process_service)

def load_config_from_env() -> Dict[str, Dict[str, str]]:
    """
    Carrega configuração dos domínios a partir de variáveis de ambiente
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
    
    # Cria e inicia o gerenciador
    manager = CloudflareDNSManager(domain_config)
    
    try:
        manager.start()
    except KeyboardInterrupt:
        logger.info("Parando o monitoramento...")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")

if __name__ == "__main__":
    main()