# Technician Dashboard Connection Debugging Guide

## 🚀 Step-by-Step Debugging Process

### Step 1: Open Browser Developer Tools
1. Open your browser (Chrome, Firefox, or Edge)
2. Navigate to: `http://localhost:8000/technician`
3. Press **F12** to open Developer Tools
4. Go to the **Console** tab

### Step 2: Check for JavaScript Errors
Look for any red error messages in the console. Common errors:
- `SyntaxError`: JavaScript syntax issues
- `TypeError`: Type-related errors
- `ReferenceError`: Variable/function not found
- `NetworkError`: Network connectivity issues

**If you see errors, please copy the exact error message.**

### Step 3: Test Basic Connectivity
In the console, type these commands one by one:

```javascript
// Test 1: Check if app object exists
console.log('App object:', typeof app);

// Test 2: Check if connectToServer function exists
console.log('connectToServer function:', typeof app?.connectToServer);

// Test 3: Check if API base is correct
console.log('API base:', app?.apiBase);

// Test 4: Check form elements
console.log('Connection form:', document.getElementById('connectionForm'));
console.log('Server host field:', document.getElementById('serverHost'));
console.log('Connect button:', document.getElementById('connectBtn'));
```

### Step 4: Test Network Requests
1. Go to the **Network** tab in Developer Tools
2. Clear the network log (click the clear button)
3. Try to connect in the technician dashboard
4. Look for any failed requests (red status codes)

**Check specifically for:**
- `/api/connect` request
- Request status code (should be 200)
- Request payload (should contain serverHost, username, password, port)
- Response payload (should contain success message)

### Step 5: Manual Connection Test
In the console, try this manual connection test:

```javascript
// Manual connection test
fetch('/api/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        serverHost: '100.71.148.195',
        username: 'root',
        password: 'calvin',
        port: '443'
    })
})
.then(response => response.json())
.then(data => console.log('Manual connection result:', data))
.catch(error => console.error('Manual connection error:', error));
```

### Step 6: Check Server Status
In the console, test if the server is responding:

```javascript
// Test server health
fetch('/api/health')
.then(response => response.json())
.then(data => console.log('Server health:', data))
.catch(error => console.error('Health check error:', error));
```

### Step 7: Use the Browser Debug Tool
Open this URL in your browser:
`http://localhost:8000/browser_debug_tool.html`

This tool will automatically test:
- Browser compatibility
- Server connectivity
- API endpoints
- Connection form
- Action execution

### Step 8: Common Issues and Solutions

#### Issue: "action failed : object Object"
**Solution:** This should be fixed now. If you still see it, check the Network tab for the actual error.

#### Issue: "Not connected to server"
**Solution:** Make sure you're connected before trying actions. The connection status should show "Connected".

#### Issue: Network errors
**Solution:** Check if the server is running on port 8000.

#### Issue: Form submission not working
**Solution:** Check if all form fields are filled out correctly.

### Step 9: Report Your Findings

Please provide:
1. **Console errors** (if any)
2. **Network request status** (from Network tab)
3. **Browser debug tool results**
4. **Manual connection test results**

### Step 10: Quick Fix Checklist

- [ ] Server is running (`python main.py`)
- [ ] Browser console shows no errors
- [ ] Network requests show 200 status
- [ ] Form fields are filled correctly
- [ ] Connection status shows "Connected"

## 🔧 If Issues Persist

If you're still having problems after following this guide:

1. **Restart the server:**
   ```bash
   # Stop the server (Ctrl+C in terminal)
   # Restart it:
   python main.py
   ```

2. **Clear browser cache:**
   - Press `Ctrl+Shift+Delete`
   - Select "Cached images and files"
   - Click "Clear data"

3. **Try a different browser** (Chrome, Firefox, Edge)

4. **Check Windows Firewall:**
   - Make sure port 8000 is not blocked

## 📞 Need More Help?

If you're still stuck, please provide:
- Screenshot of browser console errors
- Screenshot of Network tab requests
- Exact error messages you're seeing
- Browser version you're using

I'll help you fix any remaining issues!
