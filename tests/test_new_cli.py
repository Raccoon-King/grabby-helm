#!/usr/bin/env python3
"""
Test script for the new state-based CLI application.
"""

import sys
import subprocess
from pathlib import Path

def test_new_cli_structure():
    """Test the new CLI structure and state-based flags."""

    print("Testing New State-Based CLI Application")
    print("=" * 50)

    # Test the help output
    print("\n1. Testing help output and argument structure...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "src.rancher_helm_exporter", "--help"
        ], capture_output=True, text=True, cwd=Path(__file__).parent)

        if result.returncode == 0:
            print("  [+] Help command successful")

            # Check for new state flags
            help_text = result.stdout
            state_flags = ["--explore", "--configs", "--bulk", "--demo", "--debug"]
            modifier_flags = ["--auto-detect", "--namespace-restricted", "--offline"]

            print("  [+] State flags found:")
            for flag in state_flags:
                if flag in help_text:
                    print(f"    [+] {flag}")
                else:
                    print(f"    [-] {flag} MISSING")

            print("  [+] Modifier flags found:")
            for flag in modifier_flags:
                if flag in help_text:
                    print(f"    [+] {flag}")
                else:
                    print(f"    [-] {flag} MISSING")

            # Check for proper sections
            sections = ["APPLICATION MODES", "BEHAVIOR MODIFIERS", "CONFIGURATION OPTIONS"]
            for section in sections:
                if section in help_text:
                    print(f"    [+] {section} section")
                else:
                    print(f"    [-] {section} section MISSING")

        else:
            print(f"  [-] Help command failed: {result.stderr}")

    except Exception as e:
        print(f"  [-] Help test failed: {e}")

    # Test different modes (non-interactive)
    print("\n2. Testing different application modes...")

    test_cases = [
        (["--demo", "--no-interactive"], "Demo mode"),
        (["--debug", "--offline", "--no-interactive"], "Debug mode"),
        (["--configs", "--no-interactive"], "Config management mode"),
    ]

    for args, description in test_cases:
        print(f"\n  Testing: {description}")
        print(f"  Command: python -m src.rancher_helm_exporter {' '.join(args)}")

        try:
            # Run with timeout to prevent hanging
            result = subprocess.run([
                sys.executable, "-m", "src.rancher_helm_exporter"
            ] + args, capture_output=True, text=True, cwd=Path(__file__).parent, timeout=15)

            print(f"    Return code: {result.returncode}")

            # Check for expected output patterns
            if "GRABBY-HELM" in result.stdout:
                print("    [+] Application banner displayed")

            if args[0].replace("--", "").upper() in result.stdout:
                print(f"    [+] Mode detected: {args[0]}")

            # Show sample output
            lines = result.stdout.split('\n')
            if len(lines) > 1:
                print("    Sample output:")
                for line in lines[:8]:  # First few lines
                    if line.strip():
                        print(f"      {line}")

            if result.stderr:
                print("    Errors:")
                for line in result.stderr.split('\n')[:3]:
                    if line.strip():
                        print(f"      {line}")

        except subprocess.TimeoutExpired:
            print("    [!] Test timed out (may be waiting for input)")
        except Exception as e:
            print(f"    [-] Test failed: {e}")

    # Test argument validation
    print("\n3. Testing argument validation...")

    invalid_cases = [
        (["--explore", "--demo"], "Multiple state flags should fail"),
        (["--bulk", "--configs", "--debug"], "Three state flags should fail"),
    ]

    for args, description in invalid_cases:
        print(f"\n  Testing: {description}")
        try:
            result = subprocess.run([
                sys.executable, "-m", "src.rancher_helm_exporter"
            ] + args, capture_output=True, text=True, cwd=Path(__file__).parent, timeout=10)

            if result.returncode != 0:
                print("    [+] Correctly rejected invalid combination")
            else:
                print("    [-] Should have rejected invalid combination")

        except subprocess.TimeoutExpired:
            print("    [!] Test timed out")
        except Exception as e:
            print(f"    [-] Test failed: {e}")

    # Test legacy compatibility
    print("\n4. Testing legacy compatibility...")

    legacy_cases = [
        (["--config-prompt"], "Legacy config-prompt should work"),
        (["--interactive"], "Legacy interactive should work"),
        (["--demo-mode"], "Legacy demo-mode should work"),
    ]

    for args, description in legacy_cases:
        print(f"\n  Testing: {description}")
        try:
            result = subprocess.run([
                sys.executable, "-m", "src.rancher_helm_exporter"
            ] + args + ["--no-interactive"], capture_output=True, text=True,
            cwd=Path(__file__).parent, timeout=10)

            if "DEPRECATED" in result.stdout:
                print("    [+] Legacy warning displayed")
            else:
                print("    [!] No deprecation warning shown")

        except subprocess.TimeoutExpired:
            print("    [!] Test timed out")
        except Exception as e:
            print(f"    [-] Test failed: {e}")

    print("\n" + "=" * 50)
    print("New CLI Structure Test Complete!")

    print("\nNew CLI Usage Examples:")
    print("  python -m src.rancher_helm_exporter                    # Interactive mode (default)")
    print("  python -m src.rancher_helm_exporter --explore          # Explore deployments")
    print("  python -m src.rancher_helm_exporter --configs          # Manage configurations")
    print("  python -m src.rancher_helm_exporter --bulk             # Bulk export mode")
    print("  python -m src.rancher_helm_exporter --demo             # Demo with sample data")
    print("  python -m src.rancher_helm_exporter --debug --offline  # Debug without cluster")
    print("  python -m src.rancher_helm_exporter --auto-detect      # Auto-detect scope")

if __name__ == "__main__":
    test_new_cli_structure()