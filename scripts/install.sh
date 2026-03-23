#!/bin/bash

# Dell Server AI Agent Installation Script
# This script installs the Dell Server AI Agent and its dependencies

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Dell Server AI Agent Installer${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_warning "Running as root is not recommended"
        read -p "Do you want to continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_status "Installation cancelled"
            exit 0
        fi
    fi
}

# Check operating system
check_os() {
    print_status "Checking operating system..."
    
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        print_status "Detected Linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        print_status "Detected macOS"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
        print_status "Detected Windows"
    else
        print_error "Unsupported operating system: $OSTYPE"
        exit 1
    fi
}

# Check Python version
check_python() {
    print_status "Checking Python version..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_error "Python is not installed"
        print_status "Please install Python 3.8 or higher"
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    REQUIRED_VERSION="3.8"
    
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
        print_status "Python version $PYTHON_VERSION is compatible"
    else
        print_error "Python $PYTHON_VERSION is not compatible. Required: $REQUIRED_VERSION or higher"
        exit 1
    fi
}

# Install system dependencies
install_system_deps() {
    print_status "Installing system dependencies..."
    
    case $OS in
        "linux")
            if command -v apt-get &> /dev/null; then
                # Debian/Ubuntu
                print_status "Using apt-get package manager"
                sudo apt-get update
                sudo apt-get install -y python3-pip python3-venv build-essential libssl-dev libffi-dev
            elif command -v yum &> /dev/null; then
                # RHEL/CentOS
                print_status "Using yum package manager"
                sudo yum install -y python3-pip python3-devel gcc openssl-devel libffi-devel
            elif command -v dnf &> /dev/null; then
                # Fedora
                print_status "Using dnf package manager"
                sudo dnf install -y python3-pip python3-devel gcc openssl-devel libffi-devel
            else
                print_error "No supported package manager found"
                exit 1
            fi
            ;;
        "macos")
            if command -v brew &> /dev/null; then
                print_status "Using Homebrew package manager"
                brew install python3 openssl libffi
            else
                print_warning "Homebrew not found. Please install Python manually."
                print_status "Visit: https://www.python.org/downloads/"
            fi
            ;;
        "windows")
            print_status "Windows detected. Please ensure Python 3.8+ is installed"
            print_status "Download from: https://www.python.org/downloads/"
            ;;
    esac
}

# Create virtual environment
create_venv() {
    print_status "Creating Python virtual environment..."
    
    VENV_DIR="venv"
    
    if [[ -d "$VENV_DIR" ]]; then
        print_warning "Virtual environment already exists"
        read -p "Do you want to recreate it? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
        else
            print_status "Using existing virtual environment"
            return 0
        fi
    fi
    
    $PYTHON_CMD -m venv "$VENV_DIR"
    print_status "Virtual environment created: $VENV_DIR"
}

# Activate virtual environment
activate_venv() {
    print_status "Activating virtual environment..."
    
    VENV_DIR="venv"
    
    if [[ "$OS" == "windows" ]]; then
        source "$VENV_DIR/Scripts/activate"
    else
        source "$VENV_DIR/bin/activate"
    fi
    
    print_status "Virtual environment activated"
}

# Upgrade pip
upgrade_pip() {
    print_status "Upgrading pip..."
    pip install --upgrade pip
}

# Install Python dependencies
install_python_deps() {
    print_status "Installing Python dependencies..."
    
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt
        print_status "Dependencies installed from requirements.txt"
    else
        print_error "requirements.txt not found"
        exit 1
    fi
}

# Create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    
    directories=(
        "logs"
        "data"
        "config"
        "backups"
        "temp"
    )
    
    for dir in "${directories[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_status "Created directory: $dir"
        fi
    done
}

# Create configuration file
create_config() {
    print_status "Creating configuration file..."
    
    CONFIG_FILE="config/.env"
    
    if [[ -f "$CONFIG_FILE" ]]; then
        print_warning "Configuration file already exists"
        read -p "Do you want to overwrite it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 0
        fi
    fi
    
    cat > "$CONFIG_FILE" << EOF
# Dell Server AI Agent Configuration

# Server Connection Settings
REDFISH_PORT=443
CONNECTION_TIMEOUT=30
MAX_RETRIES=3

# Security Settings
SECURITY_LEVEL=medium
REQUIRE_HTTPS=true
VERIFY_SSL=false

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=logs/agent.log
MAX_LOG_SIZE=10485760

# Agent Behavior
MAX_CONCURRENT_OPERATIONS=5
OPERATION_TIMEOUT=300
AUTO_SAVE_LOGS=true

# AI/ML Settings
ENABLE_AI_RECOMMENDATIONS=true
CONFIDENCE_THRESHOLD=0.7

# Data Retention
LOG_RETENTION_DAYS=30
CACHE_RETENTION_HOURS=24

# Dell-Specific Settings
RACADM_TIMEOUT=60
REDFISH_API_VERSION=1.8.0

# Authentication
SECRET_KEY=your-secret-key-here-change-in-production
JWT_EXPIRY_HOURS=24

# Development Settings
DEBUG=false
DEVELOPMENT_MODE=true
EOF

    print_status "Configuration file created: $CONFIG_FILE"
    print_warning "Please edit $CONFIG_FILE to customize your settings"
}

# Create systemd service (Linux only)
create_systemd_service() {
    if [[ "$OS" != "linux" ]]; then
        return 0
    fi
    
    print_status "Creating systemd service..."
    
    SERVICE_FILE="/etc/systemd/system/dell-ai-agent.service"
    
    if [[ -f "$SERVICE_FILE" ]]; then
        print_warning "Systemd service already exists"
        read -p "Do you want to overwrite it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 0
        fi
    fi
    
    # Get current directory
    CURRENT_DIR=$(pwd)
    CURRENT_USER=$(whoami)
    
    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Dell Server AI Agent
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
Environment=PATH=$CURRENT_DIR/venv/bin
ExecStart=$CURRENT_DIR/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dell-ai-agent

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable dell-ai-agent
    
    print_status "Systemd service created and enabled"
    print_status "Start service with: sudo systemctl start dell-ai-agent"
}

# Create startup script (Windows)
create_startup_script() {
    if [[ "$OS" != "windows" ]]; then
        return 0
    fi
    
    print_status "Creating Windows startup script..."
    
    STARTUP_SCRIPT="start_dell_ai_agent.bat"
    
    cat > "$STARTUP_SCRIPT" << EOF
@echo off
echo Starting Dell Server AI Agent...

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start the agent
python main.py

pause
EOF

    print_status "Startup script created: $STARTUP_SCRIPT"
    print_status "You can run this script to start the agent manually"
}

# Test installation
test_installation() {
    print_status "Testing installation..."
    
    # Test Python import
    if python -c "import fastapi, aiohttp, redfish" 2>/dev/null; then
        print_status "Python dependencies test passed"
    else
        print_error "Python dependencies test failed"
        return 1
    fi
    
    # Test main script
    if python -c "import main" 2>/dev/null; then
        print_status "Main script import test passed"
    else
        print_error "Main script import test failed"
        return 1
    fi
    
    print_status "Installation test completed successfully"
}

# Print next steps
print_next_steps() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Installation Completed Successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo ""
    echo "1. Edit configuration file:"
    echo "   nano config/.env"
    echo ""
    echo "2. Start the application:"
    if [[ "$OS" == "windows" ]]; then
        echo "   start_dell_ai_agent.bat"
    else
        echo "   ./venv/bin/python main.py"
    fi
    echo ""
    echo "3. Access the web interface:"
    echo "   http://localhost:8000"
    echo ""
    echo "4. Connect your first Dell server:"
    echo "   - Server IP: 192.168.1.100"
    echo "   - Username: root"
    echo "   - Password: calvin"
    echo "   - Port: 443"
    echo ""
    echo -e "${YELLOW}Important Notes:${NC}"
    echo "- Change default iDRAC passwords in production"
    echo "- Configure HTTPS for production deployments"
    echo "- Review security settings in config/.env"
    echo "- Check logs in logs/ directory for troubleshooting"
    echo ""
    echo -e "${BLUE}Documentation:${NC}"
    echo "- README_COMPREHENSIVE.md - Complete documentation"
    echo "- USAGE_GUIDE.md - Step-by-step usage instructions"
    echo "- QUICK_START.md - Quick start guide"
    echo ""
    echo -e "${GREEN}Happy server managing! 🚀${NC}"
}

# Main installation function
main() {
    print_header
    check_root
    check_os
    check_python
    install_system_deps
    create_venv
    activate_venv
    upgrade_pip
    install_python_deps
    create_directories
    create_config
    create_systemd_service
    create_startup_script
    test_installation
    print_next_steps
}

# Run main function
main "$@"
