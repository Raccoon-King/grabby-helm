# RPM spec file for rancher-helm-exporter
# Build with: rpmbuild -ba rancher-helm-exporter.spec

%global pypi_name rancher-helm-exporter
%global pypi_version 2.0.0

Name:           python3-%{pypi_name}
Version:        %{pypi_version}
Release:        1%{?dist}
Summary:        Export live Kubernetes resources into Helm charts

License:        MIT
URL:            https://github.com/your-org/rancher-helm-exporter
Source0:        %{pypi_name}-%{pypi_version}.tar.gz

BuildArch:      noarch

# Build dependencies
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-pip
BuildRequires:  python3-wheel

# Runtime dependencies
Requires:       python3
Requires:       python3-pyyaml >= 6.0
Requires:       python3-rich >= 10.0.0

# Optional dependencies
Recommends:     kubectl
Recommends:     helm
Recommends:     bash-completion

# System user for service mode
Requires(pre):  shadow-utils
Requires:       systemd
%{?systemd_requires}

%description
Rancher Helm Exporter inspects existing Kubernetes workloads deployed through 
Rancher and reconstructs them into Helm charts. The tool can export deployments, 
services, configmaps, secrets, and other resources while cleaning Kubernetes-managed 
metadata to create portable Helm charts.

Features:
- Export live Kubernetes resources to Helm charts
- Interactive resource selection
- Test chart generation with -test suffixed names
- Robust kubectl interface with retry logic
- Air-gapped environment support
- Rich progress tracking and validation

%package doc
Summary:        Documentation for %{name}
BuildArch:      noarch

%description doc
Documentation and examples for rancher-helm-exporter.

%prep
%autosetup -n %{pypi_name}-%{pypi_version}

%build
%py3_build

%install
%py3_install

# Install executable script
install -Dm755 -t %{buildroot}%{_bindir} scripts/rancher-helm-exporter

# Install configuration files
install -Dm644 config.example.yaml %{buildroot}%{_sysconfdir}/%{pypi_name}/config.yaml

# Install systemd service files
install -Dm644 scripts/systemd/rancher-helm-exporter@.service \
    %{buildroot}%{_unitdir}/rancher-helm-exporter@.service
install -Dm644 scripts/systemd/rancher-helm-exporter.timer \
    %{buildroot}%{_unitdir}/rancher-helm-exporter.timer

# Create basic non-parameterized service
cat > %{buildroot}%{_unitdir}/rancher-helm-exporter.service << 'EOF'
[Unit]
Description=Rancher Helm Exporter
Documentation=https://github.com/your-org/rancher-helm-exporter
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=rancher-exporter
Group=rancher-exporter
WorkingDirectory=/var/lib/rancher-helm-exporter
Environment=HOME=/var/lib/rancher-helm-exporter
Environment=XDG_CONFIG_HOME=/etc/rancher-helm-exporter
Environment=KUBECONFIG=/etc/rancher-helm-exporter/kubeconfig

ExecStart=%{_bindir}/rancher-helm-exporter default-app \
          --config /etc/rancher-helm-exporter/config.yaml \
          --output-dir /var/lib/rancher-helm-exporter/exports/default \
          --force

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/rancher-helm-exporter/exports
ReadOnlyPaths=/etc/rancher-helm-exporter

MemoryMax=512M
CPUQuota=50%

Restart=on-failure
RestartSec=30

StandardOutput=journal
StandardError=journal
SyslogIdentifier=rancher-helm-exporter

[Install]
WantedBy=multi-user.target
EOF

# Install bash completion
install -Dm644 scripts/bash_completion.sh \
    %{buildroot}%{_datadir}/bash-completion/completions/%{pypi_name}

# Install logrotate configuration
install -Dm644 /dev/stdin %{buildroot}%{_sysconfdir}/logrotate.d/%{pypi_name} << 'EOF'
/var/log/rancher-helm-exporter/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 rancher-exporter rancher-exporter
    postrotate
        /bin/systemctl reload-or-restart rancher-helm-exporter.service > /dev/null 2>&1 || true
    endscript
}
EOF

# Create directories
install -dm755 %{buildroot}%{_localstatedir}/lib/%{pypi_name}
install -dm755 %{buildroot}%{_localstatedir}/lib/%{pypi_name}/exports
install -dm755 %{buildroot}%{_localstatedir}/lib/%{pypi_name}/cache
install -dm755 %{buildroot}%{_localstatedir}/log/%{pypi_name}

%pre
# Create system user and group
getent group rancher-exporter >/dev/null || groupadd -r rancher-exporter
getent passwd rancher-exporter >/dev/null || \
    useradd -r -g rancher-exporter -d /var/lib/rancher-helm-exporter \
    -s /sbin/nologin -c "Rancher Helm Exporter service user" rancher-exporter
exit 0

%post
%systemd_post rancher-helm-exporter.service rancher-helm-exporter.timer

# Set directory ownership
chown -R rancher-exporter:rancher-exporter %{_localstatedir}/lib/%{pypi_name}
chown -R rancher-exporter:rancher-exporter %{_localstatedir}/log/%{pypi_name}

%preun
%systemd_preun rancher-helm-exporter.service rancher-helm-exporter.timer

%postun
%systemd_postun_with_restart rancher-helm-exporter.service

%files
%license LICENSE
%doc README.md CHANGELOG.md
%{python3_sitelib}/*
%{_bindir}/rancher-helm-exporter

# Configuration
%dir %{_sysconfdir}/%{pypi_name}
%config(noreplace) %{_sysconfdir}/%{pypi_name}/config.yaml
%config(noreplace) %{_sysconfdir}/logrotate.d/%{pypi_name}

# Systemd files
%{_unitdir}/rancher-helm-exporter.service
%{_unitdir}/rancher-helm-exporter@.service
%{_unitdir}/rancher-helm-exporter.timer

# Bash completion
%{_datadir}/bash-completion/completions/%{pypi_name}

# Runtime directories
%attr(755, rancher-exporter, rancher-exporter) %{_localstatedir}/lib/%{pypi_name}
%attr(755, rancher-exporter, rancher-exporter) %{_localstatedir}/lib/%{pypi_name}/exports
%attr(755, rancher-exporter, rancher-exporter) %{_localstatedir}/lib/%{pypi_name}/cache
%attr(750, rancher-exporter, rancher-exporter) %{_localstatedir}/log/%{pypi_name}

%files doc
%doc docs/*
%doc config.example.yaml
%doc scripts/

%changelog
* Wed Sep 18 2024 Grabby Helm Developer <ops@example.com> - 2.0.0-1
- Initial RPM package
- Added test chart generation functionality
- Enhanced error handling and retry logic
- Added Linux/Fedora optimizations
- Systemd service integration
- Bash completion support