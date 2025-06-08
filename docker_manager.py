import docker
import logging
import os
import re
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

class DockerManager:
    def __init__(self):
        """
        Inicializa o gerenciador do Docker
        """
        self.docker_client = docker.from_env()
        self.processed_services: Set[str] = set()
    
    def get_swarm_node_ip(self) -> str:
        """
        Obtém o IP do nó do Swarm
        """
        try:
            swarm_info = self.docker_client.info()
            if 'Swarm' in swarm_info and swarm_info['Swarm']['LocalNodeState'] == 'active':
                return os.getenv('SWARM_PUBLIC_IP', '0.0.0.0')
        except Exception as e:
            logger.warning(f"Erro ao obter IP do Swarm: {e}")
        
        return os.getenv('PUBLIC_IP', '0.0.0.0')
    
    def extract_hostname_from_rule(self, rule: str) -> Optional[str]:
        """
        Extrai o hostname da regra do Traefik
        """
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
    
    def get_service_info(self, service) -> Dict:
        """
        Extrai informações relevantes de um serviço
        """
        service_name = service.name
        labels = service.attrs.get('Spec', {}).get('Labels', {})
        
        traefik_rules = []
        proxied_settings = {}
        
        for key, value in labels.items():
            if '.rule' in key and 'Host(' in value:
                traefik_rules.append(value)
            
            if key.endswith('.cloudflare.proxied'):
                router_name = key.split('.cloudflare.proxied')[0].split('.')[-1]
                proxied_settings[router_name] = value.lower() == 'true'
        
        return {
            'name': service_name,
            'rules': traefik_rules,
            'proxied_settings': proxied_settings
        }
    
    def monitor_services(self, callback) -> None:
        """
        Monitora eventos do Docker Swarm em tempo real
        
        Args:
            callback: Função chamada quando um serviço é criado/atualizado/removido
        """
        logger.info("Iniciando monitoramento de eventos do Docker...")
        
        try:
            # Processa serviços existentes primeiro
            services = self.docker_client.services.list()
            for service in services:
                callback(service, 'create')
            
            # Escuta eventos de serviços
            for event in self.docker_client.events(
                filters={'type': 'service'},
                decode=True
            ):
                try:
                    if event['Type'] == 'service':
                        service_id = event['Actor']['ID']
                        service = self.docker_client.services.get(service_id)
                        
                        if event['Action'] in ['create', 'update', 'remove']:
                            callback(service, event['Action'])
                            
                except Exception as e:
                    logger.error(f"Erro ao processar evento: {e}")
                    
        except Exception as e:
            logger.error(f"Erro fatal no monitoramento: {e}")
            raise 