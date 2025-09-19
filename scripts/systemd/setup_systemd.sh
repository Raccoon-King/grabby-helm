#!/bin/bash
# Setup script for systemd services for rancher-helm-exporter on Fedora

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

APP_NAME="rancher-helm-exporter"
SERVICE_USER="rancher-exporter"
SERVICE_GROUP="rancher-exporter"
CONFIG_DIR="/etc/$APP_NAME"
DATA_DIR="/var/lib/$APP_NAME"
LOG_DIR="/var/log/$APP_NAME"

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        print_status "Use: sudo $0"
        exit 1
    fi
}

create_service_user() {
    print_status "Creating service user and group..."
    
    # Create group if it doesn't exist
    if ! getent group "$SERVICE_GROUP" > /dev/null 2>&1; then
        groupadd --system "$SERVICE_GROUP"
        print_success "Created group: $SERVICE_GROUP"
    fi
    
    # Create user if it doesn't exist
    if ! getent passwd "$SERVICE_USER" > /dev/null 2>&1; then
        useradd --system --gid "$SERVICE_GROUP" --home-dir "$DATA_DIR" \
                --no-create-home --shell /usr/sbin/nologin \
                --comment "Rancher Helm Exporter service user" "$SERVICE_USER"
        print_success "Created user: $SERVICE_USER"
    fi
}

setup_directories() {
    print_status "Setting up directories..."
    
    # Create directories
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$DATA_DIR"/{exports,cache,tmp}
    mkdir -p "$LOG_DIR"
    
    # Set ownership
    chown root:root "$CONFIG_DIR"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR" "$LOG_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR"/*
    
    # Set permissions
    chmod 755 "$CONFIG_DIR"
    chmod 755 "$DATA_DIR"
    chmod 750 "$LOG_DIR"
    chmod 750 "$DATA_DIR"/{exports,cache,tmp}
    
    print_success "Directories configured"
}

install_systemd_files() {
    print_status "Installing systemd service files..."
    
    local script_dir="$(dirname "$0")"
    
    # Copy service files
    if [[ -f "$script_dir/rancher-helm-exporter@.service" ]]; then
        cp "$script_dir/rancher-helm-exporter@.service" /etc/systemd/system/
        print_success "Installed parameterized service"
    fi
    
    if [[ -f "$script_dir/rancher-helm-exporter.timer" ]]; then
        cp "$script_dir/rancher-helm-exporter.timer" /etc/systemd/system/
        print_success "Installed timer"
    fi
    
    # Create a simple non-parameterized service too
    cat > /etc/systemd/system/rancher-helm-exporter.service << EOF
[Unit]
Description=Rancher Helm Exporter
Documentation=https://github.com/your-org/rancher-helm-exporter
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$DATA_DIR
Environment=HOME=$DATA_DIR
Environment=XDG_CONFIG_HOME=$CONFIG_DIR
Environment=KUBECONFIG=$CONFIG_DIR/kubeconfig

# Default export command - override via drop-in files
ExecStart=/usr/local/bin/rancher-helm-exporter default-app \\
          --config $CONFIG_DIR/config.yaml \\
          --output-dir $DATA_DIR/exports/default \\
          --force

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR/exports
ReadOnlyPaths=$CONFIG_DIR

# Resource limits
MemoryMax=512M
CPUQuota=50%

# Restart policy
Restart=on-failure
RestartSec=30

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rancher-helm-exporter

[Install]
WantedBy=multi-user.target
EOF
    
    print_success "Created basic service file"
    
    # Reload systemd
    systemctl daemon-reload
    print_success "Systemd daemon reloaded"
}

create_sample_configs() {
    print_status "Creating sample configuration files..."
    
    # Main config
    cat > "$CONFIG_DIR/config.yaml" << 'EOF'
# Global configuration for rancher-helm-exporter service
# This file is used by systemd services

# Retry configuration
retry:
  max_retries: 5
  timeout_seconds: 60
  backoff_base: 2.0

# Cleaning configuration
cleaning:
  additional_metadata_fields: []
  annotation_patterns_to_remove: []
  remove_namespace_references: true

# Feature flags
enable_rich_progress: false  # Disable for service mode
enable_validation: true
enable_templating: false

# Progress settings
progress_update_interval: 1.0
progress_log_interval: 50
EOF
    
    # Sample app-specific config
    cat > "$CONFIG_DIR/myapp.yaml" << 'EOF'
# Sample configuration for myapp export
# Used with: systemctl start rancher-helm-exporter@myapp.service

# Basic settings
namespace: production
selector: app=myapp
include_secrets: true
secret_mode: include

# Chart settings
chart_version: "1.0.0"
app_version: "1.0.0"

# Output settings
force: true
lint: true

# Test chart
create_test_chart: true
test_suffix: staging
EOF
    
    # Sample kubeconfig template
    cat > "$CONFIG_DIR/kubeconfig.template" << 'EOF'
# Copy your kubeconfig here or create a service account token
# Example service account setup:
#   kubectl create serviceaccount rancher-exporter -n default
#   kubectl create clusterrolebinding rancher-exporter --clusterrole=view --serviceaccount=default:rancher-exporter
#   kubectl create token rancher-exporter --duration=8760h > token
#
# Then create kubeconfig with the token
EOF
    
    # Set permissions
    chmod 640 "$CONFIG_DIR"/*.yaml
    chmod 644 "$CONFIG_DIR"/*.template
    chown root:"$SERVICE_GROUP" "$CONFIG_DIR"/*.yaml
    chown root:root "$CONFIG_DIR"/*.template
    
    print_success "Sample configurations created"
}

setup_logrotate() {
    print_status "Setting up log rotation..."
    
    cat > /etc/logrotate.d/rancher-helm-exporter << EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 $SERVICE_USER $SERVICE_GROUP
    postrotate
        /bin/systemctl reload-or-restart rancher-helm-exporter.service > /dev/null 2>&1 || true
    endscript
}
EOF
    
    print_success "Log rotation configured"
}

print_setup_summary() {
    echo ""
    echo -e "${GREEN}=================================="
    echo -e "Systemd Setup Complete!"
    echo -e "==================================${NC}"
    echo ""
    echo "Service user: $SERVICE_USER"
    echo "Configuration: $CONFIG_DIR/"
    echo "Data directory: $DATA_DIR/"
    echo "Log directory: $LOG_DIR/"
    echo ""
    echo "Available services:"
    echo "  rancher-helm-exporter.service           - Basic service"
    echo "  rancher-helm-exporter@<app>.service     - Parameterized service"
    echo "  rancher-helm-exporter.timer             - Scheduled exports"
    echo ""
    echo "Quick start:"
    echo "  1. Configure kubectl access:"
    echo "     cp ~/.kube/config $CONFIG_DIR/kubeconfig"
    echo "     chown root:$SERVICE_GROUP $CONFIG_DIR/kubeconfig"
    echo "     chmod 640 $CONFIG_DIR/kubeconfig"
    echo ""
    echo "  2. Test the service:"
    echo "     systemctl start rancher-helm-exporter.service"
    echo "     journalctl -u rancher-helm-exporter.service"
    echo ""
    echo "  3. Enable scheduled exports:"
    echo "     systemctl enable rancher-helm-exporter.timer"
    echo "     systemctl start rancher-helm-exporter.timer"
    echo ""
    echo "  4. Create app-specific exports:"
    echo "     cp $CONFIG_DIR/myapp.yaml $CONFIG_DIR/webapp.yaml"
    echo "     systemctl start rancher-helm-exporter@webapp.service"
    echo ""
}

# Main setup flow
main() {
    echo -e "${BLUE}Rancher Helm Exporter - Systemd Setup${NC}"
    echo ""
    
    check_root
    create_service_user
    setup_directories
    install_systemd_files
    create_sample_configs
    setup_logrotate
    print_setup_summary
}

# Run main function
main "$@"