#!/usr/bin/env python3
"""Download project dependencies into a local wheel cache for offline installs."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = ROOT / "requirements.txt"
DEFAULT_VENDOR = ROOT / "vendor"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the wheels needed to install this project without internet access. "
            "Run the script on a connected machine, copy the resulting vendor directory "
            "to the airgapped environment, then install with pip using --no-index."
        )
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        default=DEFAULT_REQUIREMENTS,
        help="Path to the requirements file to resolve (default: requirements.txt).",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_VENDOR,
        help="Directory where downloaded wheels should be stored (default: vendor/).",
    )
    parser.add_argument(
        "--python-version",
        help=(
            "Target Python version for the wheels (format: '3.9', '3.11'). "
            "Defaults to the interpreter running this script."
        ),
    )
    parser.add_argument(
        "--platform",
        help=(
            "Target platform tag (e.g. 'linux_x86_64', 'manylinux2014_x86_64', 'manylinux_2_17_x86_64'). "
            "For Fedora/RHEL use 'linux_x86_64' or 'manylinux2014_x86_64'. Defaults to current platform."
        ),
    )
    parser.add_argument(
        "--implementation",
        default="cp",
        help="Python implementation tag (default: cp).",
    )
    parser.add_argument(
        "--abi",
        help=(
            "Target ABI tag (for example 'cp39', 'cp311'). Required if --platform is set."
        ),
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Remove the destination directory before downloading wheels.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    requirements = args.requirements.resolve()
    if not requirements.exists():
        parser.error(f"requirements file not found: {requirements}")

    dest = args.dest.resolve()
    if args.clear and dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    pip_cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--requirement",
        str(requirements),
        "--dest",
        str(dest),
        "--only-binary=:all:",
        "--no-deps",
    ]

    if args.platform:
        if not args.python_version:
            parser.error("--python-version is required when --platform is specified")
        if not args.abi:
            parser.error("--abi is required when --platform is specified")
        pip_cmd.extend(
            [
                "--platform",
                args.platform,
                "--python-version",
                args.python_version,
                "--implementation",
                args.implementation,
                "--abi",
                args.abi,
            ]
        )
    elif args.python_version or args.abi:
        parser.error("--platform must be provided when specifying --python-version or --abi")

    print("Running:", " ".join(pip_cmd))
    try:
        subprocess.run(pip_cmd, check=True)
    except subprocess.CalledProcessError as exc:
        return exc.returncode

    print(f"Wheels downloaded to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
