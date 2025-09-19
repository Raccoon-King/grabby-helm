#!/bin/bash
# Installation script for rancher-helm-exporter on Fedora Linux

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="rancher-helm-exporter"
CONFIG_DIR="$HOME/.config/$APP_NAME"
GLOBAL_CONFIG_DIR="/etc/$APP_NAME"
VENV_DIR="$HOME/.local/share/$APP_NAME/venv"
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

check_requirements() {
    print_status "Checking system requirements..."
    
    # Check for Python 3.9+
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        print_status "Ask your system administrator to install: python3 python3-pip python3-venv"
        print_status "Or try installing via conda/miniconda in user space"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
        print_error "Python 3.9+ required, found Python $PYTHON_VERSION"
        exit 1
    fi
    print_success "Python $PYTHON_VERSION found"
    
    # Check for kubectl
    if ! command -v kubectl &> /dev/null; then
        print_warning "kubectl not found - required for operation"
        print_status "User-space install: curl -LO https://dl.k8s.io/release/\$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
        print_status "Then: chmod +x kubectl && mv kubectl ~/.local/bin/"
        print_status "Make sure ~/.local/bin is in your PATH"
    else
        KUBECTL_VERSION=$(kubectl version --client --short 2>/dev/null | cut -d' ' -f3 || echo "unknown")
        print_success "kubectl found: $KUBECTL_VERSION"
    fi
    
    # Check for helm (optional)
    if ! command -v helm &> /dev/null; then
        print_warning "helm not found - optional for chart linting"
        print_status "User-space install: curl https://get.helm.sh/helm-v3.12.0-linux-amd64.tar.gz | tar -xzO linux-amd64/helm > ~/.local/bin/helm"
        print_status "Then: chmod +x ~/.local/bin/helm"
    else
        HELM_VERSION=$(helm version --short 2>/dev/null | cut -d'+' -f1 || echo "unknown")
        print_success "helm found: $HELM_VERSION"
    fi
}

install_user_dependencies() {
    print_status "Installing user-space dependencies..."
    
    # Ensure ~/.local/bin exists and is in PATH
    mkdir -p "$BIN_DIR"
    
    # Install kubectl if not present
    if ! command -v kubectl &> /dev/null; then
        print_status "Installing kubectl to user space..."
        curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
        chmod +x kubectl
        mv kubectl "$BIN_DIR/"
        print_success "kubectl installed to $BIN_DIR/kubectl"
    fi
    
    # Install helm if not present
    if ! command -v helm &> /dev/null; then
        print_status "Installing helm to user space..."
        HELM_VERSION="v3.12.0"
        curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" | tar -xzO linux-amd64/helm > "$BIN_DIR/helm"
        chmod +x "$BIN_DIR/helm"
        print_success "helm installed to $BIN_DIR/helm"
    fi
}

install_system_dependencies() {
    print_status "Installing system dependencies..."
    
    # Check if running as root or if sudo is available
    if [[ $EUID -eq 0 ]]; then
        SUDO=""
    elif command -v sudo &> /dev/null; then
        SUDO="sudo"
    else
        print_warning "No sudo access available - skipping system package installation"
        print_status "Ask your system administrator to install: python3 python3-pip python3-venv git curl"
        return 0
    fi
    
    # Install required packages
    $SUDO dnf install -y python3 python3-pip python3-venv git curl
    
    # Install kubectl if not present and we have sudo
    if ! command -v kubectl &> /dev/null; then
        print_status "Installing kubectl system-wide..."
        curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
        chmod +x kubectl
        $SUDO mv kubectl /usr/local/bin/
    fi
    
    # Install helm if not present and we have sudo
    if ! command -v helm &> /dev/null; then
        print_status "Installing helm system-wide..."
        curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
        chmod 700 get_helm.sh
        ./get_helm.sh
        rm get_helm.sh
    fi
}

setup_directories() {
    print_status "Setting up directories..."
    
    # Create user config directories
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$BIN_DIR"
    mkdir -p "$(dirname "$VENV_DIR")"
    
    # Create global config directory if we have permission (but don't require it)
    if [[ $EUID -eq 0 ]] || [[ -w /etc ]] 2>/dev/null; then
        mkdir -p "$GLOBAL_CONFIG_DIR" 2>/dev/null && \
        print_success "Created global config directory: $GLOBAL_CONFIG_DIR" || \
        print_warning "Could not create global config directory (no sudo access)"
    else
        print_warning "No write access to /etc - using user config only"
        print_status "Global config would be at: $GLOBAL_CONFIG_DIR"
    fi
    
    print_success "Created user directories"
}

install_python_package() {
    print_status "Installing rancher-helm-exporter..."
    
    # Create virtual environment
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install the package
    if [[ -f "pyproject.toml" ]]; then
        # Local development install
        print_status "Installing from local source..."
        pip install -e .
    else
        # Install from PyPI (when available)
        print_status "Installing from PyPI..."
        pip install rancher-helm-exporter
    fi
    
    print_success "Python package installed"
}

create_wrapper_script() {
    print_status "Creating wrapper script..."
    
    cat > "$BIN_DIR/$APP_NAME" << EOF
#!/bin/bash
# Wrapper script for rancher-helm-exporter
exec "$VENV_DIR/bin/python" -m rancher_helm_exporter "\$@"
EOF
    
    chmod +x "$BIN_DIR/$APP_NAME"
    print_success "Wrapper script created: $BIN_DIR/$APP_NAME"
}

setup_bash_completion() {
    print_status "Setting up bash completion..."
    
    # Create completion script
    COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
    mkdir -p "$COMPLETION_DIR"
    
    cat > "$COMPLETION_DIR/$APP_NAME" << 'EOF'
# Bash completion for rancher-helm-exporter
_rancher_helm_exporter() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    opts="--namespace --output-dir --selector --only --exclude --kubeconfig --context 
          --include-secrets --include-service-account-secrets --secret-mode --prefix 
          --force --lint --chart-version --app-version --timeout --max-retries 
          --parallel --max-workers --verbose --progress --no-progress --rich-progress 
          --silent-progress --config --interactive --create-test-chart --test-suffix 
          --test-chart-dir --dry-run --validate --no-validate --help"
    
    case "${prev}" in
        --namespace|--output-dir|--kubeconfig|--context|--prefix|--chart-version|--app-version|--config|--test-chart-dir|--test-suffix)
            # Complete with files/directories
            COMPREPLY=( $(compgen -f -- ${cur}) )
            return 0
            ;;
        --secret-mode)
            COMPREPLY=( $(compgen -W "include skip encrypt external-ref" -- ${cur}) )
            return 0
            ;;
        --only|--exclude)
            COMPREPLY=( $(compgen -W "deployments statefulsets daemonsets cronjobs jobs services configmaps secrets serviceaccounts persistentvolumeclaims ingresses" -- ${cur}) )
            return 0
            ;;
    esac
    
    if [[ ${cur} == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
        return 0
    fi
    
    # Complete release names (first positional argument)
    if [[ ${COMP_CWORD} == 1 ]]; then
        COMPREPLY=( $(compgen -W "" -- ${cur}) )
    fi
}

complete -F _rancher_helm_exporter rancher-helm-exporter
EOF
    
    print_success "Bash completion installed"
}

create_sample_config() {
    print_status "Creating sample configuration..."
    
    cat > "$CONFIG_DIR/config.yaml" << 'EOF'
# Sample configuration for rancher-helm-exporter
# Copy and modify as needed

# Retry configuration for kubectl operations
retry:
  max_retries: 3
  timeout_seconds: 30
  backoff_base: 2.0

# Resource cleaning configuration
cleaning:
  # Additional metadata fields to remove (beyond defaults)
  additional_metadata_fields: []
  
  # Additional annotation patterns to remove
  annotation_patterns_to_remove: []
  
  # Whether to remove namespace references
  remove_namespace_references: true

# Feature flags
enable_rich_progress: true
enable_validation: true
enable_templating: false

# Progress tracking
progress_update_interval: 0.1
progress_log_interval: 10
EOF
    
    print_success "Sample config created: $CONFIG_DIR/config.yaml"
}

setup_systemd_service() {
    print_status "Setting up systemd user service (optional)..."
    
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"
    
    cat > "$SYSTEMD_DIR/$APP_NAME.service" << EOF
[Unit]
Description=Rancher Helm Exporter
Documentation=https://github.com/your-org/rancher-helm-exporter
After=network.target

[Service]
Type=oneshot
ExecStart=$VENV_DIR/bin/python -m rancher_helm_exporter --help
WorkingDirectory=%h
Environment=PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF
    
    # Reload systemd and enable the service
    systemctl --user daemon-reload
    print_success "Systemd service created (not enabled by default)"
    print_status "Enable with: systemctl --user enable $APP_NAME.service"
}

update_shell_profile() {
    print_status "Updating shell profile..."
    
    # Add ~/.local/bin to PATH if not already there
    SHELL_RC="$HOME/.bashrc"
    if [[ -f "$SHELL_RC" ]]; then
        if ! grep -q "$BIN_DIR" "$SHELL_RC"; then
            echo "" >> "$SHELL_RC"
            echo "# Added by rancher-helm-exporter installer" >> "$SHELL_RC"
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$SHELL_RC"
            print_success "Added $BIN_DIR to PATH in $SHELL_RC"
        fi
    fi
    
    # Add bash completion
    if [[ -f "$SHELL_RC" ]]; then
        COMPLETION_LINE="source ~/.local/share/bash-completion/completions/$APP_NAME"
        if ! grep -q "$COMPLETION_LINE" "$SHELL_RC"; then
            echo "$COMPLETION_LINE" >> "$SHELL_RC"
            print_success "Added bash completion to $SHELL_RC"
        fi
    fi
}

print_installation_summary() {
    echo ""
    echo -e "${GREEN}=================================="
    echo -e "Installation Complete!"
    echo -e "==================================${NC}"
    echo ""
    echo "Configuration:"
    echo "  User config: $CONFIG_DIR/config.yaml"
    echo "  Global config: $GLOBAL_CONFIG_DIR/config.yaml (if accessible)"
    echo "  Virtual env: $VENV_DIR"
    echo "  Executable: $BIN_DIR/$APP_NAME"
    echo ""
    echo "Usage:"
    echo "  $APP_NAME my-app --namespace production"
    echo "  $APP_NAME my-app --interactive"
    echo "  $APP_NAME my-app --create-test-chart"
    echo ""
    echo "Next steps:"
    echo "  1. Restart your shell or run: source ~/.bashrc"
    echo "  2. Verify installation: $APP_NAME --help"
    echo "  3. Configure kubectl access to your Rancher cluster"
    echo "  4. Test with: $APP_NAME --dry-run my-test-app"
    echo ""
}

# Main installation flow
main() {
    echo -e "${BLUE}Rancher Helm Exporter - Fedora Linux Installer${NC}"
    echo ""
    
    # Parse command line arguments
    INSTALL_DEPS=false
    INSTALL_USER_DEPS=false
    SKIP_COMPLETION=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --install-deps)
                INSTALL_DEPS=true
                shift
                ;;
            --install-user-deps)
                INSTALL_USER_DEPS=true
                shift
                ;;
            --skip-completion)
                SKIP_COMPLETION=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --install-deps      Install system dependencies (requires sudo)"
                echo "  --install-user-deps Install kubectl/helm to user space (no sudo)"
                echo "  --skip-completion   Skip bash completion setup"
                echo "  --help, -h          Show this help message"
                echo ""
                echo "Examples:"
                echo "  $0                        # Basic install (no deps)"
                echo "  $0 --install-user-deps    # Install with user-space tools"
                echo "  $0 --install-deps         # Install with system deps (sudo)"
                echo ""
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    check_requirements
    
    if [[ "$INSTALL_DEPS" == "true" ]]; then
        install_system_dependencies
    elif [[ "$INSTALL_USER_DEPS" == "true" ]]; then
        install_user_dependencies
    fi
    
    setup_directories
    install_python_package
    create_wrapper_script
    create_sample_config
    
    if [[ "$SKIP_COMPLETION" == "false" ]]; then
        setup_bash_completion
    fi
    
    setup_systemd_service
    update_shell_profile
    print_installation_summary
}

# Run main function
main "$@"