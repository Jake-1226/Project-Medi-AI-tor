# Dell Server AI Agent

🖥️ A lightweight AI-powered agent that acts as an intermediary between Virtual Assistants and Dell servers, leveraging Redfish API and RACADM for comprehensive server management and troubleshooting.

## 🚀 Features

### Core Capabilities
- **Multi-Protocol Support**: Redfish API + RACADM integration for comprehensive Dell server management
- **AI-Powered Troubleshooting**: Intelligent analysis of server issues with contextual recommendations
- **Configurable Action Levels**: From read-only monitoring to full server control
- **Real-time Log Analysis**: Pattern detection and anomaly identification in system logs
- **Modern Web Interface**: Responsive dashboard for technicians and field engineers

### Action Levels
- 🔍 **Read Only**: Safe monitoring and data collection
- 🔧 **Diagnostic**: Run diagnostics and performance analysis
- 🚀 **Full Control**: Complete server management including power operations

### Dell-Specific Features
- **iDRAC Management**: Full integration with Dell iDRAC controllers
- **Hardware Monitoring**: Real-time monitoring of power supplies, temperature sensors, fans
- **Storage Management**: RAID controller and disk health monitoring
- **Firmware Management**: BIOS and iDRAC firmware updates
- **SupportAssist Integration**: Automated support collection generation

## 📋 Prerequisites

### System Requirements
- Python 3.8 or higher
- Dell server with iDRAC (version 7 or higher recommended)
- Network connectivity to server iDRAC
- For RACADM features: Dell OpenManage Server Administrator installed

### Dependencies
```bash
pip install -r requirements.txt
```

## 🛠️ Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd dell-server-ai-agent
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment (optional)**
```bash
cp .env.example .env
# Edit .env with your settings
```

4. **Run the application**
```bash
python main.py
```

The application will be available at `http://localhost:8000`

## 🔧 Configuration

### Environment Variables
```bash
# Server Configuration
REDFISH_PORT=443
CONNECTION_TIMEOUT=30
MAX_RETRIES=3

# Security
SECURITY_LEVEL=medium
REQUIRE_HTTPS=true
VERIFY_SSL=false

# Logging
LOG_LEVEL=INFO
LOG_FILE=agent.log

# AI Settings
ENABLE_AI_RECOMMENDATIONS=true
CONFIDENCE_THRESHOLD=0.7

# Dell Specific
RACADM_TIMEOUT=60
REDFISH_API_VERSION=1.8.0
```

### Security Levels
- **Low**: Read-only operations only
- **Medium**: Read-only + diagnostic operations
- **High**: Full control including power operations

## 📖 Usage

### Web Interface
1. Open `http://localhost:8000` in your browser
2. Enter server connection details:
   - Server Host/IP
   - Username (typically root or administrator)
   - Password
   - Port (default 443 for Redfish)
3. Select action level based on your requirements
4. Use quick actions or AI troubleshooting

### API Usage

#### Connect to Server
```bash
curl -X POST "http://localhost:8000/connect" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "192.168.1.100",
    "username": "root",
    "password": "calvin",
    "port": 443
  }'
```

#### Get Server Information
```bash
curl -X POST "http://localhost:8000/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "action_level": "read_only",
    "command": "get_server_info",
    "parameters": {}
  }'
```

#### AI Troubleshooting
```bash
curl -X POST "http://localhost:8000/troubleshoot" \
  -H "Content-Type: application/json" \
  -d '{
    "server_info": {
      "host": "192.168.1.100",
      "username": "root",
      "password": "calvin",
      "port": 443
    },
    "issue_description": "Server is running slow and showing temperature warnings",
    "action_level": "diagnostic"
  }'
```

### Available Commands

#### Read-Only Commands
- `get_server_info` - Basic server information
- `get_system_info` - Detailed system information
- `get_processors` - CPU information
- `get_memory` - Memory module details
- `get_power_supplies` - Power supply status
- `get_temperature_sensors` - Temperature readings
- `get_fans` - Fan speeds and status
- `get_storage_devices` - Storage device information
- `get_network_interfaces` - Network interface details
- `health_check` - Overall system health
- `collect_logs` - System log collection

#### Diagnostic Commands
- `performance_analysis` - Performance metrics analysis
- `connectivity_test` - Network and service connectivity
- `firmware_check` - Firmware version analysis

#### Full Control Commands
- `power_on` - Power on the server
- `power_off` - Power off the server
- `restart_server` - Graceful restart
- `force_restart` - Force restart
- `set_boot_order` - Configure boot order
- `create_support_collection` - Generate SupportAssist collection
- `export_config` - Export system configuration
- `update_firmware` - Update component firmware

## 🤖 AI Troubleshooting

The AI engine analyzes server issues and provides contextual recommendations:

### Issue Categories
- **Power Issues**: PSU failures, power loss, boot problems
- **Overheating**: Temperature warnings, fan failures
- **Memory Issues**: ECC errors, module failures
- **Storage Issues**: Disk failures, RAID problems
- **Network Issues**: Connectivity problems, NIC failures
- **Firmware Issues**: BIOS/iDRAC problems

### Example Troubleshooting Session
```
Issue: "Server is running slow and getting temperature warnings"

AI Recommendations:
1. Check temperature sensors (Priority: Critical)
   - Monitor all temperature sensors
   - Identify overheating components
   - Commands: get_temperature_sensors, get_fans

2. Verify fan operation (Priority: High)
   - Check if all fans are operating correctly
   - Commands: get_fans

3. Check airflow and ventilation (Priority: Medium)
   - Ensure proper airflow around server
   - Check for blocked vents
```

## 🔒 Security

### Authentication
- JWT-based authentication
- Role-based access control
- Session management
- Account lockout protection

### Authorization Levels
- **Admin**: Full access to all features
- **Operator**: Read-only + diagnostic access
- **Viewer**: Read-only access only

### Data Protection
- Encrypted credential storage
- Secure session management
- SSL/TLS communication support

## 📊 Monitoring & Logging

### Log Types
- System event logs
- Lifecycle Controller logs
- Hardware sensor logs
- Agent activity logs

### Metrics Collection
- Power consumption
- Temperature trends
- Fan speeds
- Network statistics
- Storage performance

## 🛠️ Development

### Project Structure
```
dell-server-ai-agent/
├── core/                   # Core agent functionality
│   ├── agent_core.py      # Main agent logic
│   └── config.py          # Configuration management
├── integrations/          # Server integrations
│   ├── redfish_client.py  # Redfish API client
│   └── racadm_client.py   # RACADM client
├── ai/                    # AI components
│   ├── troubleshooting_engine.py  # AI troubleshooting
│   └── log_analyzer.py    # Log analysis engine
├── models/                # Data models
│   └── server_models.py   # Server data models
├── security/              # Security components
│   └── auth.py           # Authentication & authorization
├── static/               # Web assets
│   ├── css/
│   └── js/
├── templates/            # HTML templates
├── main.py              # FastAPI application
└── requirements.txt     # Dependencies
```

### Adding New Features
1. Add new commands to the agent core
2. Extend data models in `models/`
3. Update the web interface
4. Add tests

## 🐛 Troubleshooting

### Common Issues

#### Connection Problems
- Verify iDRAC IP and credentials
- Check network connectivity
- Ensure iDRAC is enabled and accessible
- Verify SSL certificate settings

#### RACADM Issues
- Install Dell OpenManage Server Administrator
- Ensure RACADM is in system PATH
- Check RACADM version compatibility

#### Performance Issues
- Increase timeout settings
- Check network latency
- Monitor agent resource usage

### Debug Mode
Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
python main.py
```

## 📚 API Reference

### REST Endpoints

#### Authentication
- `POST /login` - User authentication
- `POST /logout` - User logout

#### Server Management
- `POST /connect` - Connect to server
- `POST /disconnect` - Disconnect from server
- `POST /execute` - Execute agent command
- `POST /troubleshoot` - Start AI troubleshooting

#### Monitoring
- `GET /health` - Agent health check
- `GET /sessions` - Active sessions
- `GET /logs` - Agent logs

### WebSocket
- `WS /ws` - Real-time communication

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review the API documentation

## 🎯 Roadmap

### Future Enhancements
- [ ] Multi-server management
- [ ] Advanced analytics dashboard
- [ ] Integration with monitoring systems
- [ ] Mobile application
- [ ] Voice assistant integration
- [ ] Predictive maintenance
- [ ] Automated remediation

### Dell Ecosystem Integration
- [ ] Dell EMC storage arrays
- [ ] Dell networking equipment
- [ ] Cloud integration
- [ ] Dell SupportAssist automation

---

**Built for the Dell Hackathon** 🚀

This project showcases advanced AI-powered server management capabilities specifically designed for Dell infrastructure, demonstrating comprehensive integration with Dell's management APIs and intelligent troubleshooting capabilities.
