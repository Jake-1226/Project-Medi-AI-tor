"""
SSH Client for OS-level server management
Connects directly to the server OS via SSH for operations that require OS access.
Works independently or alongside iDRAC/Redfish for maximum functionality.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import paramiko (SSH library)
try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False
    logger.warning("paramiko not installed - SSH functionality will be unavailable")


class SSHClient:
    """SSH client for OS-level server management"""
    
    def __init__(self, host: str, username: str, password: str = None, 
                 port: int = 22, key_file: str = None, timeout: int = 30):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.key_file = key_file
        self.timeout = timeout
        self.client = None
        self.connected = False
        self.os_type = None  # 'linux', 'windows', 'esxi'
        self.os_info = {}
    
    async def connect(self) -> bool:
        """Establish SSH connection to server OS"""
        if not PARAMIKO_AVAILABLE:
            logger.error("paramiko not installed - cannot establish SSH connection")
            return False
        
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Run connect in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            connect_kwargs = {
                'hostname': self.host,
                'port': self.port,
                'username': self.username,
                'timeout': self.timeout,
                'allow_agent': False,
                'look_for_keys': False,
            }
            
            if self.key_file:
                connect_kwargs['key_filename'] = self.key_file
            elif self.password:
                connect_kwargs['password'] = self.password
            
            await loop.run_in_executor(None, lambda: self.client.connect(**connect_kwargs))
            self.connected = True
            
            # Detect OS type
            await self._detect_os()
            
            logger.info(f"SSH connected to {self.host}:{self.port} (OS: {self.os_type})")
            return True
            
        except paramiko.AuthenticationException:
            logger.error(f"SSH authentication failed for {self.username}@{self.host}")
            self.connected = False
            return False
        except paramiko.SSHException as e:
            logger.error(f"SSH connection error to {self.host}: {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"SSH connection failed to {self.host}: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Close SSH connection"""
        if self.client:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.client.close)
            except:
                pass
        self.client = None
        self.connected = False
        logger.info(f"SSH disconnected from {self.host}")
    
    async def execute(self, command: str, timeout: int = None) -> Tuple[bool, str, str]:
        """Execute command via SSH. Returns (success, stdout, stderr)"""
        if not self.connected or not self.client:
            return False, "", "Not connected via SSH"
        
        try:
            loop = asyncio.get_event_loop()
            
            def _exec():
                stdin, stdout, stderr = self.client.exec_command(
                    command, timeout=timeout or self.timeout
                )
                out = stdout.read().decode('utf-8', errors='replace').strip()
                err = stderr.read().decode('utf-8', errors='replace').strip()
                exit_code = stdout.channel.recv_exit_status()
                return exit_code == 0, out, err
            
            success, out, err = await loop.run_in_executor(None, _exec)
            return success, out, err
            
        except Exception as e:
            logger.error(f"SSH command execution error: {e}")
            return False, "", str(e)
    
    async def _detect_os(self):
        """Detect the operating system type"""
        # Try Linux first
        success, out, _ = await self.execute("uname -s", timeout=10)
        if success:
            kernel = out.strip().lower()
            if 'linux' in kernel:
                self.os_type = 'linux'
                await self._collect_linux_info()
                return
            elif 'vmkernel' in kernel:
                self.os_type = 'esxi'
                await self._collect_esxi_info()
                return
        
        # Try Windows
        success, out, _ = await self.execute("ver", timeout=10)
        if success and 'windows' in out.lower():
            self.os_type = 'windows'
            await self._collect_windows_info()
            return
        
        # Try PowerShell
        success, out, _ = await self.execute("powershell -Command \"$PSVersionTable.PSVersion\"", timeout=10)
        if success:
            self.os_type = 'windows'
            await self._collect_windows_info()
            return
        
        self.os_type = 'unknown'
    
    async def _collect_linux_info(self):
        """Collect Linux OS information"""
        info = {}
        
        # Distribution
        success, out, _ = await self.execute("cat /etc/os-release 2>/dev/null | head -5")
        if success:
            for line in out.split('\n'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    info[k.strip()] = v.strip().strip('"')
        
        # Hostname
        success, out, _ = await self.execute("hostname")
        if success:
            info['hostname'] = out.strip()
        
        # Kernel
        success, out, _ = await self.execute("uname -r")
        if success:
            info['kernel'] = out.strip()
        
        # Uptime
        success, out, _ = await self.execute("uptime -p 2>/dev/null || uptime")
        if success:
            info['uptime'] = out.strip()
        
        self.os_info = info
    
    async def _collect_windows_info(self):
        """Collect Windows OS information"""
        info = {}
        success, out, _ = await self.execute('powershell -Command "Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber | Format-List"')
        if success:
            for line in out.split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    info[k.strip()] = v.strip()
        
        success, out, _ = await self.execute("hostname")
        if success:
            info['hostname'] = out.strip()
        
        self.os_info = info
    
    async def _collect_esxi_info(self):
        """Collect ESXi information"""
        info = {}
        success, out, _ = await self.execute("esxcli system version get")
        if success:
            for line in out.split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    info[k.strip()] = v.strip()
        
        success, out, _ = await self.execute("hostname")
        if success:
            info['hostname'] = out.strip()
        
        self.os_info = info
    
    # ─── OS-Level Information Commands ─────────────────────────
    
    async def get_os_info(self) -> Dict[str, Any]:
        """Get comprehensive OS information"""
        return {
            "os_type": self.os_type,
            "os_info": self.os_info,
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "username": self.username,
        }
    
    async def get_system_resources(self) -> Dict[str, Any]:
        """Get CPU, memory, disk usage from OS level"""
        result = {"timestamp": datetime.now().isoformat()}
        
        if self.os_type == 'linux':
            # CPU usage
            success, out, _ = await self.execute("top -bn1 | head -5")
            if success:
                result['cpu_info'] = out
            
            # Memory
            success, out, _ = await self.execute("free -h")
            if success:
                result['memory'] = out
            
            # Disk usage
            success, out, _ = await self.execute("df -h")
            if success:
                result['disk_usage'] = out
            
            # Load average
            success, out, _ = await self.execute("cat /proc/loadavg")
            if success:
                parts = out.split()
                result['load_average'] = {
                    '1min': float(parts[0]) if len(parts) > 0 else 0,
                    '5min': float(parts[1]) if len(parts) > 1 else 0,
                    '15min': float(parts[2]) if len(parts) > 2 else 0,
                }
            
            # Uptime
            success, out, _ = await self.execute("uptime -p 2>/dev/null || uptime")
            if success:
                result['uptime'] = out.strip()
                
        elif self.os_type == 'windows':
            success, out, _ = await self.execute('powershell -Command "Get-CimInstance Win32_Processor | Select-Object LoadPercentage; Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory, TotalVisibleMemorySize"')
            if success:
                result['system_stats'] = out
            
            success, out, _ = await self.execute('powershell -Command "Get-PSDrive -PSProvider FileSystem | Format-Table Name, Used, Free, @{N=\'Size\';E={$_.Used+$_.Free}} -AutoSize"')
            if success:
                result['disk_usage'] = out
        
        elif self.os_type == 'esxi':
            success, out, _ = await self.execute("esxcli hardware memory get")
            if success:
                result['memory'] = out
            
            success, out, _ = await self.execute("esxcli storage filesystem list")
            if success:
                result['disk_usage'] = out
        
        return result
    
    async def get_running_processes(self, top_n: int = 20) -> Dict[str, Any]:
        """Get top running processes"""
        if self.os_type == 'linux':
            success, out, _ = await self.execute(f"ps aux --sort=-%cpu | head -{top_n + 1}")
            if success:
                return {"processes": out, "os_type": self.os_type}
        elif self.os_type == 'windows':
            success, out, _ = await self.execute(f'powershell -Command "Get-Process | Sort-Object CPU -Descending | Select-Object -First {top_n} Name, Id, CPU, WorkingSet64 | Format-Table -AutoSize"')
            if success:
                return {"processes": out, "os_type": self.os_type}
        elif self.os_type == 'esxi':
            success, out, _ = await self.execute("esxtop -b -n 1 | head -5")
            if success:
                return {"processes": out, "os_type": self.os_type}
        
        return {"processes": "Unable to retrieve processes", "os_type": self.os_type}
    
    async def get_services(self) -> Dict[str, Any]:
        """Get running services"""
        if self.os_type == 'linux':
            success, out, _ = await self.execute("systemctl list-units --type=service --state=running --no-pager 2>/dev/null || service --status-all 2>/dev/null")
            if success:
                return {"services": out, "os_type": self.os_type}
        elif self.os_type == 'windows':
            success, out, _ = await self.execute('powershell -Command "Get-Service | Where-Object {$_.Status -eq \'Running\'} | Select-Object Name, DisplayName, Status | Format-Table -AutoSize"')
            if success:
                return {"services": out, "os_type": self.os_type}
        elif self.os_type == 'esxi':
            success, out, _ = await self.execute("/etc/init.d/hostd status; esxcli system process list")
            if success:
                return {"services": out, "os_type": self.os_type}
        
        return {"services": "Unable to retrieve services", "os_type": self.os_type}
    
    async def get_network_info(self) -> Dict[str, Any]:
        """Get OS-level network configuration"""
        result = {"os_type": self.os_type}
        
        if self.os_type == 'linux':
            success, out, _ = await self.execute("ip addr show 2>/dev/null || ifconfig")
            if success:
                result['interfaces'] = out
            
            success, out, _ = await self.execute("ip route show 2>/dev/null || route -n")
            if success:
                result['routes'] = out
            
            success, out, _ = await self.execute("cat /etc/resolv.conf 2>/dev/null")
            if success:
                result['dns'] = out
            
            success, out, _ = await self.execute("ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")
            if success:
                result['listening_ports'] = out
                
        elif self.os_type == 'windows':
            success, out, _ = await self.execute('powershell -Command "Get-NetIPConfiguration | Format-List"')
            if success:
                result['interfaces'] = out
            
            success, out, _ = await self.execute("netstat -an | findstr LISTENING")
            if success:
                result['listening_ports'] = out
        
        return result
    
    async def get_os_logs(self, lines: int = 100) -> Dict[str, Any]:
        """Get recent OS-level logs"""
        result = {"os_type": self.os_type, "timestamp": datetime.now().isoformat()}
        
        if self.os_type == 'linux':
            # System journal
            success, out, _ = await self.execute(f"journalctl -n {lines} --no-pager 2>/dev/null || tail -{lines} /var/log/syslog 2>/dev/null || tail -{lines} /var/log/messages")
            if success:
                result['system_log'] = out
            
            # Kernel messages
            success, out, _ = await self.execute(f"dmesg | tail -{lines}")
            if success:
                result['kernel_log'] = out
            
            # Auth log
            success, out, _ = await self.execute(f"tail -{min(lines, 50)} /var/log/auth.log 2>/dev/null || tail -{min(lines, 50)} /var/log/secure 2>/dev/null")
            if success:
                result['auth_log'] = out
                
        elif self.os_type == 'windows':
            success, out, _ = await self.execute(f'powershell -Command "Get-EventLog -LogName System -Newest {lines} | Format-Table TimeGenerated, EntryType, Source, Message -AutoSize"')
            if success:
                result['system_log'] = out
            
            success, out, _ = await self.execute(f'powershell -Command "Get-EventLog -LogName Application -Newest {lines} | Format-Table TimeGenerated, EntryType, Source, Message -AutoSize"')
            if success:
                result['application_log'] = out
        
        elif self.os_type == 'esxi':
            success, out, _ = await self.execute(f"tail -{lines} /var/log/vmkernel.log")
            if success:
                result['vmkernel_log'] = out
        
        return result
    
    async def get_storage_info(self) -> Dict[str, Any]:
        """Get OS-level storage details"""
        result = {"os_type": self.os_type}
        
        if self.os_type == 'linux':
            success, out, _ = await self.execute("lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL 2>/dev/null || fdisk -l 2>/dev/null")
            if success:
                result['block_devices'] = out
            
            success, out, _ = await self.execute("df -Th")
            if success:
                result['filesystem_usage'] = out
            
            success, out, _ = await self.execute("cat /proc/mdstat 2>/dev/null")
            if success and out.strip():
                result['md_raid'] = out
            
            success, out, _ = await self.execute("pvs 2>/dev/null && vgs 2>/dev/null && lvs 2>/dev/null")
            if success and out.strip():
                result['lvm'] = out
                
        elif self.os_type == 'windows':
            success, out, _ = await self.execute('powershell -Command "Get-Disk | Format-Table Number, FriendlyName, Size, PartitionStyle, OperationalStatus -AutoSize"')
            if success:
                result['disks'] = out
            
            success, out, _ = await self.execute('powershell -Command "Get-Volume | Format-Table DriveLetter, FileSystemLabel, FileSystem, Size, SizeRemaining -AutoSize"')
            if success:
                result['volumes'] = out
        
        elif self.os_type == 'esxi':
            success, out, _ = await self.execute("esxcli storage core device list")
            if success:
                result['devices'] = out
        
        return result
    
    async def get_installed_packages(self) -> Dict[str, Any]:
        """Get installed packages/software"""
        result = {"os_type": self.os_type}
        
        if self.os_type == 'linux':
            # Try rpm first, then dpkg
            success, out, _ = await self.execute("rpm -qa --queryformat '%{NAME} %{VERSION}-%{RELEASE}\\n' 2>/dev/null | sort | head -100")
            if success and out.strip():
                result['packages'] = out
                result['package_manager'] = 'rpm'
            else:
                success, out, _ = await self.execute("dpkg -l | tail -n +6 | head -100")
                if success:
                    result['packages'] = out
                    result['package_manager'] = 'dpkg'
        
        elif self.os_type == 'windows':
            success, out, _ = await self.execute('powershell -Command "Get-WmiObject -Class Win32_Product | Select-Object Name, Version | Sort-Object Name | Format-Table -AutoSize"')
            if success:
                result['packages'] = out
        
        return result
    
    async def check_service_status(self, service_name: str) -> Dict[str, Any]:
        """Check specific service status"""
        if self.os_type == 'linux':
            success, out, _ = await self.execute(f"systemctl status {service_name} 2>/dev/null || service {service_name} status 2>/dev/null")
            return {"service": service_name, "status": out if success else "not found", "running": success}
        elif self.os_type == 'windows':
            success, out, _ = await self.execute(f'powershell -Command "Get-Service -Name {service_name} | Format-List"')
            return {"service": service_name, "status": out if success else "not found", "running": success}
        return {"service": service_name, "status": "unsupported OS", "running": False}
    
    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        """Restart a service"""
        if self.os_type == 'linux':
            success, out, err = await self.execute(f"sudo systemctl restart {service_name} 2>&1 || sudo service {service_name} restart 2>&1")
            return {"service": service_name, "action": "restart", "success": success, "output": out or err}
        elif self.os_type == 'windows':
            success, out, err = await self.execute(f'powershell -Command "Restart-Service -Name {service_name} -Force"')
            return {"service": service_name, "action": "restart", "success": success, "output": out or err}
        return {"service": service_name, "action": "restart", "success": False, "output": "unsupported OS"}
    
    async def run_custom_command(self, command: str) -> Dict[str, Any]:
        """Run a custom command on the OS"""
        success, out, err = await self.execute(command)
        return {
            "command": command,
            "success": success,
            "stdout": out,
            "stderr": err,
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_hardware_info(self) -> Dict[str, Any]:
        """Get hardware info from OS level (complements iDRAC data)"""
        result = {"os_type": self.os_type}
        
        if self.os_type == 'linux':
            success, out, _ = await self.execute("lscpu 2>/dev/null")
            if success:
                result['cpu'] = out
            
            success, out, _ = await self.execute("cat /proc/meminfo | head -10")
            if success:
                result['memory'] = out
            
            success, out, _ = await self.execute("lspci 2>/dev/null | head -30")
            if success:
                result['pci_devices'] = out
            
            success, out, _ = await self.execute("dmidecode -t system 2>/dev/null | head -20")
            if success:
                result['system'] = out
                
        elif self.os_type == 'windows':
            success, out, _ = await self.execute('powershell -Command "Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors | Format-List"')
            if success:
                result['cpu'] = out
            
            success, out, _ = await self.execute('powershell -Command "Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed, Manufacturer | Format-Table"')
            if success:
                result['memory'] = out
        
        return result
    
    def is_connected(self) -> bool:
        """Check if SSH connection is active"""
        if not self.connected or not self.client:
            return False
        try:
            transport = self.client.get_transport()
            return transport is not None and transport.is_active()
        except:
            return False
