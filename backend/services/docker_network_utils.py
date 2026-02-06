"""
Docker Network Utilities

Handles dynamic discovery of the tsushin Docker network name.
Docker Compose prefixes network names with the project name (derived from
the directory name), so the actual network name varies by installation.
This module resolves the correct name at runtime.
"""

import logging
import docker

logger = logging.getLogger(__name__)

# Canonical network name (matches docker-compose.yml `name:` property)
CANONICAL_NETWORK_NAME = "tsushin-network"
# Suffix used to identify tsushin networks in legacy installations
NETWORK_SUFFIX = "tsushin-network"
# Backend container has a fixed name via docker-compose.yml container_name
BACKEND_CONTAINER_NAME = "tsushin-backend"

_cached_network_name: str = ""


def resolve_tsushin_network_name(docker_client: docker.DockerClient) -> str:
    """
    Discover the actual Docker network name for the tsushin network.

    Handles both new installations (explicit name: tsushin-network) and
    legacy installations (prefixed like tsushin-installer_tsushin-network).
    Results are cached after first successful discovery.
    """
    global _cached_network_name

    if _cached_network_name:
        return _cached_network_name

    # Strategy 1: Canonical name (new installations with name: property)
    try:
        docker_client.networks.get(CANONICAL_NETWORK_NAME)
        _cached_network_name = CANONICAL_NETWORK_NAME
        logger.info(f"Found canonical network: {CANONICAL_NETWORK_NAME}")
        return _cached_network_name
    except docker.errors.NotFound:
        pass

    # Strategy 2: Inspect backend container (always has fixed container_name)
    try:
        backend = docker_client.containers.get(BACKEND_CONTAINER_NAME)
        backend.reload()
        networks = backend.attrs.get("NetworkSettings", {}).get("Networks", {})
        for net_name in networks:
            if net_name.endswith(NETWORK_SUFFIX):
                _cached_network_name = net_name
                logger.info(f"Discovered network from backend container: {net_name}")
                return _cached_network_name
    except docker.errors.NotFound:
        logger.debug(f"Backend container '{BACKEND_CONTAINER_NAME}' not found")
    except Exception as e:
        logger.debug(f"Backend container inspection failed: {e}")

    # Strategy 3: Pattern search across all networks
    try:
        for network in docker_client.networks.list():
            if network.name.endswith(NETWORK_SUFFIX):
                _cached_network_name = network.name
                logger.info(f"Discovered network by search: {network.name}")
                return _cached_network_name
    except Exception as e:
        logger.debug(f"Network search failed: {e}")

    # Fallback: canonical name (will be created if needed)
    _cached_network_name = CANONICAL_NETWORK_NAME
    logger.info(f"Using canonical network name: {CANONICAL_NETWORK_NAME}")
    return _cached_network_name
