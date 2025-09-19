"""Interactive configuration prompting and persistence for rancher-helm-exporter."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class ConfigManager:
    """Manages saved configurations for the exporter."""

    def __init__(self, config_dir: Optional[str] = None):
        self.logger = logging.getLogger(__name__)

        if config_dir:
            self.config_dir = Path(config_dir).expanduser()
        else:
            self.config_dir = Path.home() / ".config" / "rancher-helm-exporter"

        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.configs_file = self.config_dir / "saved_configs.json"

    def save_config(self, name: str, config: Dict[str, Any]) -> None:
        """Save a configuration with a given name."""
        configs = self.load_all_configs()

        # Add metadata
        config_with_meta = {
            "config": config,
            "saved_at": datetime.now().isoformat(),
            "name": name
        }

        configs[name] = config_with_meta

        try:
            with self.configs_file.open('w', encoding='utf-8') as f:
                json.dump(configs, f, indent=2)
            self.logger.info("Saved configuration: %s", name)
        except Exception as e:
            self.logger.error("Failed to save config %s: %s", name, e)

    def load_config(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a specific configuration by name."""
        configs = self.load_all_configs()
        config_entry = configs.get(name)
        if config_entry:
            return config_entry.get("config")
        return None

    def load_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load all saved configurations."""
        if not self.configs_file.exists():
            return {}

        try:
            with self.configs_file.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error("Failed to load configs: %s", e)
            return {}

    def list_configs(self) -> List[str]:
        """List all saved configuration names."""
        configs = self.load_all_configs()
        return sorted(configs.keys())

    def delete_config(self, name: str) -> bool:
        """Delete a saved configuration."""
        configs = self.load_all_configs()
        if name in configs:
            del configs[name]
            try:
                with self.configs_file.open('w', encoding='utf-8') as f:
                    json.dump(configs, f, indent=2)
                self.logger.info("Deleted configuration: %s", name)
                return True
            except Exception as e:
                self.logger.error("Failed to delete config %s: %s", name, e)
        return False

    def get_last_used_config(self) -> Optional[Dict[str, Any]]:
        """Get the most recently saved configuration."""
        configs = self.load_all_configs()
        if not configs:
            return None

        # Find the most recent config by saved_at timestamp
        latest_config = None
        latest_time = None

        for config_entry in configs.values():
            saved_at = config_entry.get("saved_at")
            if saved_at:
                if latest_time is None or saved_at > latest_time:
                    latest_time = saved_at
                    latest_config = config_entry.get("config")

        return latest_config


class InteractiveConfigPrompt:
    """Handles interactive prompting for configuration values."""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.logger = logging.getLogger(__name__)
        self.config_manager = config_manager or ConfigManager()

    def prompt_for_config(self) -> Dict[str, Any]:
        """Interactive prompt for configuration values."""
        print("Rancher Helm Exporter - Interactive Configuration")
        print("=" * 50)

        # Check for existing configs
        if self._offer_existing_configs():
            return {}  # User selected existing config, handled elsewhere

        print("\nConfiguring new export...")
        config = {}

        # Required fields
        config['release'] = self._prompt_required("Release name (Helm chart name)", "my-app")
        config['namespace'] = self._prompt_optional("Kubernetes namespace", "default")

        # Optional but common fields
        config['output_dir'] = self._prompt_optional("Output directory", "./generated-chart")
        config['selector'] = self._prompt_optional("Label selector (e.g., app=my-app)", None)

        # Advanced options
        if self._prompt_yes_no("Configure advanced options?", False):
            config.update(self._prompt_advanced_options())

        # Secret handling
        if self._prompt_yes_no("Include secrets?", False):
            config['include_secrets'] = True
            if self._prompt_yes_no("Include service account secrets?", False):
                config['include_service_account_secrets'] = True

        # Test chart
        if self._prompt_yes_no("Create test chart alongside main chart?", False):
            config['create_test_chart'] = True
            config['test_suffix'] = self._prompt_optional("Test suffix", "test")

        # Validation and linting
        config['lint'] = self._prompt_yes_no("Run helm lint after generation?", True)
        config['force'] = self._prompt_yes_no("Overwrite output directory if it exists?", False)

        # Save this config
        if self._prompt_yes_no("Save this configuration for future use?", True):
            config_name = self._prompt_required("Configuration name", f"config-{datetime.now().strftime('%Y%m%d-%H%M')}")
            self.config_manager.save_config(config_name, config)

        return config

    def _offer_existing_configs(self) -> bool:
        """Offer to use existing configurations."""
        configs = self.config_manager.list_configs()

        if not configs:
            return False

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
                    config = self.config_manager.load_config(selected_config)
                    if config:
                        print(f"\nUsing configuration: {selected_config}")
                        self._display_config_summary(config)
                        # Set the config as the current one to use
                        self._apply_config_to_args(config)
                        return True
                elif choice_num == len(configs) + 1:
                    # User wants to create new config
                    return False
                else:
                    print(f"Invalid choice. Please enter 1-{len(configs) + 1}")
            except ValueError:
                print("Please enter a valid number")

        return False

    def _prompt_required(self, prompt: str, default: Optional[str] = None) -> str:
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

    def _prompt_optional(self, prompt: str, default: Optional[str] = None) -> Optional[str]:
        """Prompt for an optional value."""
        if default:
            value = input(f"{prompt} [{default}]: ").strip()
            return value if value else default
        else:
            value = input(f"{prompt} (optional): ").strip()
            return value if value else None

    def _prompt_yes_no(self, prompt: str, default: bool = False) -> bool:
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

    def _prompt_advanced_options(self) -> Dict[str, Any]:
        """Prompt for advanced configuration options."""
        config = {}

        print("\nAdvanced Options:")

        # Kubectl options
        kubeconfig = self._prompt_optional("Custom kubeconfig path", None)
        if kubeconfig:
            config['kubeconfig'] = kubeconfig

        context = self._prompt_optional("Kubernetes context", None)
        if context:
            config['context'] = context

        # Resource filtering
        only_resources = self._prompt_optional("Only export these resource types (comma-separated)", None)
        if only_resources:
            config['only'] = [r.strip() for r in only_resources.split(',')]

        exclude_resources = self._prompt_optional("Exclude these resource types (comma-separated)", None)
        if exclude_resources:
            config['exclude'] = [r.strip() for r in exclude_resources.split(',')]

        # Chart metadata
        chart_version = self._prompt_optional("Chart version", "0.1.0")
        if chart_version:
            config['chart_version'] = chart_version

        app_version = self._prompt_optional("App version", "1.0.0")
        if app_version:
            config['app_version'] = app_version

        # File prefix
        prefix = self._prompt_optional("Filename prefix for manifests", None)
        if prefix:
            config['prefix'] = prefix

        return config

    def _display_config_summary(self, config: Dict[str, Any]) -> None:
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

    def _apply_config_to_args(self, config: Dict[str, Any]) -> None:
        """Apply configuration to command line arguments."""
        # This would typically modify a global args object or return values
        # For now, we'll store it in a way that can be retrieved
        self._selected_config = config

    def get_selected_config(self) -> Optional[Dict[str, Any]]:
        """Get the configuration selected by the user."""
        return getattr(self, '_selected_config', None)


def run_interactive_config() -> Dict[str, Any]:
    """Run the interactive configuration prompt."""
    config_manager = ConfigManager()
    prompt = InteractiveConfigPrompt(config_manager)

    return prompt.prompt_for_config()


def apply_config_to_namespace(args, config: Dict[str, Any]) -> None:
    """Apply configuration dictionary to an argparse namespace."""
    for key, value in config.items():
        if hasattr(args, key):
            setattr(args, key, value)
        elif key == 'release':
            # Map 'release' to the positional argument
            args.release = value