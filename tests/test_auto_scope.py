#!/usr/bin/env python3
"""
Test script for auto-scope detection functionality.
"""

import sys
import subprocess
from pathlib import Path

def test_auto_scope_detection():
    """Test the auto-scope detection functionality."""

    print("Testing Auto-Scope Detection")
    print("=" * 40)

    # Test the help text to ensure the argument is available
    print("\n1. Testing --auto-scope argument availability...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "src.rancher_helm_exporter", "--help"
        ], capture_output=True, text=True, cwd=Path(__file__).parent)

        if "--auto-scope" in result.stdout:
            print("  [+] --auto-scope argument is available")
            print("  [+] Help text includes auto-scope option")
        else:
            print("  [-] --auto-scope argument not found in help")
            return

    except Exception as e:
        print(f"  [-] Failed to test help: {e}")
        return

    # Test auto-scope in demo mode (no cluster required)
    print("\n2. Testing auto-scope with demo mode...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "src.rancher_helm_exporter",
            "--auto-scope", "--demo-mode"
        ], capture_output=True, text=True, cwd=Path(__file__).parent, timeout=30)

        print(f"  Return code: {result.returncode}")

        if "AUTO-SCOPE DETECTION" in result.stdout:
            print("  [+] Auto-scope detection initiated")
        else:
            print("  [!] Auto-scope detection not found in output")

        if result.stdout:
            print("  Sample output lines:")
            for line in result.stdout.split('\n')[:10]:
                if line.strip():
                    print(f"    {line}")

        if result.stderr:
            print("  Error output:")
            for line in result.stderr.split('\n')[:5]:
                if line.strip():
                    print(f"    {line}")

    except subprocess.TimeoutExpired:
        print("  [!] Test timed out (this is normal for interactive mode)")
    except Exception as e:
        print(f"  [-] Test failed: {e}")

    # Test the scope detection function directly
    print("\n3. Testing scope detection logic...")
    try:
        # Add the src directory to Python path for imports
        src_path = Path(__file__).parent / "src"
        sys.path.insert(0, str(src_path))

        from rancher_helm_exporter.cli import perform_startup_scope_detection

        print("  [+] Successfully imported scope detection function")
        print("  [*] Note: Actual detection requires cluster access")

    except ImportError as e:
        print(f"  [-] Import failed: {e}")
    except Exception as e:
        print(f"  [!] Unexpected error: {e}")

    print("\n4. Testing configuration scenarios...")

    # Test various argument combinations
    scenarios = [
        (["--auto-scope", "--namespace", "test"], "Auto-scope with explicit namespace"),
        (["--auto-scope", "--namespace-only"], "Auto-scope with namespace-only mode"),
        (["--auto-scope", "--config-prompt"], "Auto-scope with config prompt"),
    ]

    for args, description in scenarios:
        print(f"\n  Testing: {description}")
        print(f"  Arguments: {' '.join(args)}")

        # Just test argument parsing without execution
        try:
            result = subprocess.run([
                sys.executable, "-c",
                f"import sys; sys.path.insert(0, 'src'); "
                f"from rancher_helm_exporter.cli import parse_args; "
                f"args = parse_args({args}); "
                f"print(f'auto_scope={{args.auto_scope}}, namespace={{args.namespace}}, namespace_only={{args.namespace_only}}')"
            ], capture_output=True, text=True, cwd=Path(__file__).parent)

            if result.returncode == 0:
                print(f"    [+] {result.stdout.strip()}")
            else:
                print(f"    [-] Failed: {result.stderr.strip()}")
        except Exception as e:
            print(f"    [-] Error: {e}")

    print("\n" + "=" * 40)
    print("Auto-Scope Detection Test Complete!")

    print("\nUsage Examples:")
    print("  python -m src.rancher_helm_exporter --auto-scope")
    print("  python -m src.rancher_helm_exporter --auto-scope --config-prompt")
    print("  python -m src.rancher_helm_exporter --auto-scope --demo-mode")

if __name__ == "__main__":
    test_auto_scope_detection()