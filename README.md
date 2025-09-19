# Rancher Helm Exporter

```
  ____           _     _              ____ _                _       
 / ___|_ __ __ _| |__ | |__  _   _   / ___| |__   __ _ _ __| |_ ___ 
| |  _| '__/ _` | '_ \| '_ \| | | | | |   | '_ \ / _` | '__| __/ __|
| |_| | | | (_| | |_) | |_) | |_| | | |___| | | | (_| | |  | |_\__ \
 \____|_|  \__,_|_.__/|_.__/ \__, |  \____|_| |_|\__,_|_|   \__|___/
                             |___/                                  

```

This repository contains a command-line utility that inspects an existing Kubernetes
workload (for example, a deployment that was manually installed through Rancher) and
reconstructs the live resources into a Helm chart. The chart can then be versioned or
promoted through standard Helm-based workflows.

## Features

- Uses `kubectl` to pull the current state of Deployments, StatefulSets, DaemonSets,
  CronJobs, Jobs, Services, ConfigMaps, Secrets, ServiceAccounts, PersistentVolumeClaims
  and Ingresses.
- Generates a fully structured Helm chart directory with `Chart.yaml`, `values.yaml`,
  `.helmignore`, individual manifests under `templates/` and an `EXPORT.md` summary.
- Normalises the exported manifests by trimming Kubernetes-managed metadata so they can
  be re-applied safely.
- Optional `helm lint` integration to validate the generated chart.
- Guided terminal interactive mode to combine multiple workloads and cherry-pick
  supporting ConfigMaps, Secrets, Services, ServiceAccounts, PersistentVolumeClaims
  and Ingresses before exporting.
- Flexible filtering via namespaces, label selectors, inclusion/exclusion lists and
  control over whether Secrets are captured.

## Requirements

- **Python 3.9 or newer** (3.11+ recommended for Fedora)
- **kubectl** installed and configured with access to the target Rancher cluster
- **helm** installed if you wish to run `helm lint` as part of the export process
- **Linux environment** (optimized for Fedora/RHEL)

## Installation

### Fedora/RHEL Quick Install

```bash
# Download and run the installer
curl -fsSL https://raw.githubusercontent.com/your-org/rancher-helm-exporter/main/scripts/install_fedora.sh -o install_fedora.sh
chmod +x install_fedora.sh

# Install with system dependencies
./install_fedora.sh --install-deps

# Or install without system dependencies (if kubectl/helm already present)
./install_fedora.sh
```

### Manual Installation

1. **Install system dependencies:**
   ```bash
   sudo dnf install python3 python3-pip python3-venv kubectl helm
   ```

2. **Install the Python package:**
   ```bash
   # Create virtual environment
   python3 -m venv ~/.local/share/rancher-helm-exporter/venv
   source ~/.local/share/rancher-helm-exporter/venv/bin/activate
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Install the package
   pip install -e .
   ```

3. **Set up PATH and completion:**
   ```bash
   # Add to ~/.bashrc
   export PATH="$HOME/.local/bin:$PATH"
   source ~/.local/share/bash-completion/completions/rancher-helm-exporter
   ```

### RPM Package Installation

```bash
# Build RPM package
cd packaging/rpm
./build_rpm.sh --repo /tmp/repo --test

# Install from local repository
sudo tee /etc/yum.repos.d/rancher-helm-exporter-local.repo << 'EOF'
[rancher-helm-exporter-local]
name=Rancher Helm Exporter Local Repository
baseurl=file:///tmp/repo
enabled=1
gpgcheck=0
EOF

sudo dnf install python3-rancher-helm-exporter
```

### Air-gapped Installation

1. **On a connected machine, prepare offline bundle:**
   ```bash
   # For Fedora x86_64
   python scripts/prepare_offline_bundle.py \
     --dest vendor/linux-x86_64-cp311 \
     --platform linux_x86_64 \
     --python-version 3.11 \
     --abi cp311
   ```

2. **Copy to air-gapped environment:**
   ```bash
   # Copy entire repository including vendor/ directory
   scp -r rancher-helm-exporter/ user@airgapped-host:
   ```

3. **Install offline:**
   ```bash
   # On the air-gapped host
   pip install --no-index --find-links vendor/linux-x86_64-cp311 -r requirements.txt
   ```

## Usage

Run the exporter with:

```bash
python -m rancher_helm_exporter <release-name> \
  --namespace <namespace> \
  --selector app=my-app \
  --output-dir ./my-app-chart \
  --include-secrets \
  --lint
```

Key arguments:

- `release`: Helm release/chart name to use when creating `Chart.yaml`.
- `--namespace`: Kubernetes namespace containing the workload (defaults to `default`).
- `--selector`: Label selector applied to all `kubectl get` calls for precise targeting.
- `--only`: Restrict the export to specific resource kinds (for example `--only deployments services`).
- `--exclude`: Omit resource kinds from the export (for example `--exclude secrets`).
- `--include-secrets`: Capture user-managed `Secret` resources. Service account tokens are skipped
  unless `--include-service-account-secrets` is passed.
- `--kubeconfig` / `--context`: Point to alternate kubeconfig files or contexts when running `kubectl`.
- `--force`: Overwrite the output directory if it already exists.
- `--lint`: Run `helm lint` after the manifests have been generated.
- `--verbose`: Enable more detailed logging.
- `--interactive`: Launch a built-in picker (arrow keys to move, space to toggle, enter to confirm)
  for combining workloads and selecting ConfigMaps, Secrets, Services,
  ServiceAccounts, PersistentVolumeClaims and Ingresses.

### Interactive selection walkthrough

Run the exporter with `--interactive` to query Rancher via `kubectl` and present an
interactive checklist:

1. Pick one or more workloads (Deployments, StatefulSets, DaemonSets, CronJobs or
   Jobs) to include in the chart.
2. Review all supporting ConfigMaps, Secrets, Services, ServiceAccounts,
   PersistentVolumeClaims and Ingresses in the namespace. The exporter preselects
   items referenced by the chosen workloads, and you can deselect any that are not
   required.
3. Confirm your choices to generate a chart containing exactly those resources. The
   exporter automatically enables secret export when you pick any secrets.

The generated chart mirrors the live objects as closely as possible while removing fields that
Kubernetes manages automatically (timestamps, status blocks, generated names, pod template hashes
and so on). This makes the manifests safe to apply via Helm without surfacing spurious diffs.

## Workflow Tips

1. Make sure the target Rancher cluster context is active (`kubectl config use-context ...`).
2. Export the current workload using the command above.
3. Review the manifests under `templates/` and adjust templating or values as needed to introduce
   parameterisation (image tags, replica counts, etc.).
4. Commit the generated chart to version control and promote it through your preferred Helm pipeline.

## Enhanced Features (v2.0+)

The tool includes several architectural improvements for better reliability and usability:

### Reliability & Performance
- **Robust kubectl interface**: Automatic retries with exponential backoff for transient failures
- **Timeout handling**: Configurable timeouts prevent hanging on slow cluster operations  
- **Progress tracking**: Rich progress indicators show export status and estimated completion
- **Parallel processing**: Optional parallel resource collection for large namespaces
- **Enhanced error handling**: Detailed error reporting with actionable suggestions

### Configuration & Customization
- **Configuration files**: YAML-based configuration for complex setups (`.rancher-helm-exporter.yaml`)
- **Secret handling modes**: Multiple options for handling secrets (`include`, `skip`, `encrypt`, `external-ref`)
- **Resource filtering**: Advanced filtering with label selectors and resource type inclusion/exclusion
- **Validation**: Optional manifest validation to catch issues before chart generation

### Developer Experience
- **Type safety**: Comprehensive type definitions for better IDE support and error detection
- **Modular architecture**: Clean separation of concerns for easier maintenance and testing
- **Rich console output**: Enhanced progress bars and status reporting with the `rich` library
- **Dry run mode**: Preview exports without creating files

### Usage Examples

```bash
# Basic export with progress tracking
python -m rancher_helm_exporter my-app --namespace production --progress

# Advanced export with configuration file
python -m rancher_helm_exporter my-app --config ./my-config.yaml --secret-mode external-ref

# Interactive mode with rich progress
python -m rancher_helm_exporter my-app --interactive --rich-progress

# Create test chart alongside production chart
python -m rancher_helm_exporter my-app --create-test-chart --test-suffix staging

# Parallel processing for large namespaces
python -m rancher_helm_exporter my-app --parallel --max-workers 8 --timeout 60

# Dry run to preview without creating files
python -m rancher_helm_exporter my-app --dry-run --verbose
```

### Configuration File Example

```yaml
# .rancher-helm-exporter.yaml
retry:
  max_retries: 5
  timeout_seconds: 45
  
cleaning:
  additional_metadata_fields:
    - "company.com/build-timestamp"
  
enable_rich_progress: true
enable_validation: true
```

## Test Chart Generation

The tool can automatically create test versions of your applications alongside the main chart. Test charts help you:

- Deploy test versions safely alongside production
- Validate configuration changes before production deployment
- Run integration tests in isolated environments
- Practice deployment procedures

### How Test Charts Work

Test charts automatically transform your resources by:

1. **Renaming resources** with a configurable suffix (default: `-test`)
   - `my-app` deployment → `my-app-test` deployment
   - `my-service` service → `my-service-test` service
   - `my-config` configmap → `my-config-test` configmap

2. **Updating references** between resources
   - Service selectors point to test pods
   - ConfigMap/Secret references updated
   - Ingress backends point to test services

3. **Applying test-friendly modifications**
   - Reduced replica counts (max 1 for tests)
   - Smaller resource limits and requests
   - Reduced storage sizes for PVCs
   - Test-specific labels and annotations

### Usage

```bash
# Create test chart with CLI flag
python -m rancher_helm_exporter my-app --create-test-chart

# Customize test suffix
python -m rancher_helm_exporter my-app --create-test-chart --test-suffix staging

# Specify test chart output directory
python -m rancher_helm_exporter my-app --create-test-chart --test-chart-dir ./my-app-staging

# Interactive mode will prompt for test chart creation
python -m rancher_helm_exporter my-app --interactive
```

### Test Chart Structure

Test charts include:

```
my-app-test/
├── Chart.yaml              # Test chart metadata
├── values.yaml             # Test-specific values
├── README.md               # Test chart documentation
├── EXPORT.md               # Export summary
└── templates/
    ├── test-deployment-my-app-test.yaml
    ├── test-service-my-service-test.yaml
    ├── test-configmap-my-config-test.yaml
    └── ...
```

### Installing Test Charts

```bash
# Install test chart in same namespace
helm install my-app-test ./my-app-test

# Install in dedicated test namespace (recommended)
helm install my-app-test ./my-app-test --namespace my-app-test --create-namespace

# Install alongside production
helm install my-app ./my-app                    # Production
helm install my-app-test ./my-app-test          # Test version
```

### Test Chart Features

- **Automatic name transformation**: All resource names get test suffix
- **Cross-reference updates**: Services, ConfigMaps, Secrets properly linked
- **Resource optimization**: Reduced resources suitable for test environments
- **Test-specific configuration**: Modified values.yaml for test scenarios
- **Clear identification**: Test labels and annotations for easy filtering

## Service Deployment (Linux/Systemd)

For production environments, run rancher-helm-exporter as a systemd service:

### Service Setup

```bash
# Set up systemd services
sudo ./scripts/systemd/setup_systemd.sh

# Configure kubectl access for service user
sudo cp ~/.kube/config /etc/rancher-helm-exporter/kubeconfig
sudo chown root:rancher-exporter /etc/rancher-helm-exporter/kubeconfig
sudo chmod 640 /etc/rancher-helm-exporter/kubeconfig
```

### Service Usage

```bash
# One-time export
sudo systemctl start rancher-helm-exporter.service

# Scheduled daily exports
sudo systemctl enable rancher-helm-exporter.timer
sudo systemctl start rancher-helm-exporter.timer

# App-specific exports
sudo cp /etc/rancher-helm-exporter/myapp.yaml /etc/rancher-helm-exporter/webapp.yaml
sudo systemctl start rancher-helm-exporter@webapp.service

# Monitor exports
journalctl -u rancher-helm-exporter.service -f
```

### Configuration Locations

- **Global config**: `/etc/rancher-helm-exporter/config.yaml`
- **App configs**: `/etc/rancher-helm-exporter/<app>.yaml`
- **Kubeconfig**: `/etc/rancher-helm-exporter/kubeconfig`
- **Data directory**: `/var/lib/rancher-helm-exporter/`
- **Exports**: `/var/lib/rancher-helm-exporter/exports/`
- **Logs**: `/var/log/rancher-helm-exporter/`

### Shell Integration

```bash
# Bash completion (auto-installed)
rancher-helm-exporter <TAB><TAB>

# Command aliases
alias rhe='rancher-helm-exporter'
alias helm-export='rancher-helm-exporter'

# Quick exports
rhe my-app --namespace production --create-test-chart
```

## Limitations & Next Steps

- The generated manifests intentionally contain minimal Helm templating. They are usable as-is, but
  further customisation is encouraged to parameterise environment-specific values.
- Custom Resource Definitions (CRDs) are not exported automatically. You can add additional resource
  types through subsequent enhancements.
- Secret encryption requires integration with external tools (sealed-secrets, external-secrets-operator)

## Backward Compatibility

The tool maintains full backward compatibility with existing command-line usage. The enhanced features
are opt-in and the original functionality remains unchanged.

Contributions and feedback are welcome! Open an issue or submit a pull request to share ideas.
