# Quick Test Setup for Grabby-Helm

## Option 1: Kind (Kubernetes in Docker) - Recommended
```bash
# Install kind (if not already installed)
# Windows:
curl.exe -Lo kind-windows-amd64.exe https://kind.sigs.k8s.io/dl/v0.20.0/kind-windows-amd64
# Linux: curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
# macOS: brew install kind

# Create test cluster
kind create cluster --name grabby-helm-test

# Verify connection
kubectl cluster-info --context kind-grabby-helm-test

# Deploy a test application
kubectl create deployment nginx --image=nginx:1.21
kubectl create deployment redis --image=redis:7-alpine
kubectl expose deployment nginx --port=80 --target-port=80
kubectl create configmap app-config --from-literal=database.host=localhost --from-literal=database.port=5432

# Wait for deployments to be ready
kubectl wait --for=condition=available --timeout=300s deployment/nginx
kubectl wait --for=condition=available --timeout=300s deployment/redis

# Test Grabby-Helm
python -m src.rancher_helm_exporter --config-prompt
```

## Option 2: Minikube
```bash
# Install minikube
# Windows: choco install minikube
# Linux: curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
# macOS: brew install minikube

# Start cluster
minikube start

# Deploy test apps (same as above)
kubectl create deployment nginx --image=nginx:1.21
# ... etc
```

## Option 3: Mock Data Mode (Development)
Create sample deployment data for testing without a cluster.