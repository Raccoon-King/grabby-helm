"""Improved command line interface using the new architecture."""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional, Sequence

from .config import ConfigLoader, ConfigValidator, ExportConfig, GlobalConfig, load_config_from_args
from .exporter import ExportOrchestrator
from .types import ExportError


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Export live Kubernetes resources into a Helm chart",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # Required arguments
    parser.add_argument("release", help="Name to use for the generated Helm chart")
    
    # Basic options
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
    
    # Filtering options
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
    
    # kubectl options
    parser.add_argument(
        "--kubeconfig",
        help="Path to an alternate kubeconfig file",
    )
    parser.add_argument(
        "--context",
        help="Kubernetes context to use when executing kubectl commands",
    )
    
    # Secret handling
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
        "--secret-mode",
        choices=["include", "skip", "encrypt", "external-ref"],
        default="include",
        help="How to handle secrets in the export",
    )
    
    # Output options
    parser.add_argument(
        "--prefix",
        default="",
        help="Prefix to prepend to generated manifest filenames",
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
    
    # Chart metadata
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
    
    # Performance and reliability
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds for kubectl operations",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retries for failed operations",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel processing of resources",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of worker threads for parallel processing",
    )
    
    # Progress and logging
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        default=True,
        help="Show progress indicators (default: enabled)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress indicators",
    )
    parser.add_argument(
        "--rich-progress",
        action="store_true",
        default=True,
        help="Use rich progress bars if available (default: enabled)",
    )
    parser.add_argument(
        "--silent-progress",
        action="store_true",
        help="Only log progress, don't show interactive progress",
    )
    
    # Configuration
    parser.add_argument(
        "--config",
        help="Path to configuration file",
    )
    
    # Interactive mode
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch an interactive picker to choose deployments and related resources",
    )
    
    # Test chart options
    parser.add_argument(
        "--create-test-chart",
        action="store_true",
        help="Create an additional test chart with -test suffixed resource names",
    )
    parser.add_argument(
        "--test-suffix",
        default="test",
        help="Suffix to append to resource names in test chart (default: test)",
    )
    parser.add_argument(
        "--test-chart-dir",
        help="Directory for test chart (default: {output-dir}-test)",
    )
    
    # Development and debugging
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be exported without actually creating files",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Validate exported manifests (default: enabled)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip manifest validation",
    )

    args = parser.parse_args(argv)

    # Post-process arguments
    if args.include_service_account_secrets:
        args.include_secrets = True
    
    if args.no_progress:
        args.progress = False
    
    if args.no_validate:
        args.validate = False
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    return args


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Main entry point for the improved CLI."""
    try:
        # Parse arguments
        args = parse_args(argv)
        
        # Load configuration
        config_loader = ConfigLoader()
        global_config = config_loader.load_config(config_file=args.config)
        
        # Update global config based on args
        global_config.enable_validation = args.validate
        global_config.enable_rich_progress = args.rich_progress
        
        # Create export configuration
        export_config = load_config_from_args(args)
        export_config.progress_enabled = args.progress
        export_config.use_rich_progress = args.rich_progress
        export_config.silent_progress = args.silent_progress
        export_config.parallel_exports = args.parallel
        export_config.max_workers = args.max_workers
        export_config.secret_mode = args.secret_mode
        export_config.create_test_chart = args.create_test_chart
        export_config.test_suffix = args.test_suffix
        export_config.test_chart_dir = args.test_chart_dir
        
        # Validate configuration
        validator = ConfigValidator()
        
        global_errors = validator.validate_global_config(global_config)
        if global_errors:
            print("Configuration validation errors:", file=sys.stderr)
            for error in global_errors:
                print(f"  - {error}", file=sys.stderr)
            sys.exit(1)
        
        export_errors = validator.validate_export_config(export_config)
        if export_errors:
            print("Export configuration validation errors:", file=sys.stderr)
            for error in export_errors:
                print(f"  - {error}", file=sys.stderr)
            sys.exit(1)
        
        # Handle dry run
        if args.dry_run:
            print("DRY RUN MODE - would export the following configuration:")
            print(f"  Release: {export_config.release_name}")
            print(f"  Namespace: {export_config.namespace}")
            print(f"  Output: {export_config.output_dir}")
            if export_config.selector:
                print(f"  Selector: {export_config.selector}")
            if export_config.only:
                print(f"  Include only: {', '.join(export_config.only)}")
            if export_config.exclude:
                print(f"  Exclude: {', '.join(export_config.exclude)}")
            print(f"  Include secrets: {export_config.include_secrets}")
            print(f"  Secret mode: {export_config.secret_mode}")
            
            if export_config.create_test_chart:
                print()
                print("Test chart configuration:")
                print(f"  Test suffix: {export_config.test_suffix}")
                test_chart_dir = export_config.test_chart_dir or f"{export_config.output_dir}-{export_config.test_suffix}"
                print(f"  Test output: {test_chart_dir}")
                print(f"  Test release: {export_config.release_name}-{export_config.test_suffix}")
            
            return
        
        # Create orchestrator and run export
        orchestrator = ExportOrchestrator(global_config)
        
        if export_config.interactive:
            result = orchestrator.export_interactive(export_config)
        else:
            result = orchestrator.export_from_config(export_config)
        
        # Report results
        if result["success"]:
            print(f"✅ Export completed successfully!")
            print(f"   📁 Chart created at: {result['output_path']}")
            print(f"   📊 Resources exported: {result['exported_count']}")
            
            if result["failed_count"] > 0:
                print(f"   ⚠️  Failed resources: {result['failed_count']}")
            
            print()
            print("Next steps:")
            print(f"  1. Review the generated chart: cd {result['output_path']}")
            print("  2. Customize values.yaml as needed")
            print(f"  3. Install the chart: helm install {export_config.release_name} {result['output_path']}")
            
            # Add test chart information if created
            if export_config.create_test_chart:
                test_chart_dir = export_config.test_chart_dir or f"{export_config.output_dir}-{export_config.test_suffix}"
                print()
                print("🧪 Test chart created:")
                print(f"  📁 Test chart location: {test_chart_dir}")
                print(f"  🚀 Install test chart: helm install {export_config.release_name}-{export_config.test_suffix} {test_chart_dir}")
                print(f"  🔧 Test with namespace: helm install {export_config.release_name}-{export_config.test_suffix} {test_chart_dir} --namespace {export_config.release_name}-test --create-namespace")
        else:
            print("❌ Export failed!", file=sys.stderr)
            if result["errors"]:
                for error in result["errors"]:
                    print(f"   {error}", file=sys.stderr)
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\\n🛑 Export cancelled by user", file=sys.stderr)
        sys.exit(130)
        
    except ExportError as e:
        print(f"❌ Export failed: {e}", file=sys.stderr)
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        if args.verbose if 'args' in locals() else False:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()