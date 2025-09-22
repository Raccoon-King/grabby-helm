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
from typing import Dict, List, Optional, Sequence, Any

# PyYAML import handling

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


def delete_config(name: str) -> bool:
    """Delete a saved configuration by name."""
    config_dir = get_config_dir()
    configs_file = config_dir / "saved_configs.json"

    if not configs_file.exists():
        return False

    try:
        # Load existing configs
        with configs_file.open('r', encoding='utf-8') as f:
            configs = json.load(f)

        if name not in configs:
            return False

        # Remove the config
        del configs[name]

        # Save back to file
        with configs_file.open('w', encoding='utf-8') as f:
            json.dump(configs, f, indent=2)

        print(f"Configuration deleted: {name}")
        return True

    except Exception as e:
        print(f"Failed to delete config: {e}")
        return False


def delete_all_configs() -> bool:
    """Delete all saved configurations."""
    config_dir = get_config_dir()
    configs_file = config_dir / "saved_configs.json"

    try:
        if configs_file.exists():
            configs_file.unlink()
            print("All configurations deleted.")
        return True
    except Exception as e:
        print(f"Failed to delete all configs: {e}")
        return False


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
    print(f"  {len(configs) + 2}. Manage configurations")

    while True:
        try:
            choice = input(f"\nSelect option [1-{len(configs) + 2}]: ").strip()
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
            elif choice_num == len(configs) + 2:
                # User wants to manage configs
                if manage_configs_menu():
                    # Refresh the configs list and restart the selection
                    return offer_existing_configs()
                else:
                    # User cancelled config management, continue with selection
                    continue
            else:
                print(f"Invalid choice. Please enter 1-{len(configs) + 2}")
        except ValueError:
            print("Please enter a valid number")

    return None


def manage_configs_menu() -> bool:
    """Interactive menu for managing saved configurations. Returns True if changes were made."""
    configs = list_config_names()

    if not configs:
        print("\nNo saved configurations found.")
        return False

    changes_made = False

    while True:
        # Refresh configs list in case of deletions
        configs = list_config_names()

        if not configs:
            print("\nAll configurations have been deleted.")
            return changes_made

        print("\n" + "=" * 50)
        print("             CONFIGURATION MANAGEMENT")
        print("=" * 50)
        print(f"\nFound {len(configs)} saved configuration(s):")

        # Show configs with additional metadata
        all_configs = load_all_configs()
        for i, config_name in enumerate(configs, 1):
            config_entry = all_configs.get(config_name, {})
            saved_at = config_entry.get("saved_at", "Unknown")
            if saved_at != "Unknown":
                # Format the timestamp nicely
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(saved_at)
                    saved_at = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass

            print(f"  {i}. {config_name} (saved: {saved_at})")

        print(f"\n  v. View configuration details")
        print(f"  d. Delete a configuration")
        print(f"  D. Delete all configurations")
        print(f"  q. Return to main menu")

        choice = input(f"\nSelect option [1-{len(configs)}, v, d, D, q]: ").strip().lower()

        if choice == 'q':
            break
        elif choice == 'v':
            # View configuration details
            view_config_details(configs)
        elif choice == 'd':
            # Delete a specific configuration
            if delete_specific_config(configs):
                changes_made = True
        elif choice.upper() == 'D':
            # Delete all configurations
            if delete_all_configs_interactive():
                changes_made = True
        else:
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(configs):
                    # Show details for selected config
                    config_name = configs[choice_num - 1]
                    config = load_config(config_name)
                    if config:
                        print(f"\nConfiguration: {config_name}")
                        display_config_summary(config)

                        # Offer actions on this specific config
                        action = input("\n[d] Delete this config, [Enter] Continue: ").strip().lower()
                        if action == 'd':
                            if prompt_yes_no(f"Delete configuration '{config_name}'?", False):
                                if delete_config(config_name):
                                    changes_made = True
                else:
                    print(f"Invalid choice. Please enter 1-{len(configs)}, v, d, D, or q")
            except ValueError:
                print("Please enter a valid option")

    return changes_made


def view_config_details(configs: List[str]) -> None:
    """Display detailed information about configurations."""
    if not configs:
        print("No configurations available.")
        return

    print("\nSelect configuration to view details:")
    for i, config_name in enumerate(configs, 1):
        print(f"  {i}. {config_name}")

    try:
        choice = input(f"\nEnter number [1-{len(configs)}] or [Enter] to cancel: ").strip()
        if not choice:
            return

        choice_num = int(choice)
        if 1 <= choice_num <= len(configs):
            config_name = configs[choice_num - 1]
            config = load_config(config_name)
            if config:
                print(f"\n{'='*60}")
                print(f"Configuration Details: {config_name}")
                print(f"{'='*60}")
                display_config_summary(config)
            else:
                print(f"Failed to load configuration: {config_name}")
        else:
            print(f"Invalid choice. Please enter 1-{len(configs)}")
    except ValueError:
        print("Please enter a valid number")


def delete_specific_config(configs: List[str]) -> bool:
    """Delete a specific configuration. Returns True if a deletion occurred."""
    if not configs:
        print("No configurations available to delete.")
        return False

    print("\nSelect configuration to delete:")
    for i, config_name in enumerate(configs, 1):
        print(f"  {i}. {config_name}")

    try:
        choice = input(f"\nEnter number [1-{len(configs)}] or [Enter] to cancel: ").strip()
        if not choice:
            return False

        choice_num = int(choice)
        if 1 <= choice_num <= len(configs):
            config_name = configs[choice_num - 1]

            # Show config details before deletion
            config = load_config(config_name)
            if config:
                print(f"\nConfiguration to delete: {config_name}")
                display_config_summary(config)

            if prompt_yes_no(f"\nAre you sure you want to delete '{config_name}'?", False):
                return delete_config(config_name)
        else:
            print(f"Invalid choice. Please enter 1-{len(configs)}")
    except ValueError:
        print("Please enter a valid number")

    return False


def delete_all_configs_interactive() -> bool:
    """Delete all configurations with confirmation. Returns True if deletion occurred."""
    configs = list_config_names()

    if not configs:
        print("No configurations to delete.")
        return False

    print(f"\nThis will delete ALL {len(configs)} saved configurations:")
    for config_name in configs:
        print(f"  - {config_name}")

    if prompt_yes_no(f"\nAre you sure you want to delete all {len(configs)} configurations?", False):
        if prompt_yes_no("This action cannot be undone. Continue?", False):
            return delete_all_configs()

    return False


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


def debug_cluster_data(namespace: str = "default") -> None:
    """Debug function to show raw cluster data."""
    print(f"\n>> Debug: Cluster Data Analysis")
    print("=" * 50)

    # Test basic connectivity
    print(f"Testing basic kubectl connectivity...")
    try:
        cmd = ["kubectl", "cluster-info"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
        print(f"[+] Cluster info successful")
        print(f">> Cluster details:")
        for line in result.stdout.split('\n')[:3]:  # First 3 lines
            if line.strip():
                print(f"  {line.strip()}")
    except Exception as e:
        print(f"[-] Cluster info failed: {e}")
        return

    # Test namespace access
    print(f"\nTesting namespace access...")
    try:
        cmd = ["kubectl", "get", "namespaces"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"[+] Can list namespaces")
        namespaces = [line.split()[0] for line in result.stdout.split('\n')[1:] if line.strip()]
        print(f">> Available namespaces: {', '.join(namespaces[:5])}")
        if namespace not in namespaces:
            print(f"[!]  Target namespace '{namespace}' not found!")
    except Exception as e:
        print(f"[-] Namespace access failed: {e}")

    # Test deployment access
    print(f"\nTesting deployment access in namespace '{namespace}'...")
    try:
        cmd = ["kubectl", "get", "deployments", "-n", namespace]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"[+] Can list deployments")
        lines = result.stdout.split('\n')[1:]  # Skip header
        deployments = [line.split()[0] for line in lines if line.strip()]
        print(f">> Found deployments: {', '.join(deployments) if deployments else 'None'}")
    except Exception as e:
        print(f"[-] Deployment access failed: {e}")
        print(f">> Error details: {e.stderr if hasattr(e, 'stderr') else str(e)}")

    # Test JSON output
    print(f"\nTesting JSON data retrieval...")
    try:
        cmd = ["kubectl", "get", "deployments", "-n", namespace, "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        items = data.get("items", [])
        print(f"[+] JSON retrieval successful")
        print(f">> Found {len(items)} deployment(s) in JSON format")

        if items:
            # Show details of first deployment
            first_deployment = items[0]
            metadata = first_deployment.get("metadata", {})
            spec = first_deployment.get("spec", {})
            status = first_deployment.get("status", {})

            print(f"\n[BOX] Sample deployment details:")
            print(f"  Name: {metadata.get('name', 'unknown')}")
            print(f"  Namespace: {metadata.get('namespace', 'unknown')}")
            print(f"  Labels: {metadata.get('labels', {})}")
            print(f"  Replicas: {spec.get('replicas', 0)}")
            print(f"  Ready Replicas: {status.get('readyReplicas', 0)}")

            # Check containers
            containers = spec.get("template", {}).get("spec", {}).get("containers", [])
            print(f"  Containers: {len(containers)}")
            for i, container in enumerate(containers[:2]):  # First 2 containers
                print(f"    {i+1}. {container.get('name', 'unnamed')}: {container.get('image', 'no-image')}")

    except json.JSONDecodeError as e:
        print(f"[-] JSON parsing failed: {e}")
    except Exception as e:
        print(f"[-] JSON retrieval failed: {e}")


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
            "ready": lambda d: get_deployment_status(d).startswith("[+]"),
            "failed": lambda d: get_deployment_status(d).startswith("[-]"),
            "issue": lambda d: get_deployment_status(d).startswith("[!]"),
            "scaling": lambda d: get_deployment_status(d).startswith("[CYCLE]"),
            "stopped": lambda d: get_deployment_status(d).startswith("[CIRCLE]")
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
    print(f"\n>> Chart Creation Preview")
    print("=" * 50)

    if len(selected_deployments) == 1:
        deployment = selected_deployments[0]
        chart_name = config.get('release', deployment['name'])
        output_dir = config.get('output_dir', f"./{deployment['name']}-chart")

        print(f"Chart Name: {chart_name}")
        print(f"Output Directory: {output_dir}")
        print(f"Source Deployment: {deployment['name']} ({deployment['ready_replicas']}/{deployment['replicas']} replicas)")

        # Estimate resources to be included
        print(f"\n[BOX] Resources to include:")
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

        print(f"\n[BOX] Deployments to include:")
        total_replicas = 0
        for deployment in selected_deployments:
            print(f"  ✓ {deployment['name']} ({deployment['ready_replicas']}/{deployment['replicas']} replicas)")
            total_replicas += deployment['replicas']

        print(f"\n[CHART] Summary:")
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
    print(f"\n[DIR] Chart Structure:")
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
    print(f"\n[SEARCH] Validation Checks:")
    validation_passed = True

    # Check if output directory exists
    output_path = Path(output_dir)
    if output_path.exists():
        print(f"  [!]  Output directory exists (will be overwritten)")
        if not config.get('force', False):
            validation_passed = False
    else:
        print(f"  [+] Output directory is available")

    # Check deployment health
    healthy_deployments = sum(1 for d in selected_deployments
                            if get_deployment_status(d).startswith("[+]"))
    if healthy_deployments == len(selected_deployments):
        print(f"  [+] All deployments are healthy")
    else:
        print(f"  [!]  {len(selected_deployments) - healthy_deployments} deployment(s) have issues")

    # Check for required fields
    if config.get('release'):
        print(f"  [+] Chart name specified")
    else:
        print(f"  [!]  No chart name specified (will use default)")

    # Summary
    print(f"\n[UP] Estimated Chart Complexity: {'Low' if template_count <= 5 else 'Medium' if template_count <= 15 else 'High'}")
    print(f"[RULER] Estimated Size: ~{template_count * 2}KB")

    if not validation_passed:
        print(f"\n[!]  Validation issues detected. Use --force to override.")
        return False

    print(f"\n[+] Ready to create chart!")
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

    print(f"\n[SEARCH] Chart Comparison: {output_dir}")
    print("=" * 50)

    # Check Chart.yaml
    chart_yaml_path = chart_path / "Chart.yaml"
    if chart_yaml_path.exists():
        try:
            with open(chart_yaml_path, 'r') as f:
                existing_chart = yaml.safe_load(f)

            current_version = existing_chart.get('version', '0.1.0')
            current_app_version = existing_chart.get('appVersion', '1.0.0')

            print(f"[PAGE] Existing Chart:")
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
            print(f"[!]  Could not read existing Chart.yaml: {e}")
            comparison_result["differences"].append("Chart.yaml unreadable")
    else:
        print(f"[PAGE] Chart.yaml: Not found")
        comparison_result["differences"].append("Chart.yaml missing")

    # Check values.yaml
    values_yaml_path = chart_path / "values.yaml"
    if values_yaml_path.exists():
        try:
            with open(values_yaml_path, 'r') as f:
                existing_values = yaml.safe_load(f)

            print(f"\n>> Existing values.yaml:")
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
                print(f"  [!]  Empty or invalid values.yaml")
                comparison_result["differences"].append("values.yaml empty")

        except Exception as e:
            print(f"[!]  Could not read existing values.yaml: {e}")
            comparison_result["differences"].append("values.yaml unreadable")
    else:
        print(f">> values.yaml: Not found")
        comparison_result["differences"].append("values.yaml missing")

    # Check templates directory
    templates_path = chart_path / "templates"
    if templates_path.exists() and templates_path.is_dir():
        template_files = list(templates_path.glob("*.yaml"))
        print(f"\n[DIR] Templates: {len(template_files)} files")

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
        print(f"[DIR] templates/: Not found or empty")
        comparison_result["differences"].append("templates directory missing")

    # Generate recommendations
    if comparison_result["differences"]:
        print(f"\n[TIP] Recommendations:")
        comparison_result["recommendations"].extend([
            "Update chart to include missing components",
            "Review and merge existing configuration",
            "Backup existing chart before updating"
        ])
        for rec in comparison_result["recommendations"]:
            print(f"  • {rec}")
    else:
        print(f"\n[+] Chart structure looks complete")
        comparison_result["recommendations"].append("Consider incremental update")

    return comparison_result


def handle_existing_chart_update(output_dir: str, config: Dict[str, Any]) -> str:
    """Handle updating an existing chart with user choices."""
    comparison = compare_with_existing_chart(output_dir, config)

    if not comparison or not comparison["exists"]:
        return "create"  # No existing chart, create new one

    print(f"\n[CYCLE] Chart Update Options:")
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
    print(f"\n[ROCKET] Bulk Export: Namespace '{namespace}'")
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

    print(f"\n[BOX] Starting bulk export...")
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
            print(f"  >> Chart: {deployment_name}")
            print(f"  [DIR] Output: {config['output_dir']}")

            # Find related resources
            related_resources = find_related_resources([deployment], namespace)
            total_resources = 1  # deployment itself
            if related_resources:
                for resource_type, items in related_resources.items():
                    if items:
                        total_resources += len(items)
                        print(f"  [BOX] {resource_type.title()}: {len(items)}")

            print(f"  [CHART] Total resources: {total_resources}")

            # Create the chart
            exporter = ChartExporter(args)
            exporter.run()

            successful_exports.append({
                'name': deployment_name,
                'path': config['output_dir'],
                'resources': total_resources
            })
            print(f"  [+] Exported successfully")

        except Exception as e:
            failed_exports.append({
                'name': deployment_name,
                'error': str(e)
            })
            print(f"  [-] Export failed: {e}")

    # Create combined chart if requested
    if create_combined_chart and successful_exports:
        print(f"\n[LINK] Creating combined chart...")
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

            print(f"  [+] Combined chart created: {combined_config['output_dir']}")

        except Exception as e:
            print(f"  [-] Combined chart failed: {e}")

    # Summary report
    print(f"\n[CHART] Bulk Export Summary")
    print("=" * 30)
    print(f"[+] Successful: {len(successful_exports)}")
    print(f"[-] Failed: {len(failed_exports)}")

    if successful_exports:
        print(f"\n[BOX] Successfully exported charts:")
        for export in successful_exports:
            print(f"  • {export['name']} ({export['resources']} resources)")
            print(f"    [DIR] {export['path']}")

    if failed_exports:
        print(f"\n[-] Failed exports:")
        for failure in failed_exports:
            print(f"  • {failure['name']}: {failure['error']}")

    # Next steps
    if successful_exports:
        print(f"\n[TARGET] Next Steps:")
        print(f"[BOX] Package charts:")
        for export in successful_exports:
            chart_dir = Path(export['path']).name
            print(f"  helm package {chart_dir}")

        print(f"\n[ROCKET] Deploy charts:")
        for export in successful_exports:
            chart_dir = Path(export['path']).name
            print(f"  helm install {export['name']} ./{chart_dir}")


def bulk_export_by_selector(label_selector: str, namespace: str = "default",
                           output_base_dir: str = "./charts") -> None:
    """Export all deployments matching a label selector."""
    print(f"\n[TARGET] Bulk Export by Selector: '{label_selector}'")
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
    print(f"\n[ROCKET] Bulk Export: {len(deployments)} filtered deployments")
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
            print(f"  [+] Success")

        except Exception as e:
            failed_exports.append((deployment_name, str(e)))
            print(f"  [-] Failed: {e}")

    # Summary
    print(f"\n[CHART] Bulk Export Results:")
    print(f"[+] Success: {len(successful_exports)}")
    print(f"[-] Failed: {len(failed_exports)}")


def handle_kubectl_error(error: subprocess.CalledProcessError, operation: str) -> None:
    """Handle kubectl command errors with helpful suggestions."""
    print(f"\n[-] {operation} failed")

    stderr = error.stderr or ""

    if "connection refused" in stderr.lower():
        print("[TOOL] Kubernetes connection issue:")
        print("  • Check if kubectl is configured correctly")
        print("  • Verify cluster is accessible: kubectl cluster-info")
        print("  • Check if you're using the right context: kubectl config current-context")

    elif "forbidden" in stderr.lower() or "unauthorized" in stderr.lower():
        print("[LOCK] Permission issue:")
        print("  • Check if you have the required permissions")
        print("  • Verify your kubeconfig is valid")
        print("  • Try: kubectl auth can-i get deployments")

    elif "not found" in stderr.lower():
        print("[SEARCH] Resource not found:")
        print("  • Check if the namespace exists: kubectl get namespaces")
        print("  • Verify deployment names: kubectl get deployments -A")
        print("  • Check if you're using the correct namespace")

    elif "no such host" in stderr.lower() or "network" in stderr.lower():
        print("[NET] Network connectivity issue:")
        print("  • Check your internet connection")
        print("  • Verify VPN settings if using corporate network")
        print("  • Try: kubectl version --client")

    else:
        print(f">> Error details: {stderr}")
        print("[TIP] Troubleshooting tips:")
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

            print(f"\n[!]  {operation_name} failed (attempt {attempt + 1}/{max_retries})")
            print(f"Error: {e.stderr or e}")

            if not prompt_yes_no(f"Retry {operation_name}?", True):
                raise

            print("Retrying...")
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"\n[-] {operation_name} failed: {e}")
                raise

            print(f"\n[!]  {operation_name} failed (attempt {attempt + 1}/{max_retries}): {e}")

            if not prompt_yes_no(f"Retry {operation_name}?", True):
                raise

            print("Retrying...")


def detect_kubernetes_access_scope() -> Dict[str, Any]:
    """Detect the user's Kubernetes access scope and capabilities."""
    access_info = {
        "cluster_access": False,
        "namespace_access": {},
        "default_namespace": "default",
        "available_namespaces": [],
        "recommended_mode": "namespace-only"
    }

    print(">> Detecting Kubernetes access scope...")

    # Test 1: Try cluster-level access
    try:
        result = subprocess.run(["kubectl", "cluster-info"],
                              capture_output=True, text=True, check=True, timeout=5)
        access_info["cluster_access"] = True
        print("[+] Cluster-level access detected")
    except:
        print("[!] No cluster-level access (restricted environment)")

    # Test 2: Try to list namespaces
    try:
        result = subprocess.run(["kubectl", "get", "namespaces", "--no-headers"],
                              capture_output=True, text=True, check=True, timeout=5)
        namespaces = [line.split()[0] for line in result.stdout.split('\n') if line.strip()]
        access_info["available_namespaces"] = namespaces
        print(f"[+] Can list namespaces: {len(namespaces)} found")
        if namespaces:
            access_info["recommended_mode"] = "multi-namespace"
    except:
        print("[!] Cannot list namespaces (namespace-scoped access)")

    # Test 3: Check current context default namespace
    try:
        result = subprocess.run(["kubectl", "config", "view", "--minify", "-o",
                               "jsonpath={.contexts[0].context.namespace}"],
                              capture_output=True, text=True, check=True)
        if result.stdout.strip():
            access_info["default_namespace"] = result.stdout.strip()
            print(f"[*] Default namespace from context: {access_info['default_namespace']}")
    except:
        pass

    # Test 4: Test namespace access for common namespaces
    test_namespaces = [access_info["default_namespace"], "default", "kube-system"]
    for ns in test_namespaces:
        try:
            result = subprocess.run(["kubectl", "get", "deployments", "-n", ns, "--no-headers"],
                                  capture_output=True, text=True, check=True, timeout=5)
            lines = [line for line in result.stdout.split('\n') if line.strip()]
            access_info["namespace_access"][ns] = {
                "accessible": True,
                "deployment_count": len(lines)
            }
            print(f"[+] Namespace '{ns}': {len(lines)} deployment(s)")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            if "forbidden" in stderr.lower():
                access_info["namespace_access"][ns] = {"accessible": False, "reason": "forbidden"}
                print(f"[-] Namespace '{ns}': Access denied")
            elif "not found" in stderr.lower():
                access_info["namespace_access"][ns] = {"accessible": False, "reason": "not_found"}
                print(f"[?] Namespace '{ns}': Not found")
        except:
            access_info["namespace_access"][ns] = {"accessible": False, "reason": "unknown"}

    return access_info


def prompt_for_access_scope(access_info: Dict[str, Any]) -> Dict[str, Any]:
    """Interactive prompt to select access scope and target namespace."""
    print(f"\n[TARGET] Kubernetes Access Configuration")
    print("=" * 50)

    # Show detected capabilities
    print(">> Detected capabilities:")
    if access_info["cluster_access"]:
        print("  [+] Cluster-level access (can run cluster-info)")
    else:
        print("  [NOTE] Namespace-scoped access (no cluster-level permissions)")

    if access_info["available_namespaces"]:
        print(f"  [+] Can list namespaces ({len(access_info['available_namespaces'])} available)")
    else:
        print("  [NOTE] Cannot list namespaces (restricted to specific namespaces)")

    # Show accessible namespaces
    accessible_ns = {ns: info for ns, info in access_info["namespace_access"].items()
                    if info.get("accessible", False)}

    if accessible_ns:
        print(f"\n[BOX] Accessible namespaces with deployments:")
        for ns, info in accessible_ns.items():
            count = info.get("deployment_count", 0)
            print(f"  • {ns}: {count} deployment(s)")
    else:
        print(f"\n[!]  No accessible namespaces detected with the test")

    # Determine options based on access level
    options = []

    if access_info["available_namespaces"]:
        options.append(("multi", f"Browse all available namespaces ({len(access_info['available_namespaces'])} found)"))

    if accessible_ns:
        if len(accessible_ns) == 1:
            ns_name = list(accessible_ns.keys())[0]
            options.append(("single", f"Use accessible namespace: {ns_name}"))
        else:
            options.append(("select", f"Select from accessible namespaces ({len(accessible_ns)} found)"))

    options.append(("specify", "Specify a namespace manually"))

    if not options:
        # Fallback if we can't detect anything
        options.append(("manual", "Manual configuration (specify namespace)"))

    print(f"\n[TARGET] Access mode options:")
    for i, (mode, description) in enumerate(options, 1):
        print(f"  {i}. {description}")

    # Get user choice
    while True:
        try:
            choice = input(f"\nSelect option [1-{len(options)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                mode, _ = options[idx]
                break
            else:
                print(f"Invalid choice. Please enter 1-{len(options)}")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except (KeyboardInterrupt, EOFError):
            print("\nConfiguration cancelled.")
            return {}

    # Handle the selected mode
    selected_config = {"mode": mode}

    if mode == "multi":
        # Let user browse all namespaces
        print(f"\n>> Available namespaces:")
        for i, ns in enumerate(access_info["available_namespaces"], 1):
            print(f"  {i}. {ns}")

        while True:
            try:
                ns_choice = input(f"\nSelect namespace [1-{len(access_info['available_namespaces'])}]: ").strip()
                ns_idx = int(ns_choice) - 1
                if 0 <= ns_idx < len(access_info["available_namespaces"]):
                    selected_config["namespace"] = access_info["available_namespaces"][ns_idx]
                    break
                else:
                    print(f"Invalid choice. Please enter 1-{len(access_info['available_namespaces'])}")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except (KeyboardInterrupt, EOFError):
                return {}

    elif mode == "single":
        # Use the single accessible namespace
        selected_config["namespace"] = list(accessible_ns.keys())[0]

    elif mode == "select":
        # Let user select from accessible namespaces
        accessible_list = list(accessible_ns.keys())
        print(f"\n[BOX] Select from accessible namespaces:")
        for i, ns in enumerate(accessible_list, 1):
            count = accessible_ns[ns].get("deployment_count", 0)
            print(f"  {i}. {ns} ({count} deployments)")

        while True:
            try:
                ns_choice = input(f"\nSelect namespace [1-{len(accessible_list)}]: ").strip()
                ns_idx = int(ns_choice) - 1
                if 0 <= ns_idx < len(accessible_list):
                    selected_config["namespace"] = accessible_list[ns_idx]
                    break
                else:
                    print(f"Invalid choice. Please enter 1-{len(accessible_list)}")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except (KeyboardInterrupt, EOFError):
                return {}

    elif mode in ["specify", "manual"]:
        # Manual namespace entry
        default_ns = access_info["default_namespace"]
        namespace = input(f"Enter namespace name [{default_ns}]: ").strip()
        selected_config["namespace"] = namespace if namespace else default_ns

    # Determine if we need cluster-level validation
    selected_config["skip_cluster_check"] = not access_info["cluster_access"]
    selected_config["namespace_only"] = not access_info["cluster_access"]

    print(f"\n[+] Configuration selected:")
    print(f"  [PIN] Target namespace: {selected_config['namespace']}")
    print(f"  [LOCK] Mode: {'Namespace-only' if selected_config['namespace_only'] else 'Cluster-aware'}")

    return selected_config


def validate_prerequisites(skip_cluster_check: bool = False, namespace: str = "default") -> bool:
    """Validate that required tools are available."""
    print("[SEARCH] Validating prerequisites...")

    missing_tools = []

    # Check kubectl
    try:
        result = subprocess.run(["kubectl", "version", "--client"],
                              capture_output=True, text=True, check=True)
        print("[+] kubectl is available")
    except FileNotFoundError:
        missing_tools.append("kubectl")
        print("[-] kubectl not found")
    except subprocess.CalledProcessError:
        print("[!]  kubectl found but may have issues")

    # Check namespace access (more reliable than cluster-info for restricted environments)
    if not skip_cluster_check:
        try:
            # Try namespace-scoped access first (works with restricted permissions)
            result = subprocess.run(["kubectl", "get", "deployments", "-n", namespace, "--no-headers"],
                                  capture_output=True, text=True, check=True, timeout=10)
            print(f"[+] Kubernetes namespace '{namespace}' is accessible")

            # Count deployments
            lines = [line for line in result.stdout.split('\n') if line.strip()]
            print(f"[BOX] Found {len(lines)} deployment(s) in namespace '{namespace}'")

        except subprocess.CalledProcessError as e:
            print(f"[-] Cannot access namespace '{namespace}'")

            # Try to give helpful error messages
            stderr = e.stderr or ""
            if "forbidden" in stderr.lower():
                print("[LOCK] Permission issue:")
                print(f"  • Check if you have access to namespace '{namespace}'")
                print(f"  • Try: kubectl auth can-i get deployments -n {namespace}")
                print(f"  • Contact your cluster administrator for namespace access")
            elif "not found" in stderr.lower():
                print("[SEARCH] Namespace not found:")
                print(f"  • Check if namespace '{namespace}' exists")
                print(f"  • Try: kubectl get namespaces (if you have permission)")
                print(f"  • Or specify a different namespace with --namespace")
            else:
                handle_kubectl_error(e, f"Namespace '{namespace}' access check")

            return False
        except subprocess.TimeoutExpired:
            print(f"[!]  Kubernetes namespace '{namespace}' connection timeout")
            print("   This may indicate network issues or slow cluster")
        except FileNotFoundError:
            pass  # kubectl already reported as missing
    else:
        print("[!]  Namespace connectivity check skipped")

    # Check helm (optional)
    try:
        result = subprocess.run(["helm", "version"],
                              capture_output=True, text=True, check=True)
        print("[+] helm is available (optional)")
    except FileNotFoundError:
        print("ℹ️  helm not found (optional - charts can still be created)")
    except subprocess.CalledProcessError:
        print("[!]  helm found but may have issues (optional)")

    if missing_tools:
        print(f"\n[-] Missing required tools: {', '.join(missing_tools)}")
        print("📖 Installation help:")
        for tool in missing_tools:
            if tool == "kubectl":
                print("  kubectl: https://kubernetes.io/docs/tasks/tools/")
        return False

    return True


def handle_chart_creation_error(error: Exception, deployment_name: str) -> bool:
    """Handle chart creation errors with recovery options."""
    print(f"\n[-] Chart creation failed for '{deployment_name}': {error}")

    # Analyze error and provide specific guidance
    error_str = str(error).lower()

    if "permission denied" in error_str:
        print("[LOCK] File permission issue:")
        print("  • Check if output directory is writable")
        print("  • Try a different output directory")
        print("  • On Windows, try running as administrator")

    elif "no space left" in error_str:
        print("[DISK] Disk space issue:")
        print("  • Free up disk space")
        print("  • Try a different output directory")

    elif "file exists" in error_str or "directory not empty" in error_str:
        print("[DIR] Output directory conflict:")
        print("  • Use --force to overwrite existing files")
        print("  • Choose a different output directory")
        print("  • Manually remove existing directory")

    elif "template" in error_str or "yaml" in error_str:
        print("[NOTE] Template generation issue:")
        print("  • This may be due to unusual resource configurations")
        print("  • Try with a simpler deployment first")
        print("  • Check if deployment has all required fields")

    else:
        print("[TOOL] General troubleshooting:")
        print("  • Try with --verbose for more details")
        print("  • Ensure deployment is running properly")
        print("  • Check kubectl permissions")

    return prompt_yes_no("Would you like to try creating another chart?", True)


def safe_file_operation(operation_func, operation_name: str, file_path: str = ""):
    """Safely perform file operations with error handling."""
    try:
        return operation_func()
    except PermissionError:
        print(f"[-] Permission denied: {operation_name}")
        if file_path:
            print(f"   File: {file_path}")
        print("[TIP] Try:")
        print("  • Check file/directory permissions")
        print("  • Close any applications using the file")
        print("  • Run with elevated permissions if necessary")
        raise
    except FileNotFoundError:
        print(f"[-] File not found: {operation_name}")
        if file_path:
            print(f"   File: {file_path}")
        print("[TIP] Check if the path exists and is correct")
        raise
    except OSError as e:
        print(f"[-] File system error: {operation_name}")
        if file_path:
            print(f"   File: {file_path}")
        print(f"   Error: {e}")
        print("[TIP] This may be due to:")
        print("  • Insufficient disk space")
        print("  • File system corruption")
        print("  • Path too long (Windows)")
        raise


def generate_demo_deployments() -> List[Dict[str, Any]]:
    """Generate sample deployment data for demo mode."""
    return [
        {
            "name": "frontend-app",
            "replicas": 3,
            "ready_replicas": 3,
            "namespace": "production",
            "labels": {"app": "frontend", "tier": "web"},
            "creation_time": "2024-01-15T10:30:00Z",
            "images": ["nginx:1.21", "myapp/frontend:v2.1.0"]
        },
        {
            "name": "api-service",
            "replicas": 2,
            "ready_replicas": 2,
            "namespace": "production",
            "labels": {"app": "api", "tier": "backend"},
            "creation_time": "2024-01-15T10:25:00Z",
            "images": ["myregistry/api:v3.2.1"]
        },
        {
            "name": "worker-service",
            "replicas": 1,
            "ready_replicas": 0,
            "namespace": "production",
            "labels": {"app": "worker", "tier": "processing"},
            "creation_time": "2024-01-15T09:45:00Z",
            "images": ["redis:7-alpine", "myapp/worker:v1.5.0"]
        },
        {
            "name": "notification-service",
            "replicas": 5,
            "ready_replicas": 3,
            "namespace": "production",
            "labels": {"app": "notifications", "tier": "messaging"},
            "creation_time": "2024-01-15T11:00:00Z",
            "images": ["myapp/notifications:v1.8.2"]
        }
    ]


def extract_deployment_details(deployment_name: str, namespace: str) -> Dict[str, Any]:
    """Extract comprehensive deployment configuration from Kubernetes."""
    try:
        cmd = ["kubectl", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        deployment_data = json.loads(result.stdout)

        metadata = deployment_data.get("metadata", {})
        spec = deployment_data.get("spec", {})
        template = spec.get("template", {})
        pod_spec = template.get("spec", {})
        containers = pod_spec.get("containers", [])
        init_containers = pod_spec.get("initContainers", [])

        if not containers:
            return {}

        # Extract from first container (main container)
        main_container = containers[0]

        extracted = {
            "name": deployment_name,
            "namespace": namespace,
            "replicas": spec.get("replicas", 1),
            "revisionHistoryLimit": spec.get("revisionHistoryLimit", 10),
            "strategy": spec.get("strategy", {}),
            "minReadySeconds": spec.get("minReadySeconds", 0),
            "progressDeadlineSeconds": spec.get("progressDeadlineSeconds", 600),

            # Metadata
            "labels": metadata.get("labels", {}),
            "annotations": metadata.get("annotations", {}),

            # Pod template metadata
            "podLabels": template.get("metadata", {}).get("labels", {}),
            "podAnnotations": template.get("metadata", {}).get("annotations", {}),

            # Main container image
            "image": {
                "repository": main_container.get("image", "").split(":")[0] if ":" in main_container.get("image", "") else main_container.get("image", ""),
                "tag": main_container.get("image", "").split(":")[-1] if ":" in main_container.get("image", "") else "latest",
                "pullPolicy": main_container.get("imagePullPolicy", "IfNotPresent")
            },

            # All containers
            "containers": [],
            "initContainers": [],

            # Environment configuration
            "env": {},
            "envFrom": [],

            # Resource configuration
            "resources": {},

            # Networking
            "ports": [],
            "hostNetwork": pod_spec.get("hostNetwork", False),
            "dnsPolicy": pod_spec.get("dnsPolicy", "ClusterFirst"),
            "dnsConfig": pod_spec.get("dnsConfig", {}),

            # Storage
            "volumeMounts": [],
            "volumes": [],

            # Security
            "securityContext": {},
            "podSecurityContext": pod_spec.get("securityContext", {}),
            "serviceAccount": pod_spec.get("serviceAccountName", ""),
            "serviceAccountName": pod_spec.get("serviceAccountName", ""),
            "automountServiceAccountToken": pod_spec.get("automountServiceAccountToken", True),

            # Scheduling
            "nodeSelector": pod_spec.get("nodeSelector", {}),
            "tolerations": pod_spec.get("tolerations", []),
            "affinity": pod_spec.get("affinity", {}),
            "topologySpreadConstraints": pod_spec.get("topologySpreadConstraints", []),
            "schedulerName": pod_spec.get("schedulerName", ""),
            "priority": pod_spec.get("priority", 0),
            "priorityClassName": pod_spec.get("priorityClassName", ""),
            "runtimeClassName": pod_spec.get("runtimeClassName", ""),

            # Lifecycle
            "restartPolicy": pod_spec.get("restartPolicy", "Always"),
            "terminationGracePeriodSeconds": pod_spec.get("terminationGracePeriodSeconds", 30),
            "activeDeadlineSeconds": pod_spec.get("activeDeadlineSeconds", 0),

            # Image pull
            "imagePullSecrets": pod_spec.get("imagePullSecrets", []),

            # Host configuration
            "hostPID": pod_spec.get("hostPID", False),
            "hostIPC": pod_spec.get("hostIPC", False),
            "shareProcessNamespace": pod_spec.get("shareProcessNamespace", False),

            # Probes (from main container)
            "livenessProbe": main_container.get("livenessProbe", {}),
            "readinessProbe": main_container.get("readinessProbe", {}),
            "startupProbe": main_container.get("startupProbe", {}),

            # Additional container settings
            "workingDir": main_container.get("workingDir", ""),
            "command": main_container.get("command", []),
            "args": main_container.get("args", []),
            "stdin": main_container.get("stdin", False),
            "stdinOnce": main_container.get("stdinOnce", False),
            "tty": main_container.get("tty", False)
        }

        # Extract all containers (main + sidecars)
        for container in containers:
            container_info = {
                "name": container.get("name", ""),
                "image": container.get("image", ""),
                "imagePullPolicy": container.get("imagePullPolicy", "IfNotPresent"),
                "ports": container.get("ports", []),
                "env": container.get("env", []),
                "envFrom": container.get("envFrom", []),
                "resources": container.get("resources", {}),
                "volumeMounts": container.get("volumeMounts", []),
                "securityContext": container.get("securityContext", {}),
                "livenessProbe": container.get("livenessProbe", {}),
                "readinessProbe": container.get("readinessProbe", {}),
                "startupProbe": container.get("startupProbe", {}),
                "lifecycle": container.get("lifecycle", {}),
                "workingDir": container.get("workingDir", ""),
                "command": container.get("command", []),
                "args": container.get("args", []),
                "stdin": container.get("stdin", False),
                "stdinOnce": container.get("stdinOnce", False),
                "tty": container.get("tty", False),
                "terminationMessagePath": container.get("terminationMessagePath", "/dev/termination-log"),
                "terminationMessagePolicy": container.get("terminationMessagePolicy", "File")
            }
            extracted["containers"].append(container_info)

        # Extract init containers
        for init_container in init_containers:
            init_info = {
                "name": init_container.get("name", ""),
                "image": init_container.get("image", ""),
                "imagePullPolicy": init_container.get("imagePullPolicy", "IfNotPresent"),
                "env": init_container.get("env", []),
                "envFrom": init_container.get("envFrom", []),
                "resources": init_container.get("resources", {}),
                "volumeMounts": init_container.get("volumeMounts", []),
                "securityContext": init_container.get("securityContext", {}),
                "workingDir": init_container.get("workingDir", ""),
                "command": init_container.get("command", []),
                "args": init_container.get("args", [])
            }
            extracted["initContainers"].append(init_info)

        # Extract environment variables from main container with comprehensive handling
        main_env = main_container.get("env", [])
        for env_var in main_env:
            name = env_var.get("name", "")
            if "value" in env_var:
                # Direct string value
                extracted["env"][name] = env_var["value"]
            elif "valueFrom" in env_var:
                # Handle references to ConfigMaps, Secrets, resource fields, etc.
                value_from = env_var["valueFrom"]
                if "configMapKeyRef" in value_from:
                    ref = value_from["configMapKeyRef"]
                    extracted["env"][name] = {
                        "valueFrom": {
                            "configMapKeyRef": {
                                "name": ref.get("name", ""),
                                "key": ref.get("key", ""),
                                "optional": ref.get("optional", False)
                            }
                        }
                    }
                elif "secretKeyRef" in value_from:
                    ref = value_from["secretKeyRef"]
                    extracted["env"][name] = {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": ref.get("name", ""),
                                "key": ref.get("key", ""),
                                "optional": ref.get("optional", False)
                            }
                        }
                    }
                elif "fieldRef" in value_from:
                    field_ref = value_from["fieldRef"]
                    extracted["env"][name] = {
                        "valueFrom": {
                            "fieldRef": {
                                "fieldPath": field_ref.get("fieldPath", ""),
                                "apiVersion": field_ref.get("apiVersion", "v1")
                            }
                        }
                    }
                elif "resourceFieldRef" in value_from:
                    resource_ref = value_from["resourceFieldRef"]
                    extracted["env"][name] = {
                        "valueFrom": {
                            "resourceFieldRef": {
                                "resource": resource_ref.get("resource", ""),
                                "containerName": resource_ref.get("containerName", ""),
                                "divisor": resource_ref.get("divisor", "1")
                            }
                        }
                    }

        # Extract envFrom (ConfigMaps and Secrets)
        extracted["envFrom"] = main_container.get("envFrom", [])

        # Extract resources
        resources = main_container.get("resources", {})
        if resources:
            extracted["resources"] = resources

        # Extract ports
        ports = main_container.get("ports", [])
        for port in ports:
            extracted["ports"].append({
                "name": port.get("name", ""),
                "containerPort": port.get("containerPort", 8080),
                "protocol": port.get("protocol", "TCP")
            })

        # Extract volume mounts
        extracted["volumeMounts"] = main_container.get("volumeMounts", [])

        # Extract volumes from pod spec
        extracted["volumes"] = pod_spec.get("volumes", [])

        # Extract security context
        extracted["securityContext"] = pod_spec.get("securityContext", {})

        return extracted

    except Exception as e:
        print(f"[!]  Failed to extract deployment details for {deployment_name}: {e}")
        return {}


def generate_enhanced_values_yaml(deployment_details: Dict[str, Any], related_resources: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive values.yaml from deployment details and related resources."""
    values = {
        "# Values extracted from live Kubernetes deployment": None,
        "replicaCount": deployment_details.get("replicas", 1),
        "image": deployment_details.get("image", {
            "repository": "nginx",
            "tag": "latest",
            "pullPolicy": "IfNotPresent"
        })
    }

    # Add environment variables
    env_vars = deployment_details.get("env", {})
    if env_vars:
        values["env"] = env_vars

    # Add envFrom references
    env_from = deployment_details.get("envFrom", [])
    if env_from:
        values["envFrom"] = env_from

    # Add resources
    resources = deployment_details.get("resources", {})
    if resources:
        values["resources"] = resources
    else:
        # Provide sensible defaults
        values["resources"] = {
            "limits": {
                "cpu": "500m",
                "memory": "512Mi"
            },
            "requests": {
                "cpu": "100m",
                "memory": "128Mi"
            }
        }

    # Add ports
    ports = deployment_details.get("ports", [])
    if ports:
        values["ports"] = ports
        # Set main service port from first container port
        if ports[0].get("containerPort"):
            values["service"] = {
                "type": "ClusterIP",
                "port": 80,
                "targetPort": ports[0]["containerPort"]
            }
    else:
        values["service"] = {
            "type": "ClusterIP",
            "port": 80,
            "targetPort": 8080
        }

    # Add volume mounts
    volume_mounts = deployment_details.get("volumeMounts", [])
    if volume_mounts:
        values["volumeMounts"] = volume_mounts

    # Add volumes
    volumes = deployment_details.get("volumes", [])
    if volumes:
        values["volumes"] = volumes

    # Add security context
    security_context = deployment_details.get("securityContext", {})
    if security_context:
        values["securityContext"] = security_context

    # Add service account
    service_account = deployment_details.get("serviceAccount", "")
    if service_account:
        values["serviceAccount"] = {
            "create": False,
            "name": service_account
        }

    # Add node selector
    node_selector = deployment_details.get("nodeSelector", {})
    if node_selector:
        values["nodeSelector"] = node_selector

    # Add tolerations
    tolerations = deployment_details.get("tolerations", [])
    if tolerations:
        values["tolerations"] = tolerations

    # Add affinity
    affinity = deployment_details.get("affinity", {})
    if affinity:
        values["affinity"] = affinity

    # Add all containers info for multi-container deployments
    containers = deployment_details.get("containers", [])
    if len(containers) > 1:
        values["additionalContainers"] = containers[1:]  # Skip main container

    # Add related resources
    for resource_type, resources_list in related_resources.items():
        if resources_list:
            values[resource_type] = {}
            for resource in resources_list:
                resource_name = resource.get("name", "unknown")
                values[resource_type][resource_name] = {
                    "enabled": True,
                    "data": resource.get("data", {})
                }

    return values


def create_enhanced_chart(deployment_details: Dict[str, Any], related_resources: Dict[str, Any], output_dir: str) -> None:
    """Create a comprehensive Helm chart from detailed deployment and resource data."""
    chart_path = Path(output_dir)
    chart_path.mkdir(parents=True, exist_ok=True)

    # Create templates directory
    templates_path = chart_path / "templates"
    templates_path.mkdir(exist_ok=True)

    deployment_name = deployment_details.get("name", "app")
    image_info = deployment_details.get("image", {})

    # Generate Chart.yaml
    chart_yaml = {
        "apiVersion": "v2",
        "name": deployment_name,
        "description": f"Helm chart for {deployment_name} exported from Kubernetes",
        "type": "application",
        "version": "0.1.0",
        "appVersion": image_info.get("tag", "latest")
    }

    with open(chart_path / "Chart.yaml", 'w') as f:
        yaml.dump(chart_yaml, f, default_flow_style=False)

    # Generate enhanced values.yaml
    values_yaml = generate_enhanced_values_yaml(deployment_details, related_resources)

    with open(chart_path / "values.yaml", 'w') as f:
        yaml.dump(values_yaml, f, default_flow_style=False, sort_keys=False)

    # Generate enhanced deployment template
    deployment_template = generate_deployment_template(deployment_details)
    with open(templates_path / f"deployment.yaml", 'w') as f:
        f.write(deployment_template)

    # Generate service template if ports are defined
    if deployment_details.get("ports"):
        service_template = generate_service_template(deployment_name)
        with open(templates_path / f"service.yaml", 'w') as f:
            f.write(service_template)

    # Generate templates for related resources
    for resource_type, resources_list in related_resources.items():
        for resource in resources_list:
            template_content = generate_resource_template(resource_type, resource)
            if template_content:
                resource_name = resource.get("name", "resource")
                with open(templates_path / f"{resource_type}-{resource_name}.yaml", 'w') as f:
                    f.write(template_content)

    print(f"  [+] Enhanced chart created: {output_dir}")
    print(f"     [DIR] Chart.yaml, values.yaml with real config, and {len(list(templates_path.glob('*.yaml')))} templates")


def generate_deployment_template(deployment_details: Dict[str, Any]) -> str:
    """Generate a comprehensive deployment template."""
    deployment_name = deployment_details.get("name", "app")

    template = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {deployment_name}
  labels:
    {{{{- include "{deployment_name}.labels" . | nindent 4 }}}}
spec:
  {{{{- if not .Values.autoscaling.enabled }}}}
  replicas: {{{{ .Values.replicaCount }}}}
  {{{{- end }}}}
  selector:
    matchLabels:
      {{{{- include "{deployment_name}.selectorLabels" . | nindent 6 }}}}
  template:
    metadata:
      {{{{- with .Values.podAnnotations }}}}
      annotations:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      labels:
        {{{{- include "{deployment_name}.selectorLabels" . | nindent 8 }}}}
    spec:
      {{{{- with .Values.imagePullSecrets }}}}
      imagePullSecrets:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      {{{{- if .Values.serviceAccount.name }}}}
      serviceAccountName: {{{{ .Values.serviceAccount.name }}}}
      {{{{- end }}}}
      {{{{- with .Values.securityContext }}}}
      securityContext:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      containers:
        - name: {{{{ .Chart.Name }}}}
          image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag | default .Chart.AppVersion }}}}"
          imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}
          {{{{- if .Values.ports }}}}
          ports:
            {{{{- range .Values.ports }}}}
            - name: {{{{ .name | default "http" }}}}
              containerPort: {{{{ .containerPort }}}}
              protocol: {{{{ .protocol | default "TCP" }}}}
            {{{{- end }}}}
          {{{{- end }}}}
          {{{{- if .Values.env }}}}
          env:
            {{{{- range $key, $value := .Values.env }}}}
            - name: {{{{ $key }}}}
              value: {{{{ $value | quote }}}}
            {{{{- end }}}}
          {{{{- end }}}}
          {{{{- with .Values.envFrom }}}}
          envFrom:
            {{{{- toYaml . | nindent 12 }}}}
          {{{{- end }}}}
          {{{{- with .Values.resources }}}}
          resources:
            {{{{- toYaml . | nindent 12 }}}}
          {{{{- end }}}}
          {{{{- with .Values.volumeMounts }}}}
          volumeMounts:
            {{{{- toYaml . | nindent 12 }}}}
          {{{{- end }}}}
      {{{{- with .Values.volumes }}}}
      volumes:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      {{{{- with .Values.nodeSelector }}}}
      nodeSelector:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      {{{{- with .Values.affinity }}}}
      affinity:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      {{{{- with .Values.tolerations }}}}
      tolerations:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
"""
    return template


def generate_service_template(deployment_name: str) -> str:
    """Generate service template."""
    return f"""apiVersion: v1
kind: Service
metadata:
  name: {deployment_name}
  labels:
    {{{{- include "{deployment_name}.labels" . | nindent 4 }}}}
spec:
  type: {{{{ .Values.service.type }}}}
  ports:
    - port: {{{{ .Values.service.port }}}}
      targetPort: {{{{ .Values.service.targetPort }}}}
      protocol: TCP
      name: http
  selector:
    {{{{- include "{deployment_name}.selectorLabels" . | nindent 4 }}}}
"""


def generate_resource_template(resource_type: str, resource: Dict[str, Any]) -> str:
    """Generate template for ConfigMaps, Secrets, etc."""
    resource_name = resource.get("name", "resource")

    if resource_type == "configmaps":
        return f"""{{{{- if .Values.configmaps.{resource_name}.enabled }}}}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {resource_name}
  labels:
    {{{{- include "app.labels" . | nindent 4 }}}}
data:
{{{{ toYaml .Values.configmaps.{resource_name}.data | indent 2 }}}}
{{{{- end }}}}
"""
    elif resource_type == "secrets":
        return f"""{{{{- if .Values.secrets.{resource_name}.enabled }}}}
apiVersion: v1
kind: Secret
metadata:
  name: {resource_name}
  labels:
    {{{{- include "app.labels" . | nindent 4 }}}}
type: Opaque
data:
{{{{ toYaml .Values.secrets.{resource_name}.data | indent 2 }}}}
{{{{- end }}}}
"""
    elif resource_type == "persistentvolumeclaims":
        return f"""{{{{- if .Values.persistentvolumeclaims.{resource_name}.enabled }}}}
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {resource_name}
  labels:
    {{{{- include "app.labels" . | nindent 4 }}}}
spec:
{{{{ toYaml .Values.persistentvolumeclaims.{resource_name}.spec | indent 2 }}}}
{{{{- end }}}}
"""

    return ""


def create_demo_chart(deployment: Dict[str, Any], output_dir: str) -> None:
    """Create a demo chart with sample data."""
    chart_path = Path(output_dir)
    chart_path.mkdir(parents=True, exist_ok=True)

    # Create templates directory
    templates_path = chart_path / "templates"
    templates_path.mkdir(exist_ok=True)

    deployment_name = deployment["name"]
    image_parts = deployment["images"][0].split(":")
    repository = image_parts[0]
    tag = image_parts[1] if len(image_parts) > 1 else "latest"

    # Generate Chart.yaml
    chart_yaml = {
        "apiVersion": "v2",
        "name": deployment_name,
        "description": f"Helm chart for {deployment_name} exported from Kubernetes",
        "type": "application",
        "version": "0.1.0",
        "appVersion": tag
    }

    with open(chart_path / "Chart.yaml", 'w') as f:
        yaml.dump(chart_yaml, f, default_flow_style=False)

    # Generate values.yaml
    values_yaml = {
        "image": {
            "repository": repository,
            "tag": tag,
            "pullPolicy": "IfNotPresent"
        },
        "replicaCount": deployment["replicas"],
        "containerPort": 8080,
        "service": {
            "type": "ClusterIP",
            "port": 80,
            "targetPort": 8080
        },
        "resources": {
            "limits": {
                "cpu": "500m",
                "memory": "512Mi"
            },
            "requests": {
                "cpu": "250m",
                "memory": "256Mi"
            }
        }
    }

    # Add demo config if it's a web service
    if "frontend" in deployment_name or "api" in deployment_name:
        values_yaml["config"] = {
            "enabled": True,
            "data": {
                "app.properties": f"app.name={deployment_name}\napp.version={tag}\napp.environment=production"
            }
        }

    with open(chart_path / "values.yaml", 'w') as f:
        yaml.dump(values_yaml, f, default_flow_style=False)

    # Generate deployment template
    deployment_template = f"""---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {deployment_name}
  labels:
    app: {deployment_name}
spec:
  replicas: {{{{ .Values.replicaCount | default 1 }}}}
  selector:
    matchLabels:
      app: {deployment_name}
  template:
    metadata:
      labels:
        app: {deployment_name}
    spec:
      containers:
      - name: {deployment_name}
        image: {{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag }}}}
        imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}
        ports:
        - containerPort: {{{{ .Values.containerPort }}}}
        resources: {{{{ toYaml .Values.resources | nindent 10 }}}}
"""

    with open(templates_path / f"deployment-{deployment_name}.yaml", 'w') as f:
        f.write(deployment_template)

    # Generate service template
    service_template = f"""---
apiVersion: v1
kind: Service
metadata:
  name: {deployment_name}
  labels:
    app: {deployment_name}
spec:
  type: {{{{ .Values.service.type }}}}
  ports:
  - port: {{{{ .Values.service.port }}}}
    targetPort: {{{{ .Values.service.targetPort }}}}
    protocol: TCP
  selector:
    app: {deployment_name}
"""

    with open(templates_path / f"service-{deployment_name}.yaml", 'w') as f:
        f.write(service_template)

    # Generate configmap template if config exists
    if "config" in values_yaml:
        configmap_template = f"""{{{{- if .Values.config.enabled }}}}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {deployment_name}-config
  labels:
    app: {deployment_name}
data:
{{{{ toYaml .Values.config.data | indent 2 }}}}
{{{{- end }}}}
"""
        with open(templates_path / f"configmap-{deployment_name}.yaml", 'w') as f:
            f.write(configmap_template)

    print(f"  [+] Demo chart created: {output_dir}")
    print(f"     [DIR] Chart.yaml, values.yaml, and {len(list(templates_path.glob('*.yaml')))} templates")


def run_demo_mode() -> None:
    """Run demo mode with sample deployments."""
    print("[MASK] Demo Mode: Generating sample charts")
    print("=" * 50)

    deployments = generate_demo_deployments()

    print(f"[BOX] Sample deployments available:")
    display_deployments_menu(deployments)

    print(f"\n[TARGET] Demo Options:")
    print("  1. Create individual charts for each deployment")
    print("  2. Interactive selection (test search/filter)")
    print("  3. Bulk export demo")

    while True:
        choice = input("\nSelect option [1-3]: ").strip()

        if choice == "1":
            # Create all demo charts
            base_dir = "./demo-charts"
            Path(base_dir).mkdir(exist_ok=True)

            for deployment in deployments:
                deployment_name = deployment["name"]
                output_dir = f"{base_dir}/{deployment_name}-chart"
                print(f"\nCreating demo chart: {deployment_name}")
                create_demo_chart(deployment, output_dir)

            print(f"\n[PARTY] Created {len(deployments)} demo charts in {base_dir}/")
            print(f"\n[TOOL] Test with Helm:")
            for deployment in deployments:
                chart_dir = f"{deployment['name']}-chart"
                print(f"  helm template {deployment['name']} {base_dir}/{chart_dir}")
            break

        elif choice == "2":
            # Interactive selection demo
            print(f"\n[SEARCH] Testing search and filter interface...")
            selected = select_deployments_multi(deployments)

            if selected:
                base_dir = "./demo-charts"
                Path(base_dir).mkdir(exist_ok=True)

                for deployment in selected:
                    output_dir = f"{base_dir}/{deployment['name']}-chart"
                    create_demo_chart(deployment, output_dir)

                print(f"\n[+] Created charts for {len(selected)} selected deployments")
            break

        elif choice == "3":
            # Bulk demo
            print(f"\n[ROCKET] Bulk export demo...")
            base_dir = "./demo-charts"
            Path(base_dir).mkdir(exist_ok=True)

            for i, deployment in enumerate(deployments, 1):
                print(f"\n[{i}/{len(deployments)}] {deployment['name']}")
                output_dir = f"{base_dir}/{deployment['name']}-chart"
                create_demo_chart(deployment, output_dir)

            print(f"\n[CHART] Bulk Demo Complete:")
            print(f"[+] Success: {len(deployments)}")
            print(f"[-] Failed: 0")
            break

        else:
            print("Invalid choice. Please enter 1-3.")


def get_deployment_status(deployment_data: Dict[str, Any]) -> str:
    """Get visual status indicator for deployment."""
    ready_replicas = deployment_data.get("ready_replicas", 0)
    total_replicas = deployment_data.get("replicas", 0)

    if total_replicas == 0:
        return "[CIRCLE] Stopped"
    elif ready_replicas == total_replicas:
        return "[+] Ready"
    elif ready_replicas == 0:
        return "[-] Failed"
    elif ready_replicas < total_replicas:
        return "[!] Issue"
    else:
        return "[CYCLE] Scaling"


def interactive_search_filter(deployments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Interactive search and filter interface for deployments."""
    if not deployments:
        print("No deployments available to filter.")
        return deployments

    filtered_deployments = deployments.copy()
    active_filters = {}

    while True:
        print(f"\n[SEARCH] Search & Filter Interface")
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
            print("[+] Enabled secret inclusion due to discovered dependencies")

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


def extract_related_resource_data(resource_type: str, resource_name: str, namespace: str) -> Dict[str, Any]:
    """Extract actual data from a related resource."""
    try:
        cmd = ["kubectl", "get", resource_type, resource_name, "-n", namespace, "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        resource_data = json.loads(result.stdout)

        extracted = {
            "name": resource_name,
            "type": resource_data.get("type", "Opaque") if resource_type == "secret" else None,
            "data": resource_data.get("data", {}),
            "metadata": {
                "labels": resource_data.get("metadata", {}).get("labels", {}),
                "annotations": resource_data.get("metadata", {}).get("annotations", {})
            }
        }

        # For PVCs, capture the spec
        if resource_type == "persistentvolumeclaim":
            extracted["spec"] = resource_data.get("spec", {})
            extracted["status"] = resource_data.get("status", {})

        # For Services, capture the spec
        if resource_type == "service":
            extracted["spec"] = resource_data.get("spec", {})

        return extracted
    except Exception as e:
        print(f"[!]  Failed to extract {resource_type} {resource_name}: {e}")
        return {"name": resource_name, "data": {}}


def find_related_resources_with_data(deployments: List[Dict[str, Any]], namespace: str) -> Dict[str, List[Dict[str, Any]]]:
    """Find ConfigMaps, Secrets, Services, and PVCs related to selected deployments with their actual data."""
    related_resources = {
        "configmaps": [],
        "secrets": [],
        "services": [],
        "persistentvolumeclaims": []
    }

    found_names = {
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
                # Use singular form for kubectl
                kubectl_resource_type = resource_type[:-1] if resource_type.endswith('s') else resource_type

                cmd = ["kubectl", "get", kubectl_resource_type, "-n", namespace, "-o", "json"]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                data = json.loads(result.stdout)

                for item in data.get("items", []):
                    item_metadata = item.get("metadata", {})
                    item_name = item_metadata.get("name", "")
                    item_labels = item_metadata.get("labels", {})

                    # Skip if already found
                    if item_name in found_names[resource_type]:
                        continue

                    # Match by name patterns
                    is_related = False
                    if (deployment_name in item_name or
                        item_name in deployment_name or
                        any(label_value == item_name for label_value in labels.values())):
                        is_related = True

                    # Match by common labels
                    if "app" in labels and labels["app"] in item_labels.get("app", ""):
                        is_related = True

                    if is_related:
                        # Extract the actual resource data
                        resource_data = extract_related_resource_data(kubectl_resource_type, item_name, namespace)
                        if resource_data:
                            related_resources[resource_type].append(resource_data)
                            found_names[resource_type].add(item_name)

        except subprocess.CalledProcessError:
            continue  # Skip if resource type not accessible
        except Exception:
            continue  # Skip on any error

    return related_resources


def find_related_resources(deployments: List[Dict[str, Any]], namespace: str) -> Dict[str, List[str]]:
    """Legacy function - find related resource names only."""
    data_resources = find_related_resources_with_data(deployments, namespace)
    return {k: [res["name"] for res in v] for k, v in data_resources.items()}


def display_dependency_suggestions(deployments: List[Dict[str, Any]], namespace: str) -> Dict[str, List[str]]:
    """Display and let user select related resources."""
    print(f"\n[SEARCH] Scanning for related resources...")
    related = find_related_resources(deployments, namespace)

    selected_resources = {}
    total_found = sum(len(resources) for resources in related.values())

    if total_found == 0:
        print("No related resources found.")
        return {}

    print(f"\nFound {total_found} potentially related resources:")

    for resource_type, resources in related.items():
        if resources:
            print(f"\n[BOX] {resource_type.title()}:")
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

        # Enhanced chart generation for deployments
        if hasattr(self.args, 'selected_deployments') and self.args.selected_deployments:
            self._generate_enhanced_charts()
        else:
            # Update Chart.yaml and values.yaml with actual resource data
            if exported:
                self._update_chart_metadata(exported)
                self._generate_values_yaml(exported)

        if self.args.lint and shutil.which("helm"):
            self._run_helm_lint()

        self._write_summary(exported)

    # ------------------------------------------------------------------
    # Enhanced chart generation
    # ------------------------------------------------------------------
    def _generate_enhanced_charts(self) -> None:
        """Generate enhanced charts with comprehensive deployment details and related resources."""
        print("\n[TOOL] Generating enhanced charts with comprehensive configuration...")

        for deployment in self.args.selected_deployments:
            deployment_name = deployment["name"]
            namespace = self.args.namespace

            print(f"\n[BOX] Processing deployment: {deployment_name}")

            # Extract comprehensive deployment details
            print("  [SEARCH] Extracting deployment configuration...")
            deployment_details = extract_deployment_details(deployment_name, namespace)

            if not deployment_details:
                print(f"  [-] Failed to extract deployment details for {deployment_name}")
                continue

            # Find and extract related resources with their data
            print("  [LINK] Finding related resources...")
            related_resources_with_data = find_related_resources_with_data([deployment], namespace)

            # Count related resources
            total_related = sum(len(resources) for resources in related_resources_with_data.values())
            if total_related > 0:
                print(f"  [PAGE] Found {total_related} related resources")
                for resource_type, resources in related_resources_with_data.items():
                    if resources:
                        print(f"    - {len(resources)} {resource_type}")

            # Create enhanced chart
            chart_output_dir = str(self.chart_path)
            if hasattr(self.args, 'multi_deployment') and self.args.multi_deployment:
                # For multi-deployment, create a combined chart
                chart_output_dir = str(self.chart_path)
            else:
                # For single deployment, use specific directory
                chart_output_dir = str(self.chart_path)

            print(f"  [ART] Creating enhanced Helm chart...")
            create_enhanced_chart(deployment_details, related_resources_with_data, chart_output_dir)

            # Print summary
            print(f"  [+] Enhanced chart created for {deployment_name}")
            print(f"     [CHART] Configuration: {len(deployment_details.get('env', {}))} env vars, "
                  f"{len(deployment_details.get('volumes', []))} volumes, "
                  f"{len(deployment_details.get('containers', []))} containers")

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
        prog="grabby-helm",
        description="Grabby-Helm: Interactive Kubernetes to Helm Chart Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  grabby-helm                          # Interactive mode (default)
  grabby-helm --explore               # Explore deployments and create charts
  grabby-helm --configs               # Manage saved configurations
  grabby-helm --bulk                  # Bulk export entire namespaces
  grabby-helm --demo                  # Demo mode with sample data

STATE FLAGS (select application mode):
  Default behavior is interactive mode if no state flag is provided.
        """)

    # === PRIMARY COMMANDS (State Flags) ===
    command_group = parser.add_argument_group('APPLICATION MODES')

    # Interactive mode (default)
    command_group.add_argument(
        "--explore",
        action="store_true",
        help="Launch interactive deployment explorer and chart creator",
    )

    # Configuration management
    command_group.add_argument(
        "--configs",
        action="store_true",
        help="Manage saved configurations (view, delete, organize)",
    )

    # Bulk operations
    command_group.add_argument(
        "--bulk",
        action="store_true",
        help="Bulk export mode - export entire namespaces or label selections",
    )

    # Demo and testing
    command_group.add_argument(
        "--demo",
        action="store_true",
        help="Demo mode - generate sample charts without cluster access",
    )

    # Debug and diagnostics
    command_group.add_argument(
        "--debug",
        action="store_true",
        help="Debug mode - analyze cluster connectivity and permissions",
    )

    # === MODIFIER FLAGS (modify behavior) ===
    modifier_group = parser.add_argument_group('BEHAVIOR MODIFIERS')

    modifier_group.add_argument(
        "--auto-detect",
        action="store_true",
        help="Automatically detect and configure access scope",
    )

    modifier_group.add_argument(
        "--namespace-restricted",
        action="store_true",
        help="Use namespace-only mode (for restricted environments)",
    )

    modifier_group.add_argument(
        "--offline",
        action="store_true",
        help="Skip cluster connectivity checks",
    )

    modifier_group.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Overwrite existing files without confirmation",
    )

    modifier_group.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip chart creation preview and validation",
    )

    modifier_group.add_argument(
        "--no-interactive",
        action="store_true",
        help="Disable all interactive prompts (use defaults)",
    )

    modifier_group.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed output and logging",
    )

    # === CONFIGURATION OPTIONS ===
    config_group = parser.add_argument_group('CONFIGURATION OPTIONS')

    config_group.add_argument(
        "--namespace",
        metavar="NAME",
        help="Target namespace (default: auto-detect or 'default')",
    )

    config_group.add_argument(
        "--kubeconfig",
        metavar="PATH",
        help="Path to kubeconfig file (default: ~/.kube/config)",
    )

    config_group.add_argument(
        "--context",
        metavar="NAME",
        help="Kubernetes context to use",
    )

    config_group.add_argument(
        "--output",
        metavar="DIR",
        help="Output directory for generated charts",
    )

    config_group.add_argument(
        "--chart-version",
        default="0.1.0",
        help="Chart version to set in Chart.yaml",
    )
    config_group.add_argument(
        "--app-version",
        default="1.0.0",
        help="Application version to set in Chart.yaml",
    )
    config_group.add_argument(
        "--prefix",
        default="",
        help="Prefix to prepend to generated manifest filenames",
    )
    config_group.add_argument(
        "--include-secrets",
        action="store_true",
        help="Include Kubernetes Secret resources in the generated chart",
    )
    config_group.add_argument(
        "--include-service-account-secrets",
        action="store_true",
        help="Also capture service account token secrets (implies --include-secrets)",
    )
    config_group.add_argument(
        "--lint",
        action="store_true",
        help="Run 'helm lint' after generating the chart",
    )
    config_group.add_argument(
        "--selector",
        help="Label selector used to filter resources (e.g. app=my-app)",
    )
    config_group.add_argument(
        "--only",
        nargs="*",
        help="Limit the export to the specified resource kinds",
    )
    config_group.add_argument(
        "--exclude",
        nargs="*",
        help="Exclude specific resource kinds from the export",
    )

    # === LEGACY COMPATIBILITY ===
    legacy_group = parser.add_argument_group('LEGACY COMPATIBILITY (deprecated)')

    # Keep some key legacy arguments for backward compatibility
    legacy_group.add_argument(
        "release",
        nargs='?',
        help="[DEPRECATED] Chart name - use interactive mode instead",
    )

    legacy_group.add_argument(
        "--config-prompt",
        action="store_true",
        help="[DEPRECATED] Use --explore instead",
    )

    legacy_group.add_argument(
        "--interactive",
        action="store_true",
        help="[DEPRECATED] Use --explore instead",
    )

    legacy_group.add_argument(
        "--bulk-namespace",
        metavar="NAMESPACE",
        help="[DEPRECATED] Use --bulk instead",
    )

    legacy_group.add_argument(
        "--demo-mode",
        action="store_true",
        help="[DEPRECATED] Use --demo instead",
    )

    legacy_group.add_argument(
        "--debug-data",
        action="store_true",
        help="[DEPRECATED] Use --debug instead",
    )

    args = parser.parse_args(argv)

    # === POST-PROCESSING AND VALIDATION ===

    # Handle legacy compatibility
    if hasattr(args, 'config_prompt') and args.config_prompt:
        args.explore = True
        print("[DEPRECATED] --config-prompt is deprecated. Use --explore instead.")

    if hasattr(args, 'interactive') and args.interactive:
        args.explore = True
        print("[DEPRECATED] --interactive is deprecated. Use --explore instead.")

    if hasattr(args, 'demo_mode') and args.demo_mode:
        args.demo = True
        print("[DEPRECATED] --demo-mode is deprecated. Use --demo instead.")

    if hasattr(args, 'debug_data') and args.debug_data:
        args.debug = True
        print("[DEPRECATED] --debug-data is deprecated. Use --debug instead.")

    # Map new flags to legacy internal names for compatibility
    args.namespace_only = getattr(args, 'namespace_restricted', False)
    args.skip_cluster_check = getattr(args, 'offline', False)
    args.force = getattr(args, 'force_overwrite', False)
    args.auto_scope = getattr(args, 'auto_detect', False)
    args.output_dir = getattr(args, 'output', './generated-chart')

    # Set default mode if no state flag is provided
    state_flags = [args.explore, args.configs, args.bulk, args.demo, args.debug]
    if not any(state_flags):
        # Default to explore mode (interactive)
        args.explore = True

    # Validate mutually exclusive states
    active_states = sum(state_flags)
    if active_states > 1:
        parser.error("Only one application mode can be active at a time. Use --help for examples.")

    # Set up logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    return args


def perform_startup_scope_detection() -> Dict[str, Any]:
    """Perform automatic scope detection at application startup."""
    print("\n" + "=" * 60)
    print("                AUTO-SCOPE DETECTION")
    print("=" * 60)
    print("Automatically detecting your Kubernetes access permissions...")

    # Detect access scope
    access_info = detect_kubernetes_access_scope()

    # Determine best configuration automatically
    auto_config = {
        "namespace": "default",
        "namespace_only": False,
        "skip_cluster_check": False,
        "detected_capabilities": access_info,
        "confidence": "high"
    }

    # Analysis and automatic decision making
    if access_info["cluster_access"]:
        print("[+] Cluster-level access detected")
        if access_info["available_namespaces"]:
            print(f"[+] Can list namespaces ({len(access_info['available_namespaces'])} found)")

            # Choose best namespace automatically
            accessible_ns = {ns: info for ns, info in access_info["namespace_access"].items()
                           if info.get("accessible", False)}

            if accessible_ns:
                # Pick namespace with most deployments, or default if available
                best_ns = "default"
                max_deployments = 0

                if "default" in accessible_ns and accessible_ns["default"].get("accessible", False):
                    best_ns = "default"
                    max_deployments = accessible_ns["default"].get("deployment_count", 0)

                for ns, info in accessible_ns.items():
                    if info.get("deployment_count", 0) > max_deployments:
                        best_ns = ns
                        max_deployments = info.get("deployment_count", 0)

                auto_config["namespace"] = best_ns
                print(f"[+] Selected namespace: {best_ns} ({max_deployments} deployments)")
            else:
                auto_config["namespace"] = "default"
                print("[!] No accessible namespaces found, using default")
                auto_config["confidence"] = "medium"
        else:
            print("[!] Cannot list namespaces (restricted access)")
            auto_config["namespace_only"] = True
            auto_config["confidence"] = "medium"
    else:
        print("[!] No cluster-level access (namespace-scoped environment)")
        auto_config["namespace_only"] = True
        auto_config["skip_cluster_check"] = True

        # Try to determine current namespace
        accessible_ns = {ns: info for ns, info in access_info["namespace_access"].items()
                        if info.get("accessible", False)}

        if accessible_ns:
            # Use the namespace with most deployments
            best_ns = max(accessible_ns.keys(),
                         key=lambda ns: accessible_ns[ns].get("deployment_count", 0))
            auto_config["namespace"] = best_ns
            count = accessible_ns[best_ns].get("deployment_count", 0)
            print(f"[+] Selected namespace: {best_ns} ({count} deployments)")
        else:
            print("[!] No accessible namespaces detected, using default")
            auto_config["confidence"] = "low"

    # Summary
    print(f"\n>> AUTO-DETECTED CONFIGURATION:")
    print(f"   Namespace: {auto_config['namespace']}")
    print(f"   Mode: {'Namespace-only' if auto_config['namespace_only'] else 'Cluster-aware'}")
    print(f"   Confidence: {auto_config['confidence'].upper()}")

    # Offer to save configuration for future use
    if auto_config["confidence"] in ["high", "medium"]:
        save_choice = prompt_yes_no("\nSave this configuration for future use?", True)
        if save_choice:
            config_name = prompt_optional("Configuration name", f"auto-detected-{auto_config['namespace']}")
            if config_name:
                # Create a configuration suitable for saving
                save_config_data = {
                    "namespace": auto_config["namespace"],
                    "namespace_only": auto_config["namespace_only"],
                    "skip_cluster_check": auto_config["skip_cluster_check"],
                    "selector": "",
                    "output_dir": f"./{auto_config['namespace']}-chart",
                    "release": f"{auto_config['namespace']}-app",
                    "auto_detected": True,
                    "detection_confidence": auto_config["confidence"]
                }
                save_config(config_name, save_config_data)
                print(f"[+] Configuration saved as '{config_name}'")

    return auto_config


def apply_auto_scope_config(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    """Apply auto-detected scope configuration to command line arguments."""

    # Only apply if not explicitly set by user
    if not hasattr(args, 'namespace') or args.namespace == "default":
        args.namespace = config["namespace"]

    if not args.namespace_only:
        args.namespace_only = config["namespace_only"]

    if not args.skip_cluster_check:
        args.skip_cluster_check = config["skip_cluster_check"]

    # Add detected config for later use
    args.auto_detected_config = config

    print(f"\n[+] Applied auto-detected configuration:")
    print(f"    --namespace {args.namespace}")
    if args.namespace_only:
        print(f"    --namespace-only")
    if args.skip_cluster_check:
        print(f"    --skip-cluster-check")


def run_chart_creation_workflow(original_args: argparse.Namespace, skip_cluster_check: bool = False, namespace: str = "default",
                                auto_scope: bool = True) -> None:
    """Run the chart creation workflow with option for multiple charts."""

    # Auto-detect access scope and prompt user for configuration
    if auto_scope:
        print("[SEARCH] Starting Kubernetes access detection...")
        access_info = detect_kubernetes_access_scope()
        scope_config = prompt_for_access_scope(access_info)

        if not scope_config:
            print("Configuration cancelled.")
            return

        # Update parameters based on detected scope
        namespace = scope_config.get("namespace", namespace)
        skip_cluster_check = scope_config.get("skip_cluster_check", skip_cluster_check)

    # Validate prerequisites
    if not validate_prerequisites(skip_cluster_check, namespace):
        print("\n[-] Prerequisites not met. Please install missing tools and try again.")
        print("[TIP] Use --skip-cluster-check to bypass namespace connectivity validation.")
        print(f"[TIP] Use --namespace <name> to specify a different namespace than '{namespace}'.")
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
            args = argparse.Namespace(**vars(original_args))
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
            if selected_deployments and not getattr(args, 'no_preview', False):
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
                print(f"[+] Chart '{args.release}' created successfully!")

                # Ask if user wants to create another chart
                if not prompt_yes_no("\nWould you like to create another chart from a different deployment?", False):
                    break

            except Exception as e:
                logging.error("Chart creation failed: %s", e)
                print(f"\n[SEARCH] Debug info for failed chart creation:")
                print(f"  Chart name: {args.release}")
                print(f"  Output directory: {args.output_dir}")
                print(f"  Namespace: {args.namespace}")
                print(f"  Selector: {args.selector}")

                # Check if config has deployment data
                selected_deployments = config.get('selected_deployments', [])
                if selected_deployments:
                    print(f"  Selected deployments: {len(selected_deployments)}")
                    for dep in selected_deployments:
                        print(f"    - {dep.get('name', 'unknown')}: {dep.get('images', [])}")
                else:
                    print(f"  [!]  No deployment data in config!")

                if not handle_chart_creation_error(e, args.release):
                    break

        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            break
        except Exception as e:
            logging.error("Unexpected error in workflow: %s", e)
            print(f"\n[-] Unexpected error: {e}")
            if not prompt_yes_no("Continue with the workflow?", False):
                break

    if charts_created:
        print(f"\n[PARTY] Successfully created {len(charts_created)} Helm chart(s):")
        for chart in charts_created:
            print(f"  - {chart}")
        print("\nYou can now package and deploy these charts:")
        for chart in charts_created:
            print(f"  helm package ./{chart}-chart")
            print(f"  helm install {chart} ./{chart}-chart")


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Main entry point for Grabby-Helm CLI application."""
    try:
        args = parse_args(argv)

        # Print banner for non-quiet modes
        if not args.no_interactive:
            print_application_banner()

        # Handle auto-detection first if requested
        if args.auto_detect:
            try:
                auto_scope_config = perform_startup_scope_detection()
                apply_auto_scope_config(args, auto_scope_config)
            except KeyboardInterrupt:
                print("\nAuto-detection cancelled.")
                return
            except Exception as e:
                print(f"Auto-detection failed: {e}")
                print("Continuing with manual configuration...")

        # Route to appropriate application mode
        if args.debug:
            run_debug_mode(args)
        elif args.demo:
            run_demo_mode(args)
        elif args.configs:
            run_config_management_mode(args)
        elif args.bulk:
            run_bulk_export_mode(args)
        elif args.explore:
            run_interactive_mode(args)
        else:
            # This should not happen due to default setting, but fallback to interactive
            run_interactive_mode(args)

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        return
    except Exception as e:
        if args.verbose if 'args' in locals() else False:
            logging.error("Application failed: %s", e, exc_info=True)
        else:
            print(f"Error: {e}")
        return


def print_application_banner() -> None:
    """Print the application banner."""
    print()
    print("=" * 60)
    print("             GRABBY-HELM")
    print("    Kubernetes to Helm Chart Converter")
    print("=" * 60)


def run_debug_mode(args: argparse.Namespace) -> None:
    """Run debug and diagnostics mode."""
    print("\n>> DEBUG & DIAGNOSTICS MODE")
    print("=" * 40)

    namespace = args.namespace or "default"
    debug_cluster_data(namespace)


def run_demo_mode(args: argparse.Namespace) -> None:
    """Run demo mode with sample data."""
    print("\n>> DEMO MODE")
    print("=" * 40)
    print("Generating sample charts with demo data...")

    # Use the existing demo mode function but adapt it
    run_demo_mode_legacy()


def run_config_management_mode(args: argparse.Namespace) -> None:
    """Run configuration management mode."""
    print("\n>> CONFIGURATION MANAGEMENT")
    print("=" * 40)

    # Launch directly into config management
    changes_made = manage_configs_menu()
    if changes_made:
        print("\nConfiguration changes saved.")
    else:
        print("\nNo changes made.")


def run_bulk_export_mode(args: argparse.Namespace) -> None:
    """Run bulk export mode."""
    print("\n>> BULK EXPORT MODE")
    print("=" * 40)

    # Check for legacy bulk arguments first
    if hasattr(args, 'bulk_namespace') and args.bulk_namespace:
        print(f"Bulk exporting namespace: {args.bulk_namespace}")
        bulk_export_namespace(args.bulk_namespace)
        return

    # Interactive bulk mode
    print("Select bulk export type:")
    print("  1. Export entire namespace")
    print("  2. Export by label selector")
    print("  3. Export multiple namespaces")

    try:
        choice = input("\nEnter choice [1-3]: ").strip()

        if choice == "1":
            namespace = args.namespace or prompt_required("Target namespace")
            bulk_export_namespace(namespace)
        elif choice == "2":
            namespace = args.namespace or prompt_required("Target namespace")
            selector = prompt_required("Label selector (e.g., app=frontend)")
            bulk_export_by_selector(selector, namespace)
        elif choice == "3":
            print("Multi-namespace export coming soon!")
        else:
            print("Invalid choice.")
    except (KeyboardInterrupt, EOFError):
        print("\nBulk export cancelled.")


def run_interactive_mode(args: argparse.Namespace) -> None:
    """Run interactive exploration and chart creation mode."""
    print("\n>> INTERACTIVE MODE")
    print("=" * 40)

    # Use the existing interactive workflow
    namespace = args.namespace or "default"
    skip_check = args.offline or args.namespace_restricted
    auto_scope = args.auto_detect

    if args.namespace_restricted:
        print("[*] Namespace-restricted mode enabled")
        auto_scope = False
    elif args.namespace and args.namespace != "default":
        print(f"[*] Using specified namespace: {namespace}")
        auto_scope = False

    run_chart_creation_workflow(args, skip_check, namespace, auto_scope)


def run_demo_mode_legacy() -> None:
    """Legacy demo mode implementation."""
    print("Creating demo chart with sample data...")

    demo_deployment = {
        "name": "demo-app",
        "namespace": "demo",
        "replicas": 3,
        "ready_replicas": 3,
        "images": ["nginx:1.21", "redis:7-alpine"],
        "labels": {"app": "demo-app", "version": "v1.0"},
        "creation_time": "2024-01-01T00:00:00Z"
    }

    output_dir = "./demo-chart"
    try:
        create_demo_chart(demo_deployment, output_dir)
        print(f"Demo chart created: {output_dir}")
        print("\nDemo files:")
        from pathlib import Path
        chart_path = Path(output_dir)
        if chart_path.exists():
            for file in chart_path.rglob("*.yaml"):
                print(f"  {file}")
        print("\nDemo mode completed!")
    except Exception as e:
        print(f"Demo creation failed: {e}")
        print("Demo mode uses sample data - no cluster connection required.")


if __name__ == "__main__":  # pragma: no cover
    main()
