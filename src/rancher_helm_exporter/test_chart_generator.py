"""Test chart generation utilities for creating test versions of applications."""
from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional, Set

from .chart_generator import ChartGenerator
from .constants import K8sFields
from .types import ExportResult, K8sObject
from .utils import ManifestTraverser


class TestChartGenerator:
    """Generates test charts with modified resource names and configurations."""
    
    def __init__(
        self,
        base_release_name: str,
        test_suffix: str = "test",
        chart_version: str = "0.1.0-test",
        app_version: str = "1.0.0-test",
    ):
        self.base_release_name = base_release_name
        self.test_suffix = test_suffix
        self.test_release_name = f"{base_release_name}-{test_suffix}"
        
        self.chart_generator = ChartGenerator(
            release_name=self.test_release_name,
            chart_version=chart_version,
            app_version=app_version,
        )
        
        self.logger = logging.getLogger(__name__)
        
        # Track resource name mappings for cross-references
        self.name_mappings: Dict[str, str] = {}
    
    def create_test_chart(
        self,
        manifests: List[K8sObject],
        output_path: str,
        force: bool = False,
    ) -> List[ExportResult]:
        """
        Create a test chart from existing manifests.
        
        Args:
            manifests: List of Kubernetes manifests to convert
            output_path: Path where the test chart should be created
            force: Whether to overwrite existing directory
            
        Returns:
            List of exported test resources
        """
        self.logger.info("Creating test chart: %s", self.test_release_name)
        
        # Create chart structure
        chart_path = self.chart_generator.create_chart_structure(output_path, force)
        
        # Build name mappings first pass
        self._build_name_mappings(manifests)
        
        # Transform manifests for test environment
        test_manifests = []
        for manifest in manifests:
            test_manifest = self._transform_manifest_for_test(manifest)
            if test_manifest:
                test_manifests.append(test_manifest)
        
        # Export test manifests
        export_results = []
        for test_manifest in test_manifests:
            try:
                result = self.chart_generator.write_manifest(
                    test_manifest,
                    str(chart_path),
                    prefix="test-",
                )
                export_results.append(result)
                
                self.logger.debug(
                    "Created test resource: %s/%s",
                    result.kind,
                    result.name,
                )
                
            except Exception as e:
                name = ManifestTraverser.get_manifest_name(test_manifest)
                kind = test_manifest.get(K8sFields.KIND, "Unknown")
                self.logger.error("Failed to export test resource %s/%s: %s", kind, name, e)
        
        # Create test-specific values.yaml
        self._create_test_values_file(chart_path)
        
        # Create test summary
        self.chart_generator.write_summary(export_results, chart_path)
        
        # Create test-specific README
        self._create_test_readme(chart_path, len(export_results))
        
        self.logger.info("Test chart created with %d resources", len(export_results))
        return export_results
    
    def _build_name_mappings(self, manifests: List[K8sObject]) -> None:
        """Build mappings from original names to test names."""
        self.name_mappings.clear()
        
        for manifest in manifests:
            original_name = ManifestTraverser.get_manifest_name(manifest)
            if original_name:
                test_name = self._generate_test_name(original_name)
                self.name_mappings[original_name] = test_name
    
    def _transform_manifest_for_test(self, manifest: K8sObject) -> Optional[K8sObject]:
        """
        Transform a manifest for test environment.
        
        Args:
            manifest: Original manifest
            
        Returns:
            Transformed test manifest or None if should be skipped
        """
        test_manifest = deepcopy(manifest)
        kind = test_manifest.get(K8sFields.KIND, "")
        
        # Transform based on resource type
        if kind == "Deployment":
            self._transform_deployment(test_manifest)
        elif kind == "StatefulSet":
            self._transform_statefulset(test_manifest)
        elif kind == "Service":
            self._transform_service(test_manifest)
        elif kind == "ConfigMap":
            self._transform_configmap(test_manifest)
        elif kind == "Secret":
            self._transform_secret(test_manifest)
        elif kind == "Ingress":
            self._transform_ingress(test_manifest)
        elif kind == "ServiceAccount":
            self._transform_service_account(test_manifest)
        elif kind == "PersistentVolumeClaim":
            self._transform_pvc(test_manifest)
        else:
            # Generic transformation for other resource types
            self._transform_generic_resource(test_manifest)
        
        return test_manifest
    
    def _transform_deployment(self, manifest: K8sObject) -> None:
        """Transform a Deployment for test environment."""
        self._transform_metadata(manifest)
        
        spec = manifest.get(K8sFields.SPEC, {})
        
        # Reduce replica count for test environment
        current_replicas = spec.get(K8sFields.REPLICAS, 1)
        test_replicas = min(current_replicas, 1)  # Max 1 replica for tests
        spec[K8sFields.REPLICAS] = test_replicas
        
        # Transform pod template
        template = spec.get(K8sFields.TEMPLATE, {})
        self._transform_pod_template(template)
        
        # Update selector labels
        selector = spec.get(K8sFields.SELECTOR, {})
        if K8sFields.LABELS in selector.get("matchLabels", {}):
            self._transform_labels(selector["matchLabels"])
    
    def _transform_statefulset(self, manifest: K8sObject) -> None:
        """Transform a StatefulSet for test environment."""
        self._transform_deployment(manifest)  # Same transformations as Deployment
        
        spec = manifest.get(K8sFields.SPEC, {})
        
        # Transform volume claim templates
        volume_claim_templates = spec.get("volumeClaimTemplates", [])
        for template in volume_claim_templates:
            if isinstance(template, dict):
                self._transform_metadata(template)
    
    def _transform_service(self, manifest: K8sObject) -> None:
        """Transform a Service for test environment."""
        self._transform_metadata(manifest)
        
        spec = manifest.get(K8sFields.SPEC, {})
        
        # Update selector to match test pods
        selector = spec.get(K8sFields.SELECTOR, {})
        if isinstance(selector, dict):
            self._transform_labels(selector)
    
    def _transform_configmap(self, manifest: K8sObject) -> None:
        """Transform a ConfigMap for test environment."""
        self._transform_metadata(manifest)
        
        # ConfigMap data usually doesn't need transformation,
        # but you could modify configuration values here for test environment
        data = manifest.get("data", {})
        if isinstance(data, dict):
            # Example: Update database names, URLs, etc. for test environment
            for key, value in data.items():
                if isinstance(value, str):
                    # Simple replacement for common test scenarios
                    if "database" in key.lower() and not value.endswith("-test"):
                        data[key] = f"{value}-test"
    
    def _transform_secret(self, manifest: K8sObject) -> None:
        """Transform a Secret for test environment."""
        self._transform_metadata(manifest)
        # Note: Secret data is typically left unchanged as it's base64 encoded
        # In a real scenario, you might want to reference different test secrets
    
    def _transform_ingress(self, manifest: K8sObject) -> None:
        """Transform an Ingress for test environment."""
        self._transform_metadata(manifest)
        
        spec = manifest.get(K8sFields.SPEC, {})
        
        # Update rules to point to test services
        rules = spec.get(K8sFields.RULES, [])
        for rule in rules:
            if isinstance(rule, dict):
                http = rule.get(K8sFields.HTTP, {})
                if isinstance(http, dict):
                    paths = http.get(K8sFields.PATHS, [])
                    for path in paths:
                        if isinstance(path, dict):
                            self._update_backend_service_references(path.get(K8sFields.BACKEND, {}))
        
        # Update default backend if present
        default_backend = spec.get(K8sFields.DEFAULT_BACKEND, {})
        if default_backend:
            self._update_backend_service_references(default_backend)
    
    def _transform_service_account(self, manifest: K8sObject) -> None:
        """Transform a ServiceAccount for test environment."""
        self._transform_metadata(manifest)
        # ServiceAccounts typically don't need special transformation beyond metadata
    
    def _transform_pvc(self, manifest: K8sObject) -> None:
        """Transform a PersistentVolumeClaim for test environment."""
        self._transform_metadata(manifest)
        
        spec = manifest.get(K8sFields.SPEC, {})
        
        # Reduce storage size for test environment
        resources = spec.get("resources", {})
        requests = resources.get("requests", {})
        if "storage" in requests:
            # Reduce storage size for tests (e.g., from 10Gi to 1Gi)
            current_storage = requests["storage"]
            if isinstance(current_storage, str) and "Gi" in current_storage:
                try:
                    size = int(current_storage.replace("Gi", ""))
                    test_size = min(size, 1)  # Max 1Gi for tests
                    requests["storage"] = f"{test_size}Gi"
                except ValueError:
                    pass  # Keep original value if parsing fails
    
    def _transform_generic_resource(self, manifest: K8sObject) -> None:
        """Generic transformation for any resource type."""
        self._transform_metadata(manifest)
    
    def _transform_metadata(self, manifest: K8sObject) -> None:
        """Transform metadata for test environment."""
        metadata = manifest.get(K8sFields.METADATA, {})
        if not isinstance(metadata, dict):
            return
        
        # Transform name
        original_name = metadata.get(K8sFields.NAME, "")
        if original_name:
            test_name = self._generate_test_name(original_name)
            metadata[K8sFields.NAME] = test_name
        
        # Transform labels
        labels = metadata.get(K8sFields.LABELS, {})
        if isinstance(labels, dict):
            self._transform_labels(labels)
            
            # Add test-specific labels
            labels["app.kubernetes.io/instance"] = f"{self.base_release_name}-{self.test_suffix}"
            labels["app.kubernetes.io/part-of"] = f"{self.base_release_name}-test-suite"
            labels["environment"] = "test"
        
        # Transform annotations
        annotations = metadata.get(K8sFields.ANNOTATIONS, {})
        if isinstance(annotations, dict):
            annotations["helm.sh/test-chart"] = "true"
            annotations["description"] = f"Test version of {original_name}"
    
    def _transform_pod_template(self, template: Dict) -> None:
        """Transform pod template metadata and spec."""
        if not isinstance(template, dict):
            return
        
        # Transform template metadata
        template_metadata = template.get(K8sFields.METADATA, {})
        if isinstance(template_metadata, dict):
            labels = template_metadata.get(K8sFields.LABELS, {})
            if isinstance(labels, dict):
                self._transform_labels(labels)
                
                # Add test-specific pod labels
                labels["environment"] = "test"
                labels["test-suite"] = f"{self.base_release_name}-{self.test_suffix}"
        
        # Transform pod spec
        pod_spec = template.get(K8sFields.SPEC, {})
        if isinstance(pod_spec, dict):
            # Transform container references to ConfigMaps/Secrets
            self._transform_container_references(pod_spec)
    
    def _transform_container_references(self, pod_spec: Dict) -> None:
        """Transform container references to ConfigMaps and Secrets."""
        containers = pod_spec.get(K8sFields.CONTAINERS, [])
        for container in containers:
            if isinstance(container, dict):
                # Transform environment variable references
                env = container.get(K8sFields.ENV, [])
                for env_var in env:
                    if isinstance(env_var, dict):
                        value_from = env_var.get(K8sFields.VALUE_FROM, {})
                        self._transform_value_from_references(value_from)
                
                # Transform envFrom references
                env_from = container.get(K8sFields.ENV_FROM, [])
                for env_source in env_from:
                    if isinstance(env_source, dict):
                        config_map_ref = env_source.get(K8sFields.CONFIG_MAP_REF, {})
                        if K8sFields.NAME in config_map_ref:
                            original_name = config_map_ref[K8sFields.NAME]
                            config_map_ref[K8sFields.NAME] = self.name_mappings.get(original_name, original_name)
                        
                        secret_ref = env_source.get(K8sFields.SECRET_REF, {})
                        if K8sFields.NAME in secret_ref:
                            original_name = secret_ref[K8sFields.NAME]
                            secret_ref[K8sFields.NAME] = self.name_mappings.get(original_name, original_name)
        
        # Transform volume references
        volumes = pod_spec.get(K8sFields.VOLUMES, [])
        for volume in volumes:
            if isinstance(volume, dict):
                # ConfigMap volumes
                config_map = volume.get(K8sFields.CONFIG_MAP, {})
                if K8sFields.NAME in config_map:
                    original_name = config_map[K8sFields.NAME]
                    config_map[K8sFields.NAME] = self.name_mappings.get(original_name, original_name)
                
                # Secret volumes
                secret = volume.get(K8sFields.SECRET, {})
                if K8sFields.SECRET_NAME in secret:
                    original_name = secret[K8sFields.SECRET_NAME]
                    secret[K8sFields.SECRET_NAME] = self.name_mappings.get(original_name, original_name)
                elif K8sFields.NAME in secret:
                    original_name = secret[K8sFields.NAME]
                    secret[K8sFields.NAME] = self.name_mappings.get(original_name, original_name)
                
                # PVC volumes
                pvc = volume.get(K8sFields.PERSISTENT_VOLUME_CLAIM, {})
                if K8sFields.CLAIM_NAME in pvc:
                    original_name = pvc[K8sFields.CLAIM_NAME]
                    pvc[K8sFields.CLAIM_NAME] = self.name_mappings.get(original_name, original_name)
    
    def _transform_value_from_references(self, value_from: Dict) -> None:
        """Transform valueFrom references in environment variables."""
        if not isinstance(value_from, dict):
            return
        
        config_map_ref = value_from.get(K8sFields.CONFIG_MAP_KEY_REF, {})
        if K8sFields.NAME in config_map_ref:
            original_name = config_map_ref[K8sFields.NAME]
            config_map_ref[K8sFields.NAME] = self.name_mappings.get(original_name, original_name)
        
        secret_ref = value_from.get(K8sFields.SECRET_KEY_REF, {})
        if K8sFields.NAME in secret_ref:
            original_name = secret_ref[K8sFields.NAME]
            secret_ref[K8sFields.NAME] = self.name_mappings.get(original_name, original_name)
    
    def _transform_labels(self, labels: Dict) -> None:
        """Transform labels that might reference other resources."""
        # Transform app labels to include test suffix
        if "app" in labels and not labels["app"].endswith(f"-{self.test_suffix}"):
            labels["app"] = f"{labels['app']}-{self.test_suffix}"
        
        if "app.kubernetes.io/name" in labels:
            original_name = labels["app.kubernetes.io/name"]
            labels["app.kubernetes.io/name"] = self._generate_test_name(original_name)
    
    def _update_backend_service_references(self, backend: Dict) -> None:
        """Update service references in ingress backends."""
        if not isinstance(backend, dict):
            return
        
        # New format
        service = backend.get(K8sFields.SERVICE, {})
        if K8sFields.NAME in service:
            original_name = service[K8sFields.NAME]
            service[K8sFields.NAME] = self.name_mappings.get(original_name, original_name)
        
        # Legacy format
        if K8sFields.SERVICE_NAME in backend:
            original_name = backend[K8sFields.SERVICE_NAME]
            backend[K8sFields.SERVICE_NAME] = self.name_mappings.get(original_name, original_name)
    
    def _generate_test_name(self, original_name: str) -> str:
        """Generate a test name from an original name."""
        if original_name.endswith(f"-{self.test_suffix}"):
            return original_name
        return f"{original_name}-{self.test_suffix}"
    
    def _create_test_values_file(self, chart_path: Path) -> None:
        """Create a test-specific values.yaml file."""
        values_content = f"""# Test values for {self.test_release_name}
# This file contains test-specific configurations

# Test environment settings
global:
  environment: test
  testSuite: "{self.base_release_name}-{self.test_suffix}"

# Reduced resource requirements for test environment
resources:
  limits:
    cpu: 100m
    memory: 128Mi
  requests:
    cpu: 50m
    memory: 64Mi

# Test-specific scaling
replicaCount: 1

# Storage settings for test
persistence:
  size: 1Gi

# Test database settings (example)
database:
  name: "{self.base_release_name}_test"
  
# Test-specific annotations
commonAnnotations:
  helm.sh/test-chart: "true"
  environment: "test"

# Test-specific labels
commonLabels:
  environment: "test"
  test-suite: "{self.base_release_name}-{self.test_suffix}"
  app.kubernetes.io/part-of: "{self.base_release_name}-test-suite"
"""
        
        values_path = chart_path / "values.yaml"
        values_path.write_text(values_content, encoding="utf-8")
        
        self.logger.debug("Created test values.yaml at: %s", values_path)
    
    def _create_test_readme(self, chart_path: Path, resource_count: int) -> None:
        """Create a test-specific README.md file."""
        readme_content = f"""# {self.test_release_name}

This is a **test chart** generated from the production `{self.base_release_name}` application.
It contains {resource_count} test resources with `-{self.test_suffix}` suffixed names.

## Purpose

This test chart allows you to:
- Deploy test versions alongside production deployments
- Test configuration changes safely
- Validate deployment procedures
- Run integration tests

## Installation

```bash
# Install the test chart
helm install {self.test_release_name} .

# Or install with custom test namespace
helm install {self.test_release_name} . --namespace {self.base_release_name}-test --create-namespace
```

## Key Differences from Production

- **Resource Names**: All resources have `-{self.test_suffix}` suffix
- **Reduced Resources**: Lower CPU/memory limits and requests
- **Single Replica**: Deployments limited to 1 replica for testing
- **Smaller Storage**: PVCs use minimal storage sizes
- **Test Labels**: Additional labels identify this as a test deployment

## Testing

After installation, verify the test deployment:

```bash
# Check test pods
kubectl get pods -l test-suite={self.base_release_name}-{self.test_suffix}

# Check test services
kubectl get services -l environment=test

# Run connectivity tests (if applicable)
kubectl exec deployment/{self.base_release_name}-{self.test_suffix} -- curl http://{self.base_release_name}service-{self.test_suffix}
```

## Cleanup

```bash
# Uninstall test chart
helm uninstall {self.test_release_name}
```

## Notes

- This chart is automatically generated for testing purposes
- Do not use in production environments
- Resource names are automatically transformed to avoid conflicts
- Database names and other configuration may be suffixed with `-test`

"""
        
        readme_path = chart_path / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        
        self.logger.debug("Created test README.md at: %s", readme_path)