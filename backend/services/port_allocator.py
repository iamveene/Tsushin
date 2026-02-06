"""
Port Allocation Service
Phase 8: Multi-Tenant MCP Containerization

Manages dynamic port allocation for WhatsApp MCP containers.
Ensures no port conflicts by checking both database and system.
"""

import socket
import logging
from typing import Set
from sqlalchemy.orm import Session
from models import WhatsAppMCPInstance

logger = logging.getLogger(__name__)


class PortAllocator:
    """Allocates ports for MCP containers with conflict detection"""

    DEFAULT_START_PORT = 8080
    DEFAULT_END_PORT = 8180
    MAX_PORTS = DEFAULT_END_PORT - DEFAULT_START_PORT  # 100 ports

    def __init__(self, start_port: int = DEFAULT_START_PORT, end_port: int = DEFAULT_END_PORT):
        """
        Initialize port allocator

        Args:
            start_port: First port in allocation range (default: 8080)
            end_port: Last port in allocation range (default: 8180)
        """
        self.start_port = start_port
        self.end_port = end_port
        self.port_range = range(start_port, end_port)

    def allocate_port(self, db: Session) -> int:
        """
        Find and allocate an available port

        Args:
            db: Database session

        Returns:
            int: Available port number

        Raises:
            RuntimeError: If no ports available in range
        """
        # Get ports already allocated in database
        used_ports = self._get_used_ports_from_db(db)

        # Find first available port
        for port in self.port_range:
            if port in used_ports:
                logger.debug(f"Port {port} already allocated in database")
                continue

            # Test if port is bindable (not in use by system)
            if self._is_port_available(port):
                logger.info(f"Allocated port {port}")
                return port
            else:
                logger.debug(f"Port {port} in use by system")

        # No ports available
        raise RuntimeError(
            f"No available ports in range {self.start_port}-{self.end_port}. "
            f"Consider cleaning up unused MCP instances or expanding port range."
        )

    def _get_used_ports_from_db(self, db: Session) -> Set[int]:
        """
        Get set of ports already allocated in database

        Args:
            db: Database session

        Returns:
            Set of port numbers
        """
        instances = db.query(WhatsAppMCPInstance.mcp_port).all()
        return {instance.mcp_port for instance in instances}

    def _is_port_available(self, port: int) -> bool:
        """
        Test if port is available for binding

        Args:
            port: Port number to test

        Returns:
            True if port can be bound, False otherwise
        """
        try:
            # Try to bind to 127.0.0.1 (localhost only)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', port))
            sock.close()
            return True
        except OSError as e:
            logger.debug(f"Port {port} not available: {e}")
            return False

    def get_port_usage_stats(self, db: Session) -> dict:
        """
        Get statistics about port allocation

        Args:
            db: Database session

        Returns:
            Dict with usage statistics
        """
        used_ports = self._get_used_ports_from_db(db)
        total_ports = len(self.port_range)
        used_count = len(used_ports)
        available_count = total_ports - used_count
        usage_percent = (used_count / total_ports) * 100 if total_ports > 0 else 0

        return {
            'start_port': self.start_port,
            'end_port': self.end_port,
            'total_ports': total_ports,
            'used_ports': used_count,
            'available_ports': available_count,
            'usage_percent': round(usage_percent, 2),
            'used_port_list': sorted(used_ports),
            'warning': usage_percent > 80,  # Warn when >80% used
        }


# Singleton instance
_port_allocator = None


def get_port_allocator(start_port: int = None, end_port: int = None) -> PortAllocator:
    """
    Get singleton port allocator instance

    Args:
        start_port: Override default start port
        end_port: Override default end port

    Returns:
        PortAllocator instance
    """
    global _port_allocator

    if _port_allocator is None:
        _port_allocator = PortAllocator(
            start_port=start_port or PortAllocator.DEFAULT_START_PORT,
            end_port=end_port or PortAllocator.DEFAULT_END_PORT
        )

    return _port_allocator
