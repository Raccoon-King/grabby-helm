#!/bin/bash
# Installation script for environments without sudo access
# This script installs everything in user space

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="rancher-helm-exporter"
USER_HOME="$HOME"
LOCAL_BIN="$USER_HOME/.local/bin"
LOCAL_LIB="$USER_HOME/.local/lib"
CONFIG_DIR="$USER_HOME/.config/$APP_NAME"
DATA_DIR="$USER_HOME/.local/share/$APP_NAME"
VENV_DIR="$DATA_DIR/venv"

# Tool versions
KUBECTL_VERSION=""  # Will be auto-detected
HELM_VERSION="v3.12.0"
MINICONDA_VERSION="latest"

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

check_no_sudo() {
    print_status "Verifying non-privileged installation..."
    
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should not be run as root"
        print_status "Use the regular install script if you have sudo access"
        exit 1
    fi
    
    if groups | grep -q "wheel\|sudo\|admin"; then
        print_warning "You appear to have admin privileges"
        print_status "Consider using: ./install_fedora.sh --install-deps"
    fi
    
    print_success "Running in user-space mode"
}

setup_user_environment() {
    print_status "Setting up user environment..."
    
    # Create directory structure
    mkdir -p "$LOCAL_BIN"
    mkdir -p "$LOCAL_LIB"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$DATA_DIR"/{exports,cache,tmp}
    
    # Ensure .local/bin is in PATH
    if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
        print_status "Adding $LOCAL_BIN to PATH"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        export PATH="$LOCAL_BIN:$PATH"
    fi
    
    print_success "User environment configured"
}

install_python_userspace() {
    print_status "Checking Python installation..."
    
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
            print_success "Python $PYTHON_VERSION found and suitable"
            return 0
        else
            print_warning "Python $PYTHON_VERSION found but too old (need 3.9+)"
        fi
    else
        print_warning "Python 3 not found in PATH"
    fi
    
    # Offer to install miniconda
    print_status "Python 3.9+ is required. Options:"
    echo "  1. Ask system administrator to install python3"
    echo "  2. Install Miniconda in user space (recommended)"
    echo "  3. Exit and install Python manually"
    echo ""
    read -p "Choose option [1/2/3]: " python_choice
    
    case $python_choice in
        2)
            install_miniconda
            ;;
        3)
            print_status "Manual Python installation resources:"
            print_status "- Download from: https://www.python.org/downloads/"
            print_status "- Or use pyenv: https://github.com/pyenv/pyenv"
            exit 0
            ;;
        *)
            print_error "Please install Python 3.9+ and run this script again"
            exit 1
            ;;
    esac
}

install_miniconda() {
    print_status "Installing Miniconda in user space..."
    
    local miniconda_dir="$DATA_DIR/miniconda3"
    
    if [[ -d "$miniconda_dir" ]]; then
        print_success "Miniconda already installed at $miniconda_dir"
        return 0
    fi
    
    # Download and install miniconda
    local installer_url="https://repo.anaconda.com/miniconda/Miniconda3-$MINICONDA_VERSION-Linux-x86_64.sh"
    local installer_path="/tmp/miniconda_installer.sh"
    
    print_status "Downloading Miniconda installer..."
    curl -fsSL "$installer_url" -o "$installer_path"
    
    print_status "Installing Miniconda to $miniconda_dir..."
    bash "$installer_path" -b -p "$miniconda_dir"
    rm "$installer_path"
    
    # Initialize conda
    "$miniconda_dir/bin/conda" init bash
    
    # Add to current session
    export PATH="$miniconda_dir/bin:$PATH"
    
    print_success "Miniconda installed successfully"
}

install_kubectl_userspace() {
    print_status "Installing kubectl in user space..."
    
    if command -v kubectl >/dev/null 2>&1; then
        local version=$(kubectl version --client --short 2>/dev/null | cut -d' ' -f3 || echo "unknown")
        print_success "kubectl already available: $version"
        return 0
    fi
    
    # Get latest stable version
    if [[ -z "$KUBECTL_VERSION" ]]; then
        KUBECTL_VERSION=$(curl -L -s https://dl.k8s.io/release/stable.txt)
    fi
    
    print_status "Downloading kubectl $KUBECTL_VERSION..."
    curl -LO "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl"
    
    # Verify checksum
    curl -LO "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl.sha256"
    echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check
    
    # Install
    chmod +x kubectl
    mv kubectl "$LOCAL_BIN/"
    rm kubectl.sha256
    
    print_success "kubectl $KUBECTL_VERSION installed to $LOCAL_BIN/kubectl"
}

install_helm_userspace() {
    print_status "Installing Helm in user space..."
    
    if command -v helm >/dev/null 2>&1; then
        local version=$(helm version --short 2>/dev/null | cut -d'+' -f1 || echo "unknown")
        print_success "Helm already available: $version"
        return 0
    fi
    
    print_status "Downloading Helm $HELM_VERSION..."
    curl -fsSL "https://get.helm.sh/helm-$HELM_VERSION-linux-amd64.tar.gz" | \
        tar -xzO linux-amd64/helm > "$LOCAL_BIN/helm"
    
    chmod +x "$LOCAL_BIN/helm"
    
    print_success "Helm $HELM_VERSION installed to $LOCAL_BIN/helm"
}

install_app_userspace() {
    print_status "Installing rancher-helm-exporter in user space..."
    
    # Create virtual environment
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install the application
    if [[ -f "pyproject.toml" ]]; then
        # Local development install
        print_status "Installing from local source..."
        pip install -e .
    else
        # Install from PyPI (when available) or requirements
        if [[ -f "requirements.txt" ]]; then
            print_status "Installing from requirements.txt..."
            pip install -r requirements.txt
        else
            print_status "Installing basic dependencies..."
            pip install PyYAML>=6.0 rich>=10.0.0
        fi
    fi
    
    # Create wrapper script
    cat > "$LOCAL_BIN/$APP_NAME" << EOF
#!/bin/bash
# Wrapper script for rancher-helm-exporter (user space)
exec "$VENV_DIR/bin/python" -m rancher_helm_exporter "\$@"
EOF
    
    chmod +x "$LOCAL_BIN/$APP_NAME"
    
    print_success "rancher-helm-exporter installed to $LOCAL_BIN/$APP_NAME"
}

setup_user_config() {
    print_status "Setting up user configuration..."
    
    # Create basic config
    cat > "$CONFIG_DIR/config.yaml" << 'EOF'
# User-space configuration for rancher-helm-exporter

# Retry configuration
retry:
  max_retries: 3
  timeout_seconds: 30
  backoff_base: 2.0

# Feature flags
enable_rich_progress: true
enable_validation: true

# Progress settings
progress_update_interval: 0.1
progress_log_interval: 10
EOF
    
    chmod 600 "$CONFIG_DIR/config.yaml"
    
    print_success "Configuration created at $CONFIG_DIR/config.yaml"
}

setup_shell_integration() {
    print_status "Setting up shell integration..."
    
    # Set up bash completion
    local completion_dir="$HOME/.local/share/bash-completion/completions"
    mkdir -p "$completion_dir"
    
    # Create basic completion
    cat > "$completion_dir/$APP_NAME" << 'EOF'
# Basic bash completion for rancher-helm-exporter
_rancher_helm_exporter() {
    local cur opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    opts="--namespace --output-dir --selector --interactive --create-test-chart --help"
    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
}
complete -F _rancher_helm_exporter rancher-helm-exporter
EOF
    
    # Add to .bashrc if not already there
    local bashrc_line="source $completion_dir/$APP_NAME"
    if [[ -f "$HOME/.bashrc" ]] && ! grep -Fq "$bashrc_line" "$HOME/.bashrc"; then
        echo "" >> "$HOME/.bashrc"
        echo "# rancher-helm-exporter completion" >> "$HOME/.bashrc"
        echo "$bashrc_line" >> "$HOME/.bashrc"
    fi
    
    print_success "Shell integration configured"
}

verify_installation() {
    print_status "Verifying installation..."
    
    # Test tools
    local tools=("python3" "kubectl" "helm" "$APP_NAME")
    local all_good=true
    
    for tool in "${tools[@]}"; do
        if command -v "$tool" >/dev/null 2>&1; then
            print_success "$tool: Available"
        else
            print_error "$tool: Not found in PATH"
            all_good=false
        fi
    done
    
    if [[ "$all_good" == true ]]; then
        print_success "All tools installed successfully"
    else
        print_error "Some tools are missing - check installation"
        return 1
    fi
    
    # Test the app
    if "$APP_NAME" --help >/dev/null 2>&1; then
        print_success "rancher-helm-exporter is working"
    else
        print_error "rancher-helm-exporter failed to run"
        return 1
    fi
    
    return 0
}

print_final_summary() {
    echo ""
    echo -e "${GREEN}=================================="
    echo -e "User-Space Installation Complete!"
    echo -e "==================================${NC}"
    echo ""
    echo "Installed tools:"
    echo "  Python: $(python3 --version 2>/dev/null || echo 'Not found')"
    echo "  kubectl: $(kubectl version --client --short 2>/dev/null | cut -d' ' -f3 || echo 'Not found')"
    echo "  helm: $(helm version --short 2>/dev/null | cut -d'+' -f1 || echo 'Not found')"
    echo "  rancher-helm-exporter: $LOCAL_BIN/$APP_NAME"
    echo ""
    echo "Configuration:"
    echo "  Config: $CONFIG_DIR/config.yaml"
    echo "  Data: $DATA_DIR/"
    echo "  Virtual env: $VENV_DIR/"
    echo ""
    echo "Next steps:"
    echo "  1. Restart your shell: exec bash"
    echo "  2. Configure kubectl: kubectl config use-context <your-context>"
    echo "  3. Test the tool: $APP_NAME --help"
    echo "  4. Run a dry test: $APP_NAME --dry-run my-test-app"
    echo "  5. Export your first app: $APP_NAME my-app --namespace default"
    echo ""
    echo "Optional:"
    echo "  - Set up user services: ./scripts/systemd/user-service-setup.sh"
    echo "  - Create shell aliases: alias rhe='$APP_NAME'"
    echo ""
}

# Main installation flow
main() {
    echo -e "${BLUE}Rancher Helm Exporter - User Space Installation${NC}"
    echo -e "${BLUE}(No sudo/admin privileges required)${NC}"
    echo ""
    
    check_no_sudo
    setup_user_environment
    install_python_userspace
    install_kubectl_userspace
    install_helm_userspace
    install_app_userspace
    setup_user_config
    setup_shell_integration
    
    if verify_installation; then
        print_final_summary
    else
        print_error "Installation verification failed"
        exit 1
    fi
}

# Run main function
main "$@"