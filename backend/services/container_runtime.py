"""
Container Runtime Abstraction Layer
Phase: GKE Readiness

Provides a pluggable interface for container orchestration backends.
Currently supports Docker (default, local dev) with a Kubernetes stub
for future GKE deployment.

Usage:
    from services.container_runtime import get_container_runtime
    runtime = get_container_runtime()
    container = runtime.create_container(...)
"""

import os
import re
import logging
import shlex
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class ContainerRuntime(ABC):
    """
    Abstract base class for container runtime backends.

    All container lifecycle operations go through this interface,
    allowing the application to run on Docker (local) or Kubernetes (GKE)
    without changing service-layer code.
    """

    @abstractmethod
    def create_container(
        self,
        image: str,
        name: str,
        *,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        environment: Optional[Dict[str, str]] = None,
        ports: Optional[Dict[str, Any]] = None,
        network: Optional[str] = None,
        restart_policy: Optional[Dict[str, str]] = None,
        mem_limit: Optional[str] = None,
        memswap_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
        command: Optional[List[str]] = None,
        labels: Optional[Dict[str, str]] = None,
        detach: bool = True,
        security_opt: Optional[List[str]] = None,
        cap_drop: Optional[List[str]] = None,
        pids_limit: Optional[int] = None,
    ) -> Any:
        """
        Create and start a container.

        Args:
            image: Container image name/tag
            name: Container name
            volumes: Volume mount mapping {host_path: {bind, mode}}
            environment: Environment variables
            ports: Port mapping {container_port: (host_ip, host_port)}
            network: Network name to attach to
            restart_policy: Restart policy dict (e.g. {"Name": "unless-stopped"})
            mem_limit: Memory limit (e.g. "2g")
            memswap_limit: Memory + swap limit
            cpu_quota: CPU quota in microseconds
            command: Command to run in container
            labels: Container labels
            detach: Run in background (always True for our use cases)
            security_opt: Security options (e.g. ["no-new-privileges:true"])
            cap_drop: Linux capabilities to drop (e.g. ["ALL"])
            pids_limit: Maximum number of PIDs in the container

        Returns:
            Container object (Docker Container or K8s Pod wrapper)
        """
        ...

    @abstractmethod
    def get_container(self, name_or_id: str) -> Any:
        """
        Get a container by name or ID.

        Args:
            name_or_id: Container name or ID

        Returns:
            Container object

        Raises:
            ContainerNotFoundError: If container doesn't exist
        """
        ...

    @abstractmethod
    def stop_container(self, name_or_id: str, timeout: int = 30) -> None:
        """
        Stop a running container.

        Args:
            name_or_id: Container name or ID
            timeout: Graceful shutdown timeout in seconds

        Raises:
            ContainerNotFoundError: If container doesn't exist
        """
        ...

    @abstractmethod
    def remove_container(self, name_or_id: str, force: bool = False) -> None:
        """
        Remove a container.

        Args:
            name_or_id: Container name or ID
            force: Force remove even if running

        Raises:
            ContainerNotFoundError: If container doesn't exist
        """
        ...

    @abstractmethod
    def start_container(self, name_or_id: str) -> None:
        """
        Start a stopped container.

        Args:
            name_or_id: Container name or ID

        Raises:
            ContainerNotFoundError: If container doesn't exist
        """
        ...

    @abstractmethod
    def restart_container(self, name_or_id: str, timeout: int = 30) -> None:
        """
        Restart a container.

        Args:
            name_or_id: Container name or ID
            timeout: Graceful shutdown timeout in seconds
        """
        ...

    @abstractmethod
    def get_container_status(self, name_or_id: str) -> str:
        """
        Get container status string.

        Args:
            name_or_id: Container name or ID

        Returns:
            Status string: "running", "exited", "not_found", etc.
        """
        ...

    @abstractmethod
    def get_container_attrs(self, name_or_id: str) -> Dict[str, Any]:
        """
        Get full container attributes/metadata.

        Args:
            name_or_id: Container name or ID

        Returns:
            Dict of container attributes (image tags, state, created timestamp, etc.)
        """
        ...

    @abstractmethod
    def exec_run(
        self,
        name_or_id: str,
        cmd: List[str],
        *,
        workdir: Optional[str] = None,
        user: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        demux: bool = False,
        detach: bool = False,
    ) -> Any:
        """
        Execute a command inside a running container.

        Args:
            name_or_id: Container name or ID
            cmd: Command and arguments
            workdir: Working directory inside container
            user: User to run as (e.g. "root")
            environment: Additional environment variables
            demux: Separate stdout/stderr
            detach: Run in background

        Returns:
            Exec result with exit_code and output
        """
        ...

    @abstractmethod
    def exec_create_and_start(
        self,
        name_or_id: str,
        cmd: List[str],
        *,
        workdir: Optional[str] = None,
        stream: bool = False,
        demux: bool = False,
    ) -> Any:
        """
        Low-level exec create + start for streaming use cases.

        Args:
            name_or_id: Container name or ID
            cmd: Command and arguments
            workdir: Working directory
            stream: Enable output streaming
            demux: Separate stdout/stderr

        Returns:
            Tuple of (exec_id, output_generator_or_bytes)
        """
        ...

    @abstractmethod
    def exec_inspect(self, exec_id: str) -> Dict[str, Any]:
        """
        Inspect an exec instance to get exit code etc.

        Args:
            exec_id: Exec instance ID

        Returns:
            Dict with ExitCode and other exec metadata
        """
        ...

    @abstractmethod
    def commit_container(
        self,
        name_or_id: str,
        repository: str,
        tag: str,
        message: str = "",
    ) -> Any:
        """
        Commit a container's current state as a new image.

        Args:
            name_or_id: Container name or ID
            repository: Image repository name
            tag: Image tag
            message: Commit message

        Returns:
            Image object/reference
        """
        ...

    @abstractmethod
    def image_exists(self, image_name: str) -> bool:
        """
        Check if a container image exists locally.

        Args:
            image_name: Full image name with tag

        Returns:
            True if image exists
        """
        ...

    @abstractmethod
    def remove_image(self, image_name: str, force: bool = False) -> None:
        """
        Remove a container image.

        Args:
            image_name: Full image name with tag
            force: Force removal
        """
        ...

    @abstractmethod
    def list_containers(self, filters: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        List containers, optionally filtered.

        Args:
            filters: Docker-style filters dict

        Returns:
            List of container objects
        """
        ...

    @abstractmethod
    def get_logs(self, name_or_id: str, tail: int = 100) -> str:
        """
        Get container logs.

        Args:
            name_or_id: Container name or ID
            tail: Number of lines from the end

        Returns:
            Log output as string
        """
        ...

    @abstractmethod
    def health_check(self, name_or_id: str) -> Dict[str, Any]:
        """
        Perform a basic health check on a container.

        Args:
            name_or_id: Container name or ID

        Returns:
            Dict with status, container_state, and optional error
        """
        ...

    @abstractmethod
    def get_or_create_network(self, network_name: str) -> Any:
        """
        Get an existing network or create it.

        Args:
            network_name: Network name

        Returns:
            Network object
        """
        ...

    @abstractmethod
    def ensure_container_on_network(self, name_or_id: str, network_name: str) -> None:
        """
        Ensure a container is connected to a specific network.

        Args:
            name_or_id: Container name or ID
            network_name: Network to connect to
        """
        ...

    @abstractmethod
    def get_container_network_ip(self, name_or_id: str, network_name: str) -> str:
        """
        Get a container's IP address on a specific network.

        Args:
            name_or_id: Container name or ID
            network_name: Network name

        Returns:
            IP address string, or empty string if not found
        """
        ...


class ContainerNotFoundError(Exception):
    """Raised when a container is not found by the runtime."""
    pass


class ContainerRuntimeError(Exception):
    """Raised for general container runtime errors."""
    pass


# ---------------------------------------------------------------------------
# Docker Runtime — wraps the existing docker-py behavior exactly
# ---------------------------------------------------------------------------

class DockerRuntime(ContainerRuntime):
    """
    Docker runtime implementation using docker-py.

    This preserves the exact behavior of the existing direct Docker calls
    in ToolboxContainerService and MCPContainerManager.
    """

    def __init__(self):
        import docker as docker_lib
        try:
            self._client = docker_lib.from_env()
            logger.info("DockerRuntime: Docker client initialized")
        except docker_lib.errors.DockerException as e:
            logger.error(f"DockerRuntime: Failed to initialize Docker client: {e}")
            raise RuntimeError(
                f"Docker is not available. Please ensure Docker is installed and running. Error: {e}"
            )

    @property
    def raw_client(self):
        """Access the underlying docker.DockerClient for advanced/legacy operations."""
        return self._client

    def create_container(
        self,
        image: str,
        name: str,
        *,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        environment: Optional[Dict[str, str]] = None,
        ports: Optional[Dict[str, Any]] = None,
        network: Optional[str] = None,
        restart_policy: Optional[Dict[str, str]] = None,
        mem_limit: Optional[str] = None,
        memswap_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
        command: Optional[List[str]] = None,
        labels: Optional[Dict[str, str]] = None,
        detach: bool = True,
        security_opt: Optional[List[str]] = None,
        cap_drop: Optional[List[str]] = None,
        pids_limit: Optional[int] = None,
    ) -> Any:
        import docker as docker_lib
        try:
            kwargs = {
                "image": image,
                "name": name,
                "detach": detach,
            }
            if volumes is not None:
                kwargs["volumes"] = volumes
            if environment is not None:
                kwargs["environment"] = environment
            if ports is not None:
                kwargs["ports"] = ports
            if network is not None:
                kwargs["network"] = network
            if restart_policy is not None:
                kwargs["restart_policy"] = restart_policy
            if mem_limit is not None:
                kwargs["mem_limit"] = mem_limit
            if memswap_limit is not None:
                kwargs["memswap_limit"] = memswap_limit
            if cpu_quota is not None:
                kwargs["cpu_quota"] = cpu_quota
            if command is not None:
                kwargs["command"] = command
            if labels is not None:
                kwargs["labels"] = labels
            if security_opt is not None:
                kwargs["security_opt"] = security_opt
            if cap_drop is not None:
                kwargs["cap_drop"] = cap_drop
            if pids_limit is not None:
                kwargs["pids_limit"] = pids_limit

            container = self._client.containers.run(**kwargs)
            logger.info(f"DockerRuntime: Created container {name} (ID: {container.id})")
            return container
        except docker_lib.errors.APIError as e:
            logger.error(f"DockerRuntime: Failed to create container {name}: {e}")
            raise ContainerRuntimeError(f"Failed to create container: {e}")

    def get_container(self, name_or_id: str) -> Any:
        import docker as docker_lib
        try:
            return self._client.containers.get(name_or_id)
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Docker API error: {e}")

    def stop_container(self, name_or_id: str, timeout: int = 30) -> None:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            container.stop(timeout=timeout)
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Failed to stop container: {e}")

    def remove_container(self, name_or_id: str, force: bool = False) -> None:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            container.remove(force=force)
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Failed to remove container: {e}")

    def start_container(self, name_or_id: str) -> None:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            container.start()
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Failed to start container: {e}")

    def restart_container(self, name_or_id: str, timeout: int = 30) -> None:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            container.restart(timeout=timeout)
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Failed to restart container: {e}")

    def get_container_status(self, name_or_id: str) -> str:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            container.reload()
            return container.status
        except docker_lib.errors.NotFound:
            return "not_found"
        except docker_lib.errors.APIError:
            return "error"

    def get_container_attrs(self, name_or_id: str) -> Dict[str, Any]:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            container.reload()
            return {
                "id": container.id,
                "name": container.name,
                "status": container.status,
                "image_tags": container.image.tags if container.image.tags else [str(container.image.id)[:12]],
                "created": container.attrs.get("Created"),
                "state": container.attrs.get("State", {}),
                "network_settings": container.attrs.get("NetworkSettings", {}),
            }
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Docker API error: {e}")

    def exec_run(
        self,
        name_or_id: str,
        cmd: List[str],
        *,
        workdir: Optional[str] = None,
        user: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        demux: bool = False,
        detach: bool = False,
    ) -> Any:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            kwargs = {"cmd": cmd, "demux": demux, "detach": detach}
            if workdir is not None:
                kwargs["workdir"] = workdir
            if user is not None:
                kwargs["user"] = user
            if environment is not None:
                kwargs["environment"] = environment
            return container.exec_run(**kwargs)
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Docker API error during exec: {e}")

    def exec_create_and_start(
        self,
        name_or_id: str,
        cmd: List[str],
        *,
        workdir: Optional[str] = None,
        stream: bool = False,
        demux: bool = False,
    ) -> Any:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            exec_id = container.client.api.exec_create(
                container.id,
                cmd,
                workdir=workdir,
                tty=False,
                stdout=True,
                stderr=True,
            )
            output = container.client.api.exec_start(exec_id, stream=stream, demux=demux)
            return exec_id, output
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Docker API error during exec: {e}")

    def exec_inspect(self, exec_id: str) -> Dict[str, Any]:
        return self._client.api.exec_inspect(exec_id)

    def commit_container(
        self,
        name_or_id: str,
        repository: str,
        tag: str,
        message: str = "",
    ) -> Any:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            return container.commit(repository=repository, tag=tag, message=message)
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Failed to commit container: {e}")

    def image_exists(self, image_name: str) -> bool:
        import docker as docker_lib
        try:
            self._client.images.get(image_name)
            return True
        except docker_lib.errors.ImageNotFound:
            return False

    def remove_image(self, image_name: str, force: bool = False) -> None:
        import docker as docker_lib
        try:
            self._client.images.remove(image_name, force=force)
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Failed to remove image: {e}")

    def list_containers(self, filters: Optional[Dict[str, Any]] = None) -> List[Any]:
        kwargs = {}
        if filters:
            kwargs["filters"] = filters
        return self._client.containers.list(**kwargs)

    def get_logs(self, name_or_id: str, tail: int = 100) -> str:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            logs = container.logs(tail=tail)
            return logs.decode("utf-8", errors="replace") if isinstance(logs, bytes) else str(logs)
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except docker_lib.errors.APIError as e:
            raise ContainerRuntimeError(f"Failed to get logs: {e}")

    def health_check(self, name_or_id: str) -> Dict[str, Any]:
        import docker as docker_lib
        result = {"status": "unknown", "container_state": "unknown", "error": None}
        try:
            container = self._client.containers.get(name_or_id)
            container.reload()
            result["container_state"] = container.status
            if container.status == "running":
                result["status"] = "healthy"
            elif container.status == "exited":
                result["status"] = "stopped"
            else:
                result["status"] = container.status
        except docker_lib.errors.NotFound:
            result["status"] = "not_found"
            result["container_state"] = "not_found"
            result["error"] = "Container not found"
        except docker_lib.errors.APIError as e:
            result["status"] = "error"
            result["error"] = str(e)
        return result

    def get_or_create_network(self, network_name: str) -> Any:
        import docker as docker_lib
        try:
            return self._client.networks.get(network_name)
        except docker_lib.errors.NotFound:
            logger.info(f"DockerRuntime: Creating network {network_name}")
            return self._client.networks.create(network_name, driver="bridge")

    def ensure_container_on_network(self, name_or_id: str, network_name: str) -> None:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            container.reload()
            networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
            if network_name not in networks:
                logger.info(f"DockerRuntime: Connecting {name_or_id} to {network_name}")
                network = self.get_or_create_network(network_name)
                network.connect(container)
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except Exception as e:
            logger.error(f"DockerRuntime: Failed to ensure container on network: {e}")

    def get_container_network_ip(self, name_or_id: str, network_name: str) -> str:
        import docker as docker_lib
        try:
            container = self._client.containers.get(name_or_id)
            container.reload()
            networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
            if network_name in networks:
                return networks[network_name].get("IPAddress", "")
            # Fallback: first available network IP
            for net_name, net_config in networks.items():
                ip = net_config.get("IPAddress", "")
                if ip:
                    logger.warning(
                        f"DockerRuntime: Container not on {network_name}, using {net_name} IP: {ip}"
                    )
                    return ip
            return ""
        except docker_lib.errors.NotFound:
            raise ContainerNotFoundError(f"Container {name_or_id} not found")
        except Exception as e:
            logger.error(f"DockerRuntime: Failed to get container IP: {e}")
            return ""


# ---------------------------------------------------------------------------
# Kubernetes Runtime — GKE / K8s implementation
# ---------------------------------------------------------------------------


class _K8sExecResult:
    """Mimics the Docker exec_run result interface (exit_code, output)."""

    def __init__(self, exit_code: int, output):
        self.exit_code = exit_code
        self.output = output


class _K8sPodWrapper:
    """
    Lightweight wrapper around a K8s Pod that exposes the same attributes
    that service-layer code reads from Docker container objects (id, name, image).
    """

    def __init__(self, pod):
        self._pod = pod
        self.id = pod.metadata.uid
        self.name = pod.metadata.name
        self.status = self._translate_phase(pod.status.phase if pod.status else None)
        # Best-effort image tag from the first container spec
        self.image = ""
        if pod.spec and pod.spec.containers:
            self.image = pod.spec.containers[0].image or ""

    @staticmethod
    def _translate_phase(phase: Optional[str]) -> str:
        mapping = {
            "Running": "running",
            "Pending": "pending",
            "Succeeded": "exited",
            "Failed": "exited",
        }
        return mapping.get(phase, "unknown") if phase else "unknown"


class K8sRuntime(ContainerRuntime):
    """
    Kubernetes runtime implementation for GKE deployment.

    Maps Docker container lifecycle operations to K8s Deployments + Services.
    Long-running containers (MCP instances, toolboxes) become single-replica
    Deployments; port bindings become ClusterIP Services.

    Configuration env vars:
        TSN_K8S_NAMESPACE          — target namespace (default: tsushin)
        TSN_K8S_IMAGE_PULL_POLICY  — IfNotPresent | Always (default: IfNotPresent)
    """

    # Standard labels applied to every resource we create
    MANAGED_BY = "tsushin"

    def __init__(self):
        from kubernetes import client as k8s_client, config as k8s_config
        from kubernetes.client.rest import ApiException  # noqa: F401

        # Store references for use throughout the class
        self._k8s_client_module = k8s_client
        self._ApiException = ApiException

        # Try in-cluster config first (GKE), fall back to kubeconfig (local dev)
        try:
            k8s_config.load_incluster_config()
            logger.info("K8sRuntime: Loaded in-cluster Kubernetes config")
        except k8s_config.ConfigException:
            try:
                k8s_config.load_kube_config()
                logger.info("K8sRuntime: Loaded kubeconfig (local dev)")
            except k8s_config.ConfigException as e:
                raise RuntimeError(
                    f"Cannot configure Kubernetes client. Ensure you are running "
                    f"inside a cluster or have a valid kubeconfig. Error: {e}"
                )

        self._core_v1 = k8s_client.CoreV1Api()
        self._apps_v1 = k8s_client.AppsV1Api()

        self._namespace = os.getenv("TSN_K8S_NAMESPACE", "tsushin")
        self._image_pull_policy = os.getenv("TSN_K8S_IMAGE_PULL_POLICY", "IfNotPresent")

        # Cache for exec exit codes — K8s stream returns exit code inline,
        # so we stash it here for exec_inspect() lookups.
        self._exec_exit_codes: Dict[str, int] = {}
        self._exec_lock = threading.Lock()

        logger.info(
            f"K8sRuntime: Initialized (namespace={self._namespace}, "
            f"pull_policy={self._image_pull_policy})"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """
        Convert a Docker-style container name to a K8s-safe DNS label.
        K8s names must be lowercase, alphanumeric + hyphens, max 63 chars,
        starting and ending with an alphanumeric character.
        """
        sanitized = re.sub(r"[^a-z0-9\-]", "-", name.lower())
        sanitized = re.sub(r"-+", "-", sanitized).strip("-")
        sanitized = sanitized[:63]
        if not sanitized:
            raise ValueError(f"Container name '{name}' cannot be sanitized to a valid K8s name")
        return sanitized

    def _standard_labels(
        self, name: str, extra: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Build the standard label set for a resource."""
        labels = {
            "app.kubernetes.io/managed-by": self.MANAGED_BY,
            "tsushin.io/container-name": self._sanitize_name(name),
        }
        if extra:
            labels.update(extra)
        return labels

    def _label_selector(self, name: str) -> str:
        safe = self._sanitize_name(name)
        return f"tsushin.io/container-name={safe}"

    def _svc_name(self, name: str) -> str:
        """Derive a predictable Service name from a container name."""
        return f"{self._sanitize_name(name)}-svc"

    def _find_pod(self, name: str):
        """
        Find the Pod owned by the Deployment for *name*.
        Returns the first Ready (or at least existing) pod, or raises
        ContainerNotFoundError.
        """
        selector = self._label_selector(name)
        try:
            pods = self._core_v1.list_namespaced_pod(
                namespace=self._namespace, label_selector=selector
            )
        except self._ApiException as e:
            raise ContainerRuntimeError(f"K8s API error listing pods: {e}")

        if not pods.items:
            raise ContainerNotFoundError(
                f"No pod found for container '{name}' (selector: {selector})"
            )
        # Prefer a Running pod; fall back to any pod
        for pod in pods.items:
            if pod.status and pod.status.phase == "Running":
                return pod
        return pods.items[0]

    def _get_deployment(self, name: str):
        """Get the Deployment for *name*, or raise ContainerNotFoundError."""
        dep_name = self._sanitize_name(name)
        try:
            return self._apps_v1.read_namespaced_deployment(
                name=dep_name, namespace=self._namespace
            )
        except self._ApiException as e:
            if e.status == 404:
                raise ContainerNotFoundError(f"Deployment '{dep_name}' not found")
            raise ContainerRuntimeError(f"K8s API error: {e}")

    def _scale_deployment(self, name: str, replicas: int) -> None:
        dep_name = self._sanitize_name(name)
        body = {"spec": {"replicas": replicas}}
        try:
            self._apps_v1.patch_namespaced_deployment_scale(
                name=dep_name, namespace=self._namespace, body=body
            )
        except self._ApiException as e:
            if e.status == 404:
                raise ContainerNotFoundError(f"Deployment '{dep_name}' not found")
            raise ContainerRuntimeError(f"Failed to scale deployment: {e}")

    def _wait_for_pod_ready(self, name: str, timeout: int = 120) -> None:
        """Poll until at least one pod for the deployment is Running."""
        selector = self._label_selector(name)
        deadline = time.time() + timeout
        while time.time() < deadline:
            pods = self._core_v1.list_namespaced_pod(
                namespace=self._namespace, label_selector=selector
            )
            for pod in pods.items:
                if pod.status and pod.status.phase == "Running":
                    return
            time.sleep(2)
        logger.warning(f"K8sRuntime: Pod for '{name}' did not become Ready within {timeout}s")

    def _build_volume_specs(self, volumes: Optional[Dict[str, Dict[str, str]]] = None):
        """
        Convert Docker-style volume dict to K8s volume + volumeMount specs.

        Docker format:
            {host_path_or_pvc: {"bind": container_path, "mode": "rw"}}

        Mapping rules:
            - Named volumes (no '/' prefix) -> PVC references
            - Host paths -> emptyDir (data is ephemeral in K8s; persistent storage
              must be handled via PVCs in the Helm chart)
        """
        k8s_client = self._k8s_client_module
        k8s_volumes = []
        k8s_mounts = []

        if not volumes:
            return k8s_volumes, k8s_mounts

        for idx, (source, mount_spec) in enumerate(volumes.items()):
            container_path = mount_spec.get("bind", mount_spec) if isinstance(mount_spec, dict) else mount_spec
            mode_str = mount_spec.get("mode", "rw") if isinstance(mount_spec, dict) else "rw"
            read_only = "ro" in mode_str.split(",")

            vol_name = f"vol-{idx}"

            if "/" not in source and not source.startswith("."):
                # Named volume -> assume a PVC with the same name exists
                k8s_volumes.append(
                    k8s_client.V1Volume(
                        name=vol_name,
                        persistent_volume_claim=k8s_client.V1PersistentVolumeClaimVolumeSource(
                            claim_name=source, read_only=read_only
                        ),
                    )
                )
            else:
                # Host path or relative path -> emptyDir (ephemeral)
                # In production, the Helm chart should provide PVCs instead
                k8s_volumes.append(
                    k8s_client.V1Volume(
                        name=vol_name,
                        empty_dir=k8s_client.V1EmptyDirVolumeSource(),
                    )
                )

            k8s_mounts.append(
                k8s_client.V1VolumeMount(
                    name=vol_name,
                    mount_path=container_path,
                    read_only=read_only,
                )
            )

        return k8s_volumes, k8s_mounts

    def _build_resource_requirements(
        self,
        mem_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
    ):
        """Convert Docker resource limits to K8s resource requirements."""
        k8s_client = self._k8s_client_module
        limits = {}
        if mem_limit:
            # Docker format: "2g" -> K8s: "2Gi"
            limits["memory"] = mem_limit.replace("g", "Gi").replace("m", "Mi")
        if cpu_quota:
            # Docker cpu_quota is in microseconds per 100ms period (100000 = 1 CPU)
            cpu_cores = cpu_quota / 100000
            limits["cpu"] = str(cpu_cores)
        if limits:
            return k8s_client.V1ResourceRequirements(limits=limits)
        return None

    def _build_restart_policy_strategy(self, restart_policy: Optional[Dict[str, str]] = None):
        """Map Docker restart_policy to K8s Deployment strategy (always restarts)."""
        # Deployments inherently restart; this is a no-op conceptually.
        # We return RollingUpdate as default.
        k8s_client = self._k8s_client_module
        return k8s_client.V1DeploymentStrategy(type="RollingUpdate")

    def _parse_ports(self, ports: Optional[Dict[str, Any]] = None):
        """
        Convert Docker port mapping to K8s container ports and Service spec.

        Docker format: {"8080/tcp": ("127.0.0.1", 8080)}
        Returns: (container_ports, service_ports)
        """
        k8s_client = self._k8s_client_module
        container_ports = []
        service_ports = []

        if not ports:
            return container_ports, service_ports

        for container_port_spec, host_binding in ports.items():
            # Parse "8080/tcp" or "8080"
            parts = str(container_port_spec).split("/")
            container_port = int(parts[0])
            protocol = (parts[1] if len(parts) > 1 else "TCP").upper()

            # Host binding can be (ip, port), port, or None
            if isinstance(host_binding, (list, tuple)):
                target_port = int(host_binding[1]) if len(host_binding) > 1 else container_port
            elif host_binding is not None:
                target_port = int(host_binding)
            else:
                target_port = container_port

            container_ports.append(
                k8s_client.V1ContainerPort(
                    container_port=container_port, protocol=protocol
                )
            )
            service_ports.append(
                k8s_client.V1ServicePort(
                    port=target_port,
                    target_port=container_port,
                    protocol=protocol,
                    name=f"port-{container_port}",
                )
            )

        return container_ports, service_ports

    # ------------------------------------------------------------------
    # ContainerRuntime interface
    # ------------------------------------------------------------------

    def create_container(
        self,
        image: str,
        name: str,
        *,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        environment: Optional[Dict[str, str]] = None,
        ports: Optional[Dict[str, Any]] = None,
        network: Optional[str] = None,
        restart_policy: Optional[Dict[str, str]] = None,
        mem_limit: Optional[str] = None,
        memswap_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
        command: Optional[List[str]] = None,
        labels: Optional[Dict[str, str]] = None,
        detach: bool = True,
        security_opt: Optional[List[str]] = None,
        cap_drop: Optional[List[str]] = None,
        pids_limit: Optional[int] = None,
    ) -> Any:
        k8s_client = self._k8s_client_module
        dep_name = self._sanitize_name(name)

        # Extract tenant-id from labels or environment for labelling
        tenant_id = ""
        if labels and "tenant_id" in labels:
            tenant_id = labels["tenant_id"]
        elif environment and "TENANT_ID" in environment:
            tenant_id = environment["TENANT_ID"]

        extra_labels = {}
        if tenant_id:
            extra_labels["tsushin.io/tenant-id"] = self._sanitize_name(tenant_id)
        if labels:
            # Sanitize user labels to be K8s-safe values
            for k, v in labels.items():
                safe_k = re.sub(r"[^a-zA-Z0-9_./-]", "-", k)
                safe_v = re.sub(r"[^a-zA-Z0-9_./-]", "-", str(v))[:63]
                extra_labels[safe_k] = safe_v

        all_labels = self._standard_labels(name, extra_labels)

        # Environment variables
        env_list = []
        if environment:
            for k, v in environment.items():
                env_list.append(k8s_client.V1EnvVar(name=k, value=str(v)))

        # Volumes
        k8s_volumes, k8s_mounts = self._build_volume_specs(volumes)

        # Ports
        container_ports, service_ports = self._parse_ports(ports)

        # Resource limits
        resources = self._build_resource_requirements(mem_limit, cpu_quota)

        # Security context for container hardening
        security_context = None
        if cap_drop or security_opt:
            sc_kwargs = {}
            if cap_drop:
                sc_kwargs["capabilities"] = k8s_client.V1Capabilities(drop=cap_drop)
            if security_opt:
                # Map "no-new-privileges:true" to K8s allowPrivilegeEscalation=False
                for opt in security_opt:
                    if "no-new-privileges" in opt.lower():
                        sc_kwargs["allow_privilege_escalation"] = False
            if sc_kwargs:
                security_context = k8s_client.V1SecurityContext(**sc_kwargs)

        # Container spec
        container_spec = k8s_client.V1Container(
            name=dep_name,
            image=image,
            image_pull_policy=self._image_pull_policy,
            env=env_list or None,
            ports=container_ports or None,
            volume_mounts=k8s_mounts or None,
            resources=resources,
            command=command or None,
            security_context=security_context,
        )

        # Pod spec
        pod_spec = k8s_client.V1PodSpec(
            containers=[container_spec],
            volumes=k8s_volumes or None,
            restart_policy="Always",
        )

        # Pod template
        template = k8s_client.V1PodTemplateSpec(
            metadata=k8s_client.V1ObjectMeta(labels=all_labels),
            spec=pod_spec,
        )

        # Deployment spec
        dep_spec = k8s_client.V1DeploymentSpec(
            replicas=1,
            selector=k8s_client.V1LabelSelector(
                match_labels={"tsushin.io/container-name": self._sanitize_name(name)}
            ),
            template=template,
            strategy=self._build_restart_policy_strategy(restart_policy),
        )

        deployment = k8s_client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=k8s_client.V1ObjectMeta(
                name=dep_name,
                namespace=self._namespace,
                labels=all_labels,
            ),
            spec=dep_spec,
        )

        try:
            self._apps_v1.create_namespaced_deployment(
                namespace=self._namespace, body=deployment
            )
            logger.info(f"K8sRuntime: Created Deployment '{dep_name}'")
        except self._ApiException as e:
            if e.status == 409:
                # Already exists — update it instead
                logger.info(f"K8sRuntime: Deployment '{dep_name}' already exists, updating")
                self._apps_v1.replace_namespaced_deployment(
                    name=dep_name, namespace=self._namespace, body=deployment
                )
            else:
                raise ContainerRuntimeError(f"Failed to create Deployment: {e}")

        # Create Service if ports are specified
        if service_ports:
            svc_name = self._svc_name(name)
            service = k8s_client.V1Service(
                api_version="v1",
                kind="Service",
                metadata=k8s_client.V1ObjectMeta(
                    name=svc_name,
                    namespace=self._namespace,
                    labels=all_labels,
                ),
                spec=k8s_client.V1ServiceSpec(
                    selector={"tsushin.io/container-name": self._sanitize_name(name)},
                    ports=service_ports,
                    type="ClusterIP",
                ),
            )
            try:
                self._core_v1.create_namespaced_service(
                    namespace=self._namespace, body=service
                )
                logger.info(f"K8sRuntime: Created Service '{svc_name}'")
            except self._ApiException as e:
                if e.status == 409:
                    logger.info(f"K8sRuntime: Service '{svc_name}' already exists, updating")
                    self._core_v1.replace_namespaced_service(
                        name=svc_name, namespace=self._namespace, body=service
                    )
                else:
                    logger.error(f"K8sRuntime: Failed to create Service: {e}")
                    # Non-fatal — Deployment still works without a Service

        # Wait for the pod to start
        self._wait_for_pod_ready(name, timeout=120)

        # Return a wrapper that looks like a Docker container object
        try:
            pod = self._find_pod(name)
            wrapper = _K8sPodWrapper(pod)
            logger.info(f"K8sRuntime: Container '{name}' running as Pod '{pod.metadata.name}'")
            return wrapper
        except ContainerNotFoundError:
            # Deployment was created but pod isn't up yet — return a minimal wrapper
            wrapper = _K8sPodWrapper.__new__(_K8sPodWrapper)
            wrapper.id = dep_name
            wrapper.name = dep_name
            wrapper.status = "pending"
            wrapper.image = image
            return wrapper

    def get_container(self, name_or_id: str) -> Any:
        pod = self._find_pod(name_or_id)
        return _K8sPodWrapper(pod)

    def stop_container(self, name_or_id: str, timeout: int = 30) -> None:
        self._get_deployment(name_or_id)  # Verify it exists
        self._scale_deployment(name_or_id, 0)
        logger.info(f"K8sRuntime: Scaled Deployment '{name_or_id}' to 0 (stopped)")

    def remove_container(self, name_or_id: str, force: bool = False) -> None:
        dep_name = self._sanitize_name(name_or_id)

        # Delete Deployment
        try:
            self._apps_v1.delete_namespaced_deployment(
                name=dep_name, namespace=self._namespace
            )
            logger.info(f"K8sRuntime: Deleted Deployment '{dep_name}'")
        except self._ApiException as e:
            if e.status == 404:
                raise ContainerNotFoundError(f"Deployment '{dep_name}' not found")
            raise ContainerRuntimeError(f"Failed to delete Deployment: {e}")

        # Delete Service (best-effort)
        svc_name = self._svc_name(name_or_id)
        try:
            self._core_v1.delete_namespaced_service(
                name=svc_name, namespace=self._namespace
            )
            logger.info(f"K8sRuntime: Deleted Service '{svc_name}'")
        except self._ApiException:
            pass  # Service may not exist

        # Delete associated PVCs (best-effort, prevent resource leaks)
        try:
            selector = f"tsushin.io/container-name={dep_name}"
            pvcs = self._core_v1.list_namespaced_persistent_volume_claim(
                namespace=self._namespace, label_selector=selector
            )
            for pvc in pvcs.items:
                self._core_v1.delete_namespaced_persistent_volume_claim(
                    name=pvc.metadata.name, namespace=self._namespace
                )
                logger.info(f"K8sRuntime: Deleted PVC '{pvc.metadata.name}'")
        except Exception:
            pass  # PVC cleanup is best-effort

    def start_container(self, name_or_id: str) -> None:
        self._get_deployment(name_or_id)  # Verify it exists
        self._scale_deployment(name_or_id, 1)
        logger.info(f"K8sRuntime: Scaled Deployment '{name_or_id}' to 1 (started)")
        self._wait_for_pod_ready(name_or_id, timeout=120)

    def restart_container(self, name_or_id: str, timeout: int = 30) -> None:
        # Delete the pod; the Deployment controller will recreate it
        try:
            pod = self._find_pod(name_or_id)
            self._core_v1.delete_namespaced_pod(
                name=pod.metadata.name, namespace=self._namespace
            )
            logger.info(
                f"K8sRuntime: Deleted Pod '{pod.metadata.name}' for restart "
                f"(Deployment will recreate)"
            )
            self._wait_for_pod_ready(name_or_id, timeout=120)
        except ContainerNotFoundError:
            # No running pod — just ensure scale is 1
            self._scale_deployment(name_or_id, 1)
            self._wait_for_pod_ready(name_or_id, timeout=120)

    def get_container_status(self, name_or_id: str) -> str:
        dep_name = self._sanitize_name(name_or_id)
        try:
            dep = self._apps_v1.read_namespaced_deployment(
                name=dep_name, namespace=self._namespace
            )
        except self._ApiException as e:
            if e.status == 404:
                return "not_found"
            return "error"

        # Check if scaled to 0
        if dep.spec.replicas == 0:
            return "exited"

        # Try to find a running pod
        try:
            pod = self._find_pod(name_or_id)
            return _K8sPodWrapper._translate_phase(
                pod.status.phase if pod.status else None
            )
        except ContainerNotFoundError:
            return "pending"
        except ContainerRuntimeError:
            return "error"

    def get_container_attrs(self, name_or_id: str) -> Dict[str, Any]:
        pod = self._find_pod(name_or_id)
        image_tags = []
        if pod.spec and pod.spec.containers:
            image_tags = [c.image for c in pod.spec.containers if c.image]

        state_info = {}
        if pod.status:
            state_info = {
                "phase": pod.status.phase,
                "start_time": str(pod.status.start_time) if pod.status.start_time else None,
                "conditions": [
                    {"type": c.type, "status": c.status}
                    for c in (pod.status.conditions or [])
                ],
            }

        return {
            "id": pod.metadata.uid,
            "name": pod.metadata.name,
            "status": _K8sPodWrapper._translate_phase(
                pod.status.phase if pod.status else None
            ),
            "image_tags": image_tags or [name_or_id],
            "created": str(pod.metadata.creation_timestamp),
            "state": state_info,
            "network_settings": {
                "pod_ip": pod.status.pod_ip if pod.status else "",
            },
        }

    def exec_run(
        self,
        name_or_id: str,
        cmd: List[str],
        *,
        workdir: Optional[str] = None,
        user: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        demux: bool = False,
        detach: bool = False,
    ) -> Any:
        from kubernetes.stream import stream as k8s_stream

        pod = self._find_pod(name_or_id)
        container_name = self._sanitize_name(name_or_id)

        # Build the command — prepend env vars and cd if needed
        full_cmd = self._build_exec_command(cmd, workdir, user, environment)

        try:
            resp = k8s_stream(
                self._core_v1.connect_get_namespaced_pod_exec,
                name=pod.metadata.name,
                namespace=self._namespace,
                container=container_name,
                command=full_cmd,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _preload_content=True,
            )

            # k8s_stream with _preload_content=True returns the full output as string
            stdout_bytes = resp.encode("utf-8") if isinstance(resp, str) else resp
            stderr_bytes = b""

            # Try to get the return code from the channel
            exit_code = 0
            if hasattr(resp, "returncode"):
                exit_code = resp.returncode or 0

            if demux:
                return _K8sExecResult(exit_code, (stdout_bytes, stderr_bytes))
            return _K8sExecResult(exit_code, stdout_bytes)

        except self._ApiException as e:
            if e.status == 404:
                raise ContainerNotFoundError(f"Pod for '{name_or_id}' not found")
            raise ContainerRuntimeError(f"K8s exec error: {e}")
        except Exception as e:
            raise ContainerRuntimeError(f"K8s exec error: {e}")

    def exec_create_and_start(
        self,
        name_or_id: str,
        cmd: List[str],
        *,
        workdir: Optional[str] = None,
        stream: bool = False,
        demux: bool = False,
    ) -> Any:
        from kubernetes.stream import stream as k8s_stream

        pod = self._find_pod(name_or_id)
        container_name = self._sanitize_name(name_or_id)
        exec_id = f"k8s-exec-{uuid.uuid4().hex[:12]}"

        full_cmd = self._build_exec_command(cmd, workdir)

        try:
            if stream:
                resp = k8s_stream(
                    self._core_v1.connect_get_namespaced_pod_exec,
                    name=pod.metadata.name,
                    namespace=self._namespace,
                    container=container_name,
                    command=full_cmd,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False,
                )

                def _streaming_generator():
                    """Yield (stdout_chunk, stderr_chunk) tuples like Docker demux."""
                    try:
                        while resp.is_open():
                            resp.update(timeout=1)
                            stdout_data = resp.read_stdout()
                            stderr_data = resp.read_stderr()
                            if stdout_data or stderr_data:
                                stdout_bytes = stdout_data.encode("utf-8") if stdout_data else None
                                stderr_bytes = stderr_data.encode("utf-8") if stderr_data else None
                                if demux:
                                    yield (stdout_bytes, stderr_bytes)
                                else:
                                    if stdout_bytes:
                                        yield (stdout_bytes, None)
                                    if stderr_bytes:
                                        yield (None, stderr_bytes)
                        # Capture exit code when stream closes
                        exit_code = resp.returncode if hasattr(resp, "returncode") else 0
                        with self._exec_lock:
                            self._exec_exit_codes[exec_id] = exit_code or 0
                    except Exception as e:
                        logger.error(f"K8sRuntime: Streaming exec error: {e}")
                        with self._exec_lock:
                            self._exec_exit_codes[exec_id] = -1

                return exec_id, _streaming_generator()

            else:
                resp = k8s_stream(
                    self._core_v1.connect_get_namespaced_pod_exec,
                    name=pod.metadata.name,
                    namespace=self._namespace,
                    container=container_name,
                    command=full_cmd,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=True,
                )
                output = resp.encode("utf-8") if isinstance(resp, str) else resp
                exit_code = resp.returncode if hasattr(resp, "returncode") else 0
                self._exec_exit_codes[exec_id] = exit_code or 0
                return exec_id, output

        except self._ApiException as e:
            if e.status == 404:
                raise ContainerNotFoundError(f"Pod for '{name_or_id}' not found")
            raise ContainerRuntimeError(f"K8s exec error: {e}")

    def exec_inspect(self, exec_id: str) -> Dict[str, Any]:
        # For K8s, we return cached exit codes from exec_create_and_start
        if isinstance(exec_id, dict) and "Id" in exec_id:
            exec_id = exec_id["Id"]
        with self._exec_lock:
            exit_code = self._exec_exit_codes.pop(str(exec_id), 0)
        return {"ExitCode": exit_code}

    def commit_container(
        self,
        name_or_id: str,
        repository: str,
        tag: str,
        message: str = "",
    ) -> Any:
        raise ContainerRuntimeError(
            "commit not supported in K8s mode; use pre-built images"
        )

    def image_exists(self, image_name: str) -> bool:
        # In K8s, images are pulled from a registry. We assume the image is
        # available if it contains a registry prefix or tag; the kubelet will
        # handle pull failures at pod creation time.
        return True

    def remove_image(self, image_name: str, force: bool = False) -> None:
        # No-op — images are managed by the container registry, not the runtime
        logger.debug(f"K8sRuntime: remove_image is a no-op (image={image_name})")

    def list_containers(self, filters: Optional[Dict[str, Any]] = None) -> List[Any]:
        label_selector = f"app.kubernetes.io/managed-by={self.MANAGED_BY}"

        # Translate Docker-style filters to K8s label selectors
        if filters:
            if "name" in filters:
                name_filter = filters["name"]
                if isinstance(name_filter, list):
                    name_filter = name_filter[0]
                label_selector += f",tsushin.io/container-name={self._sanitize_name(name_filter)}"
            if "label" in filters:
                label_list = filters["label"]
                if isinstance(label_list, str):
                    label_list = [label_list]
                for lbl in label_list:
                    if "=" in lbl:
                        label_selector += f",{lbl}"

        try:
            pods = self._core_v1.list_namespaced_pod(
                namespace=self._namespace, label_selector=label_selector
            )
            return [_K8sPodWrapper(pod) for pod in pods.items]
        except self._ApiException as e:
            raise ContainerRuntimeError(f"K8s API error listing pods: {e}")

    def get_logs(self, name_or_id: str, tail: int = 100) -> str:
        pod = self._find_pod(name_or_id)
        try:
            logs = self._core_v1.read_namespaced_pod_log(
                name=pod.metadata.name,
                namespace=self._namespace,
                tail_lines=tail,
            )
            return logs if isinstance(logs, str) else logs.decode("utf-8", errors="replace")
        except self._ApiException as e:
            if e.status == 404:
                raise ContainerNotFoundError(f"Pod for '{name_or_id}' not found")
            raise ContainerRuntimeError(f"Failed to get logs: {e}")

    def health_check(self, name_or_id: str) -> Dict[str, Any]:
        result = {"status": "unknown", "container_state": "unknown", "error": None}
        try:
            pod = self._find_pod(name_or_id)
            phase = pod.status.phase if pod.status else "Unknown"
            result["container_state"] = phase.lower()

            if phase == "Running":
                # Check container statuses for readiness
                all_ready = True
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        if not cs.ready:
                            all_ready = False
                            break
                result["status"] = "healthy" if all_ready else "unhealthy"
            elif phase in ("Succeeded", "Failed"):
                result["status"] = "stopped"
            else:
                result["status"] = phase.lower()

        except ContainerNotFoundError:
            result["status"] = "not_found"
            result["container_state"] = "not_found"
            result["error"] = "Container not found"
        except ContainerRuntimeError as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def get_or_create_network(self, network_name: str) -> Any:
        # K8s networking is flat — all pods in the same namespace can communicate.
        # Return a placeholder object with a .name attribute for compatibility.
        class _K8sNetworkPlaceholder:
            def __init__(self, name):
                self.name = name
                self.id = name

        logger.debug(
            f"K8sRuntime: get_or_create_network is a no-op "
            f"(K8s networking is flat, namespace={self._namespace})"
        )
        return _K8sNetworkPlaceholder(network_name)

    def ensure_container_on_network(self, name_or_id: str, network_name: str) -> None:
        # No-op — all pods in the same namespace can communicate
        logger.debug(
            f"K8sRuntime: ensure_container_on_network is a no-op for '{name_or_id}'"
        )

    def get_container_network_ip(self, name_or_id: str, network_name: str) -> str:
        # Try Service ClusterIP first, fall back to Pod IP
        svc_name = self._svc_name(name_or_id)
        try:
            svc = self._core_v1.read_namespaced_service(
                name=svc_name, namespace=self._namespace
            )
            if svc.spec.cluster_ip and svc.spec.cluster_ip != "None":
                return svc.spec.cluster_ip
        except self._ApiException:
            pass  # No service — fall through to pod IP

        # Fall back to Pod IP
        try:
            pod = self._find_pod(name_or_id)
            return pod.status.pod_ip if pod.status and pod.status.pod_ip else ""
        except (ContainerNotFoundError, ContainerRuntimeError):
            return ""

    # ------------------------------------------------------------------
    # Private exec helper
    # ------------------------------------------------------------------

    @staticmethod
    def _build_exec_command(
        cmd: List[str],
        workdir: Optional[str] = None,
        user: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """
        Wrap exec command with cd, env, and su directives as needed.
        K8s exec doesn't support workdir/user/env natively in the same way
        Docker does, so we prepend shell commands.
        """
        prefix_parts = []

        # Set environment variables
        if environment:
            for k, v in environment.items():
                prefix_parts.append(f"export {k}={shlex.quote(str(v))}")

        # Change directory
        if workdir:
            prefix_parts.append(f"cd {shlex.quote(workdir)}")

        if prefix_parts or user:
            # Join the original command into a single shell string
            if len(cmd) == 1:
                cmd_str = cmd[0]
            else:
                # If the command is ["sh", "-c", "..."], extract the inner command
                if len(cmd) >= 3 and cmd[0] in ("sh", "bash", "/bin/sh", "/bin/bash") and cmd[1] == "-c":
                    cmd_str = cmd[2]
                else:
                    cmd_str = " ".join(cmd)

            inner = " && ".join(prefix_parts + [cmd_str]) if prefix_parts else cmd_str

            if user and user != "root":
                return ["su", "-s", "/bin/sh", user, "-c", inner]
            else:
                return ["sh", "-c", inner]

        return cmd


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_runtime_instance: Optional[ContainerRuntime] = None
_runtime_lock = threading.Lock()


def get_container_runtime() -> ContainerRuntime:
    """
    Factory: return the configured container runtime singleton.

    Reads TSN_CONTAINER_RUNTIME env var:
        - "docker"     (default) -> DockerRuntime
        - "kubernetes" -> K8sRuntime

    Returns:
        ContainerRuntime instance
    """
    global _runtime_instance
    if _runtime_instance is not None:
        return _runtime_instance

    with _runtime_lock:
        if _runtime_instance is not None:
            return _runtime_instance

        backend = os.getenv("TSN_CONTAINER_RUNTIME", "docker").lower().strip()

        if backend == "docker":
            _runtime_instance = DockerRuntime()
        elif backend == "kubernetes":
            _runtime_instance = K8sRuntime()
        else:
            raise ValueError(
                f"Unknown container runtime: '{backend}'. "
                f"Set TSN_CONTAINER_RUNTIME to 'docker' or 'kubernetes'."
            )

        logger.info(f"Container runtime initialized: {backend}")
    return _runtime_instance
