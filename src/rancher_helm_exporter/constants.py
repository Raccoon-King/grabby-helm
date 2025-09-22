"""Constants for Kubernetes field names and configuration values."""
from __future__ import annotations

from typing import Final, Sequence

# Kubernetes API field names
class K8sFields:
    """Standard Kubernetes resource field names."""
    
    # Top-level fields
    API_VERSION: Final[str] = "apiVersion"
    KIND: Final[str] = "kind"
    METADATA: Final[str] = "metadata"
    SPEC: Final[str] = "spec"
    STATUS: Final[str] = "status"
    
    # Metadata fields
    NAME: Final[str] = "name"
    NAMESPACE: Final[str] = "namespace"
    LABELS: Final[str] = "labels"
    ANNOTATIONS: Final[str] = "annotations"
    CREATION_TIMESTAMP: Final[str] = "creationTimestamp"
    DELETION_TIMESTAMP: Final[str] = "deletionTimestamp"
    DELETION_GRACE_PERIOD: Final[str] = "deletionGracePeriodSeconds"
    GENERATE_NAME: Final[str] = "generateName"
    GENERATION: Final[str] = "generation"
    MANAGED_FIELDS: Final[str] = "managedFields"
    OWNER_REFERENCES: Final[str] = "ownerReferences"
    RESOURCE_VERSION: Final[str] = "resourceVersion"
    SELF_LINK: Final[str] = "selfLink"
    UID: Final[str] = "uid"
    
    # Spec fields
    TEMPLATE: Final[str] = "template"
    SELECTOR: Final[str] = "selector"
    REPLICAS: Final[str] = "replicas"
    CONTAINERS: Final[str] = "containers"
    INIT_CONTAINERS: Final[str] = "initContainers"
    EPHEMERAL_CONTAINERS: Final[str] = "ephemeralContainers"
    VOLUMES: Final[str] = "volumes"
    SERVICE_ACCOUNT_NAME: Final[str] = "serviceAccountName"
    SERVICE_ACCOUNT: Final[str] = "serviceAccount"
    IMAGE_PULL_SECRETS: Final[str] = "imagePullSecrets"
    
    # Container fields
    ENV: Final[str] = "env"
    ENV_FROM: Final[str] = "envFrom"
    VALUE_FROM: Final[str] = "valueFrom"
    
    # Volume fields
    CONFIG_MAP: Final[str] = "configMap"
    SECRET: Final[str] = "secret"
    SECRET_NAME: Final[str] = "secretName"
    PERSISTENT_VOLUME_CLAIM: Final[str] = "persistentVolumeClaim"
    CLAIM_NAME: Final[str] = "claimName"
    PROJECTED: Final[str] = "projected"
    SOURCES: Final[str] = "sources"
    
    # Reference fields
    CONFIG_MAP_REF: Final[str] = "configMapRef"
    SECRET_REF: Final[str] = "secretRef"
    CONFIG_MAP_KEY_REF: Final[str] = "configMapKeyRef"
    SECRET_KEY_REF: Final[str] = "secretKeyRef"
    
    # Service fields
    CLUSTER_IP: Final[str] = "clusterIP"
    CLUSTER_IPS: Final[str] = "clusterIPs"
    IP_FAMILIES: Final[str] = "ipFamilies"
    IP_FAMILY_POLICY: Final[str] = "ipFamilyPolicy"
    SESSION_AFFINITY_CONFIG: Final[str] = "sessionAffinityConfig"
    TYPE: Final[str] = "type"
    
    # Job/CronJob fields
    JOB_TEMPLATE: Final[str] = "jobTemplate"
    SCHEDULE: Final[str] = "schedule"
    COMPLETIONS: Final[str] = "completions"
    
    # Ingress fields
    DEFAULT_BACKEND: Final[str] = "defaultBackend"
    RULES: Final[str] = "rules"
    HTTP: Final[str] = "http"
    PATHS: Final[str] = "paths"
    BACKEND: Final[str] = "backend"
    SERVICE: Final[str] = "service"
    SERVICE_NAME: Final[str] = "serviceName"  # Legacy field
    
    # PVC fields
    VOLUME_NAME: Final[str] = "volumeName"
    DATA_SOURCE: Final[str] = "dataSource"
    DATA_SOURCE_REF: Final[str] = "dataSourceRef"


# Resource types
class ResourceTypes:
    """Supported Kubernetes resource types."""
    
    DEPLOYMENTS: Final[str] = "deployments"
    STATEFUL_SETS: Final[str] = "statefulsets"
    DAEMON_SETS: Final[str] = "daemonsets"
    CRON_JOBS: Final[str] = "cronjobs"
    JOBS: Final[str] = "jobs"
    SERVICES: Final[str] = "services"
    CONFIG_MAPS: Final[str] = "configmaps"
    SECRETS: Final[str] = "secrets"
    SERVICE_ACCOUNTS: Final[str] = "serviceaccounts"
    PERSISTENT_VOLUME_CLAIMS: Final[str] = "persistentvolumeclaims"
    INGRESSES: Final[str] = "ingresses"


# Supported resource types
SUPPORTED_RESOURCES: Final[Sequence[str]] = (
    ResourceTypes.DEPLOYMENTS,
    ResourceTypes.STATEFUL_SETS,
    ResourceTypes.DAEMON_SETS,
    ResourceTypes.CRON_JOBS,
    ResourceTypes.JOBS,
    ResourceTypes.SERVICES,
    ResourceTypes.CONFIG_MAPS,
    ResourceTypes.SECRETS,
    ResourceTypes.SERVICE_ACCOUNTS,
    ResourceTypes.PERSISTENT_VOLUME_CLAIMS,
    ResourceTypes.INGRESSES,
)

# Workload resource types
WORKLOAD_RESOURCES: Final[Sequence[str]] = (
    ResourceTypes.DEPLOYMENTS,
    ResourceTypes.STATEFUL_SETS,
    ResourceTypes.DAEMON_SETS,
    ResourceTypes.CRON_JOBS,
    ResourceTypes.JOBS,
)

# Supporting resource types
SUPPORTING_RESOURCES: Final[Sequence[str]] = (
    ResourceTypes.CONFIG_MAPS,
    ResourceTypes.SECRETS,
    ResourceTypes.SERVICES,
    ResourceTypes.SERVICE_ACCOUNTS,
    ResourceTypes.PERSISTENT_VOLUME_CLAIMS,
    ResourceTypes.INGRESSES,
)

# Fields to remove from metadata during cleaning
METADATA_FIELDS_TO_DROP: Final[Sequence[str]] = (
    K8sFields.CREATION_TIMESTAMP,
    K8sFields.DELETION_GRACE_PERIOD,
    K8sFields.DELETION_TIMESTAMP,
    K8sFields.GENERATE_NAME,
    K8sFields.GENERATION,
    K8sFields.MANAGED_FIELDS,
    K8sFields.OWNER_REFERENCES,
    K8sFields.RESOURCE_VERSION,
    K8sFields.SELF_LINK,
    K8sFields.UID,
)

# Secret types to skip by default
DEFAULT_SECRET_TYPES_TO_SKIP: Final[Sequence[str]] = (
    "kubernetes.io/service-account-token",
)

# Annotation prefixes to remove
KUBECTL_ANNOTATION_PREFIXES: Final[Sequence[str]] = (
    "kubectl.kubernetes.io",
)

KUBECTL_ANNOTATION_SUFFIXES: Final[Sequence[str]] = (
    "last-applied-configuration",
)

# Service fields to clean
SERVICE_FIELDS_TO_CLEAN: Final[Sequence[str]] = (
    K8sFields.CLUSTER_IP,
    K8sFields.CLUSTER_IPS,
    K8sFields.IP_FAMILIES,
    K8sFields.IP_FAMILY_POLICY,
    K8sFields.SESSION_AFFINITY_CONFIG,
)

# Pod controller fields to clean
POD_CONTROLLER_FIELDS_TO_CLEAN: Final[Sequence[str]] = (
    "revisionHistoryLimit",
    "progressDeadlineSeconds",
)

# PVC fields to clean
PVC_FIELDS_TO_CLEAN: Final[Sequence[str]] = (
    K8sFields.VOLUME_NAME,
    K8sFields.DATA_SOURCE,
    K8sFields.DATA_SOURCE_REF,
)

# PVC annotations to remove
PVC_ANNOTATIONS_TO_REMOVE: Final[Sequence[str]] = (
    "pv.kubernetes.io/bind-completed",
    "pv.kubernetes.io/bound-by-controller",
)

# Special labels to remove
SPECIAL_LABELS_TO_REMOVE: Final[Sequence[str]] = (
    "pod-template-hash",
)

# Default values
DEFAULT_CHART_VERSION: Final[str] = "0.1.0"
DEFAULT_APP_VERSION: Final[str] = "1.0.0"
DEFAULT_NAMESPACE: Final[str] = "default"
DEFAULT_OUTPUT_DIR: Final[str] = "./k8"

# Retry configuration
DEFAULT_RETRY_COUNT: Final[int] = 3
DEFAULT_TIMEOUT_SECONDS: Final[int] = 30
DEFAULT_RETRY_BACKOFF_BASE: Final[float] = 2.0

# Progress tracking
DEFAULT_PAGE_SIZE: Final[int] = 100