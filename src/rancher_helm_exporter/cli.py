"""Command line interface for exporting Kubernetes resources to a Helm chart."""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping, Optional, Sequence, Set, Any

from .interactive import build_interactive_plan
from .utils import StringUtils

# Import new improved modules
try:
    from .cli_improved import main as improved_main
    from .config import ExportConfig, GlobalConfig, load_config_from_args
    from .exporter import ExportOrchestrator
    USE_IMPROVED = True
except ImportError:
    USE_IMPROVED = False

# Ensure that PyYAML is available before importing it. The project intentionally avoids
# wrapping imports in try/except blocks, so we rely on importlib to perform the check.
_YAML_SPEC = importlib.util.find_spec("yaml")
if _YAML_SPEC is None:  # pragma: no cover - guard clause depends on environment
    sys.exit(
        "PyYAML is required to run this tool. Install dependencies with "
        "`pip install -r requirements.txt`."
    )
if _YAML_SPEC.loader is None:  # pragma: no cover - safety check
    sys.exit("PyYAML installation appears to be corrupted. Re-install the package and retry.")

yaml = importlib.util.module_from_spec(_YAML_SPEC)
_YAML_SPEC.loader.exec_module(yaml)


# Config management functions
def get_config_dir() -> Path:
    """Get the configuration directory."""
    config_dir = Path.home() / ".config" / "rancher-helm-exporter"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def save_config(name: str, config: Dict[str, Any]) -> None:
    """Save a configuration with a given name."""
    config_dir = get_config_dir()
    configs_file = config_dir / "saved_configs.json"

    # Load existing configs
    configs = {}
    if configs_file.exists():
        try:
            with configs_file.open('r', encoding='utf-8') as f:
                configs = json.load(f)
        except Exception:
            configs = {}

    # Add new config with metadata
    config_with_meta = {
        "config": config,
        "saved_at": datetime.now().isoformat(),
        "name": name
    }

    configs[name] = config_with_meta

    # Save back to file
    try:
        with configs_file.open('w', encoding='utf-8') as f:
            json.dump(configs, f, indent=2)
        print(f"Configuration saved: {name}")
    except Exception as e:
        print(f"Failed to save config: {e}")


def load_all_configs() -> Dict[str, Dict[str, Any]]:
    """Load all saved configurations."""
    config_dir = get_config_dir()
    configs_file = config_dir / "saved_configs.json"

    if not configs_file.exists():
        return {}

    try:
        with configs_file.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def list_config_names() -> List[str]:
    """List all saved configuration names."""
    configs = load_all_configs()
    return sorted(configs.keys())


def load_config(name: str) -> Optional[Dict[str, Any]]:
    """Load a specific configuration by name."""
    configs = load_all_configs()
    config_entry = configs.get(name)
    if config_entry:
        return config_entry.get("config")
    return None


# Interactive prompting functions
def prompt_required(prompt: str, default: Optional[str] = None) -> str:
    """Prompt for a required value."""
    while True:
        if default:
            value = input(f"{prompt} [{default}]: ").strip()
            if not value:
                value = default
        else:
            value = input(f"{prompt}: ").strip()

        if value:
            return value

        print("This field is required. Please provide a value.")


def prompt_optional(prompt: str, default: Optional[str] = None) -> Optional[str]:
    """Prompt for an optional value."""
    if default:
        value = input(f"{prompt} [{default}]: ").strip()
        return value if value else default
    else:
        value = input(f"{prompt} (optional): ").strip()
        return value if value else None


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    """Prompt for a yes/no answer."""
    default_str = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{prompt} [{default_str}]: ").strip().lower()
        if not answer:
            return default
        if answer in ('y', 'yes'):
            return True
        elif answer in ('n', 'no'):
            return False
        else:
            print("Please answer 'y' or 'n'")


def offer_existing_configs() -> Optional[Dict[str, Any]]:
    """Offer to use existing configurations."""
    configs = list_config_names()

    if not configs:
        return None

    print("\nFound existing configurations:")
    for i, config_name in enumerate(configs, 1):
        print(f"  {i}. {config_name}")

    print(f"  {len(configs) + 1}. Create new configuration")

    while True:
        try:
            choice = input(f"\nSelect option [1-{len(configs) + 1}]: ").strip()
            choice_num = int(choice)

            if 1 <= choice_num <= len(configs):
                # User selected existing config
                selected_config = configs[choice_num - 1]
                config = load_config(selected_config)
                if config:
                    print(f"\nUsing configuration: {selected_config}")
                    display_config_summary(config)
                    return config
            elif choice_num == len(configs) + 1:
                # User wants to create new config
                return None
            else:
                print(f"Invalid choice. Please enter 1-{len(configs) + 1}")
        except ValueError:
            print("Please enter a valid number")

    return None


def display_config_summary(config: Dict[str, Any]) -> None:
    """Display a summary of the configuration."""
    print("\nConfiguration Summary:")
    print("-" * 30)

    key_fields = ['release', 'namespace', 'output_dir', 'selector']
    for field in key_fields:
        if field in config:
            print(f"  {field}: {config[field]}")

    flags = []
    if config.get('include_secrets'):
        flags.append("include secrets")
    if config.get('create_test_chart'):
        flags.append("create test chart")
    if config.get('lint'):
        flags.append("run lint")
    if config.get('force'):
        flags.append("force overwrite")

    if flags:
        print(f"  flags: {', '.join(flags)}")


def prompt_for_new_config() -> Dict[str, Any]:
    """Interactive prompt for configuration values."""
    print("\nConfiguring new export...")
    config = {}

    # Required fields
    config['release'] = prompt_required("Release name (Helm chart name)", "my-app")
    config['namespace'] = prompt_optional("Kubernetes namespace", "default")

    # Optional but common fields
    config['output_dir'] = prompt_optional("Output directory", "./generated-chart")
    config['selector'] = prompt_optional("Label selector (e.g., app=my-app)", None)

    # Advanced options
    if prompt_yes_no("Configure advanced options?", False):
        # Kubectl options
        kubeconfig = prompt_optional("Custom kubeconfig path", None)
        if kubeconfig:
            config['kubeconfig'] = kubeconfig

        context = prompt_optional("Kubernetes context", None)
        if context:
            config['context'] = context

        # Resource filtering
        only_resources = prompt_optional("Only export these resource types (comma-separated)", None)
        if only_resources:
            config['only'] = [r.strip() for r in only_resources.split(',')]

        exclude_resources = prompt_optional("Exclude these resource types (comma-separated)", None)
        if exclude_resources:
            config['exclude'] = [r.strip() for r in exclude_resources.split(',')]

        # Chart metadata
        chart_version = prompt_optional("Chart version", "0.1.0")
        if chart_version:
            config['chart_version'] = chart_version

        app_version = prompt_optional("App version", "1.0.0")
        if app_version:
            config['app_version'] = app_version

        # File prefix
        prefix = prompt_optional("Filename prefix for manifests", None)
        if prefix:
            config['prefix'] = prefix

    # Secret handling
    if prompt_yes_no("Include secrets?", False):
        config['include_secrets'] = True
        if prompt_yes_no("Include service account secrets?", False):
            config['include_service_account_secrets'] = True

    # Test chart
    if prompt_yes_no("Create test chart alongside main chart?", False):
        config['create_test_chart'] = True
        config['test_suffix'] = prompt_optional("Test suffix", "test")

    # Validation and linting
    config['lint'] = prompt_yes_no("Run helm lint after generation?", True)
    config['force'] = prompt_yes_no("Overwrite output directory if it exists?", False)

    return config


def print_welcome_banner():
    """Print the Grabby-Helm welcome banner."""
    banner = """
+==============================================================================+
|                                                                              |
|    ####  ####    #   #### #### #   #     #   # ##### #     #   #            |
|   #     #   #   # #  #  # #  # #   #     #   # #     #     ## ##            |
|   # ##  ####   #####  ### ####  ###  --- ##### ####  #     # # #            |
|   #  #  # #    #   # #  # #  #   #       #   # #     #     #   #            |
|    ###  #  #   #   # #### ####   #       #   # ##### ##### #   #            |
|                                                                              |
|                         Kubernetes to Helm Chart Exporter                   |
|                                                                              |
|                     Transform your K8s workloads into                       |
|                        reusable Helm charts instantly!                      |
|                                                                              |
+==============================================================================+
    """
    print(banner)


def run_interactive_config() -> Optional[Dict[str, Any]]:
    """Run the interactive configuration prompt."""
    print_welcome_banner()
    print("\n>> Interactive Configuration")
    print("=" * 50)

    # Check for existing configs
    existing_config = offer_existing_configs()
    if existing_config:
        return existing_config

    # Prompt for new config
    config = prompt_for_new_config()

    # Save this config
    if prompt_yes_no("Save this configuration for future use?", True):
        config_name = prompt_required("Configuration name", f"config-{datetime.now().strftime('%Y%m%d-%H%M')}")
        save_config(config_name, config)

    return config


def apply_config_to_args(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    """Apply configuration dictionary to an argparse namespace."""
    for key, value in config.items():
        if key == 'release':
            args.release = value
        elif hasattr(args, key):
            setattr(args, key, value)


@dataclass
class ExportResult:
    """Summary details for an exported Kubernetes resource."""

    kind: str
    name: str
    path: Path


SUPPORTED_RESOURCES: Sequence[str] = (
    "deployments",
    "statefulsets",
    "daemonsets",
    "cronjobs",
    "jobs",
    "services",
    "configmaps",
    "secrets",
    "serviceaccounts",
    "persistentvolumeclaims",
    "ingresses",
)

# Fields that should be stripped from metadata in order to generate re-usable manifests.
_METADATA_FIELDS_TO_DROP: Sequence[str] = (
    "creationTimestamp",
    "deletionGracePeriodSeconds",
    "deletionTimestamp",
    "generateName",
    "generation",
    "managedFields",
    "ownerReferences",
    "resourceVersion",
    "selfLink",
    "uid",
)

# Secret types that should be ignored by default. Service account tokens are ephemeral
# objects that Kubernetes re-creates automatically and should typically not be captured in
# Helm charts.
_DEFAULT_SECRET_TYPES_TO_SKIP: Sequence[str] = (
    "kubernetes.io/service-account-token",
)


class ChartExporter:
    """Export Kubernetes API resources and render them into a Helm chart structure."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.logger = logging.getLogger("rancher_helm_exporter")
        self.chart_path = Path(args.output_dir).expanduser().resolve()
        self.templates_path = self.chart_path / "templates"
        self.kubectl_base = self._build_kubectl_base()
        raw_selection: Optional[Dict[str, Iterable[str]]] = getattr(args, "selection_names", None)
        self.selection_names: Dict[str, Set[str]] = (
            {resource: {str(name) for name in names} for resource, names in raw_selection.items()}
            if raw_selection
            else {}
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Execute the export pipeline."""

        self.ensure_required_binaries()
        self._prepare_chart_directory()

        exported: List[ExportResult] = []
        for resource in self._resources_to_process():
            items = self.list_resource_items(resource)
            if not items:
                self.logger.debug("No %s found matching filter criteria", resource)
                continue

            for manifest in items:
                if not self._should_include_manifest(resource, manifest):
                    continue

                cleaned_manifest = self._clean_manifest(manifest)
                result = self._write_manifest(resource, cleaned_manifest)
                exported.append(result)
                self.logger.info("Exported %s/%s", result.kind, result.name)

        if not exported:
            self.logger.warning("No resources were exported. Review your filters and try again.")

        if self.args.lint and shutil.which("helm"):
            self._run_helm_lint()

        self._write_summary(exported)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_kubectl_base(self) -> List[str]:
        base = ["kubectl"]
        if self.args.kubeconfig:
            base.extend(["--kubeconfig", self.args.kubeconfig])
        if self.args.context:
            base.extend(["--context", self.args.context])
        return base

    def ensure_required_binaries(self) -> None:
        for binary in ("kubectl",):
            if shutil.which(binary) is None:
                raise SystemExit(f"Required executable '{binary}' was not found in PATH.")

        if self.args.lint and shutil.which("helm") is None:
            raise SystemExit("Helm must be installed to use the --lint option.")

    def _prepare_chart_directory(self) -> None:
        if self.chart_path.exists():
            if not self.args.force:
                raise SystemExit(
                    f"Output directory '{self.chart_path}' already exists. Use --force to overwrite."
                )
            shutil.rmtree(self.chart_path)

        self.templates_path.mkdir(parents=True, exist_ok=True)
        (self.chart_path / "Chart.yaml").write_text(
            self._render_chart_yaml(), encoding="utf-8"
        )
        (self.chart_path / "values.yaml").write_text(
            "# Values file generated by rancher-helm-exporter\n", encoding="utf-8"
        )
        (self.chart_path / ".helmignore").write_text(self._default_helmignore(), encoding="utf-8")

    def _resources_to_process(self) -> Iterable[str]:
        resources = set(SUPPORTED_RESOURCES)
        if self.args.only:
            resources = {res.lower() for res in self.args.only}
        if self.args.exclude:
            resources.difference_update(res.lower() for res in self.args.exclude)
        return sorted(resources)

    def list_resource_items(self, resource: str) -> List[MutableMapping[str, object]]:
        cmd = [*self.kubectl_base, "get", resource, "-n", self.args.namespace, "-o", "json"]
        if self.args.selector:
            cmd.extend(["-l", self.args.selector])
        output = self._run(cmd)
        data = json.loads(output)
        items = data.get("items", [])
        items.sort(key=lambda item: item.get("metadata", {}).get("name", ""))  # type: ignore[no-any-return]
        return items  # type: ignore[return-value]

    def _should_include_manifest(self, resource: str, manifest: MutableMapping[str, object]) -> bool:
        selected_names = self.selection_names.get(resource)
        if selected_names is not None:
            name = self._manifest_name(manifest)
            if name not in selected_names:
                return False
            if resource == "secrets":
                return True

        if resource == "secrets" and not self.args.include_secrets:
            return False

        if resource == "secrets" and not self.args.include_service_account_secrets:
            secret_type = manifest.get("type")
            if secret_type in _DEFAULT_SECRET_TYPES_TO_SKIP:
                return False

        return True

    def _manifest_name(self, manifest: MutableMapping[str, object]) -> str:
        metadata = manifest.get("metadata")
        if isinstance(metadata, MutableMapping):
            name = metadata.get("name")
            if isinstance(name, str):
                return name
        return ""

    def _clean_manifest(self, manifest: MutableMapping[str, object]) -> MutableMapping[str, object]:
        manifest.pop("status", None)
        metadata = manifest.get("metadata")
        if isinstance(metadata, MutableMapping):
            for field in _METADATA_FIELDS_TO_DROP:
                metadata.pop(field, None)

            annotations = metadata.get("annotations")
            if isinstance(annotations, MutableMapping):
                for key in list(annotations):
                    if key.startswith("kubectl.kubernetes.io") or key.endswith("last-applied-configuration"):
                        annotations.pop(key, None)
                if not annotations:
                    metadata.pop("annotations", None)

            labels = metadata.get("labels")
            if isinstance(labels, MutableMapping) and "pod-template-hash" in labels:
                labels.pop("pod-template-hash", None)

            metadata.pop("namespace", None)

        kind = manifest.get("kind")
        if kind == "Service":
            self._clean_service_manifest(manifest)
        elif kind in {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob"}:
            self._clean_pod_controller_manifest(manifest)
        elif kind == "PersistentVolumeClaim":
            self._clean_pvc_manifest(manifest)

        return manifest

    def _clean_service_manifest(self, manifest: MutableMapping[str, object]) -> None:
        spec = manifest.get("spec")
        if not isinstance(spec, MutableMapping):
            return
        for key in ("clusterIP", "clusterIPs", "ipFamilies", "ipFamilyPolicy", "sessionAffinityConfig"):
            spec.pop(key, None)
        if spec.get("type") == "ClusterIP" and spec.get("clusterIP") == "None":
            spec.pop("clusterIP", None)

    def _clean_pod_controller_manifest(self, manifest: MutableMapping[str, object]) -> None:
        spec = manifest.get("spec")
        if not isinstance(spec, MutableMapping):
            return
        template = spec.get("template")
        if isinstance(template, MutableMapping):
            tmpl_metadata = template.get("metadata")
            if isinstance(tmpl_metadata, MutableMapping):
                tmpl_metadata.pop("creationTimestamp", None)
                annotations = tmpl_metadata.get("annotations")
                if isinstance(annotations, MutableMapping):
                    for key in list(annotations):
                        if key.startswith("kubectl.kubernetes.io"):
                            annotations.pop(key, None)
                    if not annotations:
                        tmpl_metadata.pop("annotations", None)
                labels = tmpl_metadata.get("labels")
                if isinstance(labels, MutableMapping) and "pod-template-hash" in labels:
                    labels.pop("pod-template-hash", None)
            spec.pop("revisionHistoryLimit", None)
        spec.pop("progressDeadlineSeconds", None)

    def _clean_pvc_manifest(self, manifest: MutableMapping[str, object]) -> None:
        spec = manifest.get("spec")
        if not isinstance(spec, MutableMapping):
            return
        for key in ("volumeName", "dataSource", "dataSourceRef"):
            spec.pop(key, None)

        metadata = manifest.get("metadata")
        if isinstance(metadata, MutableMapping):
            annotations = metadata.get("annotations")
            if isinstance(annotations, MutableMapping):
                for annotation in ("pv.kubernetes.io/bind-completed", "pv.kubernetes.io/bound-by-controller"):
                    annotations.pop(annotation, None)
                if not annotations:
                    metadata.pop("annotations", None)

    def _write_manifest(self, resource: str, manifest: MutableMapping[str, object]) -> ExportResult:
        kind = manifest.get("kind", resource.title())
        metadata = manifest.get("metadata", {})
        name = metadata.get("name", "resource") if isinstance(metadata, MutableMapping) else "resource"
        safe_name = StringUtils.slugify(str(name))
        filename = f"{self.args.prefix}{resource}-{safe_name}.yaml"
        output_path = self.templates_path / filename
        yaml_text = yaml.safe_dump(manifest, sort_keys=False)
        output_path.write_text(f"---\n{yaml_text}", encoding="utf-8")
        return ExportResult(kind=str(kind), name=str(name), path=output_path)

    def _write_summary(self, exported: Sequence[ExportResult]) -> None:
        if not exported:
            return

        lines = ["# Export Summary", "", f"Generated {len(exported)} manifests:"]
        for result in exported:
            rel_path = result.path.relative_to(self.chart_path)
            lines.append(f"- {result.kind}/{result.name}: templates/{rel_path.name}")
        summary_path = self.chart_path / "EXPORT.md"
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _run_helm_lint(self) -> None:
        cmd = ["helm", "lint", str(self.chart_path)]
        self.logger.info("Running helm lint on %s", self.chart_path)
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:  # pragma: no cover - passthrough
            raise SystemExit(
                "helm lint reported issues with the generated chart. Inspect the output above."
            ) from exc

    def _render_chart_yaml(self) -> str:
        return (
            "apiVersion: v2\n"
            f"name: {self.args.release}\n"
            "description: Helm chart generated from an existing Kubernetes deployment\n"
            "type: application\n"
            f"version: {self.args.chart_version}\n"
            f"appVersion: \"{self.args.app_version}\"\n"
        )

    def _default_helmignore(self) -> str:
        return (
            "# Default .helmignore generated by rancher-helm-exporter\n"
            "*.swp\n"
            "*.tmp\n"
            ".git\n"
            "*.pyc\n"
            "__pycache__/\n"
        )



    def _run(self, cmd: Sequence[str]) -> str:
        self.logger.debug("Running command: %s", shlex.join(cmd))
        try:
            completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:  # pragma: no cover - passthrough
            message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise SystemExit(f"Command failed: {message}") from exc
        return completed.stdout


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture live Kubernetes resources and generate a Helm chart",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("release", nargs='?', help="Name to use for the generated Helm chart")
    parser.add_argument(
        "--namespace",
        default="default",
        help="Namespace to inspect when fetching resources",
    )
    parser.add_argument(
        "--output-dir",
        default="./generated-chart",
        help="Directory where the chart will be written",
    )
    parser.add_argument(
        "--selector",
        help="Label selector used to filter resources (e.g. app=my-app)",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="Limit the export to the specified resource kinds",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        help="Exclude specific resource kinds from the export",
    )
    parser.add_argument(
        "--kubeconfig",
        help="Path to an alternate kubeconfig file",
    )
    parser.add_argument(
        "--context",
        help="Kubernetes context to use when executing kubectl commands",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Prefix to prepend to generated manifest filenames",
    )
    parser.add_argument(
        "--include-secrets",
        action="store_true",
        help="Include Kubernetes Secret resources in the generated chart",
    )
    parser.add_argument(
        "--include-service-account-secrets",
        action="store_true",
        help="Also capture service account token secrets (implies --include-secrets)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output directory if it already exists",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="Run 'helm lint' after generating the chart",
    )
    parser.add_argument(
        "--chart-version",
        default="0.1.0",
        help="Chart version to set in Chart.yaml",
    )
    parser.add_argument(
        "--app-version",
        default="1.0.0",
        help="Application version to set in Chart.yaml",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch an interactive picker to choose deployments and related resources",
    )
    parser.add_argument(
        "--config-prompt",
        action="store_true",
        help="Use interactive configuration prompting",
    )

    args = parser.parse_args(argv)

    if args.include_service_account_secrets:
        args.include_secrets = True

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    return args


def main(argv: Optional[Sequence[str]] = None) -> None:
    # Use legacy implementation with interactive config
    # Note: Improved architecture disabled to support interactive config mode
    args = parse_args(argv)

    # If no release name provided or config-prompt flag is used, run interactive config
    if not args.release or args.config_prompt:
        try:
            config = run_interactive_config()
            if config:
                apply_config_to_args(args, config)

            # Ensure we have a release name after interactive config
            if not args.release:
                print("No release name provided. Exiting.")
                return

        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return
        except Exception as e:
            logging.error("Interactive configuration failed: %s", e)
            return

    if args.interactive:
        preview_exporter = ChartExporter(args)
        preview_exporter.ensure_required_binaries()
        plan = build_interactive_plan(preview_exporter)
        if plan.resources():
            args.only = sorted(plan.resources())
        args.selection_names = plan.to_dict()
        if plan.includes_secrets():
            args.include_secrets = True
            args.include_service_account_secrets = True

    exporter = ChartExporter(args)
    exporter.run()


if __name__ == "__main__":  # pragma: no cover
    main()
