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


def list_available_deployments(namespace: str = "default") -> List[Dict[str, Any]]:
    """List available deployments in the specified namespace."""
    def _get_deployments():
        cmd = ["kubectl", "get", "deployments", "-n", namespace, "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    try:
        data = retry_operation(_get_deployments, f"Listing deployments in namespace '{namespace}'")

        deployments = []
        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})

            # Extract useful information
            deployment_info = {
                "name": metadata.get("name", "unknown"),
                "replicas": spec.get("replicas", 0),
                "ready_replicas": status.get("readyReplicas", 0),
                "namespace": metadata.get("namespace", namespace),
                "labels": metadata.get("labels", {}),
                "creation_time": metadata.get("creationTimestamp", ""),
                "images": []
            }

            # Extract container images
            containers = spec.get("template", {}).get("spec", {}).get("containers", [])
            for container in containers:
                if "image" in container:
                    deployment_info["images"].append(container["image"])

            deployments.append(deployment_info)

        return sorted(deployments, key=lambda x: x["name"])

    except subprocess.CalledProcessError as e:
        print(f"Failed to list deployments: {e.stderr or e}")
        return []
    except Exception as e:
        print(f"Error listing deployments: {e}")
        return []


def filter_deployments(deployments: List[Dict[str, Any]], search_term: str = "",
                      status_filter: str = "", min_replicas: int = 0,
                      max_age_days: int = 0) -> List[Dict[str, Any]]:
    """Filter deployments based on search criteria."""
    filtered = deployments.copy()

    # Search by name
    if search_term:
        search_lower = search_term.lower()
        filtered = [d for d in filtered if search_lower in d["name"].lower()]

    # Filter by status
    if status_filter:
        status_map = {
            "ready": lambda d: get_deployment_status(d).startswith("✅"),
            "failed": lambda d: get_deployment_status(d).startswith("❌"),
            "issue": lambda d: get_deployment_status(d).startswith("⚠️"),
            "scaling": lambda d: get_deployment_status(d).startswith("🔄"),
            "stopped": lambda d: get_deployment_status(d).startswith("⚪")
        }
        if status_filter.lower() in status_map:
            filtered = [d for d in filtered if status_map[status_filter.lower()](d)]

    # Filter by minimum replicas
    if min_replicas > 0:
        filtered = [d for d in filtered if d["replicas"] >= min_replicas]

    # Filter by age (if creation_time is available)
    if max_age_days > 0:
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        filtered = [d for d in filtered
                   if d.get("creation_time") and
                   datetime.fromisoformat(d["creation_time"].replace('Z', '+00:00')) > cutoff_date]

    return filtered


def preview_chart_creation(selected_deployments: List[Dict[str, Any]],
                          config: Dict[str, Any], namespace: str) -> bool:
    """Preview what will be created and validate before chart generation."""
    print(f"\n📋 Chart Creation Preview")
    print("=" * 50)

    if len(selected_deployments) == 1:
        deployment = selected_deployments[0]
        chart_name = config.get('release', deployment['name'])
        output_dir = config.get('output_dir', f"./{deployment['name']}-chart")

        print(f"Chart Name: {chart_name}")
        print(f"Output Directory: {output_dir}")
        print(f"Source Deployment: {deployment['name']} ({deployment['ready_replicas']}/{deployment['replicas']} replicas)")

        # Estimate resources to be included
        print(f"\n📦 Resources to include:")
        print(f"  ✓ 1 Deployment ({deployment['name']})")

        # Find related resources
        related_resources = find_related_resources([deployment], namespace)
        if related_resources:
            for resource_type, items in related_resources.items():
                if items:
                    print(f"  ✓ {len(items)} {resource_type.title()}: {', '.join([r['name'] for r in items[:3]])}")
                    if len(items) > 3:
                        print(f"    ... and {len(items) - 3} more")

    else:
        # Multi-deployment chart
        chart_name = config.get('release', 'multi-app')
        output_dir = config.get('output_dir', f"./{chart_name}-chart")

        print(f"Chart Name: {chart_name}")
        print(f"Output Directory: {output_dir}")
        print(f"Multi-Deployment Chart ({len(selected_deployments)} deployments)")

        print(f"\n📦 Deployments to include:")
        total_replicas = 0
        for deployment in selected_deployments:
            print(f"  ✓ {deployment['name']} ({deployment['ready_replicas']}/{deployment['replicas']} replicas)")
            total_replicas += deployment['replicas']

        print(f"\n📊 Summary:")
        print(f"  • Total Deployments: {len(selected_deployments)}")
        print(f"  • Total Replicas: {total_replicas}")

        # Find related resources for all deployments
        related_resources = find_related_resources(selected_deployments, namespace)
        if related_resources:
            total_resources = len(selected_deployments)  # Start with deployments
            for resource_type, items in related_resources.items():
                if items:
                    total_resources += len(items)
                    print(f"  • {resource_type.title()}: {len(items)}")
            print(f"  • Total Resources: {total_resources}")

    # Chart structure preview
    print(f"\n📁 Chart Structure:")
    print(f"  {output_dir}/")
    print(f"  ├── Chart.yaml")
    print(f"  ├── values.yaml")
    print(f"  └── templates/")

    # Estimate template files
    template_count = len(selected_deployments)  # One per deployment
    if related_resources:
        for resource_type, items in related_resources.items():
            template_count += len(items) if items else 0

    print(f"      ├── {len(selected_deployments)} deployment template(s)")
    if related_resources:
        for resource_type, items in related_resources.items():
            if items:
                print(f"      ├── {len(items)} {resource_type} template(s)")

    # Validation checks
    print(f"\n🔍 Validation Checks:")
    validation_passed = True

    # Check if output directory exists
    output_path = Path(output_dir)
    if output_path.exists():
        print(f"  ⚠️  Output directory exists (will be overwritten)")
        if not config.get('force', False):
            validation_passed = False
    else:
        print(f"  ✅ Output directory is available")

    # Check deployment health
    healthy_deployments = sum(1 for d in selected_deployments
                            if get_deployment_status(d).startswith("✅"))
    if healthy_deployments == len(selected_deployments):
        print(f"  ✅ All deployments are healthy")
    else:
        print(f"  ⚠️  {len(selected_deployments) - healthy_deployments} deployment(s) have issues")

    # Check for required fields
    if config.get('release'):
        print(f"  ✅ Chart name specified")
    else:
        print(f"  ⚠️  No chart name specified (will use default)")

    # Summary
    print(f"\n📈 Estimated Chart Complexity: {'Low' if template_count <= 5 else 'Medium' if template_count <= 15 else 'High'}")
    print(f"📏 Estimated Size: ~{template_count * 2}KB")

    if not validation_passed:
        print(f"\n⚠️  Validation issues detected. Use --force to override.")
        return False

    print(f"\n✅ Ready to create chart!")
    return True


def compare_with_existing_chart(output_dir: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compare configuration with existing chart and suggest updates."""
    chart_path = Path(output_dir)

    if not chart_path.exists():
        return None  # No existing chart to compare

    comparison_result = {
        "exists": True,
        "chart_yaml_path": chart_path / "Chart.yaml",
        "values_yaml_path": chart_path / "values.yaml",
        "templates_path": chart_path / "templates",
        "differences": [],
        "recommendations": []
    }

    print(f"\n🔍 Chart Comparison: {output_dir}")
    print("=" * 50)

    # Check Chart.yaml
    chart_yaml_path = chart_path / "Chart.yaml"
    if chart_yaml_path.exists():
        try:
            with open(chart_yaml_path, 'r') as f:
                existing_chart = yaml.safe_load(f)

            current_version = existing_chart.get('version', '0.1.0')
            current_app_version = existing_chart.get('appVersion', '1.0.0')

            print(f"📄 Existing Chart:")
            print(f"  • Name: {existing_chart.get('name', 'unknown')}")
            print(f"  • Version: {current_version}")
            print(f"  • App Version: {current_app_version}")

            # Suggest version bump
            version_parts = current_version.split('.')
            if len(version_parts) == 3:
                patch_version = int(version_parts[2]) + 1
                suggested_version = f"{version_parts[0]}.{version_parts[1]}.{patch_version}"
                comparison_result["suggested_version"] = suggested_version
                comparison_result["recommendations"].append(f"Bump version to {suggested_version}")

        except Exception as e:
            print(f"⚠️  Could not read existing Chart.yaml: {e}")
            comparison_result["differences"].append("Chart.yaml unreadable")
    else:
        print(f"📄 Chart.yaml: Not found")
        comparison_result["differences"].append("Chart.yaml missing")

    # Check values.yaml
    values_yaml_path = chart_path / "values.yaml"
    if values_yaml_path.exists():
        try:
            with open(values_yaml_path, 'r') as f:
                existing_values = yaml.safe_load(f)

            print(f"\n📋 Existing values.yaml:")
            if existing_values:
                # Check for common sections
                sections = ["image", "replicaCount", "service", "resources"]
                for section in sections:
                    if section in existing_values:
                        print(f"  ✓ {section}")
                    else:
                        print(f"  ✗ {section} (missing)")
                        comparison_result["differences"].append(f"values.yaml missing {section}")
            else:
                print(f"  ⚠️  Empty or invalid values.yaml")
                comparison_result["differences"].append("values.yaml empty")

        except Exception as e:
            print(f"⚠️  Could not read existing values.yaml: {e}")
            comparison_result["differences"].append("values.yaml unreadable")
    else:
        print(f"📋 values.yaml: Not found")
        comparison_result["differences"].append("values.yaml missing")

    # Check templates directory
    templates_path = chart_path / "templates"
    if templates_path.exists() and templates_path.is_dir():
        template_files = list(templates_path.glob("*.yaml"))
        print(f"\n📁 Templates: {len(template_files)} files")

        # Categorize templates
        template_types = {}
        for template_file in template_files:
            if template_file.name.startswith("deployments-"):
                template_types.setdefault("deployments", []).append(template_file.name)
            elif template_file.name.startswith("services-"):
                template_types.setdefault("services", []).append(template_file.name)
            elif template_file.name.startswith("configmaps-"):
                template_types.setdefault("configmaps", []).append(template_file.name)
            elif template_file.name.startswith("secrets-"):
                template_types.setdefault("secrets", []).append(template_file.name)
            else:
                template_types.setdefault("other", []).append(template_file.name)

        for resource_type, files in template_types.items():
            print(f"  • {resource_type}: {len(files)}")

    else:
        print(f"📁 templates/: Not found or empty")
        comparison_result["differences"].append("templates directory missing")

    # Generate recommendations
    if comparison_result["differences"]:
        print(f"\n💡 Recommendations:")
        comparison_result["recommendations"].extend([
            "Update chart to include missing components",
            "Review and merge existing configuration",
            "Backup existing chart before updating"
        ])
        for rec in comparison_result["recommendations"]:
            print(f"  • {rec}")
    else:
        print(f"\n✅ Chart structure looks complete")
        comparison_result["recommendations"].append("Consider incremental update")

    return comparison_result


def handle_existing_chart_update(output_dir: str, config: Dict[str, Any]) -> str:
    """Handle updating an existing chart with user choices."""
    comparison = compare_with_existing_chart(output_dir, config)

    if not comparison or not comparison["exists"]:
        return "create"  # No existing chart, create new one

    print(f"\n🔄 Chart Update Options:")
    print("=" * 30)
    print("  1. Overwrite existing chart (replace)")
    print("  2. Update chart version and merge")
    print("  3. Create backup and overwrite")
    print("  4. Cancel operation")

    while True:
        try:
            choice = input("\nSelect option [1-4]: ").strip()

            if choice == '1':
                return "overwrite"
            elif choice == '2':
                # Update version in config if suggested
                if "suggested_version" in comparison:
                    config["chart_version"] = comparison["suggested_version"]
                    print(f"Will update chart version to {comparison['suggested_version']}")
                return "merge"
            elif choice == '3':
                # Create backup
                backup_dir = f"{output_dir}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                try:
                    shutil.copytree(output_dir, backup_dir)
                    print(f"Backup created: {backup_dir}")
                    return "overwrite"
                except Exception as e:
                    print(f"Failed to create backup: {e}")
                    continue
            elif choice == '4':
                return "cancel"
            else:
                print("Invalid option. Please select 1-4.")

        except (KeyboardInterrupt, EOFError):
            return "cancel"


def bulk_export_namespace(namespace: str, output_base_dir: str = "./charts") -> None:
    """Export all deployments in a namespace as individual charts."""
    print(f"\n🚀 Bulk Export: Namespace '{namespace}'")
    print("=" * 50)

    # Get all deployments
    deployments = list_available_deployments(namespace)
    if not deployments:
        print(f"No deployments found in namespace '{namespace}'")
        return

    print(f"Found {len(deployments)} deployments to export")

    # Filter options
    filter_choice = prompt_optional("Would you like to filter deployments?", "n").lower()
    if filter_choice in ['y', 'yes']:
        deployments = interactive_search_filter(deployments)
        if not deployments:
            print("No deployments match your filters.")
            return

    # Configuration options
    print(f"\n⚙️  Bulk Export Configuration:")
    include_secrets = prompt_yes_no("Include secrets in all charts?", False)
    run_lint = prompt_yes_no("Run helm lint on all generated charts?", True)
    create_combined_chart = prompt_yes_no("Also create a combined chart with all deployments?", False)

    # Create base output directory
    base_path = Path(output_base_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    successful_exports = []
    failed_exports = []

    print(f"\n📦 Starting bulk export...")
    print(f"Output directory: {output_base_dir}")

    # Export individual charts
    for i, deployment in enumerate(deployments, 1):
        deployment_name = deployment["name"]
        print(f"\n[{i}/{len(deployments)}] Exporting: {deployment_name}")

        try:
            # Create individual chart config
            config = {
                'namespace': namespace,
                'release': deployment_name,
                'output_dir': str(base_path / f"{deployment_name}-chart"),
                'selector': f"app={deployment_name}",
                'include_secrets': include_secrets,
                'lint': run_lint,
                'force': True,  # Overwrite existing
                'selected_deployments': [deployment]
            }

            # Create args object for this export
            args = parse_args([])
            apply_config_to_args(args, config)

            # Quick preview without interaction
            print(f"  📋 Chart: {deployment_name}")
            print(f"  📁 Output: {config['output_dir']}")

            # Find related resources
            related_resources = find_related_resources([deployment], namespace)
            total_resources = 1  # deployment itself
            if related_resources:
                for resource_type, items in related_resources.items():
                    if items:
                        total_resources += len(items)
                        print(f"  📦 {resource_type.title()}: {len(items)}")

            print(f"  📊 Total resources: {total_resources}")

            # Create the chart
            exporter = ChartExporter(args)
            exporter.run()

            successful_exports.append({
                'name': deployment_name,
                'path': config['output_dir'],
                'resources': total_resources
            })
            print(f"  ✅ Exported successfully")

        except Exception as e:
            failed_exports.append({
                'name': deployment_name,
                'error': str(e)
            })
            print(f"  ❌ Export failed: {e}")

    # Create combined chart if requested
    if create_combined_chart and successful_exports:
        print(f"\n🔗 Creating combined chart...")
        try:
            combined_config = {
                'namespace': namespace,
                'release': f"{namespace}-combined",
                'output_dir': str(base_path / f"{namespace}-combined-chart"),
                'selector': "",  # Include all
                'include_secrets': include_secrets,
                'lint': run_lint,
                'force': True,
                'selected_deployments': deployments
            }

            args = parse_args([])
            apply_config_to_args(args, combined_config)

            exporter = ChartExporter(args)
            exporter.run()

            print(f"  ✅ Combined chart created: {combined_config['output_dir']}")

        except Exception as e:
            print(f"  ❌ Combined chart failed: {e}")

    # Summary report
    print(f"\n📊 Bulk Export Summary")
    print("=" * 30)
    print(f"✅ Successful: {len(successful_exports)}")
    print(f"❌ Failed: {len(failed_exports)}")

    if successful_exports:
        print(f"\n📦 Successfully exported charts:")
        for export in successful_exports:
            print(f"  • {export['name']} ({export['resources']} resources)")
            print(f"    📁 {export['path']}")

    if failed_exports:
        print(f"\n❌ Failed exports:")
        for failure in failed_exports:
            print(f"  • {failure['name']}: {failure['error']}")

    # Next steps
    if successful_exports:
        print(f"\n🎯 Next Steps:")
        print(f"📦 Package charts:")
        for export in successful_exports:
            chart_dir = Path(export['path']).name
            print(f"  helm package {chart_dir}")

        print(f"\n🚀 Deploy charts:")
        for export in successful_exports:
            chart_dir = Path(export['path']).name
            print(f"  helm install {export['name']} ./{chart_dir}")


def bulk_export_by_selector(label_selector: str, namespace: str = "default",
                           output_base_dir: str = "./charts") -> None:
    """Export all deployments matching a label selector."""
    print(f"\n🎯 Bulk Export by Selector: '{label_selector}'")
    print("=" * 50)

    try:
        # Get deployments matching selector
        cmd = ["kubectl", "get", "deployments", "-n", namespace, "-l", label_selector, "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        deployments = []
        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})

            deployment_info = {
                "name": metadata.get("name", "unknown"),
                "replicas": spec.get("replicas", 0),
                "ready_replicas": status.get("readyReplicas", 0),
                "namespace": metadata.get("namespace", namespace),
                "labels": metadata.get("labels", {}),
                "creation_time": metadata.get("creationTimestamp", ""),
                "images": []
            }

            # Extract container images
            containers = spec.get("template", {}).get("spec", {}).get("containers", [])
            for container in containers:
                if "image" in container:
                    deployment_info["images"].append(container["image"])

            deployments.append(deployment_info)

        if not deployments:
            print(f"No deployments match selector '{label_selector}' in namespace '{namespace}'")
            return

        print(f"Found {len(deployments)} deployments matching selector")
        for deployment in deployments:
            status = get_deployment_status(deployment)
            print(f"  • {deployment['name']} - {status}")

        # Proceed with bulk export
        if prompt_yes_no(f"\nProceed with bulk export of {len(deployments)} deployments?", True):
            # Use the regular bulk export but with pre-filtered deployments
            bulk_export_filtered_deployments(deployments, namespace, output_base_dir, label_selector)

    except subprocess.CalledProcessError as e:
        print(f"Failed to query deployments: {e.stderr or e}")
    except Exception as e:
        print(f"Error during bulk export: {e}")


def bulk_export_filtered_deployments(deployments: List[Dict[str, Any]], namespace: str,
                                   output_base_dir: str, selector_info: str = "") -> None:
    """Helper function to export a pre-filtered list of deployments."""
    # Similar to bulk_export_namespace but with pre-filtered deployments
    print(f"\n🚀 Bulk Export: {len(deployments)} filtered deployments")
    if selector_info:
        print(f"Selector: {selector_info}")
    print("=" * 50)

    # Configuration
    include_secrets = prompt_yes_no("Include secrets in all charts?", False)
    run_lint = prompt_yes_no("Run helm lint on all generated charts?", True)

    base_path = Path(output_base_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    successful_exports = []
    failed_exports = []

    for i, deployment in enumerate(deployments, 1):
        deployment_name = deployment["name"]
        print(f"\n[{i}/{len(deployments)}] Exporting: {deployment_name}")

        try:
            config = {
                'namespace': namespace,
                'release': deployment_name,
                'output_dir': str(base_path / f"{deployment_name}-chart"),
                'selector': f"app={deployment_name}",
                'include_secrets': include_secrets,
                'lint': run_lint,
                'force': True,
                'selected_deployments': [deployment]
            }

            args = parse_args([])
            apply_config_to_args(args, config)

            exporter = ChartExporter(args)
            exporter.run()

            successful_exports.append(deployment_name)
            print(f"  ✅ Success")

        except Exception as e:
            failed_exports.append((deployment_name, str(e)))
            print(f"  ❌ Failed: {e}")

    # Summary
    print(f"\n📊 Bulk Export Results:")
    print(f"✅ Success: {len(successful_exports)}")
    print(f"❌ Failed: {len(failed_exports)}")


def handle_kubectl_error(error: subprocess.CalledProcessError, operation: str) -> None:
    """Handle kubectl command errors with helpful suggestions."""
    print(f"\n❌ {operation} failed")

    stderr = error.stderr or ""

    if "connection refused" in stderr.lower():
        print("🔧 Kubernetes connection issue:")
        print("  • Check if kubectl is configured correctly")
        print("  • Verify cluster is accessible: kubectl cluster-info")
        print("  • Check if you're using the right context: kubectl config current-context")

    elif "forbidden" in stderr.lower() or "unauthorized" in stderr.lower():
        print("🔒 Permission issue:")
        print("  • Check if you have the required permissions")
        print("  • Verify your kubeconfig is valid")
        print("  • Try: kubectl auth can-i get deployments")

    elif "not found" in stderr.lower():
        print("🔍 Resource not found:")
        print("  • Check if the namespace exists: kubectl get namespaces")
        print("  • Verify deployment names: kubectl get deployments -A")
        print("  • Check if you're using the correct namespace")

    elif "no such host" in stderr.lower() or "network" in stderr.lower():
        print("🌐 Network connectivity issue:")
        print("  • Check your internet connection")
        print("  • Verify VPN settings if using corporate network")
        print("  • Try: kubectl version --client")

    else:
        print(f"📋 Error details: {stderr}")
        print("💡 Troubleshooting tips:")
        print("  • Check kubectl configuration: kubectl config view")
        print("  • Test basic connectivity: kubectl get nodes")
        print("  • Verify permissions: kubectl auth can-i '*' '*'")


def retry_operation(operation_func, operation_name: str, max_retries: int = 3) -> any:
    """Retry an operation with user confirmation on failure."""
    for attempt in range(max_retries):
        try:
            return operation_func()
        except subprocess.CalledProcessError as e:
            if attempt == max_retries - 1:
                handle_kubectl_error(e, operation_name)
                raise

            print(f"\n⚠️  {operation_name} failed (attempt {attempt + 1}/{max_retries})")
            print(f"Error: {e.stderr or e}")

            if not prompt_yes_no(f"Retry {operation_name}?", True):
                raise

            print("Retrying...")
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"\n❌ {operation_name} failed: {e}")
                raise

            print(f"\n⚠️  {operation_name} failed (attempt {attempt + 1}/{max_retries}): {e}")

            if not prompt_yes_no(f"Retry {operation_name}?", True):
                raise

            print("Retrying...")


def validate_prerequisites() -> bool:
    """Validate that required tools are available."""
    print("🔍 Validating prerequisites...")

    missing_tools = []

    # Check kubectl
    try:
        result = subprocess.run(["kubectl", "version", "--client"],
                              capture_output=True, text=True, check=True)
        print("✅ kubectl is available")
    except FileNotFoundError:
        missing_tools.append("kubectl")
        print("❌ kubectl not found")
    except subprocess.CalledProcessError:
        print("⚠️  kubectl found but may have issues")

    # Check cluster connectivity
    try:
        result = subprocess.run(["kubectl", "cluster-info"],
                              capture_output=True, text=True, check=True, timeout=10)
        print("✅ Kubernetes cluster is accessible")
    except subprocess.TimeoutExpired:
        print("⚠️  Kubernetes cluster connection timeout")
        print("   This may indicate network issues or slow cluster")
    except subprocess.CalledProcessError as e:
        print("❌ Cannot connect to Kubernetes cluster")
        handle_kubectl_error(e, "Cluster connectivity check")
        return False
    except FileNotFoundError:
        pass  # kubectl already reported as missing

    # Check helm (optional)
    try:
        result = subprocess.run(["helm", "version"],
                              capture_output=True, text=True, check=True)
        print("✅ helm is available (optional)")
    except FileNotFoundError:
        print("ℹ️  helm not found (optional - charts can still be created)")
    except subprocess.CalledProcessError:
        print("⚠️  helm found but may have issues (optional)")

    if missing_tools:
        print(f"\n❌ Missing required tools: {', '.join(missing_tools)}")
        print("📖 Installation help:")
        for tool in missing_tools:
            if tool == "kubectl":
                print("  kubectl: https://kubernetes.io/docs/tasks/tools/")
        return False

    return True


def handle_chart_creation_error(error: Exception, deployment_name: str) -> bool:
    """Handle chart creation errors with recovery options."""
    print(f"\n❌ Chart creation failed for '{deployment_name}': {error}")

    # Analyze error and provide specific guidance
    error_str = str(error).lower()

    if "permission denied" in error_str:
        print("🔒 File permission issue:")
        print("  • Check if output directory is writable")
        print("  • Try a different output directory")
        print("  • On Windows, try running as administrator")

    elif "no space left" in error_str:
        print("💾 Disk space issue:")
        print("  • Free up disk space")
        print("  • Try a different output directory")

    elif "file exists" in error_str or "directory not empty" in error_str:
        print("📁 Output directory conflict:")
        print("  • Use --force to overwrite existing files")
        print("  • Choose a different output directory")
        print("  • Manually remove existing directory")

    elif "template" in error_str or "yaml" in error_str:
        print("📝 Template generation issue:")
        print("  • This may be due to unusual resource configurations")
        print("  • Try with a simpler deployment first")
        print("  • Check if deployment has all required fields")

    else:
        print("🔧 General troubleshooting:")
        print("  • Try with --verbose for more details")
        print("  • Ensure deployment is running properly")
        print("  • Check kubectl permissions")

    return prompt_yes_no("Would you like to try creating another chart?", True)


def safe_file_operation(operation_func, operation_name: str, file_path: str = ""):
    """Safely perform file operations with error handling."""
    try:
        return operation_func()
    except PermissionError:
        print(f"❌ Permission denied: {operation_name}")
        if file_path:
            print(f"   File: {file_path}")
        print("💡 Try:")
        print("  • Check file/directory permissions")
        print("  • Close any applications using the file")
        print("  • Run with elevated permissions if necessary")
        raise
    except FileNotFoundError:
        print(f"❌ File not found: {operation_name}")
        if file_path:
            print(f"   File: {file_path}")
        print("💡 Check if the path exists and is correct")
        raise
    except OSError as e:
        print(f"❌ File system error: {operation_name}")
        if file_path:
            print(f"   File: {file_path}")
        print(f"   Error: {e}")
        print("💡 This may be due to:")
        print("  • Insufficient disk space")
        print("  • File system corruption")
        print("  • Path too long (Windows)")
        raise


def get_deployment_status(deployment_data: Dict[str, Any]) -> str:
    """Get visual status indicator for deployment."""
    ready_replicas = deployment_data.get("ready_replicas", 0)
    total_replicas = deployment_data.get("replicas", 0)

    if total_replicas == 0:
        return "⚪ Stopped"
    elif ready_replicas == total_replicas:
        return "✅ Ready"
    elif ready_replicas == 0:
        return "❌ Failed"
    elif ready_replicas < total_replicas:
        return "⚠️ Issue"
    else:
        return "🔄 Scaling"


def interactive_search_filter(deployments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Interactive search and filter interface for deployments."""
    if not deployments:
        print("No deployments available to filter.")
        return deployments

    filtered_deployments = deployments.copy()
    active_filters = {}

    while True:
        print(f"\n🔍 Search & Filter Interface")
        print("=" * 50)
        print(f"Showing {len(filtered_deployments)} of {len(deployments)} deployments")

        if active_filters:
            print("\nActive filters:")
            for key, value in active_filters.items():
                print(f"  • {key}: {value}")

        print("\nFilter options:")
        print("  1. Search by name")
        print("  2. Filter by status (ready/failed/issue/scaling/stopped)")
        print("  3. Filter by minimum replicas")
        print("  4. Show recent deployments (last N days)")
        print("  5. Clear all filters")
        print("  6. Continue with current selection")

        try:
            choice = input("\nSelect option [1-6]: ").strip()

            if choice == '1':
                search_term = input("Enter search term (name contains): ").strip()
                if search_term:
                    active_filters['search'] = search_term
                    filtered_deployments = filter_deployments(
                        deployments, search_term=search_term,
                        status_filter=active_filters.get('status', ''),
                        min_replicas=active_filters.get('min_replicas', 0),
                        max_age_days=active_filters.get('max_age_days', 0)
                    )

            elif choice == '2':
                print("Status options: ready, failed, issue, scaling, stopped")
                status = input("Enter status filter: ").strip().lower()
                if status in ['ready', 'failed', 'issue', 'scaling', 'stopped']:
                    active_filters['status'] = status
                    filtered_deployments = filter_deployments(
                        deployments, search_term=active_filters.get('search', ''),
                        status_filter=status,
                        min_replicas=active_filters.get('min_replicas', 0),
                        max_age_days=active_filters.get('max_age_days', 0)
                    )
                else:
                    print("Invalid status option.")

            elif choice == '3':
                try:
                    min_reps = int(input("Minimum replicas: ").strip())
                    if min_reps >= 0:
                        active_filters['min_replicas'] = min_reps
                        filtered_deployments = filter_deployments(
                            deployments, search_term=active_filters.get('search', ''),
                            status_filter=active_filters.get('status', ''),
                            min_replicas=min_reps,
                            max_age_days=active_filters.get('max_age_days', 0)
                        )
                except ValueError:
                    print("Invalid number.")

            elif choice == '4':
                try:
                    max_days = int(input("Show deployments from last N days: ").strip())
                    if max_days > 0:
                        active_filters['max_age_days'] = max_days
                        filtered_deployments = filter_deployments(
                            deployments, search_term=active_filters.get('search', ''),
                            status_filter=active_filters.get('status', ''),
                            min_replicas=active_filters.get('min_replicas', 0),
                            max_age_days=max_days
                        )
                except ValueError:
                    print("Invalid number.")

            elif choice == '5':
                active_filters.clear()
                filtered_deployments = deployments.copy()
                print("All filters cleared.")

            elif choice == '6':
                break

            else:
                print("Invalid option. Please select 1-6.")

        except (KeyboardInterrupt, EOFError):
            print("\nFilter cancelled.")
            return deployments

    return filtered_deployments


def display_deployments_menu(deployments: List[Dict[str, Any]], selected: Optional[Set[int]] = None) -> None:
    """Display a formatted menu of available deployments with selection indicators."""
    if not deployments:
        print("No deployments found in the specified namespace.")
        return

    if selected is None:
        selected = set()

    print(f"\nFound {len(deployments)} deployment(s):")
    print("-" * 80)
    print(f"{'Sel':<4} {'#':<3} {'Name':<20} {'Status':<10} {'Replicas':<8} {'Images':<30}")
    print("-" * 80)

    for i, deployment in enumerate(deployments, 1):
        checkbox = "[✓]" if i in selected else "[ ]"
        name = deployment["name"][:19]
        status = get_deployment_status(deployment)
        replicas = f"{deployment['ready_replicas']}/{deployment['replicas']}"
        images = ", ".join([img.split("/")[-1][:28] for img in deployment["images"][:2]])
        if len(deployment["images"]) > 2:
            images += "..."

        print(f"{checkbox:<4} {i:<3} {name:<20} {status:<10} {replicas:<8} {images:<30}")

    print("-" * 80)


def select_deployments_multi(deployments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Allow user to select multiple deployments with checkbox interface."""
    if not deployments:
        return []

    original_deployments = deployments.copy()  # Keep original list
    current_deployments = deployments.copy()   # Working list (filtered)
    selected = set()  # Track selected deployment indices

    while True:
        display_deployments_menu(current_deployments, selected)

        print("\nMulti-Selection Commands:")
        print("  [number]  - Toggle selection (e.g., '1', '3')")
        print("  'a'       - Select all")
        print("  'n'       - Select none")
        print("  's'       - Search/filter deployments")
        print("  'done'    - Confirm selection")
        print("  'q'       - Quit")

        choice = input("\nCommand: ").strip().lower()

        if choice == 'q':
            return []
        elif choice == 'done':
            if selected:
                selected_deployments = [current_deployments[i-1] for i in sorted(selected)]
                print(f"\nSelected {len(selected_deployments)} deployment(s):")
                for dep in selected_deployments:
                    print(f"  - {dep['name']}")
                return selected_deployments
            else:
                print("No deployments selected!")
                continue
        elif choice == 'a':
            selected = set(range(1, len(current_deployments) + 1))
            print("Selected all deployments")
        elif choice == 'n':
            selected.clear()
            print("Cleared all selections")
        elif choice == 's':
            # Launch search/filter interface
            filtered_deployments = interactive_search_filter(original_deployments)
            if filtered_deployments:
                current_deployments = filtered_deployments
                # Clear selections since indices might have changed
                selected.clear()
                print(f"Filtered to {len(current_deployments)} deployments. Selections cleared.")
            else:
                print("No deployments match your filters.")
        else:
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(current_deployments):
                    if choice_num in selected:
                        selected.remove(choice_num)
                        print(f"Deselected: {current_deployments[choice_num-1]['name']}")
                    else:
                        selected.add(choice_num)
                        print(f"Selected: {current_deployments[choice_num-1]['name']}")
                else:
                    print(f"Invalid number. Please enter 1-{len(current_deployments)}")
            except ValueError:
                print("Invalid command. Use number, 'a', 'n', 's', 'done', or 'q'")


def select_deployment(deployments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Legacy single deployment selection - now uses multi-selection."""
    selected = select_deployments_multi(deployments)
    return selected[0] if selected else None


def prompt_for_deployment_based_config() -> Dict[str, Any]:
    """Prompt for configuration based on selected deployments."""
    config = {}

    # Get namespace first
    namespace = prompt_optional("Kubernetes namespace to scan for deployments", "default")
    config['namespace'] = namespace

    print(f"\nScanning for deployments in namespace '{namespace}'...")
    deployments = list_available_deployments(namespace)

    if not deployments:
        print("\nNo deployments found. Creating manual configuration...")
        return prompt_for_new_config()

    # Optional search and filter interface
    if len(deployments) > 3:  # Only show filter option for larger lists
        filter_choice = prompt_optional("Would you like to search/filter the deployments?", "n").lower()
        if filter_choice in ['y', 'yes']:
            deployments = interactive_search_filter(deployments)
            if not deployments:
                print("No deployments match your filters. Creating manual configuration...")
                return prompt_for_new_config()

    # Select deployments (multi-selection)
    selected_deployments = select_deployments_multi(deployments)
    if not selected_deployments:
        print("No deployments selected. Exiting...")
        return {}

    # Handle multi-deployment configuration
    if len(selected_deployments) == 1:
        # Single deployment - use existing logic
        selected_deployment = selected_deployments[0]
        deployment_name = selected_deployment["name"]
        config['release'] = prompt_optional(f"Helm chart name", deployment_name)
        config['output_dir'] = prompt_optional("Output directory", f"./{deployment_name}-chart")

        # Auto-set selector to target this specific deployment
        suggested_selector = f"app={deployment_name}"
        if "app" in selected_deployment.get("labels", {}):
            suggested_selector = f"app={selected_deployment['labels']['app']}"

        config['selector'] = prompt_optional("Label selector (to include related resources)", suggested_selector)
        config['selected_deployments'] = [selected_deployment]

    else:
        # Multiple deployments - create combined chart
        deployment_names = [dep["name"] for dep in selected_deployments]
        suggested_chart_name = prompt_optional("Helm chart name for combined deployments", "multi-app")
        config['release'] = suggested_chart_name
        config['output_dir'] = prompt_optional("Output directory", f"./{suggested_chart_name}-chart")

        # For multiple deployments, use a broader selector or let user specify
        print(f"\nSelected deployments: {', '.join(deployment_names)}")
        print("For multiple deployments, you can:")
        print("  1. Use a common label selector (e.g., 'team=frontend')")
        print("  2. Leave empty to include all resources for selected deployments")

        config['selector'] = prompt_optional("Label selector (optional for multi-deployment)", None)
        config['selected_deployments'] = selected_deployments
        config['multi_deployment'] = True

    # Advanced options
    if prompt_yes_no("Configure advanced options?", False):
        kubeconfig = prompt_optional("Custom kubeconfig path", None)
        if kubeconfig:
            config['kubeconfig'] = kubeconfig

        context = prompt_optional("Kubernetes context", None)
        if context:
            config['context'] = context

        chart_version = prompt_optional("Chart version", "0.1.0")
        if chart_version:
            config['chart_version'] = chart_version

        # Use first image tag as app version if available
        app_version = "1.0.0"
        if selected_deployment["images"]:
            first_image = selected_deployment["images"][0]
            if ":" in first_image:
                app_version = first_image.split(":")[-1]

        app_version = prompt_optional("App version", app_version)
        if app_version:
            config['app_version'] = app_version

    # Smart dependency detection
    if prompt_yes_no("Auto-discover related resources (ConfigMaps, Secrets, Services, PVCs)?", True):
        selected_deps = display_dependency_suggestions(config.get('selected_deployments', []), namespace)

        # Apply dependency selections to config
        if selected_deps.get('secrets'):
            config['include_secrets'] = True
            print("✅ Enabled secret inclusion due to discovered dependencies")

        # Store selected dependencies for filtering
        config['selected_dependencies'] = selected_deps
    else:
        # Manual secret handling
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


def run_interactive_config() -> Optional[Dict[str, Any]]:
    """Run the interactive configuration prompt."""
    print_welcome_banner()
    print("\n>> Interactive Configuration")
    print("=" * 50)

    # Check for existing configs
    existing_config = offer_existing_configs()
    if existing_config:
        return existing_config

    # Choose configuration method
    print("\nConfiguration options:")
    print("  1. Auto-discover from deployments (recommended)")
    print("  2. Manual configuration")
    print("  3. Bulk export entire namespace")
    print("  4. Bulk export by label selector")

    while True:
        choice = input("\nSelect option [1-4]: ").strip()
        if choice == "1":
            config = prompt_for_deployment_based_config()
            break
        elif choice == "2":
            config = prompt_for_new_config()
            break
        elif choice == "3":
            # Bulk namespace export
            namespace = prompt_optional("Namespace to export", "default")
            output_dir = prompt_optional("Output directory", "./charts")
            try:
                bulk_export_namespace(namespace, output_dir)
                return {}  # Exit workflow after bulk operation
            except Exception as e:
                print(f"Bulk export failed: {e}")
                continue
        elif choice == "4":
            # Bulk selector export
            namespace = prompt_optional("Namespace to search", "default")
            selector = prompt_required("Label selector (e.g., 'app=frontend')")
            output_dir = prompt_optional("Output directory", "./charts")
            try:
                bulk_export_by_selector(selector, namespace, output_dir)
                return {}  # Exit workflow after bulk operation
            except Exception as e:
                print(f"Bulk export failed: {e}")
                continue
        else:
            print("Invalid choice. Please enter 1-4.")

    if not config:
        return None

    # Save this config
    if prompt_yes_no("Save this configuration for future use?", True):
        config_name = prompt_required("Configuration name", f"config-{datetime.now().strftime('%Y%m%d-%H%M')}")
        save_config(config_name, config)

    return config


def find_related_resources(deployments: List[Dict[str, Any]], namespace: str) -> Dict[str, List[str]]:
    """Find ConfigMaps, Secrets, Services, and PVCs related to selected deployments."""
    related_resources = {
        "configmaps": set(),
        "secrets": set(),
        "services": set(),
        "persistentvolumeclaims": set()
    }

    for deployment in deployments:
        deployment_name = deployment["name"]
        labels = deployment.get("labels", {})

        # Find resources by common patterns
        try:
            # Get all resources in namespace
            for resource_type in ["configmaps", "secrets", "services", "persistentvolumeclaims"]:
                cmd = ["kubectl", "get", resource_type, "-n", namespace, "-o", "json"]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                data = json.loads(result.stdout)

                for item in data.get("items", []):
                    item_metadata = item.get("metadata", {})
                    item_name = item_metadata.get("name", "")
                    item_labels = item_metadata.get("labels", {})

                    # Match by name patterns
                    if (deployment_name in item_name or
                        item_name in deployment_name or
                        any(label_value == item_name for label_value in labels.values())):
                        related_resources[resource_type].add(item_name)

                    # Match by common labels
                    if "app" in labels and labels["app"] in item_labels.get("app", ""):
                        related_resources[resource_type].add(item_name)

        except subprocess.CalledProcessError:
            continue  # Skip if resource type not accessible
        except Exception:
            continue  # Skip on any error

    # Convert sets to lists
    return {k: sorted(list(v)) for k, v in related_resources.items()}


def display_dependency_suggestions(deployments: List[Dict[str, Any]], namespace: str) -> Dict[str, List[str]]:
    """Display and let user select related resources."""
    print(f"\n🔍 Scanning for related resources...")
    related = find_related_resources(deployments, namespace)

    selected_resources = {}
    total_found = sum(len(resources) for resources in related.values())

    if total_found == 0:
        print("No related resources found.")
        return {}

    print(f"\nFound {total_found} potentially related resources:")

    for resource_type, resources in related.items():
        if resources:
            print(f"\n📦 {resource_type.title()}:")
            for i, resource in enumerate(resources, 1):
                print(f"  {i}. {resource}")

            if prompt_yes_no(f"Include all {len(resources)} {resource_type}?", True):
                selected_resources[resource_type] = resources
            else:
                # Let user select specific resources
                selected = []
                for resource in resources:
                    if prompt_yes_no(f"  Include {resource}?", True):
                        selected.append(resource)
                if selected:
                    selected_resources[resource_type] = selected

    return selected_resources


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

        # Update Chart.yaml and values.yaml with actual resource data
        if exported:
            self._update_chart_metadata(exported)
            self._generate_values_yaml(exported)

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
        # Chart.yaml will be updated after resource analysis
        (self.chart_path / "Chart.yaml").write_text(
            self._render_chart_yaml(), encoding="utf-8"
        )
        # values.yaml will be generated after resource analysis
        (self.chart_path / "values.yaml").write_text(
            "# Values file generated by rancher-helm-exporter\n# This will be updated with actual values\n", encoding="utf-8"
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

    def _templatize_manifest(self, manifest: MutableMapping[str, object], resource_name: str) -> MutableMapping[str, object]:
        """Replace hardcoded values with Helm template variables."""
        import copy
        templated = copy.deepcopy(manifest)

        kind = manifest.get("kind", "")

        if kind == "Deployment":
            self._templatize_deployment(templated, resource_name)
        elif kind == "Service":
            self._templatize_service(templated, resource_name)
        elif kind == "ConfigMap":
            self._templatize_configmap(templated, resource_name)
        elif kind == "Secret":
            self._templatize_secret(templated, resource_name)
        elif kind == "PersistentVolumeClaim":
            self._templatize_pvc(templated, resource_name)

        return templated

    def _templatize_deployment(self, manifest: MutableMapping[str, object], name: str) -> None:
        """Templatize Deployment-specific fields."""
        spec = manifest.get("spec", {})
        if isinstance(spec, MutableMapping):
            # Replicas
            if "replicas" in spec:
                spec["replicas"] = "{{ .Values.replicaCount | default 1 }}"

            # Template spec
            template = spec.get("template", {})
            if isinstance(template, MutableMapping):
                template_spec = template.get("spec", {})
                if isinstance(template_spec, MutableMapping):
                    containers = template_spec.get("containers", [])
                    if isinstance(containers, list) and containers:
                        container = containers[0]
                        if isinstance(container, MutableMapping):
                            # Image
                            if "image" in container:
                                container["image"] = "{{ .Values.image.repository }}:{{ .Values.image.tag }}"

                            # Image pull policy
                            if "imagePullPolicy" in container:
                                container["imagePullPolicy"] = "{{ .Values.image.pullPolicy }}"

                            # Resources
                            if "resources" in container:
                                container["resources"] = "{{ toYaml .Values.resources | nindent 12 }}"

                            # Environment variables (basic templating)
                            env_vars = container.get("env", [])
                            if isinstance(env_vars, list):
                                for env_var in env_vars:
                                    if isinstance(env_var, MutableMapping):
                                        env_name = env_var.get("name", "")
                                        if env_name and isinstance(env_var.get("value"), str):
                                            # Template common environment variables
                                            safe_env_name = env_name.lower().replace("_", "").replace("-", "")
                                            env_var["value"] = f"{{{{ .Values.env.{safe_env_name} | default \"{env_var['value']}\" }}}}"

    def _templatize_service(self, manifest: MutableMapping[str, object], name: str) -> None:
        """Templatize Service-specific fields."""
        spec = manifest.get("spec", {})
        if isinstance(spec, MutableMapping):
            # Service type
            if "type" in spec:
                spec["type"] = "{{ .Values.service.type }}"

            # Ports
            ports = spec.get("ports", [])
            if isinstance(ports, list) and ports:
                port = ports[0]
                if isinstance(port, MutableMapping):
                    if "port" in port:
                        port["port"] = "{{ .Values.service.port }}"
                    if "targetPort" in port:
                        port["targetPort"] = "{{ .Values.service.targetPort }}"

    def _templatize_configmap(self, manifest: MutableMapping[str, object], name: str) -> None:
        """Templatize ConfigMap fields."""
        # ConfigMaps are often environment-specific, so we template the entire data section
        if "data" in manifest:
            safe_name = name.replace("-", "_")
            manifest["data"] = f"{{{{ toYaml .Values.config.{safe_name} | nindent 2 }}}}"

    def _templatize_secret(self, manifest: MutableMapping[str, object], name: str) -> None:
        """Templatize Secret fields."""
        # Secrets should reference external secret management
        if "data" in manifest:
            safe_name = name.replace("-", "_")
            manifest["data"] = f"{{{{ toYaml .Values.secrets.{safe_name} | nindent 2 }}}}"

    def _templatize_pvc(self, manifest: MutableMapping[str, object], name: str) -> None:
        """Templatize PersistentVolumeClaim fields."""
        spec = manifest.get("spec", {})
        if isinstance(spec, MutableMapping):
            # Storage size
            resources = spec.get("resources", {})
            if isinstance(resources, MutableMapping):
                requests = resources.get("requests", {})
                if isinstance(requests, MutableMapping) and "storage" in requests:
                    safe_name = name.replace("-", "_")
                    requests["storage"] = f"{{{{ .Values.persistence.{safe_name}.size }}}}"

            # Storage class
            if "storageClassName" in spec:
                safe_name = name.replace("-", "_")
                spec["storageClassName"] = f"{{{{ .Values.persistence.{safe_name}.storageClass }}}}"

    def _write_manifest(self, resource: str, manifest: MutableMapping[str, object]) -> ExportResult:
        kind = manifest.get("kind", resource.title())
        metadata = manifest.get("metadata", {})
        name = metadata.get("name", "resource") if isinstance(metadata, MutableMapping) else "resource"
        safe_name = StringUtils.slugify(str(name))
        filename = f"{self.args.prefix}{resource}-{safe_name}.yaml"
        output_path = self.templates_path / filename

        # Apply templating to the manifest
        templated_manifest = self._templatize_manifest(manifest, str(name))

        yaml_text = yaml.safe_dump(templated_manifest, sort_keys=False, default_flow_style=False)
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

    def _update_chart_metadata(self, exported: List[ExportResult]) -> None:
        """Update Chart.yaml with metadata extracted from actual resources."""
        # Extract app version from deployments if available
        app_version = self.args.app_version
        description = "Helm chart generated from an existing Kubernetes deployment"

        # Look for deployments to extract image tags for app version
        for result in exported:
            if result.kind == "Deployment":
                try:
                    with result.path.open('r', encoding='utf-8') as f:
                        content = f.read()
                        # Extract image tag as potential app version
                        import re
                        image_match = re.search(r'image:\s*[\w.-]+:([\w.-]+)', content)
                        if image_match:
                            app_version = image_match.group(1)
                            break
                except Exception:
                    pass

        # Update description based on actual resources
        resource_kinds = sorted(set(result.kind for result in exported))
        if len(resource_kinds) > 1:
            description = f"Helm chart with {', '.join(resource_kinds)} exported from Kubernetes"
        elif resource_kinds:
            description = f"Helm chart with {resource_kinds[0]} exported from Kubernetes"

        updated_chart_yaml = (
            "apiVersion: v2\n"
            f"name: {self.args.release}\n"
            f"description: {description}\n"
            "type: application\n"
            f"version: {self.args.chart_version}\n"
            f"appVersion: \"{app_version}\"\n"
        )

        (self.chart_path / "Chart.yaml").write_text(updated_chart_yaml, encoding="utf-8")

    def _generate_values_yaml(self, exported: List[ExportResult]) -> None:
        """Generate values.yaml with actual values extracted from resources."""
        values_data = {
            "# Values extracted from live Kubernetes resources": None,
            "# Customize these values for different environments": None,
            "": None,
        }

        # Extract values from different resource types
        for result in exported:
            try:
                with result.path.open('r', encoding='utf-8') as f:
                    content = f.read()
                    manifest = yaml.safe_load(content.split('---', 1)[1] if '---' in content else content)

                    if result.kind == "Deployment":
                        self._extract_deployment_values(manifest, values_data, result.name)
                    elif result.kind == "Service":
                        self._extract_service_values(manifest, values_data, result.name)
                    elif result.kind == "ConfigMap":
                        self._extract_configmap_values(manifest, values_data, result.name)
                    elif result.kind == "PersistentVolumeClaim":
                        self._extract_pvc_values(manifest, values_data, result.name)

            except Exception as e:
                self.logger.debug("Failed to extract values from %s: %s", result.path, e)

        # Generate YAML content
        values_content = "# Values file generated by rancher-helm-exporter\n"
        values_content += "# Extracted from live Kubernetes resources\n\n"

        # Convert values_data to YAML, filtering out None placeholders
        clean_values = {k: v for k, v in values_data.items() if v is not None and not k.startswith('#')}
        if clean_values:
            values_content += yaml.safe_dump(clean_values, default_flow_style=False, sort_keys=False)

        (self.chart_path / "values.yaml").write_text(values_content, encoding="utf-8")

    def _extract_deployment_values(self, manifest: Dict, values_data: Dict, name: str) -> None:
        """Extract values from Deployment manifest."""
        spec = manifest.get("spec", {})
        template = spec.get("template", {})
        pod_spec = template.get("spec", {})
        containers = pod_spec.get("containers", [])

        if containers:
            container = containers[0]  # Primary container

            # Image information
            image = container.get("image", "")
            if ":" in image:
                repo, tag = image.rsplit(":", 1)
                values_data["image"] = {
                    "repository": repo,
                    "tag": tag,
                    "pullPolicy": container.get("imagePullPolicy", "IfNotPresent")
                }

            # Replica count
            values_data["replicaCount"] = spec.get("replicas", 1)

            # Resources
            resources = container.get("resources", {})
            if resources:
                values_data["resources"] = resources

            # Ports
            ports = container.get("ports", [])
            if ports:
                values_data["containerPort"] = ports[0].get("containerPort")

            # Environment variables
            env_vars = container.get("env", [])
            if env_vars:
                env_values = {}
                for env_var in env_vars:
                    if isinstance(env_var, dict):
                        env_name = env_var.get("name", "")
                        env_value = env_var.get("value")
                        if env_name and env_value is not None:
                            safe_env_name = env_name.lower().replace("_", "").replace("-", "")
                            env_values[safe_env_name] = env_value

                if env_values:
                    values_data["env"] = env_values

    def _extract_service_values(self, manifest: Dict, values_data: Dict, name: str) -> None:
        """Extract values from Service manifest."""
        spec = manifest.get("spec", {})

        service_values = {
            "type": spec.get("type", "ClusterIP"),
        }

        ports = spec.get("ports", [])
        if ports:
            port_info = ports[0]
            service_values["port"] = port_info.get("port")
            service_values["targetPort"] = port_info.get("targetPort")

        values_data["service"] = service_values

    def _extract_configmap_values(self, manifest: Dict, values_data: Dict, name: str) -> None:
        """Extract values from ConfigMap manifest."""
        data = manifest.get("data", {})
        if data:
            # Store config data for reference
            config_key = f"config_{name.replace('-', '_')}"
            values_data[config_key] = {
                "enabled": True,
                "data": data
            }

    def _extract_pvc_values(self, manifest: Dict, values_data: Dict, name: str) -> None:
        """Extract values from PersistentVolumeClaim manifest."""
        spec = manifest.get("spec", {})
        resources = spec.get("resources", {})
        requests = resources.get("requests", {})

        if requests.get("storage"):
            persistence_key = f"persistence_{name.replace('-', '_')}"
            values_data[persistence_key] = {
                "enabled": True,
                "size": requests["storage"],
                "storageClass": spec.get("storageClassName", ""),
                "accessMode": spec.get("accessModes", ["ReadWriteOnce"])[0]
            }


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
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip preview and validation before chart creation",
    )
    parser.add_argument(
        "--bulk-namespace",
        metavar="NAMESPACE",
        help="Export all deployments in the specified namespace",
    )
    parser.add_argument(
        "--bulk-selector",
        metavar="SELECTOR",
        help="Export all deployments matching the label selector (e.g., 'app=frontend')",
    )

    args = parser.parse_args(argv)

    if args.include_service_account_secrets:
        args.include_secrets = True

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    return args


def run_chart_creation_workflow() -> None:
    """Run the chart creation workflow with option for multiple charts."""
    # Validate prerequisites first
    if not validate_prerequisites():
        print("\n❌ Prerequisites not met. Please install missing tools and try again.")
        return

    charts_created = []

    while True:
        try:
            config = run_interactive_config()
            if not config:
                if charts_created:
                    print(f"\nCompleted! Created {len(charts_created)} chart(s):")
                    for chart in charts_created:
                        print(f"  - {chart}")
                break

            # Create a temporary args object for this chart
            args = parse_args([])  # Empty args to get defaults
            apply_config_to_args(args, config)

            # Ensure we have a release name
            if not args.release:
                print("No release name provided. Skipping this chart.")
                continue

            # Check for existing chart and handle updates
            output_dir = config.get('output_dir', f"./{args.release}-chart")
            update_action = handle_existing_chart_update(output_dir, config)

            if update_action == "cancel":
                print("Chart operation cancelled by user.")
                continue
            elif update_action == "overwrite":
                config['force'] = True  # Enable force mode for overwrite
                args.force = True

            # Preview and validation step (unless explicitly disabled)
            selected_deployments = config.get('selected_deployments', [])
            if selected_deployments and not args.no_preview:
                if not preview_chart_creation(selected_deployments, config, config.get('namespace', 'default')):
                    print("Chart creation cancelled due to validation issues.")
                    continue

                # Ask for confirmation
                if not prompt_yes_no("\nProceed with chart creation?", True):
                    print("Chart creation cancelled by user.")
                    continue

            print(f"\nCreating Helm chart '{args.release}'...")

            # Create the chart with enhanced error handling
            try:
                exporter = ChartExporter(args)
                exporter.run()

                charts_created.append(args.release)
                print(f"✅ Chart '{args.release}' created successfully!")

                # Ask if user wants to create another chart
                if not prompt_yes_no("\nWould you like to create another chart from a different deployment?", False):
                    break

            except Exception as e:
                logging.error("Chart creation failed: %s", e)
                if not handle_chart_creation_error(e, args.release):
                    break

        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            break
        except Exception as e:
            logging.error("Unexpected error in workflow: %s", e)
            print(f"\n❌ Unexpected error: {e}")
            if not prompt_yes_no("Continue with the workflow?", False):
                break

    if charts_created:
        print(f"\n🎉 Successfully created {len(charts_created)} Helm chart(s):")
        for chart in charts_created:
            print(f"  - {chart}")
        print("\nYou can now package and deploy these charts:")
        for chart in charts_created:
            print(f"  helm package ./{chart}-chart")
            print(f"  helm install {chart} ./{chart}-chart")


def main(argv: Optional[Sequence[str]] = None) -> None:
    # Use legacy implementation with interactive config
    # Note: Improved architecture disabled to support interactive config mode
    args = parse_args(argv)

    # Handle bulk operations first
    if args.bulk_namespace:
        try:
            bulk_export_namespace(args.bulk_namespace)
            return
        except KeyboardInterrupt:
            print("\nBulk export cancelled.")
            return
        except Exception as e:
            logging.error("Bulk namespace export failed: %s", e)
            return

    if args.bulk_selector:
        try:
            namespace = args.namespace or "default"
            bulk_export_by_selector(args.bulk_selector, namespace)
            return
        except KeyboardInterrupt:
            print("\nBulk export cancelled.")
            return
        except Exception as e:
            logging.error("Bulk selector export failed: %s", e)
            return

    # If no release name provided or config-prompt flag is used, run interactive workflow
    if not args.release or args.config_prompt:
        try:
            run_chart_creation_workflow()
            return

        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return
        except Exception as e:
            logging.error("Interactive workflow failed: %s", e)
            return

    # Direct command line usage (single chart)
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
