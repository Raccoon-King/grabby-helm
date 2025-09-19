"""Utility functions for manifest traversal and resource handling."""
from __future__ import annotations

import time
from typing import Any, Dict, Iterator, List, Optional, Set, Union

from .constants import K8sFields
from .types import K8sObject, ManifestDict


class ManifestTraverser:
    """Utility for traversing Kubernetes manifest structures."""
    
    @staticmethod
    def get_metadata(manifest: K8sObject) -> Dict[str, Any]:
        """Extract metadata from a manifest."""
        metadata = manifest.get(K8sFields.METADATA)
        return metadata if isinstance(metadata, dict) else {}
    
    @staticmethod
    def get_manifest_name(manifest: K8sObject) -> str:
        """Extract name from manifest metadata."""
        metadata = ManifestTraverser.get_metadata(manifest)
        name = metadata.get(K8sFields.NAME)
        return str(name) if isinstance(name, str) else ""
    
    @staticmethod
    def get_manifest_namespace(manifest: K8sObject) -> Optional[str]:
        """Extract namespace from manifest metadata."""
        metadata = ManifestTraverser.get_metadata(manifest)
        namespace = metadata.get(K8sFields.NAMESPACE)
        return str(namespace) if isinstance(namespace, str) else None
    
    @staticmethod
    def get_spec(manifest: K8sObject) -> Dict[str, Any]:
        """Extract spec from a manifest."""
        spec = manifest.get(K8sFields.SPEC)
        return spec if isinstance(spec, dict) else {}
    
    @staticmethod
    def get_pod_spec(manifest: K8sObject) -> Dict[str, Any]:
        """Extract pod spec from various workload types."""
        spec = ManifestTraverser.get_spec(manifest)
        
        # Handle CronJob -> JobTemplate -> Template -> Spec
        job_template = spec.get(K8sFields.JOB_TEMPLATE)
        if isinstance(job_template, dict):
            job_spec = job_template.get(K8sFields.SPEC)
            if isinstance(job_spec, dict):
                template = job_spec.get(K8sFields.TEMPLATE)
                if isinstance(template, dict):
                    template_spec = template.get(K8sFields.SPEC)
                    if isinstance(template_spec, dict):
                        return template_spec
        
        # Handle standard workloads: Template -> Spec
        template = spec.get(K8sFields.TEMPLATE)
        if isinstance(template, dict):
            template_spec = template.get(K8sFields.SPEC)
            if isinstance(template_spec, dict):
                return template_spec
        
        # For bare pods or Job specs
        return spec
    
    @staticmethod
    def get_pod_labels(manifest: K8sObject) -> Dict[str, str]:
        """Extract labels from pod template metadata."""
        spec = ManifestTraverser.get_spec(manifest)
        
        # Handle CronJob path
        job_template = spec.get(K8sFields.JOB_TEMPLATE)
        if isinstance(job_template, dict):
            job_spec = job_template.get(K8sFields.SPEC)
            if isinstance(job_spec, dict):
                template = job_spec.get(K8sFields.TEMPLATE)
                if isinstance(template, dict):
                    return ManifestTraverser._extract_labels_from_template(template)
        
        # Handle standard workloads
        template = spec.get(K8sFields.TEMPLATE)
        if isinstance(template, dict):
            return ManifestTraverser._extract_labels_from_template(template)
        
        return {}
    
    @staticmethod
    def _extract_labels_from_template(template: Dict[str, Any]) -> Dict[str, str]:
        """Extract labels from a pod template."""
        metadata = template.get(K8sFields.METADATA)
        if not isinstance(metadata, dict):
            return {}
        
        labels = metadata.get(K8sFields.LABELS)
        if not isinstance(labels, dict):
            return {}
        
        # Filter to string keys and values only
        clean_labels: Dict[str, str] = {}
        for key, value in labels.items():
            if isinstance(key, str) and isinstance(value, str):
                clean_labels[key] = value
        
        return clean_labels
    
    @staticmethod
    def get_containers(pod_spec: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Iterate over all containers in a pod spec."""
        for container_type in [K8sFields.CONTAINERS, K8sFields.INIT_CONTAINERS, K8sFields.EPHEMERAL_CONTAINERS]:
            containers = pod_spec.get(container_type)
            if isinstance(containers, list):
                for container in containers:
                    if isinstance(container, dict):
                        yield container
    
    @staticmethod
    def get_replica_count(manifest: K8sObject) -> int:
        """Extract replica count from a workload manifest."""
        spec = ManifestTraverser.get_spec(manifest)
        replicas = spec.get(K8sFields.REPLICAS)
        return int(replicas) if isinstance(replicas, int) else 1
    
    @staticmethod
    def get_schedule(manifest: K8sObject) -> Optional[str]:
        """Extract schedule from a CronJob manifest."""
        spec = ManifestTraverser.get_spec(manifest)
        schedule = spec.get(K8sFields.SCHEDULE)
        return str(schedule) if isinstance(schedule, str) else None
    
    @staticmethod
    def get_completions(manifest: K8sObject) -> Optional[int]:
        """Extract completions from a Job manifest."""
        spec = ManifestTraverser.get_spec(manifest)
        completions = spec.get(K8sFields.COMPLETIONS)
        return int(completions) if isinstance(completions, int) else None


class ResourceReferenceExtractor:
    """Extract references to other resources from manifests."""
    
    @staticmethod
    def extract_configmap_references(manifests: List[K8sObject]) -> Set[str]:
        """Extract all ConfigMap references from a list of manifests."""
        names: Set[str] = set()
        
        for manifest in manifests:
            pod_spec = ManifestTraverser.get_pod_spec(manifest)
            
            # From volumes
            volumes = pod_spec.get(K8sFields.VOLUMES)
            if isinstance(volumes, list):
                for volume in volumes:
                    if isinstance(volume, dict):
                        names.update(ResourceReferenceExtractor._configmaps_from_volume(volume))
            
            # From containers
            for container in ManifestTraverser.get_containers(pod_spec):
                names.update(ResourceReferenceExtractor._configmaps_from_container(container))
        
        return names
    
    @staticmethod
    def _configmaps_from_volume(volume: Dict[str, Any]) -> Set[str]:
        """Extract ConfigMap names from a volume definition."""
        names: Set[str] = set()
        
        # Direct configMap reference
        config_map = volume.get(K8sFields.CONFIG_MAP)
        if isinstance(config_map, dict):
            name = config_map.get(K8sFields.NAME)
            if isinstance(name, str):
                names.add(name)
        
        # Projected volumes
        projected = volume.get(K8sFields.PROJECTED)
        if isinstance(projected, dict):
            sources = projected.get(K8sFields.SOURCES)
            if isinstance(sources, list):
                for source in sources:
                    if isinstance(source, dict):
                        ref = source.get(K8sFields.CONFIG_MAP)
                        if isinstance(ref, dict):
                            name = ref.get(K8sFields.NAME)
                            if isinstance(name, str):
                                names.add(name)
        
        return names
    
    @staticmethod
    def _configmaps_from_container(container: Dict[str, Any]) -> Set[str]:
        """Extract ConfigMap names from a container definition."""
        names: Set[str] = set()
        
        # From envFrom
        env_from = container.get(K8sFields.ENV_FROM)
        if isinstance(env_from, list):
            for entry in env_from:
                if isinstance(entry, dict):
                    ref = entry.get(K8sFields.CONFIG_MAP_REF)
                    if isinstance(ref, dict):
                        name = ref.get(K8sFields.NAME)
                        if isinstance(name, str):
                            names.add(name)
        
        # From env valueFrom
        env = container.get(K8sFields.ENV)
        if isinstance(env, list):
            for entry in env:
                if isinstance(entry, dict):
                    value_from = entry.get(K8sFields.VALUE_FROM)
                    if isinstance(value_from, dict):
                        config_ref = value_from.get(K8sFields.CONFIG_MAP_KEY_REF)
                        if isinstance(config_ref, dict):
                            name = config_ref.get(K8sFields.NAME)
                            if isinstance(name, str):
                                names.add(name)
        
        return names
    
    @staticmethod
    def extract_secret_references(manifests: List[K8sObject]) -> Set[str]:
        """Extract all Secret references from a list of manifests."""
        names: Set[str] = set()
        
        for manifest in manifests:
            pod_spec = ManifestTraverser.get_pod_spec(manifest)
            
            # From volumes
            volumes = pod_spec.get(K8sFields.VOLUMES)
            if isinstance(volumes, list):
                for volume in volumes:
                    if isinstance(volume, dict):
                        names.update(ResourceReferenceExtractor._secrets_from_volume(volume))
            
            # From imagePullSecrets
            image_pull_secrets = pod_spec.get(K8sFields.IMAGE_PULL_SECRETS)
            if isinstance(image_pull_secrets, list):
                for pull_secret in image_pull_secrets:
                    if isinstance(pull_secret, dict):
                        name = pull_secret.get(K8sFields.NAME)
                        if isinstance(name, str):
                            names.add(name)
            
            # From containers
            for container in ManifestTraverser.get_containers(pod_spec):
                names.update(ResourceReferenceExtractor._secrets_from_container(container))
        
        return names
    
    @staticmethod
    def _secrets_from_volume(volume: Dict[str, Any]) -> Set[str]:
        """Extract Secret names from a volume definition."""
        names: Set[str] = set()
        
        # Direct secret reference
        secret = volume.get(K8sFields.SECRET)
        if isinstance(secret, dict):
            name = secret.get(K8sFields.SECRET_NAME) or secret.get(K8sFields.NAME)
            if isinstance(name, str):
                names.add(name)
        
        # Projected volumes
        projected = volume.get(K8sFields.PROJECTED)
        if isinstance(projected, dict):
            sources = projected.get(K8sFields.SOURCES)
            if isinstance(sources, list):
                for source in sources:
                    if isinstance(source, dict):
                        ref = source.get(K8sFields.SECRET)
                        if isinstance(ref, dict):
                            name = ref.get(K8sFields.NAME)
                            if isinstance(name, str):
                                names.add(name)
        
        return names
    
    @staticmethod
    def _secrets_from_container(container: Dict[str, Any]) -> Set[str]:
        """Extract Secret names from a container definition."""
        names: Set[str] = set()
        
        # From envFrom
        env_from = container.get(K8sFields.ENV_FROM)
        if isinstance(env_from, list):
            for entry in env_from:
                if isinstance(entry, dict):
                    ref = entry.get(K8sFields.SECRET_REF)
                    if isinstance(ref, dict):
                        name = ref.get(K8sFields.NAME)
                        if isinstance(name, str):
                            names.add(name)
        
        # From env valueFrom
        env = container.get(K8sFields.ENV)
        if isinstance(env, list):
            for entry in env:
                if isinstance(entry, dict):
                    value_from = entry.get(K8sFields.VALUE_FROM)
                    if isinstance(value_from, dict):
                        secret_ref = value_from.get(K8sFields.SECRET_KEY_REF)
                        if isinstance(secret_ref, dict):
                            name = secret_ref.get(K8sFields.NAME)
                            if isinstance(name, str):
                                names.add(name)
        
        return names
    
    @staticmethod
    def extract_service_account_references(manifests: List[K8sObject]) -> Set[str]:
        """Extract ServiceAccount references from manifests."""
        names: Set[str] = set()
        
        for manifest in manifests:
            pod_spec = ManifestTraverser.get_pod_spec(manifest)
            service_account = (
                pod_spec.get(K8sFields.SERVICE_ACCOUNT_NAME) or 
                pod_spec.get(K8sFields.SERVICE_ACCOUNT)
            )
            if isinstance(service_account, str) and service_account:
                names.add(service_account)
        
        return names
    
    @staticmethod
    def extract_pvc_references(manifests: List[K8sObject]) -> Set[str]:
        """Extract PersistentVolumeClaim references from manifests."""
        names: Set[str] = set()
        
        for manifest in manifests:
            pod_spec = ManifestTraverser.get_pod_spec(manifest)
            volumes = pod_spec.get(K8sFields.VOLUMES)
            if isinstance(volumes, list):
                for volume in volumes:
                    if isinstance(volume, dict):
                        claim = volume.get(K8sFields.PERSISTENT_VOLUME_CLAIM)
                        if isinstance(claim, dict):
                            name = claim.get(K8sFields.CLAIM_NAME) or claim.get(K8sFields.NAME)
                            if isinstance(name, str) and name:
                                names.add(name)
        
        return names
    
    @staticmethod
    def find_matching_services(
        workloads: List[K8sObject], 
        services: List[K8sObject]
    ) -> Set[str]:
        """Find services that match workload selectors."""
        matches: Set[str] = set()
        
        for service in services:
            service_spec = ManifestTraverser.get_spec(service)
            selector = service_spec.get(K8sFields.SELECTOR)
            if not isinstance(selector, dict) or not selector:
                continue
            
            for workload in workloads:
                labels = ManifestTraverser.get_pod_labels(workload)
                if labels and all(labels.get(key) == value for key, value in selector.items()):
                    name = ManifestTraverser.get_manifest_name(service)
                    if name:
                        matches.add(name)
                    break
        
        return matches
    
    @staticmethod
    def find_ingresses_for_services(
        ingresses: List[K8sObject], 
        service_names: Set[str]
    ) -> Set[str]:
        """Find ingresses that reference the given services."""
        if not service_names:
            return set()
        
        matches: Set[str] = set()
        
        for ingress in ingresses:
            referenced_services = ResourceReferenceExtractor._extract_services_from_ingress(ingress)
            if referenced_services.intersection(service_names):
                name = ManifestTraverser.get_manifest_name(ingress)
                if name:
                    matches.add(name)
        
        return matches
    
    @staticmethod
    def _extract_services_from_ingress(ingress: K8sObject) -> Set[str]:
        """Extract service names referenced by an ingress."""
        names: Set[str] = set()
        spec = ManifestTraverser.get_spec(ingress)
        
        # Default backend
        default_backend = spec.get(K8sFields.DEFAULT_BACKEND)
        names.update(ResourceReferenceExtractor._services_from_backend(default_backend))
        
        # Rules
        rules = spec.get(K8sFields.RULES)
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict):
                    http = rule.get(K8sFields.HTTP)
                    if isinstance(http, dict):
                        paths = http.get(K8sFields.PATHS)
                        if isinstance(paths, list):
                            for path in paths:
                                if isinstance(path, dict):
                                    backend = path.get(K8sFields.BACKEND)
                                    names.update(ResourceReferenceExtractor._services_from_backend(backend))
        
        return names
    
    @staticmethod
    def _services_from_backend(backend: Any) -> Set[str]:
        """Extract service names from an ingress backend."""
        names: Set[str] = set()
        if not isinstance(backend, dict):
            return names
        
        # New format
        service = backend.get(K8sFields.SERVICE)
        if isinstance(service, dict):
            name = service.get(K8sFields.NAME)
            if isinstance(name, str) and name:
                names.add(name)
        
        # Legacy format
        legacy_name = backend.get(K8sFields.SERVICE_NAME)
        if isinstance(legacy_name, str) and legacy_name:
            names.add(legacy_name)
        
        return names


def slugify(value: str) -> str:
    """Convert a string to a filesystem-safe slug."""
    allowed = []
    for char in value.lower():
        if char.isalnum() or char in {"-", "."}:
            allowed.append(char)
        else:
            allowed.append("-")
    slug = "".join(allowed).strip("-")
    return slug


class StringUtils:
    """String utility functions."""
    
    slugify = staticmethod(slugify)
    
    @staticmethod
    def truncate(text: str, width: int) -> str:
        """Truncate text to fit within a given width."""
        if width <= 0:
            return ""
        if len(text) <= width:
            return text
        if width == 1:
            return text[:1]
        return text[: width - 1] + "…"


class RetryUtils:
    """Utility functions for retry logic."""
    
    @staticmethod
    def exponential_backoff(
        attempt: int, 
        base: float = 2.0, 
        max_delay: float = 60.0
    ) -> float:
        """Calculate exponential backoff delay."""
        delay = base ** attempt
        return min(delay, max_delay)
    
    @staticmethod
    def retry_with_backoff(
        func,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        exceptions: tuple = (Exception,)
    ):
        """Decorator for retrying functions with exponential backoff."""
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = RetryUtils.exponential_backoff(attempt, backoff_base)
                        time.sleep(delay)
                    else:
                        break
            
            if last_exception:
                raise last_exception
            
        return wrapper