# Rancher Helm Exporter

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
- Flexible filtering via namespaces, label selectors, inclusion/exclusion lists and
  control over whether Secrets are captured.

## Requirements

- Python 3.9 or newer.
- `kubectl` installed and configured with access to the target Rancher cluster.
- `helm` installed if you wish to run `helm lint` as part of the export process.
- Python dependencies listed in `requirements.txt` (`PyYAML`). Install them with:

  ```bash
  pip install -r requirements.txt
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

The generated chart mirrors the live objects as closely as possible while removing fields that
Kubernetes manages automatically (timestamps, status blocks, generated names, pod template hashes
and so on). This makes the manifests safe to apply via Helm without surfacing spurious diffs.

## Workflow Tips

1. Make sure the target Rancher cluster context is active (`kubectl config use-context ...`).
2. Export the current workload using the command above.
3. Review the manifests under `templates/` and adjust templating or values as needed to introduce
   parameterisation (image tags, replica counts, etc.).
4. Commit the generated chart to version control and promote it through your preferred Helm pipeline.

## Limitations & Next Steps

- The generated manifests intentionally contain minimal Helm templating. They are usable as-is, but
  further customisation is encouraged to parameterise environment-specific values.
- Custom Resource Definitions (CRDs) are not exported automatically. You can add additional resource
  types through subsequent enhancements.
- Secrets remain encoded as Base64 strings exactly as retrieved from the cluster.

Contributions and feedback are welcome! Open an issue or submit a pull request to share ideas.
