#!/bin/bash
# Build script for creating RPM packages on Fedora/RHEL

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PACKAGE_NAME="rancher-helm-exporter"
VERSION="2.0.0"

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
    print_status "Checking build requirements..."
    
    # Check for required packages
    local required_packages=(
        "rpm-build"
        "python3-devel"
        "python3-setuptools"
        "python3-pip"
        "python3-wheel"
    )
    
    local missing_packages=()
    
    for package in "${required_packages[@]}"; do
        if ! rpm -q "$package" >/dev/null 2>&1; then
            missing_packages+=("$package")
        fi
    done
    
    if [[ ${#missing_packages[@]} -gt 0 ]]; then
        print_error "Missing required packages: ${missing_packages[*]}"
        print_status "Install with: sudo dnf install ${missing_packages[*]}"
        exit 1
    fi
    
    print_success "All build requirements satisfied"
}

setup_build_environment() {
    print_status "Setting up build environment..."
    
    # Create rpmbuild directory structure
    mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    
    # Create source tarball
    cd "$PROJECT_ROOT"
    tar --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.pytest_cache' --exclude='build' --exclude='dist' \
        --exclude='*.egg-info' -czf \
        ~/rpmbuild/SOURCES/${PACKAGE_NAME}-${VERSION}.tar.gz \
        --transform="s|^|${PACKAGE_NAME}-${VERSION}/|" .
    
    # Copy spec file
    cp "$SCRIPT_DIR/${PACKAGE_NAME}.spec" ~/rpmbuild/SPECS/
    
    print_success "Build environment prepared"
}

build_rpm() {
    print_status "Building RPM package..."
    
    cd ~/rpmbuild
    
    # Build source RPM
    rpmbuild -bs SPECS/${PACKAGE_NAME}.spec
    print_success "Source RPM built"
    
    # Build binary RPM
    rpmbuild -bb SPECS/${PACKAGE_NAME}.spec
    print_success "Binary RPM built"
    
    # Find built packages
    local srpms=(SRPMS/python3-${PACKAGE_NAME}-${VERSION}-*.src.rpm)
    local rpms=(RPMS/noarch/python3-${PACKAGE_NAME}-${VERSION}-*.noarch.rpm)
    local doc_rpms=(RPMS/noarch/python3-${PACKAGE_NAME}-doc-${VERSION}-*.noarch.rpm)
    
    echo ""
    echo -e "${GREEN}Built packages:${NC}"
    for rpm in "${srpms[@]}" "${rpms[@]}" "${doc_rpms[@]}"; do
        if [[ -f "$rpm" ]]; then
            echo "  $rpm"
        fi
    done
}

test_rpm() {
    print_status "Testing RPM package..."
    
    local rpm_file=$(find ~/rpmbuild/RPMS/noarch -name "python3-${PACKAGE_NAME}-${VERSION}-*.rpm" | head -1)
    
    if [[ ! -f "$rpm_file" ]]; then
        print_error "RPM file not found"
        return 1
    fi
    
    print_status "Testing RPM installation (dry run)..."
    sudo rpm -i --test "$rpm_file" || {
        print_warning "RPM test installation failed - this is normal if dependencies are missing"
    }
    
    print_status "Checking RPM contents..."
    rpm -qlp "$rpm_file"
    
    print_status "Verifying RPM..."
    rpm -K "$rpm_file"
    
    print_success "RPM package validation completed"
}

create_repo() {
    local repo_dir="$1"
    
    if [[ -z "$repo_dir" ]]; then
        return 0
    fi
    
    print_status "Creating local repository at $repo_dir..."
    
    mkdir -p "$repo_dir"
    
    # Copy RPMs to repository
    cp ~/rpmbuild/RPMS/noarch/python3-${PACKAGE_NAME}*-${VERSION}-*.rpm "$repo_dir/"
    cp ~/rpmbuild/SRPMS/python3-${PACKAGE_NAME}-${VERSION}-*.src.rpm "$repo_dir/"
    
    # Create repository metadata
    if command -v createrepo_c >/dev/null 2>&1; then
        createrepo_c "$repo_dir"
    elif command -v createrepo >/dev/null 2>&1; then
        createrepo "$repo_dir"
    else
        print_warning "createrepo not found - repository metadata not created"
        print_status "Install with: sudo dnf install createrepo_c"
        return 0
    fi
    
    print_success "Local repository created at $repo_dir"
    
    cat << EOF

To use this repository:

1. Create a repo file:
   sudo tee /etc/yum.repos.d/rancher-helm-exporter-local.repo << 'REPO_EOF'
[rancher-helm-exporter-local]
name=Rancher Helm Exporter Local Repository
baseurl=file://$repo_dir
enabled=1
gpgcheck=0
REPO_EOF

2. Install the package:
   sudo dnf install python3-rancher-helm-exporter

EOF
}

cleanup() {
    print_status "Cleaning up build artifacts..."
    
    # Remove build directories
    rm -rf ~/rpmbuild/BUILD/rancher-helm-exporter-*
    
    print_success "Cleanup completed"
}

print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --repo DIR     Create local repository in DIR"
    echo "  --test         Run package tests after build"
    echo "  --cleanup      Clean up build artifacts after build"
    echo "  --help, -h     Show this help message"
    echo ""
}

main() {
    local run_tests=false
    local cleanup_after=false
    local repo_dir=""
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --repo)
                repo_dir="$2"
                shift 2
                ;;
            --test)
                run_tests=true
                shift
                ;;
            --cleanup)
                cleanup_after=true
                shift
                ;;
            --help|-h)
                print_usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                print_usage
                exit 1
                ;;
        esac
    done
    
    echo -e "${BLUE}Rancher Helm Exporter - RPM Build Script${NC}"
    echo ""
    
    check_requirements
    setup_build_environment
    build_rpm
    
    if [[ "$run_tests" == "true" ]]; then
        test_rpm
    fi
    
    if [[ -n "$repo_dir" ]]; then
        create_repo "$repo_dir"
    fi
    
    if [[ "$cleanup_after" == "true" ]]; then
        cleanup
    fi
    
    print_success "RPM build completed successfully!"
}

# Run main function
main "$@"