"""Type definitions for Kubernetes resources and internal data structures."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, TypedDict, Union

# Basic Kubernetes types
K8sObject = Dict[str, Any]
K8sObjectList = List[K8sObject]


class KubernetesMetadata(TypedDict, total=False):
    """Kubernetes metadata structure."""
    name: str
    namespace: Optional[str]
    labels: Optional[Dict[str, str]]
    annotations: Optional[Dict[str, str]]
    creationTimestamp: Optional[str]
    deletionTimestamp: Optional[str]
    deletionGracePeriodSeconds: Optional[int]
    generateName: Optional[str]
    generation: Optional[int]
    managedFields: Optional[List[Dict[str, Any]]]
    ownerReferences: Optional[List[Dict[str, Any]]]
    resourceVersion: Optional[str]
    selfLink: Optional[str]
    uid: Optional[str]


class KubernetesResource(TypedDict, total=False):
    """Base Kubernetes resource structure."""
    apiVersion: str
    kind: str
    metadata: KubernetesMetadata
    spec: Dict[str, Any]
    status: Optional[Dict[str, Any]]


class PodSpec(TypedDict, total=False):
    """Kubernetes Pod specification."""
    containers: List[Dict[str, Any]]
    initContainers: Optional[List[Dict[str, Any]]]
    ephemeralContainers: Optional[List[Dict[str, Any]]]
    volumes: Optional[List[Dict[str, Any]]]
    serviceAccountName: Optional[str]
    serviceAccount: Optional[str]
    imagePullSecrets: Optional[List[Dict[str, str]]]


class DeploymentSpec(TypedDict, total=False):
    """Kubernetes Deployment specification."""
    replicas: Optional[int]
    selector: Dict[str, Any]
    template: Dict[str, Any]
    strategy: Optional[Dict[str, Any]]
    revisionHistoryLimit: Optional[int]
    progressDeadlineSeconds: Optional[int]


class ServiceSpec(TypedDict, total=False):
    """Kubernetes Service specification."""
    selector: Optional[Dict[str, str]]
    ports: Optional[List[Dict[str, Any]]]
    type: Optional[str]
    clusterIP: Optional[str]
    clusterIPs: Optional[List[str]]
    ipFamilies: Optional[List[str]]
    ipFamilyPolicy: Optional[str]
    sessionAffinityConfig: Optional[Dict[str, Any]]


class ConfigMapData(TypedDict, total=False):
    """Kubernetes ConfigMap data structure."""
    data: Optional[Dict[str, str]]
    binaryData: Optional[Dict[str, str]]


class SecretData(TypedDict, total=False):
    """Kubernetes Secret data structure."""
    data: Optional[Dict[str, str]]
    stringData: Optional[Dict[str, str]]
    type: Optional[str]


class ResourceReference(TypedDict, total=False):
    """Reference to another Kubernetes resource."""
    name: str
    namespace: Optional[str]
    kind: Optional[str]
    apiVersion: Optional[str]


class ExportOptions(TypedDict, total=False):
    """Options for exporting resources."""
    include_secrets: bool
    include_service_account_secrets: bool
    namespace: str
    selector: Optional[str]
    only: Optional[Sequence[str]]
    exclude: Optional[Sequence[str]]
    output_dir: str
    force: bool
    lint: bool
    prefix: str
    chart_version: str
    app_version: str
    kubeconfig: Optional[str]
    context: Optional[str]


class ResourceFilter(TypedDict, total=False):
    """Filters for selecting resources."""
    namespace: str
    selector: Optional[str]
    resource_types: Optional[Sequence[str]]
    names: Optional[Sequence[str]]


# Protocol for resource collection
class ResourceCollectorProtocol(Protocol):
    """Protocol for collecting Kubernetes resources."""
    
    def list_resources(
        self, 
        resource_type: str, 
        filters: ResourceFilter
    ) -> K8sObjectList:
        """List resources of a given type with filters."""
        ...
    
    def get_resource(
        self, 
        resource_type: str, 
        name: str, 
        namespace: str
    ) -> Optional[K8sObject]:
        """Get a specific resource."""
        ...


# Protocol for manifest cleaning
class ManifestCleanerProtocol(Protocol):
    """Protocol for cleaning Kubernetes manifests."""
    
    def clean_manifest(self, manifest: K8sObject) -> K8sObject:
        """Clean a manifest for export."""
        ...
    
    def clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Clean metadata fields."""
        ...


# Protocol for chart generation
class ChartGeneratorProtocol(Protocol):
    """Protocol for generating Helm charts."""
    
    def create_chart_structure(self, output_path: str, release_name: str) -> None:
        """Create basic chart directory structure."""
        ...
    
    def write_manifest(
        self, 
        manifest: K8sObject, 
        output_path: str
    ) -> str:
        """Write a manifest to a template file."""
        ...


# Progress tracking types
class ProgressCallback(Protocol):
    """Callback for progress updates."""
    
    def update(self, current: int, total: int, message: str = "") -> None:
        """Update progress."""
        ...


class ExportResult(TypedDict):
    """Result of an export operation."""
    success: bool
    exported_count: int
    failed_count: int
    errors: List[str]
    output_path: str


class ResourceMetrics(TypedDict):
    """Metrics for exported resources."""
    resource_type: str
    count: int
    size_bytes: int
    processing_time: float


# Configuration types
class RetryConfig(TypedDict, total=False):
    """Configuration for retry behavior."""
    max_retries: int
    timeout_seconds: int
    backoff_base: float
    backoff_max: float


class ExporterConfig(TypedDict, total=False):
    """Configuration for the exporter."""
    supported_resources: List[str]
    cleanup_rules: Dict[str, List[str]]
    retry_config: RetryConfig
    progress_enabled: bool
    page_size: int
    parallel_exports: bool
    max_workers: int


# Selection and planning types
class ResourceSelection(TypedDict):
    """Selected resources for export."""
    resource_type: str
    names: List[str]


class ExportPlan(TypedDict):
    """Plan for exporting resources."""
    workloads: List[ResourceSelection]
    supporting_resources: List[ResourceSelection]
    total_resources: int
    estimated_size: Optional[int]


# Interactive UI types
class UIOption(TypedDict):
    """Option for interactive selection."""
    label: str
    value: str
    selected: bool
    metadata: Optional[Dict[str, Any]]


class SelectionResult(TypedDict):
    """Result of interactive selection."""
    selected_values: List[str]
    cancelled: bool
    metadata: Optional[Dict[str, Any]]


# Error types
class ExportError(Exception):
    """Base exception for export operations."""
    
    def __init__(self, message: str, resource_type: Optional[str] = None):
        super().__init__(message)
        self.resource_type = resource_type


class KubectlError(ExportError):
    """Error from kubectl operations."""
    
    def __init__(self, message: str, command: Optional[List[str]] = None):
        super().__init__(message)
        self.command = command


class ManifestValidationError(ExportError):
    """Error validating manifest structure."""
    
    def __init__(self, message: str, manifest: Optional[K8sObject] = None):
        super().__init__(message)
        self.manifest = manifest


class ChartGenerationError(ExportError):
    """Error generating Helm chart."""
    pass


# Type aliases for common patterns
ResourceName = str
ResourceType = str
NamespaceFilter = Optional[str]
LabelSelector = Optional[str]
ManifestDict = Dict[str, Any]
ResourceDict = Dict[ResourceType, List[ManifestDict]]