"""Robust kubectl interface with retry logic and error handling."""
from __future__ import annotations

import json
import logging
import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .constants import DEFAULT_RETRY_COUNT, DEFAULT_TIMEOUT_SECONDS, DEFAULT_RETRY_BACKOFF_BASE
from .types import K8sObject, K8sObjectList, KubectlError, ResourceFilter


class KubectlClient:
    """Robust kubectl client with retry logic and proper error handling."""
    
    def __init__(
        self,
        kubeconfig: Optional[str] = None,
        context: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_RETRY_COUNT,
        backoff_base: float = DEFAULT_RETRY_BACKOFF_BASE,
    ):
        self.kubeconfig = kubeconfig
        self.context = context
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.logger = logging.getLogger(__name__)
        self._base_cmd = self._build_base_command()
    
    def _build_base_command(self) -> List[str]:
        """Build the base kubectl command with global options."""
        cmd = ["kubectl"]
        
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        
        if self.context:
            cmd.extend(["--context", self.context])
        
        return cmd
    
    def list_resources(
        self,
        resource_type: str,
        namespace: str = "default",
        selector: Optional[str] = None,
        field_selector: Optional[str] = None,
        all_namespaces: bool = False,
    ) -> K8sObjectList:
        """
        List resources of a given type.
        
        Args:
            resource_type: Kubernetes resource type (e.g., 'deployments', 'services')
            namespace: Namespace to query (ignored if all_namespaces=True)
            selector: Label selector for filtering
            field_selector: Field selector for filtering
            all_namespaces: Query all namespaces
            
        Returns:
            List of Kubernetes resource objects
            
        Raises:
            KubectlError: If kubectl command fails
        """
        cmd = [*self._base_cmd, "get", resource_type, "-o", "json"]
        
        if all_namespaces:
            cmd.append("--all-namespaces")
        else:
            cmd.extend(["-n", namespace])
        
        if selector:
            cmd.extend(["-l", selector])
        
        if field_selector:
            cmd.extend(["--field-selector", field_selector])
        
        output = self._run_command(cmd)
        
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            raise KubectlError(f"Failed to parse kubectl output as JSON: {e}", cmd) from e
        
        if not isinstance(data, dict):
            raise KubectlError(f"Expected JSON object, got {type(data)}", cmd)
        
        items = data.get("items", [])
        if not isinstance(items, list):
            raise KubectlError(f"Expected 'items' to be a list, got {type(items)}", cmd)
        
        # Sort by name for consistent ordering
        items.sort(key=lambda item: self._get_resource_name(item))
        
        return items
    
    def get_resource(
        self,
        resource_type: str,
        name: str,
        namespace: str = "default",
    ) -> Optional[K8sObject]:
        """
        Get a specific resource by name.
        
        Args:
            resource_type: Kubernetes resource type
            name: Resource name
            namespace: Resource namespace
            
        Returns:
            Resource object or None if not found
            
        Raises:
            KubectlError: If kubectl command fails (except for not found)
        """
        cmd = [*self._base_cmd, "get", resource_type, name, "-n", namespace, "-o", "json"]
        
        try:
            output = self._run_command(cmd)
        except KubectlError as e:
            # Check if it's a "not found" error
            if "not found" in str(e).lower():
                return None
            raise
        
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            raise KubectlError(f"Failed to parse kubectl output as JSON: {e}", cmd) from e
        
        if not isinstance(data, dict):
            raise KubectlError(f"Expected JSON object, got {type(data)}", cmd)
        
        return data
    
    def check_connection(self) -> bool:
        """
        Check if kubectl can connect to the cluster.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            cmd = [*self._base_cmd, "cluster-info"]
            self._run_command(cmd, retries=1)
            return True
        except KubectlError:
            return False
    
    def get_current_context(self) -> Optional[str]:
        """
        Get the current kubectl context.
        
        Returns:
            Current context name or None if unable to determine
        """
        try:
            cmd = [*self._base_cmd, "config", "current-context"]
            output = self._run_command(cmd, retries=1)
            return output.strip() or None
        except KubectlError:
            return None
    
    def get_namespaces(self) -> List[str]:
        """
        Get list of available namespaces.
        
        Returns:
            List of namespace names
            
        Raises:
            KubectlError: If kubectl command fails
        """
        try:
            namespaces = self.list_resources("namespaces", all_namespaces=True)
            return [self._get_resource_name(ns) for ns in namespaces if self._get_resource_name(ns)]
        except KubectlError:
            # Fallback - try to get just names
            cmd = [*self._base_cmd, "get", "namespaces", "-o", "name"]
            output = self._run_command(cmd)
            names = []
            for line in output.strip().split("\\n"):
                if "/" in line:
                    names.append(line.split("/", 1)[1])
            return names
    
    def validate_resource_access(self, resource_type: str, namespace: str) -> bool:
        """
        Check if we have access to list a specific resource type in a namespace.
        
        Args:
            resource_type: Kubernetes resource type to check
            namespace: Namespace to check access for
            
        Returns:
            True if access is available, False otherwise
        """
        try:
            # Try to list resources with a limit of 1 to minimize impact
            cmd = [*self._base_cmd, "get", resource_type, "-n", namespace, "--limit=1", "-o", "name"]
            self._run_command(cmd, retries=1)
            return True
        except KubectlError:
            return False
    
    def _run_command(
        self,
        cmd: Sequence[str],
        retries: Optional[int] = None,
    ) -> str:
        """
        Run a kubectl command with retry logic.
        
        Args:
            cmd: Command to execute
            retries: Number of retries (uses instance default if None)
            
        Returns:
            Command stdout
            
        Raises:
            KubectlError: If command fails after all retries
        """
        if retries is None:
            retries = self.max_retries
        
        self.logger.debug("Running command: %s", shlex.join(cmd))
        
        last_exception = None
        
        for attempt in range(retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                
                if attempt > 0:
                    self.logger.info("Command succeeded after %d retries", attempt)
                
                return result.stdout
                
            except subprocess.TimeoutExpired as e:
                last_exception = KubectlError(
                    f"Command timed out after {self.timeout} seconds", 
                    list(cmd)
                )
                
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.strip() or e.stdout.strip() or str(e)
                last_exception = KubectlError(f"kubectl failed: {error_msg}", list(cmd))
                
                # Don't retry certain types of errors
                if self._is_non_retryable_error(error_msg):
                    break
            
            except Exception as e:
                last_exception = KubectlError(f"Unexpected error: {e}", list(cmd))
            
            # Wait before retrying (except on last attempt)
            if attempt < retries:
                delay = self._calculate_backoff_delay(attempt)
                self.logger.debug("Retrying in %.2f seconds (attempt %d/%d)", delay, attempt + 1, retries)
                time.sleep(delay)
        
        if last_exception:
            self.logger.error("Command failed after %d attempts: %s", retries + 1, last_exception)
            raise last_exception
        
        # This should never be reached, but satisfy type checker
        raise KubectlError("Unknown error occurred", list(cmd))
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter."""
        import random
        
        base_delay = self.backoff_base ** attempt
        # Add some jitter to avoid thundering herd
        jitter = random.uniform(0.8, 1.2)
        return min(base_delay * jitter, 60.0)  # Cap at 60 seconds
    
    def _is_non_retryable_error(self, error_msg: str) -> bool:
        """Check if an error should not be retried."""
        non_retryable_patterns = [
            "not found",
            "already exists",
            "forbidden",
            "unauthorized",
            "invalid",
            "malformed",
            "syntax error",
            "bad request",
        ]
        
        error_lower = error_msg.lower()
        return any(pattern in error_lower for pattern in non_retryable_patterns)
    
    @staticmethod
    def _get_resource_name(resource: K8sObject) -> str:
        """Extract name from a Kubernetes resource."""
        metadata = resource.get("metadata")
        if isinstance(metadata, dict):
            name = metadata.get("name")
            if isinstance(name, str):
                return name
        return ""


class KubectlResourceCollector:
    """High-level resource collector using kubectl client."""
    
    def __init__(self, kubectl_client: KubectlClient):
        self.kubectl = kubectl_client
        self.logger = logging.getLogger(__name__)
    
    def collect_resources(
        self,
        resource_types: Sequence[str],
        filters: ResourceFilter,
    ) -> Dict[str, K8sObjectList]:
        """
        Collect multiple resource types with filtering.
        
        Args:
            resource_types: List of resource types to collect
            filters: Filters to apply
            
        Returns:
            Dictionary mapping resource types to their objects
        """
        results: Dict[str, K8sObjectList] = {}
        
        for resource_type in resource_types:
            try:
                self.logger.debug("Collecting %s resources", resource_type)
                
                resources = self.kubectl.list_resources(
                    resource_type=resource_type,
                    namespace=filters.get("namespace", "default"),
                    selector=filters.get("selector"),
                )
                
                # Apply additional filtering
                filtered_resources = self._apply_filters(resources, filters)
                
                if filtered_resources:
                    results[resource_type] = filtered_resources
                    self.logger.info("Collected %d %s resources", len(filtered_resources), resource_type)
                else:
                    self.logger.debug("No %s resources found matching filters", resource_type)
                    
            except KubectlError as e:
                self.logger.warning("Failed to collect %s: %s", resource_type, e)
                # Continue with other resource types
                continue
        
        return results
    
    def _apply_filters(
        self,
        resources: K8sObjectList,
        filters: ResourceFilter,
    ) -> K8sObjectList:
        """Apply additional filters to resources."""
        filtered = resources
        
        # Filter by names if specified
        names = filters.get("names")
        if names:
            name_set = set(names)
            filtered = [
                resource for resource in filtered
                if self.kubectl._get_resource_name(resource) in name_set
            ]
        
        return filtered
    
    def validate_access(self, resource_types: Sequence[str], namespace: str) -> Dict[str, bool]:
        """
        Validate access to resource types in a namespace.
        
        Args:
            resource_types: Resource types to check
            namespace: Namespace to check
            
        Returns:
            Dictionary mapping resource types to access status
        """
        results = {}
        
        for resource_type in resource_types:
            results[resource_type] = self.kubectl.validate_resource_access(resource_type, namespace)
        
        return results