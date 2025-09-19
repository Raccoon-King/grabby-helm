#!/bin/bash
# Setup script for user-space systemd services (no sudo required)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

APP_NAME="rancher-helm-exporter"
USER_CONFIG_DIR="$HOME/.config/$APP_NAME"
USER_DATA_DIR="$HOME/.local/share/$APP_NAME"
USER_LOG_DIR="$USER_DATA_DIR/logs"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
VENV_DIR="$USER_DATA_DIR/venv"
BIN_DIR="$HOME/.local/bin"

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

check_systemd_user() {
    print_status "Checking systemd user session..."
    
    # Check if systemd user session is available
    if ! systemctl --user status >/dev/null 2>&1; then
        print_error "Systemd user session not available"
        print_status "Try: systemctl --user daemon-reload"
        print_status "Or ensure you're logged in interactively"
        exit 1
    fi
    
    print_success "Systemd user session is available"
}

setup_user_directories() {
    print_status "Setting up user directories..."
    
    # Create all necessary directories
    mkdir -p "$USER_CONFIG_DIR"
    mkdir -p "$USER_DATA_DIR"/{exports,cache,tmp}
    mkdir -p "$USER_LOG_DIR"
    mkdir -p "$USER_SYSTEMD_DIR"
    
    print_success "User directories created"
}

create_user_systemd_services() {
    print_status "Creating user systemd service files..."
    
    # Create basic service
    cat > "$USER_SYSTEMD_DIR/rancher-helm-exporter.service" << EOF
[Unit]
Description=Rancher Helm Exporter (User)
Documentation=https://github.com/your-org/rancher-helm-exporter
After=graphical-session.target

[Service]
Type=oneshot
WorkingDirectory=%h/.local/share/rancher-helm-exporter
Environment=HOME=%h
Environment=XDG_CONFIG_HOME=%h/.config
Environment=KUBECONFIG=%h/.kube/config

# Use the user-installed binary
ExecStart=%h/.local/bin/rancher-helm-exporter default-app \\
          --config %h/.config/rancher-helm-exporter/config.yaml \\
          --output-dir %h/.local/share/rancher-helm-exporter/exports/default \\
          --force

# Restart policy
Restart=on-failure
RestartSec=30

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rancher-helm-exporter-user

[Install]
WantedBy=default.target
EOF

    # Create parameterized service for multiple apps
    cat > "$USER_SYSTEMD_DIR/rancher-helm-exporter@.service" << EOF
[Unit]
Description=Rancher Helm Exporter for %i (User)
Documentation=https://github.com/your-org/rancher-helm-exporter
After=graphical-session.target

[Service]
Type=oneshot
WorkingDirectory=%h/.local/share/rancher-helm-exporter
Environment=HOME=%h
Environment=XDG_CONFIG_HOME=%h/.config
Environment=KUBECONFIG=%h/.kube/config

# Use app-specific config file
ExecStart=%h/.local/bin/rancher-helm-exporter %i \\
          --config %h/.config/rancher-helm-exporter/%i.yaml \\
          --output-dir %h/.local/share/rancher-helm-exporter/exports/%i \\
          --force

# Restart policy
Restart=on-failure
RestartSec=30

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rancher-helm-exporter-%i

[Install]
WantedBy=default.target
EOF

    # Create timer for scheduled exports
    cat > "$USER_SYSTEMD_DIR/rancher-helm-exporter.timer" << EOF
[Unit]
Description=Daily Rancher Helm Export Timer (User)
Documentation=https://github.com/your-org/rancher-helm-exporter
Requires=rancher-helm-exporter.service

[Timer]
# Run daily at 9 AM (when user is likely to be logged in)
OnCalendar=*-*-* 09:00:00
Persistent=true

# Add some randomization
RandomizedDelaySec=1800

[Install]
WantedBy=timers.target
EOF

    print_success "User systemd service files created"
}

create_user_configs() {
    print_status "Creating user configuration files..."
    
    # Main config
    cat > "$USER_CONFIG_DIR/config.yaml" << 'EOF'
# User configuration for rancher-helm-exporter
# This file is used for user-space systemd services

# Retry configuration
retry:
  max_retries: 3
  timeout_seconds: 30
  backoff_base: 2.0

# Cleaning configuration
cleaning:
  additional_metadata_fields: []
  annotation_patterns_to_remove: []
  remove_namespace_references: true

# Feature flags (enabled for user sessions)
enable_rich_progress: true
enable_validation: true
enable_templating: false

# Progress settings
progress_update_interval: 0.1
progress_log_interval: 10
EOF

    # Sample app config
    cat > "$USER_CONFIG_DIR/myapp.yaml" << 'EOF'
# Sample configuration for myapp export
# Used with: systemctl --user start rancher-helm-exporter@myapp.service

# Basic settings
namespace: default
selector: app=myapp
include_secrets: false  # Be careful with secrets in user space
secret_mode: skip

# Chart settings
chart_version: "1.0.0"
app_version: "1.0.0"

# Output settings
force: true
lint: true

# Test chart
create_test_chart: true
test_suffix: dev
EOF

    # Set secure permissions
    chmod 600 "$USER_CONFIG_DIR"/*.yaml
    
    print_success "User configuration files created"
}

setup_user_logrotate() {
    print_status "Setting up log rotation for user space..."
    
    # Create a simple log rotation script
    cat > "$USER_DATA_DIR/rotate-logs.sh" << 'EOF'
#!/bin/bash
# Simple log rotation script for user space

LOG_DIR="$HOME/.local/share/rancher-helm-exporter/logs"
KEEP_DAYS=30

if [[ -d "$LOG_DIR" ]]; then
    # Remove logs older than KEEP_DAYS
    find "$LOG_DIR" -name "*.log" -type f -mtime +$KEEP_DAYS -delete
    
    # Compress logs older than 1 day
    find "$LOG_DIR" -name "*.log" -type f -mtime +1 -exec gzip {} \;
fi
EOF

    chmod +x "$USER_DATA_DIR/rotate-logs.sh"
    
    # Add to user crontab if cron is available
    if command -v crontab >/dev/null 2>&1; then
        # Check if the rotation job already exists
        if ! crontab -l 2>/dev/null | grep -q "rotate-logs.sh"; then
            print_status "Adding log rotation to user crontab..."
            (crontab -l 2>/dev/null; echo "0 2 * * * $USER_DATA_DIR/rotate-logs.sh") | crontab -
            print_success "Log rotation added to crontab"
        fi
    else
        print_warning "cron not available - manual log rotation required"
        print_status "Run periodically: $USER_DATA_DIR/rotate-logs.sh"
    fi
}

enable_user_services() {
    print_status "Enabling and starting user systemd services..."
    
    # Reload systemd user configuration
    systemctl --user daemon-reload
    
    # Enable linger so services can run when user is not logged in
    if command -v loginctl >/dev/null 2>&1; then
        if ! loginctl show-user "$USER" -p Linger | grep -q "yes"; then
            print_status "Enabling user lingering (services persist after logout)..."
            loginctl enable-linger "$USER" 2>/dev/null || \
            print_warning "Could not enable lingering - services will stop when you log out"
        fi
    fi
    
    print_success "User systemd services configured"
    
    echo ""
    echo "Service management commands:"
    echo "  systemctl --user start rancher-helm-exporter.service"
    echo "  systemctl --user enable rancher-helm-exporter.timer"
    echo "  systemctl --user start rancher-helm-exporter@myapp.service"
    echo "  journalctl --user -u rancher-helm-exporter.service -f"
}

print_user_setup_summary() {
    echo ""
    echo -e "${GREEN}=================================="
    echo -e "User Space Setup Complete!"
    echo -e "==================================${NC}"
    echo ""
    echo "Configuration:"
    echo "  User config: $USER_CONFIG_DIR/config.yaml"
    echo "  App configs: $USER_CONFIG_DIR/<app>.yaml"
    echo "  Data directory: $USER_DATA_DIR/"
    echo "  Log directory: $USER_LOG_DIR/"
    echo "  Services: $USER_SYSTEMD_DIR/"
    echo ""
    echo "Quick start:"
    echo "  1. Configure kubectl access (user space):"
    echo "     kubectl config use-context <your-context>"
    echo ""
    echo "  2. Test the service:"
    echo "     systemctl --user start rancher-helm-exporter.service"
    echo "     journalctl --user -u rancher-helm-exporter.service"
    echo ""
    echo "  3. Enable scheduled exports:"
    echo "     systemctl --user enable rancher-helm-exporter.timer"
    echo "     systemctl --user start rancher-helm-exporter.timer"
    echo ""
    echo "  4. Create app-specific exports:"
    echo "     cp $USER_CONFIG_DIR/myapp.yaml $USER_CONFIG_DIR/webapp.yaml"
    echo "     systemctl --user start rancher-helm-exporter@webapp.service"
    echo ""
    echo "  5. Check service status:"
    echo "     systemctl --user status rancher-helm-exporter.service"
    echo "     systemctl --user list-timers"
    echo ""
}

# Main setup flow
main() {
    echo -e "${BLUE}Rancher Helm Exporter - User Space Systemd Setup${NC}"
    echo ""
    
    check_systemd_user
    setup_user_directories
    create_user_systemd_services
    create_user_configs
    setup_user_logrotate
    enable_user_services
    print_user_setup_summary
}

# Run main function
main "$@"