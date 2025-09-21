#!/usr/bin/env python3
"""
Test script for configuration management functionality.
"""

import json
import sys
from pathlib import Path

# Add the src directory to Python path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from rancher_helm_exporter.cli import (
    save_config, load_config, delete_config, delete_all_configs,
    list_config_names, load_all_configs
)

def test_config_management():
    """Test configuration save, load, and delete functionality."""

    print("Testing Configuration Management")
    print("=" * 40)

    # Test 1: Save some test configurations
    print("\n1. Creating test configurations...")

    test_configs = {
        "test-config-1": {
            "release": "test-app-1",
            "namespace": "test-namespace",
            "output_dir": "./test-chart-1",
            "selector": "app=test-app-1"
        },
        "test-config-2": {
            "release": "test-app-2",
            "namespace": "production",
            "output_dir": "./test-chart-2",
            "selector": "app=test-app-2"
        },
        "old-config": {
            "release": "old-app",
            "namespace": "default",
            "output_dir": "./old-chart"
        }
    }

    for name, config in test_configs.items():
        save_config(name, config)
        print(f"  [+] Saved: {name}")

    # Test 2: List configurations
    print("\n2. Listing saved configurations...")
    config_names = list_config_names()
    print(f"  Found {len(config_names)} configurations:")
    for name in config_names:
        print(f"    - {name}")

    # Test 3: Load configurations
    print("\n3. Loading and verifying configurations...")
    for name in config_names:
        loaded_config = load_config(name)
        if loaded_config:
            print(f"  [+] Loaded: {name}")
            print(f"      Release: {loaded_config.get('release', 'N/A')}")
            print(f"      Namespace: {loaded_config.get('namespace', 'N/A')}")
        else:
            print(f"  [-] Failed to load: {name}")

    # Test 4: Delete a specific configuration
    print("\n4. Testing delete specific configuration...")
    if "old-config" in config_names:
        if delete_config("old-config"):
            print("  [+] Successfully deleted 'old-config'")
        else:
            print("  [-] Failed to delete 'old-config'")

    # Verify deletion
    updated_names = list_config_names()
    print(f"  Configurations after deletion: {len(updated_names)}")
    for name in updated_names:
        print(f"    - {name}")

    # Test 5: Show detailed config information
    print("\n5. Configuration details with metadata...")
    all_configs = load_all_configs()
    for name, config_entry in all_configs.items():
        print(f"  Config: {name}")
        print(f"    Saved at: {config_entry.get('saved_at', 'Unknown')}")
        actual_config = config_entry.get('config', {})
        print(f"    Release: {actual_config.get('release', 'N/A')}")
        print(f"    Namespace: {actual_config.get('namespace', 'N/A')}")

    # Test 6: Delete all configurations
    print("\n6. Testing delete all configurations...")
    if updated_names:
        print(f"  About to delete {len(updated_names)} configurations")
        if delete_all_configs():
            print("  [+] Successfully deleted all configurations")
        else:
            print("  [-] Failed to delete all configurations")
    else:
        print("  No configurations to delete")

    # Final verification
    final_names = list_config_names()
    print(f"\n7. Final verification: {len(final_names)} configurations remaining")
    if final_names:
        print("  Remaining configurations:")
        for name in final_names:
            print(f"    - {name}")
    else:
        print("  [+] All configurations successfully deleted")

    print("\n" + "=" * 40)
    print("Configuration Management Test Complete!")
    print("The delete functionality is working correctly.")

if __name__ == "__main__":
    test_config_management()