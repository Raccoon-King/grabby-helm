"""Main exporter class that orchestrates the export process."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set

from .chart_generator import ChartGenerator
from .config import ExportConfig, GlobalConfig
from .constants import SUPPORTING_RESOURCES, WORKLOAD_RESOURCES
from .interactive_test_prompt import prompt_for_test_chart_options
from .kubectl import KubectlClient, KubectlResourceCollector
from .manifest_cleaner import ManifestCleaner, ManifestValidator, SecretHandler
from .progress import TimedProgressTracker, create_progress_tracker
from .test_chart_generator import TestChartGenerator
from .types import ExportError, ExportResult, K8sObject, K8sObjectList, ResourceFilter
from .utils import ManifestTraverser


class HelmChartExporter:
    """Main exporter class that orchestrates the Helm chart generation process."""
    
    def __init__(
        self,
        export_config: ExportConfig,
        global_config: Optional[GlobalConfig] = None,
    ):
        self.config = export_config
        self.global_config = global_config or GlobalConfig()
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.kubectl_client = KubectlClient(
            kubeconfig=export_config.kubeconfig,
            context=export_config.context,
            timeout=export_config.timeout,
            max_retries=export_config.max_retries,
            backoff_base=export_config.backoff_base,
        )
        
        self.resource_collector = KubectlResourceCollector(self.kubectl_client)
        self.manifest_cleaner = ManifestCleaner()
        self.manifest_validator = ManifestValidator()
        self.secret_handler = SecretHandler(mode=export_config.secret_mode)
        
        self.chart_generator = ChartGenerator(
            release_name=export_config.release_name,
            chart_version=export_config.chart_version,
            app_version=export_config.app_version,
        )
        
        # Initialize progress tracking
        self.progress_tracker = create_progress_tracker(
            enabled=export_config.progress_enabled,
            use_rich=export_config.use_rich_progress,
            silent=export_config.silent_progress,
        )
        
        self.timed_tracker = TimedProgressTracker(self.progress_tracker)
    
    def export(self) -> ExportResult:
        """
        Execute the complete export process.
        
        Returns:
            Export result with statistics and output path
            
        Raises:
            ExportError: If export fails
        """
        try:
            self.logger.info("Starting Helm chart export for release: %s", self.config.release_name)
            self._validate_prerequisites()
            
            # Create chart structure
            chart_path = self._create_chart_structure()
            
            # Collect resources
            all_resources = self._collect_resources()
            
            if not all_resources:
                raise ExportError("No resources found matching the specified criteria")
            
            # Process and export resources
            export_results = self._process_and_export_resources(all_resources, chart_path)
            
            # Generate summary and validate
            self._finalize_chart(export_results, chart_path)
            
            # Handle test chart creation
            test_results = self._handle_test_chart_creation(all_resources)
            
            result = ExportResult(
                success=True,
                exported_count=len(export_results),
                failed_count=0,
                errors=[],
                output_path=str(chart_path),
            )
            
            self.logger.info(
                "Export completed successfully: %d resources exported to %s",
                result["exported_count"],
                result["output_path"],
            )
            
            if test_results:
                self.logger.info(
                    "Test chart created successfully: %d test resources exported",
                    len(test_results),
                )
            
            self.timed_tracker.finish()
            return result
            
        except Exception as e:
            self.logger.error("Export failed: %s", e)
            raise ExportError(f"Export failed: {e}") from e
    
    def _validate_prerequisites(self) -> None:
        """Validate that prerequisites are met."""
        self.logger.debug("Validating prerequisites")
        
        # Check kubectl availability
        if not shutil.which("kubectl"):
            raise ExportError("kubectl command not found in PATH")
        
        # Check cluster connectivity
        if not self.kubectl_client.check_connection():
            raise ExportError("Cannot connect to Kubernetes cluster")
        
        # Validate namespace access
        try:
            namespaces = self.kubectl_client.get_namespaces()
            if self.config.namespace not in namespaces:
                self.logger.warning(
                    "Namespace '%s' not found in cluster. Available: %s",
                    self.config.namespace,
                    ", ".join(namespaces[:5]),
                )
        except Exception as e:
            self.logger.warning("Could not validate namespace access: %s", e)
        
        # Check resource access
        access_results = self.resource_collector.validate_access(
            self._get_resource_types_to_process(),
            self.config.namespace,
        )
        
        inaccessible = [res for res, accessible in access_results.items() if not accessible]
        if inaccessible:
            self.logger.warning(
                "No access to resource types: %s",
                ", ".join(inaccessible),
            )
    
    def _create_chart_structure(self) -> Path:
        """Create the Helm chart directory structure."""
        self.logger.info("Creating chart structure at: %s", self.config.output_dir)
        
        return self.chart_generator.create_chart_structure(
            self.config.output_dir,
            force=self.config.force,
        )
    
    def _collect_resources(self) -> Dict[str, K8sObjectList]:
        """Collect all resources from the cluster."""
        self.timed_tracker.start_phase("Resource Collection")
        
        resource_types = self._get_resource_types_to_process()
        
        self.logger.info(
            "Collecting resources from namespace '%s': %s",
            self.config.namespace,
            ", ".join(resource_types),
        )
        
        filters = ResourceFilter(
            namespace=self.config.namespace,
            selector=self.config.selector,
            names=None,  # Will be set by selection if interactive mode was used
        )
        
        all_resources = self.resource_collector.collect_resources(resource_types, filters)
        
        # Apply selection filters if from interactive mode
        if self.config.selection_names:
            all_resources = self._apply_selection_filters(all_resources)
        
        # Filter secrets based on configuration
        all_resources = self._filter_secrets(all_resources)
        
        total_count = sum(len(resources) for resources in all_resources.values())
        self.logger.info("Collected %d total resources", total_count)
        
        self.timed_tracker.end_phase("Resource Collection")
        return all_resources
    
    def _process_and_export_resources(
        self,
        all_resources: Dict[str, K8sObjectList],
        chart_path: Path,
    ) -> List[ExportResult]:
        """Process and export all collected resources."""
        self.timed_tracker.start_phase("Resource Processing")
        
        total_resources = sum(len(resources) for resources in all_resources.values())
        export_results = []
        processed = 0
        
        self.progress_tracker.update(0, total_resources, "Processing resources...")
        
        for resource_type, resources in all_resources.items():
            self.logger.debug("Processing %d %s resources", len(resources), resource_type)
            
            for resource in resources:
                try:
                    # Clean the manifest
                    cleaned_manifest = self.manifest_cleaner.clean_manifest(resource)
                    
                    # Handle secrets specially
                    if resource_type == "secrets":
                        cleaned_manifest = self.secret_handler.process_secret(cleaned_manifest)
                        if not cleaned_manifest:  # Secret was skipped
                            processed += 1
                            continue
                    
                    # Validate if enabled
                    if self.global_config.enable_validation:
                        issues = self.manifest_validator.validate_manifest(cleaned_manifest)
                        if issues:
                            self.logger.warning(
                                "Validation issues for %s/%s: %s",
                                resource_type,
                                ManifestTraverser.get_manifest_name(resource),
                                "; ".join(issues),
                            )
                    
                    # Write to chart
                    result = self.chart_generator.write_manifest(
                        cleaned_manifest,
                        str(chart_path),
                        prefix=self.config.prefix,
                    )
                    
                    export_results.append(result)
                    processed += 1
                    
                    self.progress_tracker.update(
                        processed,
                        total_resources,
                        f"Exported {result.kind}/{result.name}",
                    )
                    
                except Exception as e:
                    name = ManifestTraverser.get_manifest_name(resource)
                    self.logger.error(
                        "Failed to export %s/%s: %s",
                        resource_type,
                        name,
                        e,
                    )
                    processed += 1
                    continue
        
        self.timed_tracker.end_phase("Resource Processing")
        return export_results
    
    def _finalize_chart(self, export_results: List[ExportResult], chart_path: Path) -> None:
        """Finalize the chart by creating summary and running lint."""
        self.timed_tracker.start_phase("Chart Finalization")
        
        # Write export summary
        self.chart_generator.write_summary(export_results, chart_path)
        
        # Run helm lint if requested
        if self.config.lint:
            self.logger.info("Running helm lint on generated chart")
            success = self.chart_generator.lint_chart(chart_path)
            if not success:
                self.logger.warning("Helm lint reported issues - check the chart before deployment")
        
        self.timed_tracker.end_phase("Chart Finalization")
    
    def _get_resource_types_to_process(self) -> List[str]:
        """Get the list of resource types to process based on configuration."""
        resource_types = set(self.global_config.supported_resources)
        
        if self.config.only:
            resource_types = resource_types.intersection(set(self.config.only))
        
        if self.config.exclude:
            resource_types = resource_types.difference(set(self.config.exclude))
        
        return sorted(list(resource_types))
    
    def _apply_selection_filters(
        self,
        all_resources: Dict[str, K8sObjectList],
    ) -> Dict[str, K8sObjectList]:
        """Apply selection filters from interactive mode."""
        if not self.config.selection_names:
            return all_resources
        
        filtered_resources = {}
        
        for resource_type, resources in all_resources.items():
            selected_names = self.config.selection_names.get(resource_type)
            if selected_names:
                filtered = [
                    resource for resource in resources
                    if ManifestTraverser.get_manifest_name(resource) in selected_names
                ]
                if filtered:
                    filtered_resources[resource_type] = filtered
        
        return filtered_resources
    
    def _filter_secrets(self, all_resources: Dict[str, K8sObjectList]) -> Dict[str, K8sObjectList]:
        """Filter secrets based on configuration."""
        if "secrets" not in all_resources:
            return all_resources
        
        secrets = all_resources["secrets"]
        
        if not self.config.include_secrets:
            # Remove all secrets unless explicitly selected
            if self.config.selection_names and "secrets" in self.config.selection_names:
                # Keep only explicitly selected secrets
                selected_names = self.config.selection_names["secrets"]
                filtered_secrets = [
                    secret for secret in secrets
                    if ManifestTraverser.get_manifest_name(secret) in selected_names
                ]
                if filtered_secrets:
                    all_resources["secrets"] = filtered_secrets
                else:
                    del all_resources["secrets"]
            else:
                # Remove all secrets
                del all_resources["secrets"]
            return all_resources
        
        # Filter service account secrets if not explicitly included
        if not self.config.include_service_account_secrets:
            from .constants import DEFAULT_SECRET_TYPES_TO_SKIP
            
            filtered_secrets = []
            for secret in secrets:
                secret_type = secret.get("type")
                if secret_type not in DEFAULT_SECRET_TYPES_TO_SKIP:
                    filtered_secrets.append(secret)
                else:
                    self.logger.debug(
                        "Skipping service account secret: %s",
                        ManifestTraverser.get_manifest_name(secret),
                    )
            
            if filtered_secrets:
                all_resources["secrets"] = filtered_secrets
            else:
                del all_resources["secrets"]
        
        return all_resources
    
    def _handle_test_chart_creation(
        self,
        all_resources: Dict[str, K8sObjectList],
    ) -> Optional[List[ExportResult]]:
        """Handle test chart creation if requested."""
        # Check if test chart creation is enabled
        if not self.config.create_test_chart:
            # Check if we should prompt for test chart creation in interactive mode
            if self.config.interactive:
                test_options = prompt_for_test_chart_options(
                    self.config.release_name,
                    self.config.output_dir,
                    interactive=True
                )
                
                if not test_options.create_test_chart:
                    return None
                
                # Update config with user selections
                self.config.create_test_chart = True
                self.config.test_suffix = test_options.test_suffix
                self.config.test_chart_dir = test_options.test_chart_dir
            else:
                return None
        
        try:
            self.timed_tracker.start_phase("Test Chart Generation")
            
            # Prepare test chart directory
            test_chart_dir = self.config.test_chart_dir
            if not test_chart_dir:
                test_chart_dir = f"{self.config.output_dir}-{self.config.test_suffix}"
            
            # Collect all manifests for test chart
            all_manifests = []
            for resources in all_resources.values():
                all_manifests.extend(resources)
            
            if not all_manifests:
                self.logger.warning("No resources available for test chart creation")
                return None
            
            # Clean manifests for test chart
            cleaned_manifests = []
            for manifest in all_manifests:
                try:
                    cleaned_manifest = self.manifest_cleaner.clean_manifest(manifest)
                    
                    # Handle secrets specially
                    resource_type = cleaned_manifest.get("kind", "").lower() + "s"
                    if resource_type == "secrets":
                        cleaned_manifest = self.secret_handler.process_secret(cleaned_manifest)
                        if not cleaned_manifest:  # Secret was skipped
                            continue
                    
                    cleaned_manifests.append(cleaned_manifest)
                    
                except Exception as e:
                    name = ManifestTraverser.get_manifest_name(manifest)
                    kind = manifest.get("kind", "Unknown")
                    self.logger.warning("Failed to clean manifest %s/%s for test chart: %s", kind, name, e)
            
            # Create test chart generator
            test_chart_generator = TestChartGenerator(
                base_release_name=self.config.release_name,
                test_suffix=self.config.test_suffix,
                chart_version=f"{self.config.chart_version}-{self.config.test_suffix}",
                app_version=f"{self.config.app_version}-{self.config.test_suffix}",
            )
            
            # Generate test chart
            test_results = test_chart_generator.create_test_chart(
                cleaned_manifests,
                test_chart_dir,
                force=self.config.force,
            )
            
            # Run lint on test chart if requested
            if self.config.lint:
                test_chart_path = Path(test_chart_dir)
                success = test_chart_generator.chart_generator.lint_chart(test_chart_path)
                if not success:
                    self.logger.warning("Test chart lint reported issues")
            
            self.timed_tracker.end_phase("Test Chart Generation")
            return test_results
            
        except Exception as e:
            self.logger.error("Failed to create test chart: %s", e)
            self.timed_tracker.end_phase("Test Chart Generation")
            return None
    
    # Methods for interactive mode compatibility
    def list_resource_items(self, resource_type: str) -> K8sObjectList:
        """
        List resources of a given type - for compatibility with interactive mode.
        
        Args:
            resource_type: Type of resource to list
            
        Returns:
            List of resources
        """
        return self.kubectl_client.list_resources(
            resource_type=resource_type,
            namespace=self.config.namespace,
            selector=self.config.selector,
        )
    
    def ensure_required_binaries(self) -> None:
        """Ensure required binaries are available - for compatibility."""
        self._validate_prerequisites()


class ExportOrchestrator:
    """High-level orchestrator for export operations."""
    
    def __init__(self, global_config: Optional[GlobalConfig] = None):
        self.global_config = global_config or GlobalConfig()
        self.logger = logging.getLogger(__name__)
    
    def export_from_config(self, export_config: ExportConfig) -> ExportResult:
        """
        Run export operation from configuration.
        
        Args:
            export_config: Export configuration
            
        Returns:
            Export result
        """
        exporter = HelmChartExporter(export_config, self.global_config)
        return exporter.export()
    
    def export_interactive(self, base_config: ExportConfig) -> ExportResult:
        """
        Run interactive export with resource selection.
        
        Args:
            base_config: Base configuration for the export
            
        Returns:
            Export result
        """
        from .interactive import build_interactive_plan
        
        # Create a preview exporter for resource discovery
        preview_exporter = HelmChartExporter(base_config, self.global_config)
        preview_exporter.ensure_required_binaries()
        
        # Build interactive plan
        plan = build_interactive_plan(preview_exporter)
        
        # Update configuration with selection
        if plan.resources():
            base_config.only = sorted(plan.resources())
        
        base_config.selection_names = plan.to_dict()
        
        if plan.includes_secrets():
            base_config.include_secrets = True
            base_config.include_service_account_secrets = True
        
        # Run export with selection
        return self.export_from_config(base_config)