# Gemini Project: rancher-helm-exporter

## Project Overview

This project is a Python command-line utility named "Rancher Helm Exporter". Its purpose is to inspect existing Kubernetes workloads (like those deployed via Rancher) and generate a Helm chart from the live resources. This allows for versioning and managing the application using standard Helm-based workflows.

The core technologies used are Python 3.9+ and `kubectl`. The main Python dependencies are `PyYAML` for YAML manipulation and `rich` for enhanced terminal output.

The application is structured into several modules:
- `cli.py`: Handles command-line argument parsing and user interaction.
- `exporter.py`: Orchestrates the process of fetching resources from Kubernetes.
- `chart_generator.py`: Responsible for building the Helm chart directory and files.
- `kubectl.py`: A wrapper around the `kubectl` command-line tool.
- `manifest_cleaner.py`: Cleans up the exported Kubernetes manifests to make them suitable for a Helm chart.

## Building and Running

This is a Python project and can be run directly from the source or installed as a package.

**Requirements:**
*   Python 3.9+
*   `kubectl` installed and configured
*   `helm` (optional, for linting)

**Running from source:**

The main entry point is `src/rancher_helm_exporter/__main__.py`, but it's intended to be run as a module.

To run the exporter:
```bash
python -m rancher_helm_exporter <release-name> --namespace <namespace> --output-dir ./my-chart
```

See the `README.md` for more detailed usage examples and arguments.

**Installation:**

The `README.md` provides several installation methods, including a quick install script for Fedora/RHEL, manual installation with `pip`, and building an RPM package.

For a development setup, you can install the package in editable mode:
```bash
pip install -e .
```

## Development Conventions

*   **Code Style:** The code follows standard Python conventions (PEP 8).
*   **Typing:** The code uses Python type hints extensively for better code quality and maintainability.
*   **Modularity:** The project is broken down into well-defined modules with specific responsibilities.
*   **Configuration:** The application can be configured via command-line arguments or a YAML configuration file (`.rancher-helm-exporter.yaml`).
*   **Entry Point:** The main command-line script is defined in `pyproject.toml` under `[project.scripts]`, pointing to `rancher_helm_exporter.cli:main`.
*   **Testing:** The project uses `pytest` for unit testing. Tests are located in the `tests` directory.
*   **Documentation:** The project uses `Sphinx` for API documentation. The documentation is located in the `docs` directory.
