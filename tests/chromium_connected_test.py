#!/usr/bin/env python3
"""Full browser test: login, connect to REAL iDRAC, verify data in every tab."""
import subprocess, tempfile, os, requests, re, shutil, time

tmpdir = tempfile.mkdtemp()
os.environ['HOME'] = tmpdir

S = requests.Session()

# Login
r = S.post('http://localhost/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['token']
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
print("1. Login: OK")

# Connect to REAL iDRAC
r = S.post('http://localhost/api/connect', json={
    'host': '100.71.148.195', 'username': 'root', 'password': 'calvin', 'port': 443
}, headers=H, timeout=30)
print(f"2. iDRAC connect: {r.json().get('status')}")

# Wait for data to load
time.sleep(2)

# Fetch all data via batch (same as dashboard does)
r = S.post('http://localhost/api/execute/batch', json={"commands": [
    {"action": "get_server_info", "parameters": {}},
    {"action": "get_processors", "parameters": {}},
    {"action": "get_memory", "parameters": {}},
    {"action": "get_power_supplies", "parameters": {}},
    {"action": "get_temperature_sensors", "parameters": {}},
    {"action": "get_fans", "parameters": {}},
    {"action": "get_storage_devices", "parameters": {}},
    {"action": "get_network_interfaces", "parameters": {}},
    {"action": "health_check", "parameters": {}},
    {"action": "collect_logs", "parameters": {}},
    {"action": "get_bios_attributes", "parameters": {}},
    {"action": "get_idrac_info", "parameters": {}},
    {"action": "get_lifecycle_logs", "parameters": {}},
    {"action": "performance_analysis", "parameters": {}},
    {"action": "get_firmware_inventory", "parameters": {}},
    {"action": "get_post_codes", "parameters": {}},
    {"action": "get_jobs", "parameters": {}},
    {"action": "get_boot_order", "parameters": {}},
    {"action": "get_idrac_network_config", "parameters": {}},
    {"action": "get_lifecycle_status", "parameters": {}},
]}, headers=H, timeout=60)

batch = r.json()
print(f"3. Batch data: {r.status_code}")
ok_cmds = [k for k,v in batch.get('results',{}).items() if v.get('status')=='success']
fail_cmds = [k for k,v in batch.get('results',{}).items() if v.get('status')!='success']
print(f"   OK: {len(ok_cmds)}, Failed: {len(fail_cmds)}")
if fail_cmds:
    print(f"   Failed: {fail_cmds}")

# Collect the data we need to verify shows up in the browser
data_checks = {}
results = batch.get('results', {})
for cmd, res in results.items():
    if res.get('status') == 'success' and res.get('result'):
        r_data = res['result']
        for key in r_data:
            data_checks[key] = True

print(f"   Data keys available: {list(data_checks.keys())}")

# Quick status
r = S.get('http://localhost/api/server/quick-status', headers=H)
qs = r.json().get('data', {})
model = qs.get('model', 'Unknown')
service_tag = qs.get('service_tag', '')
health = qs.get('health', 'unknown')
print(f"4. Server: {model} ({service_tag}), Health: {health}")

# Get the dashboard page
r = S.get('http://localhost/technician/app')
page = r.text
print(f"5. Dashboard: {len(page)} bytes")

# Build test script that verifies data shows up after handleActionResponse
test_js = """
<script>
var results = [];
var passed = 0;
var failed = 0;

function check(name, cond, detail) {
    if (cond) { passed++; results.push('PASS: ' + name); }
    else { failed++; results.push('FAIL: ' + name + ' -- ' + (detail||'').substring(0,80)); }
}

async function runTests() {
    results.push('=== WAITING FOR DATA LOAD ===');
    
    // Simulate what the dashboard does: call batch API and feed to handleActionResponse
    var token = '""" + token + """';
    var headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'};
    
    try {
        var r = await fetch('/api/execute/batch', {
            method: 'POST', headers: headers,
            body: JSON.stringify({commands: [
                {action:'get_server_info',parameters:{}},
                {action:'get_processors',parameters:{}},
                {action:'get_memory',parameters:{}},
                {action:'get_power_supplies',parameters:{}},
                {action:'get_temperature_sensors',parameters:{}},
                {action:'get_fans',parameters:{}},
                {action:'get_storage_devices',parameters:{}},
                {action:'get_network_interfaces',parameters:{}},
                {action:'health_check',parameters:{}},
                {action:'collect_logs',parameters:{}},
                {action:'get_bios_attributes',parameters:{}},
                {action:'get_idrac_info',parameters:{}},
                {action:'get_firmware_inventory',parameters:{}},
            ]})
        });
        var data = await r.json();
        results.push('Batch fetch: ' + (r.ok ? 'OK' : 'FAIL'));
        
        // Feed each result to handleActionResponse
        if (data.status === 'success' && data.results && window.app) {
            for (var action in data.results) {
                var res = data.results[action];
                if (res.status === 'success' && res.result) {
                    window.app.handleActionResponse(res.result);
                }
            }
            results.push('Data fed to handleActionResponse');
        }
    } catch(e) {
        results.push('Batch fetch error: ' + e.message);
    }
    
    // Wait for rendering
    await new Promise(r => setTimeout(r, 1500));
    
    // === OVERVIEW TAB ===
    results.push('');
    results.push('=== OVERVIEW ===');
    document.querySelector('[data-tab="overview"]')?.click();
    await new Promise(r => setTimeout(r, 300));
    
    var metricTiles = document.querySelectorAll('.metric-tile');
    check('overview metric tiles rendered', metricTiles.length > 0, 'found ' + metricTiles.length);
    
    // === SYSTEM INFO TAB ===
    results.push('');
    results.push('=== SYSTEM INFO ===');
    document.querySelector('[data-tab="system"]')?.click();
    await new Promise(r => setTimeout(r, 300));
    
    // Check General sub-tab
    document.querySelector('[data-subtab="sys-general"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var sysContainer = document.getElementById('systemInfoContainer');
    check('system info populated', sysContainer && sysContainer.innerText.length > 50, 'text=' + (sysContainer?.innerText?.length || 0));
    
    // Check Processors
    document.querySelector('[data-subtab="sys-processors"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var procContainer = document.getElementById('processorsContainer');
    check('processors populated', procContainer && procContainer.innerText.length > 20, 'text=' + (procContainer?.innerText?.length || 0));
    
    // Check Memory
    document.querySelector('[data-subtab="sys-memory"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var memContainer = document.getElementById('memoryContainer');
    check('memory populated', memContainer && memContainer.innerText.length > 20, 'text=' + (memContainer?.innerText?.length || 0));
    
    // Check BIOS
    document.querySelector('[data-subtab="sys-bios"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var biosContainer = document.getElementById('biosContainer');
    check('bios populated', biosContainer && biosContainer.innerText.length > 20, 'text=' + (biosContainer?.innerText?.length || 0));
    
    // Check Firmware
    document.querySelector('[data-subtab="sys-firmware"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var fwContainer = document.getElementById('firmwareContainer');
    check('firmware populated', fwContainer && fwContainer.innerText.length > 20, 'text=' + (fwContainer?.innerText?.length || 0));
    
    // Check iDRAC
    document.querySelector('[data-subtab="sys-idrac"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var idracContainer = document.getElementById('idracContainer');
    check('idrac info populated', idracContainer && idracContainer.innerText.length > 20, 'text=' + (idracContainer?.innerText?.length || 0));
    
    // === HEALTH TAB ===
    results.push('');
    results.push('=== HEALTH ===');
    document.querySelector('[data-tab="health"]')?.click();
    await new Promise(r => setTimeout(r, 300));
    
    var healthContainer = document.getElementById('healthStatusContainer');
    check('health status populated', healthContainer && healthContainer.innerText.length > 20, 'text=' + (healthContainer?.innerText?.length || 0));
    
    // Thermal
    document.querySelector('[data-subtab="health-thermal"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var thermalContainer = document.getElementById('thermalContainer');
    check('thermal data populated', thermalContainer && thermalContainer.innerText.length > 20, 'text=' + (thermalContainer?.innerText?.length || 0));
    
    // Power
    document.querySelector('[data-subtab="health-power"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var powerContainer = document.getElementById('powerContainer');
    check('power data populated', powerContainer && powerContainer.innerText.length > 20, 'text=' + (powerContainer?.innerText?.length || 0));
    
    // === LOGS TAB ===
    results.push('');
    results.push('=== LOGS ===');
    document.querySelector('[data-tab="logs"]')?.click();
    await new Promise(r => setTimeout(r, 300));
    
    var logsContainer = document.getElementById('logsContainer');
    check('logs populated', logsContainer && logsContainer.innerText.length > 20, 'text=' + (logsContainer?.innerText?.length || 0));
    
    // === OPERATIONS TAB ===
    results.push('');
    results.push('=== OPERATIONS ===');
    document.querySelector('[data-tab="operations"]')?.click();
    await new Promise(r => setTimeout(r, 300));
    
    var opsBtns = document.querySelectorAll('#operationsContent .ops-btn');
    check('operations buttons rendered', opsBtns.length > 50, 'found ' + opsBtns.length);
    var opsVisible = Array.from(opsBtns).filter(function(b){return getComputedStyle(b).display!=='none';}).length;
    check('operations buttons visible', opsVisible > 50, 'visible=' + opsVisible);
    
    // === ADVANCED TAB ===
    results.push('');
    results.push('=== ADVANCED ===');
    document.querySelector('[data-tab="advanced"]')?.click();
    await new Promise(r => setTimeout(r, 300));
    
    var advSubs = document.querySelectorAll('#advancedContent .sub-tab');
    check('advanced sub-tabs rendered', advSubs.length === 7, 'found ' + advSubs.length);
    
    // Click Diagnostics sub-tab
    document.querySelector('[data-subtab="adv-diagnostics"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var diagBtns = document.querySelectorAll('#adv-diagnostics .ops-btn');
    check('diagnostics buttons', diagBtns.length > 0, 'found ' + diagBtns.length);
    
    // Click Monitoring sub-tab
    document.querySelector('[data-subtab="adv-monitoring"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    check('monitoring start button', !!document.getElementById('startMonitoringBtn'));
    
    // Click Health Score sub-tab
    document.querySelector('[data-subtab="adv-health-score"]')?.click();
    await new Promise(r => setTimeout(r, 200));
    var hsContent = document.getElementById('adv-health-score');
    check('health score section visible', hsContent && getComputedStyle(hsContent).display !== 'none');
    
    // === SUMMARY ===
    results.push('');
    results.push('============================');
    results.push('RESULTS: ' + passed + ' passed, ' + failed + ' failed out of ' + (passed+failed));
    results.push('============================');
    
    document.body.innerHTML = '<pre id="TESTRESULT">' + results.join('\\n') + '</pre>';
}

setTimeout(function(){ runTests(); }, 2000);
</script>
"""

page = page.replace('</body>', test_js + '</body>')
path = os.path.join(tmpdir, 'connected_test.html')
with open(path, 'w') as f:
    f.write(page)
shutil.copy(path, '/opt/medi-ai-tor/static/_conntest.html')

print("6. Running Chromium with connected server data...")
result = subprocess.run([
    '/snap/bin/chromium', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--virtual-time-budget=30000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/static/_conntest.html'
], capture_output=True, text=True, timeout=45)

m = re.search(r'<pre id="TESTRESULT">(.*?)</pre>', result.stdout, re.DOTALL)
if m:
    text = m.group(1).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&#39;',"'")
    print(text)
else:
    print(f"No result. DOM: {len(result.stdout)} chars")

# Cleanup
os.remove('/opt/medi-ai-tor/static/_conntest.html')
shutil.rmtree(tmpdir, ignore_errors=True)
S.post('http://localhost/api/disconnect', headers=H)
