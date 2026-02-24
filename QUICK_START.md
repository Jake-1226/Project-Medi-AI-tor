# Quick Start Guide

🚀 Get your Dell Server AI Agent running in minutes!

## 📋 Prerequisites

- Python 3.8+
- Dell server with iDRAC access
- Network connectivity to the server

## ⚡ Quick Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Agent
```bash
python main.py
```

### 3. Access the Dashboard
Open your browser and go to: `http://localhost:8000`

## 🔗 Connect to Your Server

### Using the Web Interface
1. **Server Host/IP**: Your Dell server's IP address (e.g., `192.168.1.100`)
2. **Username**: iDRAC username (typically `root`)
3. **Password**: iDRAC password
4. **Port**: `443` (default for Redfish)

### Example Connection
```
Host: 192.168.1.100
Username: root
Password: calvin
Port: 443
```

## 🎯 First Actions

### 1. Basic Server Info
- Click **"Server Info"** to get basic server details
- View model, service tag, firmware versions

### 2. Health Check
- Click **"Health Check"** for system health overview
- Check for any critical warnings

### 3. Collect Logs
- Click **"Collect Logs"** to gather system logs
- Review recent events and errors

## 🤖 Try AI Troubleshooting

### Example Scenarios

#### Temperature Issues
```
Issue: "Server is showing high temperature warnings"
```

#### Performance Problems
```
Issue: "Server is running slow and applications are unresponsive"
```

#### Power Problems
```
Issue: "Server keeps rebooting unexpectedly"
```

#### Storage Issues
```
Issue: "RAID array is showing degraded status"
```

## ⚙️ Action Levels

### 🔍 Read Only (Safe)
- View server information
- Collect logs
- Monitor health status
- **Perfect for**: Initial assessment, monitoring

### 🔧 Diagnostic (Moderate)
- All read-only features
- Performance analysis
- Connectivity tests
- **Perfect for**: Troubleshooting, analysis

### 🚀 Full Control (Advanced)
- All diagnostic features
- Power operations (reboot, shutdown)
- Configuration changes
- **Perfect for**: Maintenance, repairs

## 📊 Common Use Cases

### 1. Daily Health Check
```
Action Level: Read Only
Steps:
1. Connect to server
2. Click "Health Check"
3. Review any warnings
4. Collect logs if needed
```

### 2. Performance Investigation
```
Action Level: Diagnostic
Steps:
1. Connect to server
2. Click "Performance Analysis"
3. Review metrics
4. Use AI Troubleshooting if issues found
```

### 3. Maintenance Operations
```
Action Level: Full Control
Steps:
1. Connect to server
2. Backup configuration
3. Perform maintenance
4. Verify system health
```

## 🔧 Troubleshooting Common Issues

### Connection Failed
- ✅ Verify server IP is correct
- ✅ Check network connectivity
- ✅ Verify iDRAC credentials
- ✅ Ensure iDRAC is enabled

### SSL Certificate Errors
- ✅ Set `VERIFY_SSL=false` in environment
- ✅ Use self-signed certificates for testing

### RACADM Not Available
- ✅ Install Dell OpenManage Server Administrator
- ✅ Add RACADM to system PATH
- ✅ Use Redfish API as alternative

## 📱 Quick Commands

### Using curl (API)

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

#### Get Server Info
```bash
curl -X POST "http://localhost:8000/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "action_level": "read_only",
    "command": "get_server_info",
    "parameters": {}
  }'
```

## 🎯 Pro Tips

### 1. Start with Read-Only
Always begin with read-only access to understand the server state before making changes.

### 2. Use AI Troubleshooting
The AI engine can quickly identify common issues and provide step-by-step solutions.

### 3. Monitor Temperature
Temperature issues are common - regularly check thermal sensors and fan operation.

### 4. Check Logs Regularly
System logs contain valuable information about potential issues.

### 5. Document Changes
Keep track of configuration changes and maintenance activities.

## 🔒 Security Best Practices

- ✅ Use strong passwords for iDRAC
- ✅ Change default credentials
- ✅ Use HTTPS in production
- ✅ Limit access to trusted networks
- ✅ Regularly update firmware

## 📞 Need Help?

### Common Issues
- **Connection problems**: Check network and credentials
- **Permission errors**: Verify action level settings
- **Timeout issues**: Increase timeout values
- **SSL errors**: Disable SSL verification for testing

### Get Support
1. Check the main README.md file
2. Review the troubleshooting section
3. Check server logs for detailed errors
4. Verify iDRAC configuration

## 🚀 Next Steps

1. **Explore Features**: Try different action levels and commands
2. **Configure Monitoring**: Set up regular health checks
3. **Integrate with Tools**: Use the API for automation
4. **Customize Settings**: Adjust configuration for your environment
5. **Learn Advanced Features**: Explore AI troubleshooting capabilities

---

**You're ready to go!** 🎉

Your Dell Server AI Agent is now configured and ready to help you manage and troubleshoot your Dell infrastructure efficiently.
