"""Manifest cleaning utilities for preparing Kubernetes resources for Helm charts."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from .constants import (
    K8sFields,
    KUBECTL_ANNOTATION_PREFIXES,
    KUBECTL_ANNOTATION_SUFFIXES,
    METADATA_FIELDS_TO_DROP,
    PVC_ANNOTATIONS_TO_REMOVE,
    PVC_FIELDS_TO_CLEAN,
    SERVICE_FIELDS_TO_CLEAN,
    SPECIAL_LABELS_TO_REMOVE,
)
from .types import K8sObject, ManifestCleanerProtocol


class ManifestCleaner(ManifestCleanerProtocol):
    """Cleans Kubernetes manifests for export to Helm charts."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def clean_manifest(self, manifest: K8sObject) -> K8sObject:
        """
        Clean a Kubernetes manifest for export.
        
        Removes Kubernetes-managed fields and normalizes the manifest
        so it can be safely applied via Helm.
        
        Args:
            manifest: Raw Kubernetes manifest
            
        Returns:
            Cleaned manifest suitable for Helm templating
        """
        # Work on a copy to avoid modifying the original
        cleaned = dict(manifest)
        
        # Remove status entirely
        cleaned.pop(K8sFields.STATUS, None)
        
        # Clean metadata
        metadata = cleaned.get(K8sFields.METADATA)
        if isinstance(metadata, dict):
            cleaned[K8sFields.METADATA] = self.clean_metadata(dict(metadata))
        
        # Apply resource-specific cleaning
        kind = cleaned.get(K8sFields.KIND)
        if kind == "Service":
            self._clean_service_manifest(cleaned)
        elif kind in {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob"}:
            self._clean_pod_controller_manifest(cleaned)
        elif kind == "PersistentVolumeClaim":
            self._clean_pvc_manifest(cleaned)
        
        self.logger.debug("Cleaned manifest for %s/%s", kind, self._get_name(cleaned))
        return cleaned
    
    def clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean metadata fields from a Kubernetes resource.
        
        Args:
            metadata: Resource metadata
            
        Returns:
            Cleaned metadata
        """
        cleaned = dict(metadata)
        
        # Remove Kubernetes-managed fields
        for field in METADATA_FIELDS_TO_DROP:
            cleaned.pop(field, None)
        
        # Clean annotations
        annotations = cleaned.get(K8sFields.ANNOTATIONS)
        if isinstance(annotations, dict):
            cleaned_annotations = self._clean_annotations(dict(annotations))
            if cleaned_annotations:
                cleaned[K8sFields.ANNOTATIONS] = cleaned_annotations
            else:
                cleaned.pop(K8sFields.ANNOTATIONS, None)
        
        # Clean labels
        labels = cleaned.get(K8sFields.LABELS)
        if isinstance(labels, dict):
            cleaned_labels = self._clean_labels(dict(labels))
            if cleaned_labels:
                cleaned[K8sFields.LABELS] = cleaned_labels
            else:
                cleaned.pop(K8sFields.LABELS, None)
        
        # Remove namespace to make it namespace-agnostic
        cleaned.pop(K8sFields.NAMESPACE, None)
        
        return cleaned
    
    def _clean_annotations(self, annotations: Dict[str, Any]) -> Dict[str, Any]:
        """Clean annotations by removing kubectl-managed entries."""
        cleaned = dict(annotations)
        
        # Remove annotations with specific prefixes
        for key in list(cleaned.keys()):
            should_remove = False
            
            # Check prefixes
            for prefix in KUBECTL_ANNOTATION_PREFIXES:
                if key.startswith(prefix):
                    should_remove = True
                    break
            
            # Check suffixes
            if not should_remove:
                for suffix in KUBECTL_ANNOTATION_SUFFIXES:
                    if key.endswith(suffix):
                        should_remove = True
                        break
            
            if should_remove:
                cleaned.pop(key, None)
        
        return cleaned
    
    def _clean_labels(self, labels: Dict[str, Any]) -> Dict[str, Any]:
        """Clean labels by removing special Kubernetes labels."""
        cleaned = dict(labels)
        
        # Remove special labels
        for label in SPECIAL_LABELS_TO_REMOVE:
            cleaned.pop(label, None)
        
        return cleaned
    
    def _clean_service_manifest(self, manifest: K8sObject) -> None:
        """Clean Service-specific fields."""
        spec = manifest.get(K8sFields.SPEC)
        if not isinstance(spec, dict):
            return
        
        # Remove cluster-managed fields
        for field in SERVICE_FIELDS_TO_CLEAN:
            spec.pop(field, None)
        
        # Handle headless services
        if spec.get(K8sFields.TYPE) == "ClusterIP" and spec.get(K8sFields.CLUSTER_IP) == "None":
            spec.pop(K8sFields.CLUSTER_IP, None)
    
    def _clean_pod_controller_manifest(self, manifest: K8sObject) -> None:
        """Clean Pod controller (Deployment, StatefulSet, etc.) fields."""
        spec = manifest.get(K8sFields.SPEC)
        if not isinstance(spec, dict):
            return
        
        # Clean pod template metadata
        template = spec.get(K8sFields.TEMPLATE)
        if isinstance(template, dict):
            template_metadata = template.get(K8sFields.METADATA)
            if isinstance(template_metadata, dict):
                # Clean template metadata
                template[K8sFields.METADATA] = self._clean_template_metadata(template_metadata)
        
        # Remove controller-specific fields
        spec.pop("revisionHistoryLimit", None)
        spec.pop("progressDeadlineSeconds", None)
    
    def _clean_template_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Clean pod template metadata."""
        cleaned = dict(metadata)
        
        # Remove timestamp
        cleaned.pop(K8sFields.CREATION_TIMESTAMP, None)
        
        # Clean annotations
        annotations = cleaned.get(K8sFields.ANNOTATIONS)
        if isinstance(annotations, dict):
            cleaned_annotations = self._clean_annotations(dict(annotations))
            if cleaned_annotations:
                cleaned[K8sFields.ANNOTATIONS] = cleaned_annotations
            else:
                cleaned.pop(K8sFields.ANNOTATIONS, None)
        
        # Clean labels
        labels = cleaned.get(K8sFields.LABELS)
        if isinstance(labels, dict):
            cleaned_labels = self._clean_labels(dict(labels))
            if cleaned_labels:
                cleaned[K8sFields.LABELS] = cleaned_labels
            else:
                cleaned.pop(K8sFields.LABELS, None)
        
        return cleaned
    
    def _clean_pvc_manifest(self, manifest: K8sObject) -> None:
        """Clean PersistentVolumeClaim-specific fields."""
        spec = manifest.get(K8sFields.SPEC)
        if isinstance(spec, dict):
            # Remove PVC-specific fields
            for field in PVC_FIELDS_TO_CLEAN:
                spec.pop(field, None)
        
        # Clean PVC-specific annotations
        metadata = manifest.get(K8sFields.METADATA)
        if isinstance(metadata, dict):
            annotations = metadata.get(K8sFields.ANNOTATIONS)
            if isinstance(annotations, dict):
                for annotation in PVC_ANNOTATIONS_TO_REMOVE:
                    annotations.pop(annotation, None)
                
                # Remove annotations dict if empty
                if not annotations:
                    metadata.pop(K8sFields.ANNOTATIONS, None)
    
    def _get_name(self, manifest: K8sObject) -> str:
        """Get the name of a manifest for logging."""
        metadata = manifest.get(K8sFields.METADATA)
        if isinstance(metadata, dict):
            name = metadata.get(K8sFields.NAME)
            if isinstance(name, str):
                return name
        return "<unknown>"


class ManifestValidator:
    """Validates cleaned manifests for common issues."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_manifest(self, manifest: K8sObject) -> List[str]:
        """
        Validate a manifest and return list of issues found.
        
        Args:
            manifest: Manifest to validate
            
        Returns:
            List of validation error messages
        """
        issues = []
        
        # Check required fields
        if not manifest.get(K8sFields.API_VERSION):
            issues.append("Missing apiVersion")
        
        if not manifest.get(K8sFields.KIND):
            issues.append("Missing kind")
        
        metadata = manifest.get(K8sFields.METADATA)
        if not isinstance(metadata, dict):
            issues.append("Missing or invalid metadata")
        else:
            if not metadata.get(K8sFields.NAME):
                issues.append("Missing metadata.name")
        
        # Check for remaining managed fields
        if isinstance(metadata, dict):
            for field in METADATA_FIELDS_TO_DROP:
                if field in metadata:
                    issues.append(f"Managed field {field} still present in metadata")
        
        # Resource-specific validations
        kind = manifest.get(K8sFields.KIND)
        if kind in {"Deployment", "StatefulSet", "DaemonSet"}:
            issues.extend(self._validate_workload(manifest))
        elif kind == "Service":
            issues.extend(self._validate_service(manifest))
        
        if issues:
            name = self._get_name(manifest)
            self.logger.warning("Validation issues for %s/%s: %s", kind, name, "; ".join(issues))
        
        return issues
    
    def _validate_workload(self, manifest: K8sObject) -> List[str]:
        """Validate workload-specific fields."""
        issues = []
        
        spec = manifest.get(K8sFields.SPEC)
        if not isinstance(spec, dict):
            issues.append("Missing or invalid spec")
            return issues
        
        template = spec.get(K8sFields.TEMPLATE)
        if not isinstance(template, dict):
            issues.append("Missing or invalid spec.template")
            return issues
        
        template_spec = template.get(K8sFields.SPEC)
        if not isinstance(template_spec, dict):
            issues.append("Missing or invalid spec.template.spec")
            return issues
        
        containers = template_spec.get(K8sFields.CONTAINERS)
        if not isinstance(containers, list) or not containers:
            issues.append("Missing or empty spec.template.spec.containers")
        
        return issues
    
    def _validate_service(self, manifest: K8sObject) -> List[str]:
        """Validate Service-specific fields."""
        issues = []
        
        spec = manifest.get(K8sFields.SPEC)
        if not isinstance(spec, dict):
            issues.append("Missing or invalid spec")
            return issues
        
        ports = spec.get("ports")
        if isinstance(ports, list) and ports:
            for i, port in enumerate(ports):
                if not isinstance(port, dict):
                    continue
                if not port.get("port"):
                    issues.append(f"Missing port in ports[{i}]")
        
        return issues
    
    def _get_name(self, manifest: K8sObject) -> str:
        """Get the name of a manifest for logging."""
        metadata = manifest.get(K8sFields.METADATA)
        if isinstance(metadata, dict):
            name = metadata.get(K8sFields.NAME)
            if isinstance(name, str):
                return name
        return "<unknown>"


class SecretHandler:
    """Handles different strategies for dealing with secrets in exports."""
    
    def __init__(self, mode: str = "include"):
        """
        Initialize secret handler.
        
        Args:
            mode: How to handle secrets ('include', 'skip', 'encrypt', 'external-ref')
        """
        self.mode = mode
        self.logger = logging.getLogger(__name__)
    
    def process_secret(self, secret: K8sObject) -> K8sObject:
        """
        Process a secret based on the configured mode.
        
        Args:
            secret: Secret manifest
            
        Returns:
            Processed secret manifest
        """
        if self.mode == "skip":
            return {}
        elif self.mode == "encrypt":
            return self._encrypt_secret(secret)
        elif self.mode == "external-ref":
            return self._create_external_reference(secret)
        else:  # include
            return secret
    
    def _encrypt_secret(self, secret: K8sObject) -> K8sObject:
        """Create an encrypted version of the secret (placeholder implementation)."""
        # This would need integration with a tool like sealed-secrets or external secrets operator
        self.logger.warning("Secret encryption not implemented, including as-is")
        return secret
    
    def _create_external_reference(self, secret: K8sObject) -> K8sObject:
        """Create an external reference instead of including the secret data."""
        metadata = secret.get(K8sFields.METADATA, {})
        name = metadata.get(K8sFields.NAME, "unknown")
        
        # Create a placeholder that documents the external dependency
        return {
            K8sFields.API_VERSION: secret.get(K8sFields.API_VERSION, "v1"),
            K8sFields.KIND: "Secret",
            K8sFields.METADATA: {
                K8sFields.NAME: name,
                K8sFields.ANNOTATIONS: {
                    "helm.sh/external-secret": "true",
                    "helm.sh/external-secret-source": f"External secret '{name}' - must be created separately",
                },
            },
            "type": secret.get("type", "Opaque"),
            # Note: No data field - this is just a placeholder
        }