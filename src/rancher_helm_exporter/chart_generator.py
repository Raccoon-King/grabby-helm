"""Helm chart generation utilities."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .constants import DEFAULT_APP_VERSION, DEFAULT_CHART_VERSION, K8sFields
from .types import ChartGenerationError, ChartGeneratorProtocol, ExportResult, K8sObject
from .utils import StringUtils


class ChartGenerator(ChartGeneratorProtocol):
    """Generates Helm chart structure and files."""
    
    def __init__(self, release_name: str, chart_version: str = DEFAULT_CHART_VERSION, app_version: str = DEFAULT_APP_VERSION):
        self.release_name = release_name
        self.chart_version = chart_version
        self.app_version = app_version
        self.logger = logging.getLogger(__name__)
    
    def create_chart_structure(self, output_path: str, force: bool = False) -> Path:
        """
        Create the basic Helm chart directory structure.
        
        Args:
            output_path: Path where the chart should be created
            force: Whether to overwrite existing directory
            
        Returns:
            Path to the created chart directory
            
        Raises:
            ChartGenerationError: If chart creation fails
        """
        chart_path = Path(output_path).expanduser().resolve()
        templates_path = chart_path / "templates"
        
        # Handle existing directory
        if chart_path.exists():
            if not force:
                raise ChartGenerationError(
                    f"Output directory '{chart_path}' already exists. Use force=True to overwrite."
                )
            self.logger.info("Removing existing chart directory: %s", chart_path)
            shutil.rmtree(chart_path)
        
        # Create directory structure
        try:
            templates_path.mkdir(parents=True, exist_ok=True)
            self.logger.info("Created chart directory structure at: %s", chart_path)
        except OSError as e:
            raise ChartGenerationError(f"Failed to create chart directory: {e}") from e
        
        # Create Chart.yaml
        chart_yaml_content = self._generate_chart_yaml()
        (chart_path / "Chart.yaml").write_text(chart_yaml_content, encoding="utf-8")
        
        # Create values.yaml
        values_yaml_content = self._generate_values_yaml()
        (chart_path / "values.yaml").write_text(values_yaml_content, encoding="utf-8")
        
        # Create .helmignore
        helmignore_content = self._generate_helmignore()
        (chart_path / ".helmignore").write_text(helmignore_content, encoding="utf-8")
        
        # Create README template
        readme_content = self._generate_readme()
        (chart_path / "README.md").write_text(readme_content, encoding="utf-8")
        
        self.logger.info("Created chart structure for release: %s", self.release_name)
        return chart_path
    
    def write_manifest(
        self, 
        manifest: K8sObject, 
        output_path: str,
        prefix: str = "",
    ) -> ExportResult:
        """
        Write a Kubernetes manifest to a Helm template file.
        
        Args:
            manifest: Kubernetes manifest to write
            output_path: Base output directory path
            prefix: Optional prefix for the filename
            
        Returns:
            ExportResult with details about the written file
            
        Raises:
            ChartGenerationError: If writing fails
        """
        import yaml
        
        chart_path = Path(output_path)
        templates_path = chart_path / "templates"
        
        # Extract manifest details
        kind = str(manifest.get(K8sFields.KIND, "resource"))
        metadata = manifest.get(K8sFields.METADATA, {})
        name = metadata.get(K8sFields.NAME, "resource") if isinstance(metadata, dict) else "resource"
        
        # Generate filename
        safe_name = StringUtils.slugify(str(name))
        resource_type = kind.lower()
        filename = f"{prefix}{resource_type}-{safe_name}.yaml"
        output_file_path = templates_path / filename
        
        try:
            # Add Helm template header comment
            yaml_content = yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False)
            
            # Add template header
            template_content = f"""{{{{- if .Values.{resource_type}.enabled | default true }}}}
---
{yaml_content}{{{{- end }}}}"""
            
            output_file_path.write_text(template_content, encoding="utf-8")
            
            self.logger.debug("Wrote manifest to: %s", output_file_path)
            
            return ExportResult(
                kind=kind,
                name=str(name),
                path=output_file_path,
            )
            
        except Exception as e:
            raise ChartGenerationError(
                f"Failed to write manifest {kind}/{name}: {e}"
            ) from e
    
    def write_summary(self, export_results: List[ExportResult], chart_path: Path) -> None:
        """
        Write an export summary file.
        
        Args:
            export_results: List of exported resources
            chart_path: Path to the chart directory
        """
        if not export_results:
            return
        
        lines = [
            f"# {self.release_name} Chart Export Summary",
            "",
            f"Generated {len(export_results)} manifests from live Kubernetes resources.",
            "",
            "## Exported Resources",
            "",
        ]
        
        # Group by kind
        by_kind: Dict[str, List[ExportResult]] = {}
        for result in export_results:
            by_kind.setdefault(result.kind, []).append(result)
        
        for kind in sorted(by_kind.keys()):
            resources = by_kind[kind]
            lines.append(f"### {kind}")
            lines.append("")
            
            for result in sorted(resources, key=lambda r: r.name):
                rel_path = result.path.relative_to(chart_path)
                lines.append(f"- **{result.name}**: `{rel_path}`")
            
            lines.append("")
        
        lines.extend([
            "## Usage",
            "",
            f"Install this chart with:",
            "",
            "```bash",
            f"helm install {self.release_name} .",
            "```",
            "",
            "To customize the installation, modify `values.yaml` or use `--set` flags:",
            "",
            "```bash",
            f"helm install {self.release_name} . --set deployment.enabled=false",
            "```",
            "",
            "## Notes",
            "",
            "- This chart was generated from live Kubernetes resources",
            "- Review and customize the templates before production use",
            "- Consider parameterizing environment-specific values",
            "",
        ])
        
        summary_path = chart_path / "EXPORT.md"
        summary_path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
        
        self.logger.info("Created export summary: %s", summary_path)
    
    def lint_chart(self, chart_path: Path) -> bool:
        """
        Run helm lint on the generated chart.
        
        Args:
            chart_path: Path to the chart directory
            
        Returns:
            True if lint passes, False otherwise
        """
        if not shutil.which("helm"):
            self.logger.warning("helm command not found, skipping lint")
            return False
        
        cmd = ["helm", "lint", str(chart_path)]
        self.logger.info("Running helm lint on %s", chart_path)
        
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            self.logger.info("Helm lint passed successfully")
            if result.stdout:
                self.logger.debug("Lint output: %s", result.stdout)
            
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error("Helm lint failed: %s", e.stderr or e.stdout)
            return False
        
        except subprocess.TimeoutExpired:
            self.logger.error("Helm lint timed out")
            return False
        
        except Exception as e:
            self.logger.error("Unexpected error running helm lint: %s", e)
            return False
    
    def _generate_chart_yaml(self) -> str:
        """Generate Chart.yaml content."""
        return f"""apiVersion: v2
name: {self.release_name}
description: Helm chart generated from existing Kubernetes deployment
type: application
version: {self.chart_version}
appVersion: "{self.app_version}"
keywords:
  - kubernetes
  - helm
  - generated
maintainers:
  - name: rancher-helm-exporter
    email: ops@example.com
sources:
  - https://github.com/your-org/your-repo
"""
    
    def _generate_values_yaml(self) -> str:
        """Generate values.yaml content with common parameterization."""
        return f"""# Default values for {self.release_name}
# This is a YAML-formatted file.
# Declare variables to be substituted into your templates.

# Global settings
global:
  imageRegistry: ""
  imagePullSecrets: []

# Resource-specific settings
deployment:
  enabled: true
  replicaCount: 1
  
statefulset:
  enabled: true
  
daemonset:
  enabled: true

cronjob:
  enabled: true
  
job:
  enabled: true

service:
  enabled: true
  type: ClusterIP

configmap:
  enabled: true

secret:
  enabled: true

serviceaccount:
  enabled: true

persistentvolumeclaim:
  enabled: true

ingress:
  enabled: true

# Common resource settings
resources:
  # limits:
  #   cpu: 100m
  #   memory: 128Mi
  # requests:
  #   cpu: 100m
  #   memory: 128Mi

nodeSelector: {{}}

tolerations: []

affinity: {{}}

# Security context
securityContext: {{}}
  # fsGroup: 2000

podSecurityContext: {{}}
  # runAsNonRoot: true
  # runAsUser: 1000

# Monitoring
monitoring:
  enabled: false
  serviceMonitor:
    enabled: false
  
# Additional labels and annotations
commonLabels: {{}}
commonAnnotations: {{}}
"""
    
    def _generate_helmignore(self) -> str:
        """Generate .helmignore content."""
        return """# Patterns to ignore when building packages.
# This supports shell glob matching, relative path matching, and
# negation (prefixed with !). Only one pattern per line.
.DS_Store
# Common VCS dirs
.git/
.gitignore
.bzr/
.bzrignore
.hg/
.hgignore
.svn/
# Common backup files
*.swp
*.bak
*.tmp
*.orig
*~
# Various IDEs
.project
.idea/
*.tmproj
.vscode/
# Generated files
EXPORT.md
*.pyc
__pycache__/
"""
    
    def _generate_readme(self) -> str:
        """Generate README.md template."""
        return f"""# {self.release_name}

This Helm chart was generated from live Kubernetes resources using rancher-helm-exporter.

## Installation

```bash
helm install {self.release_name} .
```

## Configuration

The following table lists the configurable parameters and their default values:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `deployment.enabled` | Enable Deployment resources | `true` |
| `service.enabled` | Enable Service resources | `true` |
| `configmap.enabled` | Enable ConfigMap resources | `true` |
| `secret.enabled` | Enable Secret resources | `true` |

## Customization

To customize the installation:

1. Edit `values.yaml` to modify default values
2. Use `--set` flags during installation:
   ```bash
   helm install {self.release_name} . --set deployment.replicaCount=3
   ```
3. Create your own values file:
   ```bash
   helm install {self.release_name} . -f my-values.yaml
   ```

## Upgrading

```bash
helm upgrade {self.release_name} .
```

## Uninstalling

```bash
helm uninstall {self.release_name}
```

## Generated Resources

See `EXPORT.md` for a detailed list of all exported resources.

## Notes

- This chart was generated from existing Kubernetes resources
- Review all templates before deploying to production
- Consider parameterizing environment-specific values
- Secrets are included as-is - consider using external secret management
"""


class TemplateProcessor:
    """Processes manifests to add Helm templating."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def add_basic_templating(self, manifest: K8sObject) -> K8sObject:
        """
        Add basic Helm templating to a manifest.
        
        Args:
            manifest: Original manifest
            
        Returns:
            Manifest with basic templating added
        """
        # This is a simplified version - a full implementation would
        # identify common patterns and parameterize them
        
        templated = dict(manifest)
        
        # Add common labels template
        metadata = templated.get(K8sFields.METADATA)
        if isinstance(metadata, dict):
            labels = metadata.get(K8sFields.LABELS, {})
            if isinstance(labels, dict):
                # Add Helm standard labels
                labels.update({
                    "helm.sh/chart": '{{ include "chart.chart" . }}',
                    "app.kubernetes.io/name": '{{ include "chart.name" . }}',
                    "app.kubernetes.io/instance": "{{ .Release.Name }}",
                    "app.kubernetes.io/version": "{{ .Chart.AppVersion | quote }}",
                    "app.kubernetes.io/managed-by": "{{ .Release.Service }}",
                })
                metadata[K8sFields.LABELS] = labels
        
        return templated
    
    def parameterize_common_values(self, manifest: K8sObject) -> K8sObject:
        """
        Parameterize common values that should be configurable.
        
        Args:
            manifest: Original manifest
            
        Returns:
            Manifest with parameterized values
        """
        # This would identify common patterns like:
        # - Image names and tags
        # - Replica counts
        # - Resource limits
        # - Environment variables
        # And replace them with template expressions
        
        # Simplified implementation
        return manifest