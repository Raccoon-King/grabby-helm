"""Interactive selection helpers for the Rancher Helm exporter."""
from __future__ import annotations

import curses
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, MutableMapping, Optional, Sequence, Set, Tuple


@dataclass
class SelectionPlan:
    """Resources that should be exported as captured from the interactive flow."""

    names_by_resource: Dict[str, Set[str]] = field(default_factory=dict)

    def add(self, resource: str, names: Iterable[str]) -> None:
        cleaned = {str(name) for name in names if str(name)}
        if cleaned:
            self.names_by_resource.setdefault(resource, set()).update(cleaned)

    def resources(self) -> Set[str]:
        return set(self.names_by_resource)

    def to_dict(self) -> Dict[str, Set[str]]:
        return {resource: set(names) for resource, names in self.names_by_resource.items()}

    def includes_secrets(self) -> bool:
        names = self.names_by_resource.get("secrets")
        return bool(names)


def build_interactive_plan(exporter: "_ResourceLister") -> SelectionPlan:
    """Capture the operator's desired resources via an interactive checklist."""

    workload_resources = ("deployments", "statefulsets", "daemonsets", "cronjobs", "jobs")
    workloads_by_resource: Dict[str, Dict[str, MutableMapping[str, object]]] = {}
    for resource in workload_resources:
        manifests = exporter.list_resource_items(resource)
        named_manifests = {
            name: manifest
            for manifest in manifests
            if (name := _manifest_name(manifest))
        }
        if named_manifests:
            workloads_by_resource[resource] = named_manifests

    if not workloads_by_resource:
        raise SystemExit("No workloads were found in the namespace. Nothing to export.")

    selected_workloads = _ask_workloads(workloads_by_resource)
    if not selected_workloads:
        raise SystemExit("No workloads selected. Aborting interactive session.")

    plan = SelectionPlan()
    selected_workload_manifests: List[MutableMapping[str, object]] = []
    for resource, name in selected_workloads:
        manifest = workloads_by_resource[resource][name]
        plan.add(resource, [name])
        selected_workload_manifests.append(manifest)

    configmap_items = exporter.list_resource_items("configmaps")
    configmap_names = _manifest_names(configmap_items)
    default_configmaps = sorted(
        _collect_configmaps(selected_workload_manifests).intersection(configmap_names)
    )
    chosen_configmaps = _ask_multiple(
        "Select ConfigMaps to include",
        configmap_names,
        default=default_configmaps,
    )
    plan.add("configmaps", chosen_configmaps)

    secret_items = exporter.list_resource_items("secrets")
    secret_names = _manifest_names(secret_items)
    default_secrets = sorted(
        _collect_secrets(selected_workload_manifests).intersection(secret_names)
    )
    chosen_secrets = _ask_multiple(
        "Select Secrets to include",
        secret_names,
        default=default_secrets,
    )
    plan.add("secrets", chosen_secrets)

    service_account_items = exporter.list_resource_items("serviceaccounts")
    service_account_names = _manifest_names(service_account_items)
    default_service_accounts = sorted(
        _collect_service_accounts(selected_workload_manifests).intersection(
            service_account_names
        )
    )
    chosen_service_accounts = _ask_multiple(
        "Select ServiceAccounts to include",
        service_account_names,
        default=default_service_accounts,
    )
    plan.add("serviceaccounts", chosen_service_accounts)

    pvc_items = exporter.list_resource_items("persistentvolumeclaims")
    pvc_names = _manifest_names(pvc_items)
    default_pvcs = sorted(
        _collect_persistent_volume_claims(selected_workload_manifests).intersection(
            pvc_names
        )
    )
    chosen_pvcs = _ask_multiple(
        "Select PersistentVolumeClaims to include",
        pvc_names,
        default=default_pvcs,
    )
    plan.add("persistentvolumeclaims", chosen_pvcs)

    service_items = exporter.list_resource_items("services")
    service_names = _manifest_names(service_items)
    default_services = sorted(
        _services_matching_workloads(selected_workload_manifests, service_items)
    )
    chosen_services = _ask_multiple(
        "Select Services to include",
        service_names,
        default=default_services,
    )
    plan.add("services", chosen_services)

    ingress_items = exporter.list_resource_items("ingresses")
    ingress_names = _manifest_names(ingress_items)
    default_ingresses = sorted(
        _ingresses_for_services(
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

    return plan


class _ResourceLister:
    """Protocol-like helper to satisfy type-checkers."""

    def list_resource_items(self, resource: str) -> List[MutableMapping[str, object]]:  # pragma: no cover - typing only
        raise NotImplementedError


@dataclass
class _Option:
    label: str
    value: str


class _CheckboxPrompt:
    def __init__(
        self,
        title: str,
        options: Sequence[_Option],
        *,
        default: Optional[Sequence[str]] = None,
        minimum: int = 0,
    ) -> None:
        self.title = title
        self.options = list(options)
        self.minimum = max(0, int(minimum))
        default_values = {value for value in (default or []) if value is not None}
        self.selected = {option.value: option.value in default_values for option in self.options}
        self.cursor = 0
        self.offset = 0
        self.message: Optional[str] = None

    # Public API ---------------------------------------------------------
    def run(self, stdscr: "curses._CursesWindow") -> List[str]:
        curses.use_default_colors()
        stdscr.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:  # pragma: no cover - depends on terminal capabilities
            pass

        while True:
            stdscr.erase()
            max_y, max_x = stdscr.getmaxyx()
            self._render_header(stdscr, max_x)
            start_line = self._header_height()
            visible_count = max(1, max_y - start_line - 1)
            self._adjust_offset(visible_count)
            self._render_options(stdscr, max_x, start_line, visible_count)
            _addstr(
                stdscr,
                start_line + visible_count,
                0,
                self._footer_text(),
                curses.A_DIM,
            )
            stdscr.refresh()

            key = stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                self.cursor = (self.cursor - 1) % len(self.options)
                self.message = None
            elif key in (curses.KEY_DOWN, ord("j")):
                self.cursor = (self.cursor + 1) % len(self.options)
                self.message = None
            elif key in (curses.KEY_PPAGE,):
                self.cursor = max(self.cursor - visible_count, 0)
                self.message = None
            elif key in (curses.KEY_NPAGE,):
                self.cursor = min(self.cursor + visible_count, len(self.options) - 1)
                self.message = None
            elif key == ord(" "):
                self._toggle_current()
                self.message = None
            elif key in (ord("a"), ord("A")):
                self._toggle_all()
                self.message = None
            elif key in (curses.KEY_ENTER, 10, 13):
                selected = self._selected_values()
                if len(selected) >= self.minimum:
                    return selected
                self.message = (
                    "Select at least one option."
                    if self.minimum <= 1
                    else f"Select at least {self.minimum} options."
                )
            elif key in (ord("q"), ord("Q"), 27):
                raise SystemExit("Interactive session aborted by user.")
            elif key == curses.KEY_RESIZE:  # pragma: no cover - terminal specific
                pass
            else:  # Ignore all other keys
                self.message = None

    # Rendering helpers --------------------------------------------------
    def _render_header(self, stdscr: "curses._CursesWindow", max_x: int) -> None:
        title = _truncate(self.title, max_x - 1)
        _addstr(stdscr, 0, 0, title, curses.A_BOLD)
        instructions = "Use ↑/↓ (or j/k) to move, space to toggle, enter to confirm, A to toggle all, Q to abort."
        _addstr(stdscr, 1, 0, _truncate(instructions, max_x - 1), curses.A_DIM)
        if self.message:
            _addstr(stdscr, 2, 0, _truncate(self.message, max_x - 1), curses.A_BOLD)

    def _header_height(self) -> int:
        return 3 if self.message else 2

    def _render_options(
        self,
        stdscr: "curses._CursesWindow",
        max_x: int,
        start_line: int,
        visible_count: int,
    ) -> None:
        end_index = min(self.offset + visible_count, len(self.options))
        for visual_index, option_index in enumerate(range(self.offset, end_index)):
            option = self.options[option_index]
            marker = "[x]" if self.selected.get(option.value) else "[ ]"
            text = f"{marker} {option.label}"
            attr = curses.A_REVERSE if option_index == self.cursor else curses.A_NORMAL
            _addstr(
                stdscr,
                start_line + visual_index,
                0,
                _truncate(text, max_x - 1),
                attr,
            )

    def _footer_text(self) -> str:
        selected_count = len(self._selected_values())
        total = len(self.options)
        return f"Selected {selected_count}/{total}. Press q to cancel."

    def _adjust_offset(self, visible_count: int) -> None:
        if self.cursor < self.offset:
            self.offset = self.cursor
        elif self.cursor >= self.offset + visible_count:
            self.offset = self.cursor - visible_count + 1

    def _toggle_current(self) -> None:
        option = self.options[self.cursor]
        self.selected[option.value] = not self.selected.get(option.value, False)

    def _toggle_all(self) -> None:
        values = list(self.selected)
        should_select = not all(self.selected[value] for value in values)
        for value in values:
            self.selected[value] = should_select

    def _selected_values(self) -> List[str]:
        return [option.value for option in self.options if self.selected.get(option.value)]


def _ask_workloads(
    workloads: Dict[str, Dict[str, MutableMapping[str, object]]]
) -> List[Tuple[str, str]]:
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
    options: Sequence[str],
    *,
    default: Optional[Sequence[str]] = None,
) -> List[str]:
    if not options:
        return []
    option_objects = [_Option(label=option, value=option) for option in sorted(options)]
    prompt = _CheckboxPrompt(title, option_objects, default=default or [])
    return _run_prompt(prompt)


def _run_prompt(prompt: _CheckboxPrompt) -> List[str]:
    return curses.wrapper(prompt.run)


def _truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return text[:1]
    return text[: width - 1] + "…"


def _addstr(stdscr: "curses._CursesWindow", y: int, x: int, text: str, attr: int = 0) -> None:
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:  # pragma: no cover - terminal specific bounds handling
        pass


def _manifest_name(manifest: MutableMapping[str, object]) -> str:
    metadata = manifest.get("metadata")
    if isinstance(metadata, MutableMapping):
        name = metadata.get("name")
        if isinstance(name, str):
            return name
    return ""


def _manifest_names(items: Sequence[MutableMapping[str, object]]) -> List[str]:
    names = {_manifest_name(item) for item in items}
    names.discard("")
    return sorted(names)


def _replica_count(manifest: MutableMapping[str, object]) -> int:
    spec = manifest.get("spec")
    if isinstance(spec, MutableMapping):
        replicas = spec.get("replicas")
        if isinstance(replicas, int):
            return replicas
    return 1


def _collect_configmaps(deployments: Sequence[MutableMapping[str, object]]) -> Set[str]:
    names: Set[str] = set()
    for manifest in deployments:
        pod_spec = _pod_spec(manifest)
        volumes = pod_spec.get("volumes")
        if isinstance(volumes, list):
            for volume in volumes:
                if isinstance(volume, MutableMapping):
                    config_map = volume.get("configMap")
                    if isinstance(config_map, MutableMapping):
                        name = config_map.get("name")
                        if isinstance(name, str):
                            names.add(name)
                    projected = volume.get("projected")
                    if isinstance(projected, MutableMapping):
                        sources = projected.get("sources")
                        if isinstance(sources, list):
                            for source in sources:
                                if isinstance(source, MutableMapping):
                                    ref = source.get("configMap")
                                    if isinstance(ref, MutableMapping):
                                        name = ref.get("name")
                                        if isinstance(name, str):
                                            names.add(name)
        for container in _containers_from_spec(pod_spec):
            env_from = container.get("envFrom")
            if isinstance(env_from, list):
                for entry in env_from:
                    if isinstance(entry, MutableMapping):
                        ref = entry.get("configMapRef")
                        if isinstance(ref, MutableMapping):
                            name = ref.get("name")
                            if isinstance(name, str):
                                names.add(name)
            env = container.get("env")
            if isinstance(env, list):
                for entry in env:
                    if isinstance(entry, MutableMapping):
                        value_from = entry.get("valueFrom")
                        if isinstance(value_from, MutableMapping):
                            config_ref = value_from.get("configMapKeyRef")
                            if isinstance(config_ref, MutableMapping):
                                name = config_ref.get("name")
                                if isinstance(name, str):
                                    names.add(name)
    return names


def _collect_secrets(deployments: Sequence[MutableMapping[str, object]]) -> Set[str]:
    names: Set[str] = set()
    for manifest in deployments:
        pod_spec = _pod_spec(manifest)
        volumes = pod_spec.get("volumes")
        if isinstance(volumes, list):
            for volume in volumes:
                if isinstance(volume, MutableMapping):
                    secret = volume.get("secret")
                    if isinstance(secret, MutableMapping):
                        name = secret.get("secretName") or secret.get("name")
                        if isinstance(name, str):
                            names.add(name)
                    projected = volume.get("projected")
                    if isinstance(projected, MutableMapping):
                        sources = projected.get("sources")
                        if isinstance(sources, list):
                            for source in sources:
                                if isinstance(source, MutableMapping):
                                    ref = source.get("secret")
                                    if isinstance(ref, MutableMapping):
                                        name = ref.get("name")
                                        if isinstance(name, str):
                                            names.add(name)
        image_pull_secrets = pod_spec.get("imagePullSecrets")
        if isinstance(image_pull_secrets, list):
            for pull_secret in image_pull_secrets:
                if isinstance(pull_secret, MutableMapping):
                    name = pull_secret.get("name")
                    if isinstance(name, str):
                        names.add(name)
        for container in _containers_from_spec(pod_spec):
            env_from = container.get("envFrom")
            if isinstance(env_from, list):
                for entry in env_from:
                    if isinstance(entry, MutableMapping):
                        ref = entry.get("secretRef")
                        if isinstance(ref, MutableMapping):
                            name = ref.get("name")
                            if isinstance(name, str):
                                names.add(name)
            env = container.get("env")
            if isinstance(env, list):
                for entry in env:
                    if isinstance(entry, MutableMapping):
                        value_from = entry.get("valueFrom")
                        if isinstance(value_from, MutableMapping):
                            secret_ref = value_from.get("secretKeyRef")
                            if isinstance(secret_ref, MutableMapping):
                                name = secret_ref.get("name")
                                if isinstance(name, str):
                                    names.add(name)
    return names


def _format_workload_label(resource: str, manifest: MutableMapping[str, object]) -> str:
    name = _manifest_name(manifest) or "<unknown>"
    kind = manifest.get("kind")
    if not isinstance(kind, str):
        kind = resource.rstrip("s").title()

    details: List[str] = []
    if resource in {"deployments", "statefulsets"}:
        replicas = _replica_count(manifest)
        details.append(f"{replicas} replica{'s' if replicas != 1 else ''}")
    elif resource == "cronjobs":
        spec = manifest.get("spec")
        if isinstance(spec, MutableMapping):
            schedule = spec.get("schedule")
            if isinstance(schedule, str) and schedule:
                details.append(f"schedule {schedule}")
    elif resource == "jobs":
        spec = manifest.get("spec")
        if isinstance(spec, MutableMapping):
            completions = spec.get("completions")
            if isinstance(completions, int):
                details.append(f"{completions} completion{'s' if completions != 1 else ''}")

    suffix = f" ({', '.join(details)})" if details else ""
    return f"{kind} {name}{suffix}"


def _services_matching_workloads(
    workloads: Sequence[MutableMapping[str, object]],
    services: Sequence[MutableMapping[str, object]],
) -> Set[str]:
    matches: Set[str] = set()
    for service in services:
        selector = service.get("spec")
        if isinstance(selector, MutableMapping):
            selector = selector.get("selector")
        if not isinstance(selector, MutableMapping) or not selector:
            continue
        for deployment in workloads:
            labels = _pod_labels(deployment)
            if labels and all(labels.get(key) == value for key, value in selector.items()):
                name = _manifest_name(service)
                if name:
                    matches.add(name)
                break
    return matches


def _collect_service_accounts(
    workloads: Sequence[MutableMapping[str, object]]
) -> Set[str]:
    names: Set[str] = set()
    for manifest in workloads:
        pod_spec = _pod_spec(manifest)
        service_account = pod_spec.get("serviceAccountName") or pod_spec.get("serviceAccount")
        if isinstance(service_account, str) and service_account:
            names.add(service_account)
    return names


def _collect_persistent_volume_claims(
    workloads: Sequence[MutableMapping[str, object]]
) -> Set[str]:
    names: Set[str] = set()
    for manifest in workloads:
        pod_spec = _pod_spec(manifest)
        volumes = pod_spec.get("volumes")
        if isinstance(volumes, list):
            for volume in volumes:
                if not isinstance(volume, MutableMapping):
                    continue
                claim = volume.get("persistentVolumeClaim")
                if isinstance(claim, MutableMapping):
                    name = claim.get("claimName") or claim.get("name")
                    if isinstance(name, str) and name:
                        names.add(name)
    return names


def _ingresses_for_services(
    ingresses: Sequence[MutableMapping[str, object]],
    services: Set[str],
) -> Set[str]:
    if not services:
        return set()

    matches: Set[str] = set()
    for ingress in ingresses:
        referenced = _services_referenced_by_ingress(ingress)
        if referenced.intersection(services):
            name = _manifest_name(ingress)
            if name:
                matches.add(name)
    return matches


def _services_referenced_by_ingress(
    ingress: MutableMapping[str, object]
) -> Set[str]:
    names: Set[str] = set()
    spec = ingress.get("spec")
    if not isinstance(spec, MutableMapping):
        return names

    default_backend = spec.get("defaultBackend")
    names.update(_services_from_backend(default_backend))

    rules = spec.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, MutableMapping):
                continue
            http = rule.get("http")
            if not isinstance(http, MutableMapping):
                continue
            paths = http.get("paths")
            if isinstance(paths, list):
                for path in paths:
                    if isinstance(path, MutableMapping):
                        backend = path.get("backend")
                        names.update(_services_from_backend(backend))
    return names


def _services_from_backend(backend: object) -> Set[str]:
    names: Set[str] = set()
    if not isinstance(backend, MutableMapping):
        return names

    service = backend.get("service")
    if isinstance(service, MutableMapping):
        name = service.get("name")
        if isinstance(name, str) and name:
            names.add(name)

    legacy_name = backend.get("serviceName")
    if isinstance(legacy_name, str) and legacy_name:
        names.add(legacy_name)

    return names


def _pod_spec(manifest: MutableMapping[str, object]) -> MutableMapping[str, object]:
    spec = manifest.get("spec")
    if not isinstance(spec, MutableMapping):
        return {}
    job_template = spec.get("jobTemplate")
    if isinstance(job_template, MutableMapping):
        job_spec = job_template.get("spec")
        if isinstance(job_spec, MutableMapping):
            template = job_spec.get("template")
            if isinstance(template, MutableMapping):
                template_spec = template.get("spec")
                if isinstance(template_spec, MutableMapping):
                    return template_spec
    template = spec.get("template")
    if isinstance(template, MutableMapping):
        template_spec = template.get("spec")
        if isinstance(template_spec, MutableMapping):
            return template_spec
    return {}


def _containers_from_spec(pod_spec: MutableMapping[str, object]) -> Iterator[MutableMapping[str, object]]:
    for key in ("containers", "initContainers", "ephemeralContainers"):
        containers = pod_spec.get(key)
        if isinstance(containers, list):
            for container in containers:
                if isinstance(container, MutableMapping):
                    yield container


def _pod_labels(manifest: MutableMapping[str, object]) -> Dict[str, str]:
    spec = manifest.get("spec")
    if not isinstance(spec, MutableMapping):
        return {}
    template = spec.get("template")
    if not isinstance(template, MutableMapping):
        job_template = spec.get("jobTemplate")
        if isinstance(job_template, MutableMapping):
            job_spec = job_template.get("spec")
            if isinstance(job_spec, MutableMapping):
                template = job_spec.get("template")
    if not isinstance(template, MutableMapping):
        return {}
    metadata = template.get("metadata")
    if not isinstance(metadata, MutableMapping):
        return {}
    labels = metadata.get("labels")
    if not isinstance(labels, MutableMapping):
        return {}
    clean_labels: Dict[str, str] = {}
    for key, value in labels.items():
        if isinstance(key, str) and isinstance(value, str):
            clean_labels[key] = value
    return clean_labels


__all__ = ["SelectionPlan", "build_interactive_plan"]
