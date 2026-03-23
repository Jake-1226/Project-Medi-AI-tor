# Dell Server AI Agent Installation Script for Windows PowerShell
# This script installs the Dell Server AI Agent and its dependencies

param(
    [Parameter(Mandatory=$false)]
    [string]$PythonVersion = "3.9",
    
    [Parameter(Mandatory=$false)]
    [string]$InstallPath = "C:\DellAIAgent",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipPythonCheck,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipSystemDeps,
    
    [Parameter(Mandatory=$false)]
    [switch]$CreateService
)

# Colors for output
$Colors = @{
    Red = "Red"
    Green = "Green"
    Yellow = "Yellow"
    Blue = "Blue"
    White = "White"
}

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = $Colors.White
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Status {
    param([string]$Message)
    Write-ColorOutput "[INFO] $Message" $Colors.Green
}

function Write-Warning {
    param([string]$Message)
    Write-ColorOutput "[WARNING] $Message" $Colors.Yellow
}

function Write-Error {
    param([string]$Message)
    Write-ColorOutput "[ERROR] $Message" $Colors.Red
}

function Write-Header {
    Write-ColorOutput "========================================" $Colors.Blue
    Write-ColorOutput "  Dell Server AI Agent Installer" $Colors.Blue
    Write-ColorOutput "========================================" $Colors.Blue
    Write-Host ""
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    if ($currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        return $true
    }
    return $false
}

function Test-PythonVersion {
    try {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCmd) {
            $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
        }
        
        if (-not $pythonCmd) {
            throw "Python is not installed"
        }
        
        $version = & $pythonCmd -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
        $requiredVersion = [3, 8]
        $versionParts = $version.Split('.')
        $major = [int]$versionParts[0]]
        $minor = [int]$versionParts[1]]
        
        if ($major -gt $requiredVersion[0] -or ($major -eq $requiredVersion[0] -and $minor -ge $requiredVersion[1])) {
            Write-Status "Python version $version is compatible"
            return $true
        } else {
            Write-Error "Python $version is not compatible. Required: 3.8 or higher"
            return $false
        }
    }
    catch {
        Write-Error "Failed to check Python version: $_"
        return $false
    }
}

function Install-Python {
    Write-Status "Installing Python $PythonVersion..."
    
    try {
        # Download Python installer
        $pythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
        $installerPath = "$env:TEMP\python-installer.exe"
        
        Write-Status "Downloading Python installer from: $pythonUrl"
        Invoke-WebRequest -Uri $pythonUrl -OutFile $installerPath
        
        Write-Status "Running Python installer..."
        Start-Process -FilePath $installerPath -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=0" -Wait
        
        # Refresh environment variables
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "", "User")
        [System.Environment]::SetEnvironmentVariable("PATH", $env:PATH, "Machine")
        
        Write-Status "Python installation completed"
    }
    catch {
        Write-Error "Failed to install Python: $_"
        throw
    }
}

function Install-Chocolatey {
    Write-Status "Installing Chocolatey package manager..."
    
    try {
        Set-ExecutionPolicy Bypass -Scope Process -Force
        $installScript = Invoke-WebRequest -Uri "https://chocolatey.org/install.ps1" -UseBasicParsing
        Invoke-Expression $installScript.Content
        Write-Status "Chocolatey installed successfully"
    }
    catch {
        Write-Error "Failed to install Chocolatey: $_"
        throw
    }
}

function Install-SystemDependencies {
    Write-Status "Installing system dependencies..."
    
    try {
        # Install Git if not present
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Write-Status "Installing Git..."
            choco install git -y
        }
        
        # Install Visual Studio Build Tools (for some Python packages)
        if (-not (Get-Command cl -ErrorAction SilentlyContinue)) {
            Write-Status "Installing Visual Studio Build Tools..."
            choco install visualstudio2019buildtools -y
        }
        
        Write-Status "System dependencies installed successfully"
    }
    catch {
        Write-Error "Failed to install system dependencies: $_"
        throw
    }
}

function Create-Directory {
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        Write-Status "Created directory: $Path"
    }
}

function Create-Directories {
    Write-Status "Creating necessary directories..."
    
    $directories = @(
        "$InstallPath",
        "$InstallPath\logs",
        "$InstallPath\data",
        "$InstallPath\config",
        "$InstallPath\backups",
        "$InstallPath\temp"
    )
    
    foreach ($dir in $directories) {
        Create-Directory $dir
    }
}

function Create-VirtualEnvironment {
    Write-Status "Creating Python virtual environment..."
    
    $venvPath = "$InstallPath\venv"
    
    if (Test-Path $venvPath) {
        Write-Warning "Virtual environment already exists at $venvPath"
        $response = Read-Host "Do you want to recreate it? (y/N): "
        if ($response -notmatch '^[Yy]') {
            Write-Status "Using existing virtual environment"
            return
        }
        Remove-Item -Path $venvPath -Recurse -Force
    }
    
    try {
        & python -m venv $venvPath
        Write-Status "Virtual environment created: $venvPath"
    }
    catch {
        Write-Error "Failed to create virtual environment: $_"
        throw
    }
}

function Activate-VirtualEnvironment {
    Write-Status "Activating virtual environment..."
    
    $venvPath = "$InstallPath\venv"
    $activateScript = "$venvPath\Scripts\Activate.ps1"
    
    if (Test-Path $activateScript) {
        try {
            & $activateScript
            Write-Status "Virtual environment activated"
        }
        catch {
            Write-Error "Failed to activate virtual environment: $_"
            throw
        }
    } else {
        Write-Error "Virtual environment activation script not found"
        throw
    }
}

function Install-PythonDependencies {
    Write-Status "Installing Python dependencies..."
    
    try {
        $requirementsPath = "$InstallPath\requirements.txt"
        
        if (Test-Path $requirementsPath) {
            & python -m pip install --upgrade pip
            & python -m pip install -r $requirementsPath
            Write-Status "Dependencies installed from requirements.txt"
        } else {
            Write-Error "requirements.txt not found at $requirementsPath"
            throw
        }
    }
    catch {
        Write-Error "Failed to install Python dependencies: $_"
        throw
    }
}

function Create-Configuration {
    Write-Status "Creating configuration file..."
    
    $configPath = "$InstallPath\config\.env"
    
    if (Test-Path $configPath) {
        Write-Warning "Configuration file already exists at $configPath"
        $response = Read-Host "Do you want to overwrite it? (y/N): "
        if ($response -notmatch '^[Yy]') {
            return
        }
    }
    
    $configContent = @"
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
"@
    
    $configContent | Out-File -FilePath $configPath -Encoding UTF8
    Write-Status "Configuration file created: $configPath"
    Write-Warning "Please edit $configPath to customize your settings"
}

function Create-StartupScript {
    Write-Status "Creating startup script..."
    
    $startupScript = "$InstallPath\start_agent.bat"
    
    $startupContent = @"
@echo off
echo Starting Dell Server AI Agent...

REM Change to installation directory
cd /d "$InstallPath.Replace('\', '/')"

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start the agent
python main.py

pause
"@
    
    $startupContent | Out-File -FilePath $startupScript -Encoding UTF8
    Write-Status "Startup script created: $startupScript"
    Write-Status "Run this script to start the agent manually"
}

function Create-Service {
    Write-Status "Creating Windows service..."
    
    try {
        # Check if NSSM is available
        if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
            Write-Warning "NSSM not found. Installing NSSM..."
            choco install nssm -y
        }
        
        $serviceName = "DellAIAgent"
        $serviceDisplayName = "Dell Server AI Agent"
        $serviceDescription = "AI-powered Dell server management and troubleshooting agent"
        $executablePath = "$InstallPath\venv\Scripts\python.exe"
        $arguments = "$InstallPath\main.py"
        $logPath = "$InstallPath\logs"
        
        # Create service
        nssm install $serviceName $serviceDisplayName $executablePath $arguments
        nssm set $serviceName Description "$serviceDescription"
        nssm set $serviceName DisplayName $serviceDisplayName
        nssm set $serviceName ObjectName $serviceName
        nssm set $serviceName ErrorSeverityIgnore 1
        nssm set $serviceName Start SERVICE_DELAYED_AUTO_START 2
        
        # Configure log file
        nssm set $serviceName AppStdout "$logPath\stdout.log"
        nssm set $serviceName AppStderr "$logPath\stderr.log"
        nssm set $serviceName AppRotateFiles 1
        nssm set $serviceName AppRotateOnline 1
        nssm set $serviceName AppRotateSeconds 86400
        
        # Set service to auto-start
        nssm set $serviceName Start SERVICE_DELAYED_AUTO_START 2
        
        Write-Status "Windows service created successfully"
        Write-Status "Service name: $serviceName"
        Write-Status "Start service: Start-Process $serviceName"
        Write-Status "Stop service: Stop-Process $serviceName"
        Write-Status "Remove service: nssm remove $serviceName"
    }
    catch {
        Write-Error "Failed to create Windows service: $_"
        throw
    }
}

function Test-Installation {
    Write-Status "Testing installation..."
    
    try {
        # Test Python import
        $testResult = python -c "import fastapi, aiohttp, redfish" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Status "Python dependencies test passed"
        } else {
            Write-Error "Python dependencies test failed"
            return $false
        }
        
        # Test main script import
        $testResult = python -c "import sys; sys.path.append('$InstallPath'); import main" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Status "Main script import test passed"
        } else {
            Write-Error "Main script import test failed"
            return $false
        }
        
        Write-Status "Installation test completed successfully"
        return $true
    }
    catch {
        Write-Error "Installation test failed: $_"
        return $false
    }
}

function Print-NextSteps {
    Write-Host ""
    Write-ColorOutput "========================================" $Colors.Green
    Write-ColorOutput "  Installation Completed Successfully!" $Colors.Green
    Write-ColorOutput "========================================" $Colors.Green
    Write-Host ""
    Write-ColorOutput "Next Steps:" $Colors.Blue
    Write-Host ""
    Write-Host "1. Edit configuration file:"
    Write-Host "   notepad $InstallPath\config\.env"
    Write-Host ""
    Write-Host "2. Start the application:"
    Write-Host "   $InstallPath\start_agent.bat"
    Write-Host ""
    Write-Host "3. Access the web interface:"
    Write-Host "   http://localhost:8000"
    Write-Host ""
    Write-Host "4. Connect your first Dell server:"
    Write-Host "   - Server IP: 192.168.1.100"
    Write-Host "   - Username: root"
    Write-Host "   - Password: calvin"
    Write-Host "   - Port: 443"
    Write-Host ""
    Write-ColorOutput "Important Notes:" $Colors.Yellow
    Write-Host "- Change default iDRAC passwords in production"
    Write-Host "- Configure HTTPS for production deployments"
    Write-Host "- Review security settings in config\.env"
    Write-Host "- Check logs in logs\ directory for troubleshooting"
    Write-Host ""
    Write-ColorOutput "Documentation:" $Colors.Blue
    Write-Host "- README_COMPREHENSIVE.md - Complete documentation"
    Write-Host "- USAGE_GUIDE.md - Step-by-step usage instructions"
    Write-Host "- QUICK_START.md - Quick start guide"
    Write-Host ""
    Write-ColorOutput "Happy server managing! 🚀" $Colors.Green
}

# Main installation function
function Main {
    try {
        Write-Header
        
        # Check administrator privileges
        if (-not (Test-Administrator)) {
            Write-Warning "Administrator privileges recommended for installation"
            $response = Read-Host "Do you want to continue? (y/N): "
            if ($response -notmatch '^[Yy]') {
                Write-Status "Installation cancelled"
                return
            }
        }
        
        # Check Python version
        if (-not $SkipPythonCheck) {
            if (-not (Test-PythonVersion)) {
                Write-Status "Installing Python $PythonVersion..."
                Install-Python
            }
        }
        
        # Install system dependencies
        if (-not $SkipSystemDeps) {
            Install-SystemDependencies
        }
        
        # Create directories
        Create-Directories
        
        # Create virtual environment
        Create-VirtualEnvironment
        
        # Install Python dependencies
        Install-PythonDependencies
        
        # Create configuration
        Create-Configuration
        
        # Create startup script
        Create-StartupScript
        
        # Create Windows service if requested
        if ($CreateService) {
            Create-Service
        }
        
        # Test installation
        if (Test-Installation) {
            Print-NextSteps
        } else {
            Write-Error "Installation test failed"
            exit 1
        }
    }
    catch {
        Write-Error "Installation failed: $_"
        exit 1
    }
}

# Run main function
Main
