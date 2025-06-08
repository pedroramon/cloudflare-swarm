import requests
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class CloudflareManager:
    def __init__(self, domain_config: Dict[str, Dict[str, str]]):
        """
        Inicializa o gerenciador da Cloudflare
        
        Args:
            domain_config: Dicionário com configuração dos domínios
                          formato: {"dominio.com": {"zone_id": "xxx", "api_key": "yyy"}}
        """
        self.domain_config = domain_config
    
    def get_domain_config(self, hostname: str) -> Optional[Dict[str, str]]:
        """
        Obtém a configuração do domínio baseado no hostname
        """
        for domain, config in self.domain_config.items():
            if hostname.endswith(domain):
                return config
        return None
    
    def get_record(self, zone_id: str, api_key: str, name: str) -> Optional[Dict]:
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
    
    def create_record(self, zone_id: str, api_key: str, name: str, 
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