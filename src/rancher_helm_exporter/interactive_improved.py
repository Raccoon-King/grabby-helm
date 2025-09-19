"""Improved interactive selection using the new utilities."""
from __future__ import annotations

import curses
from dataclasses import dataclass, field
from typing import Dict, List, MutableMapping, Optional, Set, Tuple

from .constants import WORKLOAD_RESOURCES
from .utils import ManifestTraverser, ResourceReferenceExtractor


@dataclass
class SelectionPlan:
    """Resources that should be exported as captured from the interactive flow."""

    names_by_resource: Dict[str, Set[str]] = field(default_factory=dict)

    def add(self, resource: str, names: List[str]) -> None:
        """Add resource names to the selection."""
        cleaned = {str(name) for name in names if str(name)}
        if cleaned:
            self.names_by_resource.setdefault(resource, set()).update(cleaned)

    def resources(self) -> Set[str]:
        """Get all selected resource types."""
        return set(self.names_by_resource)

    def to_dict(self) -> Dict[str, Set[str]]:
        """Convert to dictionary format."""
        return {resource: set(names) for resource, names in self.names_by_resource.items()}

    def includes_secrets(self) -> bool:
        """Check if secrets are included in the selection."""
        names = self.names_by_resource.get("secrets")
        return bool(names)


def build_interactive_plan(exporter) -> SelectionPlan:
    """
    Capture the operator's desired resources via an interactive checklist.
    
    Args:
        exporter: Exporter instance with list_resource_items method
        
    Returns:
        SelectionPlan with selected resources
    """
    # Collect workloads
    workloads_by_resource: Dict[str, Dict[str, MutableMapping[str, object]]] = {}
    for resource in WORKLOAD_RESOURCES:
        manifests = exporter.list_resource_items(resource)
        named_manifests = {
            name: manifest
            for manifest in manifests
            if (name := ManifestTraverser.get_manifest_name(manifest))
        }
        if named_manifests:
            workloads_by_resource[resource] = named_manifests

    if not workloads_by_resource:
        raise SystemExit("No workloads were found in the namespace. Nothing to export.")

    # Interactive workload selection
    selected_workloads = _ask_workloads(workloads_by_resource)
    if not selected_workloads:
        raise SystemExit("No workloads selected. Aborting interactive session.")

    plan = SelectionPlan()
    selected_workload_manifests: List[MutableMapping[str, object]] = []
    
    for resource, name in selected_workloads:
        manifest = workloads_by_resource[resource][name]
        plan.add(resource, [name])
        selected_workload_manifests.append(manifest)

    # Collect and select supporting resources
    _select_supporting_resources(exporter, plan, selected_workload_manifests)

    return plan


def _select_supporting_resources(
    exporter,
    plan: SelectionPlan,
    selected_workloads: List[MutableMapping[str, object]],
) -> None:
    """Select supporting resources for the workloads."""
    
    # ConfigMaps
    configmap_items = exporter.list_resource_items("configmaps")
    configmap_names = _get_manifest_names(configmap_items)
    default_configmaps = sorted(
        ResourceReferenceExtractor.extract_configmap_references(selected_workloads)
        .intersection(configmap_names)
    )
    chosen_configmaps = _ask_multiple(
        "Select ConfigMaps to include",
        configmap_names,
        default=default_configmaps,
    )
    plan.add("configmaps", chosen_configmaps)

    # Secrets
    secret_items = exporter.list_resource_items("secrets")
    secret_names = _get_manifest_names(secret_items)
    default_secrets = sorted(
        ResourceReferenceExtractor.extract_secret_references(selected_workloads)
        .intersection(secret_names)
    )
    chosen_secrets = _ask_multiple(
        "Select Secrets to include",
        secret_names,
        default=default_secrets,
    )
    plan.add("secrets", chosen_secrets)

    # ServiceAccounts
    service_account_items = exporter.list_resource_items("serviceaccounts")
    service_account_names = _get_manifest_names(service_account_items)
    default_service_accounts = sorted(
        ResourceReferenceExtractor.extract_service_account_references(selected_workloads)
        .intersection(service_account_names)
    )
    chosen_service_accounts = _ask_multiple(
        "Select ServiceAccounts to include",
        service_account_names,
        default=default_service_accounts,
    )
    plan.add("serviceaccounts", chosen_service_accounts)

    # PersistentVolumeClaims
    pvc_items = exporter.list_resource_items("persistentvolumeclaims")
    pvc_names = _get_manifest_names(pvc_items)
    default_pvcs = sorted(
        ResourceReferenceExtractor.extract_pvc_references(selected_workloads)
        .intersection(pvc_names)
    )
    chosen_pvcs = _ask_multiple(
        "Select PersistentVolumeClaims to include",
        pvc_names,
        default=default_pvcs,
    )
    plan.add("persistentvolumeclaims", chosen_pvcs)

    # Services
    service_items = exporter.list_resource_items("services")
    service_names = _get_manifest_names(service_items)
    default_services = sorted(
        ResourceReferenceExtractor.find_matching_services(selected_workloads, service_items)
    )
    chosen_services = _ask_multiple(
        "Select Services to include",
        service_names,
        default=default_services,
    )
    plan.add("services", chosen_services)

    # Ingresses
    ingress_items = exporter.list_resource_items("ingresses")
    ingress_names = _get_manifest_names(ingress_items)
    default_ingresses = sorted(
        ResourceReferenceExtractor.find_ingresses_for_services(
            ingress_items,
            set(chosen_services) if chosen_services else set(default_services),
        ).intersection(ingress_names)
    )
    chosen_ingresses = _ask_multiple(
        "Select Ingresses to include",
        ingress_names,
        default=default_ingresses,
    )
    plan.add("ingresses", chosen_ingresses)


def _get_manifest_names(items: List[MutableMapping[str, object]]) -> List[str]:
    """Extract names from a list of manifests."""
    names = {ManifestTraverser.get_manifest_name(item) for item in items}
    names.discard("")
    return sorted(names)


def _ask_workloads(
    workloads: Dict[str, Dict[str, MutableMapping[str, object]]]
) -> List[Tuple[str, str]]:
    """Ask user to select workloads interactively."""
    from .interactive import _CheckboxPrompt, _Option, _run_prompt
    
    options: List[_Option] = []
    value_map: Dict[str, Tuple[str, str]] = {}
    
    for resource in sorted(workloads):
        for name, manifest in sorted(workloads[resource].items()):
            label = _format_workload_label(resource, manifest)
            value = f"{resource}:{name}"
            value_map[value] = (resource, name)
            options.append(_Option(label=label, value=value))
    
    prompt = _CheckboxPrompt("Select workloads to export", options, minimum=1)
    chosen_values = _run_prompt(prompt)
    return [value_map[value] for value in chosen_values if value in value_map]


def _ask_multiple(
    title: str,
    options: List[str],
    *,
    default: Optional[List[str]] = None,
) -> List[str]:
    """Ask user to select multiple items from a list."""
    if not options:
        return []
    
    from .interactive import _CheckboxPrompt, _Option, _run_prompt
    
    option_objects = [_Option(label=option, value=option) for option in sorted(options)]
    prompt = _CheckboxPrompt(title, option_objects, default=default or [])
    return _run_prompt(prompt)


def _format_workload_label(resource: str, manifest: MutableMapping[str, object]) -> str:
    """Format a workload for display in the selection UI."""
    name = ManifestTraverser.get_manifest_name(manifest) or "<unknown>"
    kind = manifest.get("kind")
    if not isinstance(kind, str):
        kind = resource.rstrip("s").title()

    details: List[str] = []
    
    if resource in {"deployments", "statefulsets"}:
        replicas = ManifestTraverser.get_replica_count(manifest)
        details.append(f"{replicas} replica{'s' if replicas != 1 else ''}")
    elif resource == "cronjobs":
        schedule = ManifestTraverser.get_schedule(manifest)
        if schedule:
            details.append(f"schedule {schedule}")
    elif resource == "jobs":
        completions = ManifestTraverser.get_completions(manifest)
        if completions:
            details.append(f"{completions} completion{'s' if completions != 1 else ''}")

    suffix = f" ({', '.join(details)})" if details else ""
    return f"{kind} {name}{suffix}"