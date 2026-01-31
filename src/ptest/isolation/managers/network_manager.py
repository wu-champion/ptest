"""
Docker网络管理器

提供完整的Docker网络管理功能
"""

import logging
from typing import Dict, Any, List, Optional

try:
    import docker

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

if DOCKER_AVAILABLE:
    from docker.errors import DockerException, APIError, NotFound

from ptest.core import get_logger

logger = get_logger("network_manager")


class NetworkManager:
    """Docker网络管理器"""

    def __init__(self, docker_client, prefix: str = "ptest_"):
        self.client = docker_client
        self.prefix = prefix

    def create_network(
        self,
        network_name: str,
        subnet: str = None,
        driver: str = "bridge",
        internal: bool = False,
        enable_ipv6: bool = False,
        gateway: str = None,
        ip_range: str = None,
        aux_addresses: Dict[str, str] = None,
        dns_servers: List[str] = None,
        dns_search: List[str] = None,
        dns_options: List[str] = None,
        labels: Dict[str, str] = None,
    ) -> Optional[Any]:
        """创建Docker网络"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating network creation: {network_name}"
                )
                return None

            if not self.client:
                logger.error("Docker client not initialized")
                return None

            try:
                existing_network = self.client.networks.get(network_name)
                logger.info(f"Network {network_name} already exists")
                return existing_network
            except NotFound:
                pass

            network_config = {
                "Name": network_name,
                "Driver": driver,
                "Internal": internal,
                "EnableIPv6": enable_ipv6,
            }

            if labels:
                network_config["Labels"] = labels

            # IPAM配置
            ipam_config = {}
            if subnet:
                ipam_config["Subnet"] = subnet

            if gateway:
                ipam_config["Gateway"] = gateway

            if ip_range:
                ipam_config["IPRange"] = ip_range

            if aux_addresses:
                ipam_config["AuxiliaryAddresses"] = aux_addresses

            if ipam_config:
                network_config["IPAM"] = {"Config": [ipam_config]}

            # DNS配置
            if dns_servers:
                network_config["DNS"] = {
                    "Nameservers": dns_servers,
                }
                if dns_search:
                    network_config["DNS"]["Search"] = dns_search
                if dns_options:
                    network_config["DNS"]["Options"] = dns_options

            network = self.client.networks.create(network_config)
            logger.info(f"Created network: {network_name}")
            return network

        except Exception as e:
            logger.error(f"Failed to create network {network_name}: {e}")
            return None

    def remove_network(self, network_name: str, force: bool = False) -> bool:
        """删除Docker网络"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating network removal: {network_name}"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            network = self.client.networks.get(network_name)
            if network:
                network.remove()
                logger.info(f"Removed network: {network_name}")
                return True

            logger.info(f"Network {network_name} not found")
            return False

        except Exception as e:
            logger.error(f"Failed to remove network {network_name}: {e}")
            return False

    def connect_container(
        self,
        network_name: str,
        container_id: str,
        aliases: List[str] = None,
        ipv4_address: str = None,
        ipv6_address: str = None,
        links: List[str] = None,
        link_local_ips: bool = False,
    ) -> bool:
        """将容器连接到网络"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    "Docker SDK not available, simulating network connection"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            network = self.client.networks.get(network_name)
            if not network:
                logger.error(f"Network {network_name} not found")
                return False

            network_config = {}
            if aliases:
                network_config["aliases"] = aliases
            if ipv4_address:
                network_config["ipv4_address"] = ipv4_address
            if ipv6_address:
                network_config["ipv6_address"] = ipv6_address
            if links:
                network_config["links"] = links
            if link_local_ips:
                network_config["link_local_ips"] = link_local_ips

            network.connect(container_id, **network_config)
            logger.info(f"Connected container {container_id} to network {network_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect container to network: {e}")
            return False

    def disconnect_container(
        self, network_name: str, container_id: str, force: bool = False
    ) -> bool:
        """将容器从网络断开"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    "Docker SDK not available, simulating network disconnection"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            network = self.client.networks.get(network_name)
            if not network:
                logger.error(f"Network {network_name} not found")
                return False

            network.disconnect(container_id, force=force)
            logger.info(
                f"Disconnected container {container_id} from network {network_name}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to disconnect container from network: {e}")
            return False

    def list_networks(self) -> List[Dict[str, Any]]:
        """列出所有Docker网络"""
        try:
            if not DOCKER_AVAILABLE:
                return []

            if not self.client:
                return []

            networks = self.client.networks.list()
            result = []

            for net in networks:
                result.append(
                    {
                        "id": net.id,
                        "name": net.name,
                        "driver": net.attrs.get("Driver"),
                        "scope": net.attrs.get("Scope"),
                        "internal": net.attrs.get("Internal", False),
                        "ipv4_subnet": net.attrs.get("IPAM", {})
                        .get("Config", [{}])[0]
                        .get("Subnet"),
                        "labels": net.attrs.get("Labels", {}),
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Failed to list networks: {e}")
            return []

    def prune_networks(self) -> Dict[str, Any]:
        """清理未使用的Docker网络"""
        try:
            if not DOCKER_AVAILABLE:
                return {"NetworksDeleted": []}

            if not self.client:
                return {"NetworksDeleted": []}

            result = self.client.networks.prune()
            logger.info(f"Pruned {len(result.get('NetworksDeleted', []))} networks")
            return result

        except Exception as e:
            logger.error(f"Failed to prune networks: {e}")
            return {"NetworksDeleted": []}

    def inspect_network(self, network_name: str) -> Optional[Dict[str, Any]]:
        """检查Docker网络详细信息"""
        try:
            if not DOCKER_AVAILABLE:
                return None

            if not self.client:
                return None

            network = self.client.networks.get(network_name)
            return network.attrs

        except Exception as e:
            logger.error(f"Failed to inspect network {network_name}: {e}")
            return None
