#!/bin/bash
# Bash completion for rancher-helm-exporter
# 
# Installation:
#   1. Copy this file to ~/.local/share/bash-completion/completions/rancher-helm-exporter
#   2. Source it in your .bashrc: source ~/.local/share/bash-completion/completions/rancher-helm-exporter
#   3. Or install globally: sudo cp bash_completion.sh /etc/bash_completion.d/rancher-helm-exporter

_rancher_helm_exporter() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    # All available options
    opts="--namespace --output-dir --selector --only --exclude --kubeconfig --context 
          --include-secrets --include-service-account-secrets --secret-mode --prefix 
          --force --lint --chart-version --app-version --timeout --max-retries 
          --parallel --max-workers --verbose --progress --no-progress --rich-progress 
          --silent-progress --config --interactive --create-test-chart --test-suffix 
          --test-chart-dir --dry-run --validate --no-validate --help --version"
    
    # Resource types for --only and --exclude
    resource_types="deployments statefulsets daemonsets cronjobs jobs services 
                   configmaps secrets serviceaccounts persistentvolumeclaims ingresses"
    
    # Secret modes
    secret_modes="include skip encrypt external-ref"
    
    case "${prev}" in
        --namespace)
            # Complete with available namespaces if kubectl is available
            if command -v kubectl &> /dev/null; then
                local namespaces=$(kubectl get namespaces -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
                COMPREPLY=( $(compgen -W "${namespaces}" -- ${cur}) )
            else
                COMPREPLY=( $(compgen -W "default kube-system" -- ${cur}) )
            fi
            return 0
            ;;
        --output-dir|--kubeconfig|--config|--test-chart-dir)
            # Complete with files/directories
            COMPREPLY=( $(compgen -f -- ${cur}) )
            return 0
            ;;
        --context)
            # Complete with available kubectl contexts
            if command -v kubectl &> /dev/null; then
                local contexts=$(kubectl config get-contexts -o name 2>/dev/null)
                COMPREPLY=( $(compgen -W "${contexts}" -- ${cur}) )
            fi
            return 0
            ;;
        --secret-mode)
            COMPREPLY=( $(compgen -W "${secret_modes}" -- ${cur}) )
            return 0
            ;;
        --only|--exclude)
            COMPREPLY=( $(compgen -W "${resource_types}" -- ${cur}) )
            return 0
            ;;
        --timeout|--max-retries|--max-workers)
            # Complete with numbers
            COMPREPLY=( $(compgen -W "1 3 5 10 30 60" -- ${cur}) )
            return 0
            ;;
        --chart-version|--app-version)
            # Complete with version-like strings
            COMPREPLY=( $(compgen -W "0.1.0 1.0.0" -- ${cur}) )
            return 0
            ;;
        --prefix|--test-suffix)
            # Complete with common prefixes/suffixes
            if [[ "${prev}" == "--prefix" ]]; then
                COMPREPLY=( $(compgen -W "prod- staging- dev-" -- ${cur}) )
            else
                COMPREPLY=( $(compgen -W "test staging dev" -- ${cur}) )
            fi
            return 0
            ;;
    esac
    
    # Complete with flags if current word starts with -
    if [[ ${cur} == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
        return 0
    fi
    
    # Complete release names (first positional argument)
    if [[ ${COMP_CWORD} == 1 ]]; then
        # Try to suggest release names from current directory or common patterns
        local suggestions=""
        
        # Look for common application names in current directory
        if [[ -f "package.json" ]]; then
            local app_name=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' package.json 2>/dev/null | cut -d'"' -f4)
            suggestions="$suggestions $app_name"
        fi
        
        if [[ -f "Chart.yaml" ]]; then
            local chart_name=$(grep -o '^name:[[:space:]]*.*' Chart.yaml 2>/dev/null | cut -d':' -f2 | tr -d ' ')
            suggestions="$suggestions $chart_name"
        fi
        
        # Add common release name patterns
        suggestions="$suggestions my-app webapp backend frontend api"
        
        COMPREPLY=( $(compgen -W "${suggestions}" -- ${cur}) )
        return 0
    fi
}

# Enhanced completion for common patterns
_rancher_helm_exporter_enhanced() {
    local cur prev words cword
    _init_completion || return
    
    # Check if we're completing a multi-value option
    case "${prev}" in
        --only|--exclude)
            # Allow multiple resource types separated by space
            local resource_types="deployments statefulsets daemonsets cronjobs jobs services 
                               configmaps secrets serviceaccounts persistentvolumeclaims ingresses"
            COMPREPLY=( $(compgen -W "${resource_types}" -- ${cur}) )
            return 0
            ;;
    esac
    
    # Fall back to standard completion
    _rancher_helm_exporter
}

# Register the completion function
complete -F _rancher_helm_exporter rancher-helm-exporter

# Also register for common aliases
complete -F _rancher_helm_exporter rhe
complete -F _rancher_helm_exporter helm-export

# Advanced completion with file path intelligence
_complete_with_kubectl_resources() {
    local resource_type="$1"
    local namespace_flag=""
    
    # Find namespace in current command line
    for ((i=1; i<COMP_CWORD; i++)); do
        if [[ "${COMP_WORDS[i]}" == "--namespace" ]] && [[ $((i+1)) -lt COMP_CWORD ]]; then
            namespace_flag="-n ${COMP_WORDS[i+1]}"
            break
        fi
    done
    
    if command -v kubectl &> /dev/null; then
        local resources=$(kubectl get ${resource_type} ${namespace_flag} -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
        echo "${resources}"
    fi
}

# Function to install completion system-wide (requires sudo)
install_completion() {
    local completion_dir="/etc/bash_completion.d"
    local completion_file="rancher-helm-exporter"
    
    if [[ $EUID -eq 0 ]]; then
        cp "$0" "${completion_dir}/${completion_file}"
        echo "Bash completion installed system-wide to ${completion_dir}/${completion_file}"
        echo "Reload your shell or run: source ${completion_dir}/${completion_file}"
    else
        echo "Run with sudo to install system-wide completion"
        echo "Or install for current user:"
        echo "  mkdir -p ~/.local/share/bash-completion/completions"
        echo "  cp $0 ~/.local/share/bash-completion/completions/rancher-helm-exporter"
        echo "  echo 'source ~/.local/share/bash-completion/completions/rancher-helm-exporter' >> ~/.bashrc"
    fi
}

# Check if script is being executed directly for installation
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        install)
            install_completion
            ;;
        test)
            echo "Testing completion..."
            echo "Available functions:"
            declare -F | grep rancher_helm_exporter
            ;;
        *)
            echo "Bash completion script for rancher-helm-exporter"
            echo ""
            echo "Usage:"
            echo "  $0 install  - Install completion system-wide (requires sudo)"
            echo "  $0 test     - Test completion functions"
            echo ""
            echo "Manual installation:"
            echo "  source $0"
            echo ""
            ;;
    esac
fi