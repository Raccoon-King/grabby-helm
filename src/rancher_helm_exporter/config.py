"""Configuration management for the rancher-helm-exporter."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .constants import (
    DEFAULT_APP_VERSION,
    DEFAULT_CHART_VERSION,
    DEFAULT_NAMESPACE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_RETRY_BACKOFF_BASE,
    SUPPORTED_RESOURCES,
)
from .types import ExporterConfig, RetryConfig


@dataclass
class ExportConfig:
    """Configuration for export operations."""
    
    # Basic settings
    release_name: str
    namespace: str = DEFAULT_NAMESPACE
    output_dir: str = DEFAULT_OUTPUT_DIR
    
    # Filtering
    selector: Optional[str] = None
    only: Optional[Sequence[str]] = None
    exclude: Optional[Sequence[str]] = None
    
    # Secret handling
    include_secrets: bool = False
    include_service_account_secrets: bool = False
    secret_mode: str = "include"  # include, skip, encrypt, external-ref
    
    # kubectl settings
    kubeconfig: Optional[str] = None
    context: Optional[str] = None
    
    # Output settings
    prefix: str = ""
    force: bool = False
    lint: bool = False
    
    # Chart metadata
    chart_version: str = DEFAULT_CHART_VERSION
    app_version: str = DEFAULT_APP_VERSION
    
    # Performance settings
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_RETRY_COUNT
    backoff_base: float = DEFAULT_RETRY_BACKOFF_BASE
    parallel_exports: bool = False
    max_workers: int = 4
    
    # Progress and logging
    verbose: bool = False
    progress_enabled: bool = True
    use_rich_progress: bool = True
    silent_progress: bool = False
    
    # Interactive mode
    interactive: bool = False
    
    # Test chart options
    create_test_chart: bool = False
    test_suffix: str = "test"
    test_chart_dir: Optional[str] = None
    
    # Resource selection (set by interactive mode)
    selection_names: Optional[Dict[str, set[str]]] = None


@dataclass
class ResourceCleaningConfig:
    """Configuration for resource cleaning rules."""
    
    # Custom fields to remove from metadata
    additional_metadata_fields: List[str] = field(default_factory=list)
    
    # Custom annotation patterns to remove
    annotation_patterns_to_remove: List[str] = field(default_factory=list)
    
    # Custom label patterns to remove
    label_patterns_to_remove: List[str] = field(default_factory=list)
    
    # Resource-specific cleaning rules
    service_fields_to_clean: List[str] = field(default_factory=list)
    pvc_fields_to_clean: List[str] = field(default_factory=list)
    
    # Whether to clean namespace references
    remove_namespace_references: bool = True


@dataclass
class GlobalConfig:
    """Global configuration for the exporter."""
    
    # Supported resources (can be customized)
    supported_resources: List[str] = field(default_factory=lambda: list(SUPPORTED_RESOURCES))
    
    # Resource cleaning configuration
    cleaning: ResourceCleaningConfig = field(default_factory=ResourceCleaningConfig)
    
    # Retry configuration
    retry: RetryConfig = field(default_factory=lambda: {
        "max_retries": DEFAULT_RETRY_COUNT,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "backoff_base": DEFAULT_RETRY_BACKOFF_BASE,
        "backoff_max": 60.0,
    })
    
    # Progress configuration
    progress_update_interval: float = 0.1
    progress_log_interval: int = 10
    
    # Feature flags
    enable_rich_progress: bool = True
    enable_validation: bool = True
    enable_templating: bool = False
    
    # Paths (Linux-focused)
    config_file_paths: List[str] = field(default_factory=lambda: [
        "~/.config/rancher-helm-exporter/config.yaml",
        "~/.rancher-helm-exporter.yaml",
        "/etc/rancher-helm-exporter/config.yaml",
        "./.rancher-helm-exporter.yaml",
        "./config.yaml",
    ])


class ConfigLoader:
    """Loads configuration from various sources."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def load_config(
        self,
        config_file: Optional[str] = None,
        global_config: Optional[GlobalConfig] = None,
    ) -> GlobalConfig:
        """
        Load configuration from file and environment.
        
        Args:
            config_file: Specific config file to load
            global_config: Base configuration to extend
            
        Returns:
            Loaded global configuration
        """
        if global_config is None:
            global_config = GlobalConfig()
        
        # Try to load from file
        config_data = self._load_from_file(config_file, global_config.config_file_paths)
        
        if config_data:
            return self._merge_config_data(global_config, config_data)
        
        return global_config
    
    def _load_from_file(
        self,
        config_file: Optional[str],
        search_paths: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Load configuration from YAML file."""
        paths_to_try = []
        
        if config_file:
            paths_to_try.append(config_file)
        else:
            paths_to_try.extend(search_paths)
        
        for path_str in paths_to_try:
            try:
                path = Path(path_str).expanduser()
                if path.exists():
                    return self._parse_config_file(path)
            except Exception as e:
                self.logger.debug("Failed to load config from %s: %s", path_str, e)
        
        return None
    
    def _parse_config_file(self, path: Path) -> Dict[str, Any]:
        """Parse a YAML configuration file."""
        try:
            import yaml
            
            with path.open('r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not isinstance(data, dict):
                self.logger.warning("Config file %s does not contain a dictionary", path)
                return {}
            
            self.logger.info("Loaded configuration from: %s", path)
            return data
            
        except ImportError:
            self.logger.warning("PyYAML not available, cannot load config file: %s", path)
            return {}
        
        except Exception as e:
            self.logger.error("Failed to parse config file %s: %s", path, e)
            return {}
    
    def _merge_config_data(self, base_config: GlobalConfig, config_data: Dict[str, Any]) -> GlobalConfig:
        """Merge configuration data into base config."""
        # This is a simplified merge - a full implementation would handle
        # nested merging of dataclass fields
        
        try:
            # Update supported resources
            if "supported_resources" in config_data:
                base_config.supported_resources = config_data["supported_resources"]
            
            # Update retry configuration
            if "retry" in config_data and isinstance(config_data["retry"], dict):
                retry_data = config_data["retry"]
                base_config.retry.update(retry_data)
            
            # Update cleaning configuration
            if "cleaning" in config_data and isinstance(config_data["cleaning"], dict):
                cleaning_data = config_data["cleaning"]
                if "additional_metadata_fields" in cleaning_data:
                    base_config.cleaning.additional_metadata_fields = cleaning_data["additional_metadata_fields"]
                if "annotation_patterns_to_remove" in cleaning_data:
                    base_config.cleaning.annotation_patterns_to_remove = cleaning_data["annotation_patterns_to_remove"]
            
            # Update feature flags
            feature_flags = ["enable_rich_progress", "enable_validation", "enable_templating"]
            for flag in feature_flags:
                if flag in config_data:
                    setattr(base_config, flag, config_data[flag])
            
            self.logger.debug("Merged configuration data successfully")
            
        except Exception as e:
            self.logger.error("Failed to merge configuration data: %s", e)
        
        return base_config


class ConfigValidator:
    """Validates configuration settings."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_export_config(self, config: ExportConfig) -> List[str]:
        """
        Validate export configuration.
        
        Args:
            config: Export configuration to validate
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Validate required fields
        if not config.release_name:
            errors.append("Release name is required")
        elif not self._is_valid_helm_name(config.release_name):
            errors.append("Release name must be a valid Helm release name")
        
        if not config.namespace:
            errors.append("Namespace is required")
        elif not self._is_valid_k8s_name(config.namespace):
            errors.append("Namespace must be a valid Kubernetes namespace name")
        
        # Validate paths
        if config.kubeconfig:
            kubeconfig_path = Path(config.kubeconfig).expanduser()
            if not kubeconfig_path.exists():
                errors.append(f"Kubeconfig file not found: {config.kubeconfig}")
        
        # Validate resource filters
        if config.only:
            invalid_resources = set(config.only) - set(SUPPORTED_RESOURCES)
            if invalid_resources:
                errors.append(f"Unsupported resource types in --only: {', '.join(invalid_resources)}")
        
        if config.exclude:
            invalid_resources = set(config.exclude) - set(SUPPORTED_RESOURCES)
            if invalid_resources:
                errors.append(f"Unsupported resource types in --exclude: {', '.join(invalid_resources)}")
        
        # Validate secret mode
        valid_secret_modes = ["include", "skip", "encrypt", "external-ref"]
        if config.secret_mode not in valid_secret_modes:
            errors.append(f"Invalid secret mode: {config.secret_mode}. Must be one of: {', '.join(valid_secret_modes)}")
        
        # Validate numeric settings
        if config.timeout <= 0:
            errors.append("Timeout must be positive")
        
        if config.max_retries < 0:
            errors.append("Max retries cannot be negative")
        
        if config.backoff_base <= 1.0:
            errors.append("Backoff base must be greater than 1.0")
        
        if config.max_workers <= 0:
            errors.append("Max workers must be positive")
        
        if errors:
            self.logger.warning("Configuration validation failed: %s", "; ".join(errors))
        
        return errors
    
    def validate_global_config(self, config: GlobalConfig) -> List[str]:
        """
        Validate global configuration.
        
        Args:
            config: Global configuration to validate
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Validate supported resources
        if not config.supported_resources:
            errors.append("At least one supported resource type must be configured")
        
        # Validate retry configuration
        retry_config = config.retry
        if retry_config.get("max_retries", 0) < 0:
            errors.append("max_retries cannot be negative")
        
        if retry_config.get("timeout_seconds", 0) <= 0:
            errors.append("timeout_seconds must be positive")
        
        if retry_config.get("backoff_base", 1.0) <= 1.0:
            errors.append("backoff_base must be greater than 1.0")
        
        # Validate intervals
        if config.progress_update_interval <= 0:
            errors.append("progress_update_interval must be positive")
        
        if config.progress_log_interval <= 0:
            errors.append("progress_log_interval must be positive")
        
        if errors:
            self.logger.warning("Global configuration validation failed: %s", "; ".join(errors))
        
        return errors
    
    def _is_valid_helm_name(self, name: str) -> bool:
        """Check if a name is valid for Helm."""
        import re
        # Simplified validation - Helm names should be lowercase alphanumeric with hyphens
        return bool(re.match(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$', name)) and len(name) <= 53
    
    def _is_valid_k8s_name(self, name: str) -> bool:
        """Check if a name is valid for Kubernetes."""
        import re
        # Simplified validation for Kubernetes names
        return bool(re.match(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$', name)) and len(name) <= 63


def create_default_config() -> GlobalConfig:
    """Create a default global configuration."""
    return GlobalConfig()


def load_config_from_args(args) -> ExportConfig:
    """Convert argparse arguments to ExportConfig."""
    return ExportConfig(
        release_name=args.release,
        namespace=args.namespace,
        output_dir=args.output_dir,
        selector=args.selector,
        only=args.only,
        exclude=args.exclude,
        include_secrets=args.include_secrets,
        include_service_account_secrets=args.include_service_account_secrets,
        kubeconfig=args.kubeconfig,
        context=args.context,
        prefix=args.prefix,
        force=args.force,
        lint=args.lint,
        chart_version=args.chart_version,
        app_version=args.app_version,
        verbose=args.verbose,
        interactive=args.interactive,
        create_test_chart=getattr(args, 'create_test_chart', False),
        test_suffix=getattr(args, 'test_suffix', 'test'),
        test_chart_dir=getattr(args, 'test_chart_dir', None),
        selection_names=getattr(args, 'selection_names', None),
    )