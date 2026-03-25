#!/usr/bin/env python3
"""Comprehensive browser test: login, connect to iDRAC, test every tab/section."""
import subprocess, tempfile, os, requests, re, shutil, json, time

tmpdir = tempfile.mkdtemp()
os.environ['HOME'] = tmpdir

S = requests.Session()

# Step 1: Login
r = S.post('http://localhost/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['token']
print(f"1. Login: OK (token={token[:15]}...)")

# Step 2: Connect to iDRAC
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
r = S.post('http://localhost/api/connect', json={
    'host': '100.71.148.195', 'username': 'root', 'password': 'calvin', 'port': 443
}, headers=H, timeout=30)
print(f"2. iDRAC connect: {r.status_code} {r.json().get('status')}")

# Step 3: Fetch the actual served dashboard
r = S.get('http://localhost/technician/app')
page = r.text
print(f"3. Dashboard page: {len(page)} bytes")

# Step 4: Inject comprehensive test script
test_js = """
<script>
var results = [];
var passed = 0;
var failed = 0;

function check(name, condition, detail) {
    if (condition) { passed++; results.push('PASS: ' + name); }
    else { failed++; results.push('FAIL: ' + name + ' -- ' + (detail||'')); }
}

async function runAllTests() {
    results.push('=== APP INIT ===');
    check('app exists', typeof window.app === 'object');
    check('switchTab exists', typeof window.app?.switchTab === 'function');
    check('runOperation exists', typeof window.app?.runOperation === 'function');
    check('runAdvanced exists', typeof window.app?.runAdvanced === 'function');
    check('connectToServer exists', typeof window.app?.connectToServer === 'function');
    
    var sidebarLinks = document.querySelectorAll('.sidebar-link[data-tab]');
    check('7 sidebar tabs', sidebarLinks.length === 7, 'found ' + sidebarLinks.length);
    
    // === TEST EACH TAB ===
    var tabs = ['overview','system','health','logs','troubleshooting','operations','advanced'];
    for (var i = 0; i < tabs.length; i++) {
        var tabName = tabs[i];
        results.push('');
        results.push('=== TAB: ' + tabName.toUpperCase() + ' ===');
        
        var link = document.querySelector('[data-tab="' + tabName + '"]');
        check(tabName + ' sidebar link exists', !!link);
        if (link) link.click();
        await new Promise(r => setTimeout(r, 300));
        
        var content = document.getElementById(tabName + 'Content');
        check(tabName + ' content div exists', !!content);
        if (content) {
            check(tabName + ' is active', content.classList.contains('active'));
            check(tabName + ' display=block', getComputedStyle(content).display === 'block');
            check(tabName + ' has children', content.children.length > 0, 'children=' + content.children.length);
            check(tabName + ' has visible text', content.innerText.trim().length > 10, 'text=' + content.innerText.trim().length);
        }
        
        // Tab-specific checks
        if (tabName === 'overview') {
            check('overview has connect form', !!document.getElementById('connectionForm'));
            check('overview has quick actions', !!document.querySelector('.quick-actions-bar'));
        }
        
        if (tabName === 'system') {
            var sysSubs = document.querySelectorAll('#systemContent .sub-tab');
            check('system has sub-tabs', sysSubs.length >= 7, 'found ' + sysSubs.length);
            var sysNames = Array.from(sysSubs).map(function(s){return s.textContent.trim();});
            check('system has General tab', sysNames.indexOf('General') >= 0);
            check('system has BIOS Settings tab', sysNames.some(function(n){return n.includes('BIOS');}));
            check('system has Firmware tab', sysNames.some(function(n){return n.includes('Firmware');}));
        }
        
        if (tabName === 'health') {
            var healthSubs = document.querySelectorAll('#healthContent .sub-tab');
            check('health has sub-tabs', healthSubs.length >= 3, 'found ' + healthSubs.length);
        }
        
        if (tabName === 'logs') {
            check('logs has severity filter', !!document.getElementById('logSeverityFilter'));
            check('logs has search input', !!document.getElementById('logSearchInput'));
        }
        
        if (tabName === 'troubleshooting') {
            check('troubleshooting has issue textarea', !!document.getElementById('issueDescription'));
            check('troubleshooting has start button', !!document.getElementById('startTroubleshootingBtn'));
            var tsSubs = document.querySelectorAll('#troubleshootingContent .sub-tab');
            check('troubleshooting has sub-tabs', tsSubs.length >= 4, 'found ' + tsSubs.length);
        }
        
        if (tabName === 'operations') {
            var opsSubs = document.querySelectorAll('#operationsContent .sub-tab');
            check('operations has 8 sub-tabs', opsSubs.length === 8, 'found ' + opsSubs.length);
            var opsNames = Array.from(opsSubs).map(function(s){return s.textContent.trim();});
            results.push('  sub-tabs: ' + opsNames.join(', '));
            
            var opsBtns = document.querySelectorAll('#operationsContent .ops-btn');
            check('operations has >50 buttons', opsBtns.length > 50, 'found ' + opsBtns.length);
            var visibleBtns = Array.from(opsBtns).filter(function(b){return getComputedStyle(b).display!=='none';});
            check('operations buttons visible', visibleBtns.length > 50, 'visible=' + visibleBtns.length);
            
            // Click each ops sub-tab
            for (var j = 0; j < opsSubs.length; j++) {
                opsSubs[j].click();
                await new Promise(r => setTimeout(r, 100));
                var subId = opsSubs[j].getAttribute('data-subtab');
                var subContent = document.getElementById(subId);
                if (subContent) {
                    check('ops sub-tab ' + subId + ' visible', getComputedStyle(subContent).display !== 'none');
                }
            }
        }
        
        if (tabName === 'advanced') {
            var advSubs = document.querySelectorAll('#advancedContent .sub-tab');
            check('advanced has 7 sub-tabs', advSubs.length === 7, 'found ' + advSubs.length);
            var advNames = Array.from(advSubs).map(function(s){return s.textContent.trim();});
            results.push('  sub-tabs: ' + advNames.join(', '));
            
            var advContents = document.querySelectorAll('#advancedContent .sub-tab-content');
            check('advanced has 7 sub-contents', advContents.length === 7, 'found ' + advContents.length);
            
            // Click each adv sub-tab
            for (var j = 0; j < advSubs.length; j++) {
                advSubs[j].click();
                await new Promise(r => setTimeout(r, 100));
                var subId = advSubs[j].getAttribute('data-subtab');
                var subContent = document.getElementById(subId);
                if (subContent) {
                    var vis = getComputedStyle(subContent).display !== 'none';
                    check('adv sub-tab ' + subId + ' visible', vis, 'display=' + getComputedStyle(subContent).display);
                    check('adv sub-tab ' + subId + ' has content', subContent.children.length > 0, 'children=' + subContent.children.length);
                }
            }
            
            // Check specific advanced features
            check('adv has monitoring buttons', !!document.getElementById('startMonitoringBtn'));
            check('adv has diagnostics buttons', document.querySelectorAll('#adv-diagnostics .ops-btn').length > 0);
        }
    }
    
    results.push('');
    results.push('============================');
    results.push('RESULTS: ' + passed + ' passed, ' + failed + ' failed out of ' + (passed+failed));
    results.push('============================');
    
    document.body.innerHTML = '<pre id="TESTRESULT">' + results.join('\\n') + '</pre>';
}

setTimeout(function(){ runAllTests(); }, 3000);
</script>
"""

page = page.replace('</body>', test_js + '</body>')

path = os.path.join(tmpdir, 'fulltest.html')
with open(path, 'w') as f:
    f.write(page)
shutil.copy(path, '/opt/medi-ai-tor/static/_fulltest.html')

print("4. Running Chromium headless browser test...")
result = subprocess.run([
    '/snap/bin/chromium', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--virtual-time-budget=20000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/static/_fulltest.html'
], capture_output=True, text=True, timeout=30)

m = re.search(r'<pre id="TESTRESULT">(.*?)</pre>', result.stdout, re.DOTALL)
if m:
    text = m.group(1).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&#39;',"'")
    print(text)
else:
    print(f"No result found. DOM: {len(result.stdout)} chars")
    print(result.stdout[:500] if len(result.stdout) < 1000 else result.stdout[:300] + "..." + result.stdout[-200:])

# Check for JS errors in stderr
if result.stderr:
    errors = [l for l in result.stderr.split('\n')
              if any(x in l.lower() for x in ['uncaught','syntaxerror','typeerror','referenceerror'])
              and not any(x in l.lower() for x in ['vaapi','dbus','gpu','sandbox','viz','shared_memory'])]
    if errors:
        print("\nJS ERRORS:")
        for e in errors[:5]:
            print(f"  {e[:150]}")

os.remove('/opt/medi-ai-tor/static/_fulltest.html')
shutil.rmtree(tmpdir, ignore_errors=True)

# Disconnect
S.post('http://localhost/api/disconnect', headers=H)
