#!/usr/bin/env python3
"""COMPLETE browser + API verification with real F710 data.
Connects to iDRAC, loads data into browser, verifies every container has real content.
"""
import subprocess, tempfile, os, requests, re, shutil, time

tmpdir = tempfile.mkdtemp()
os.environ['HOME'] = tmpdir
S = requests.Session()

# Login + Connect
r = S.post('http://localhost/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['token']
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
r = S.post('http://localhost/api/connect', json={'host':'100.71.148.195','username':'root','password':'calvin','port':443}, headers=H, timeout=30)
print(f"Connect: {r.json().get('status')}")

# Start monitoring for live metrics
S.post('http://localhost/monitoring/start', headers=H)
time.sleep(2)

# Get dashboard page
r = S.get('http://localhost/technician/app')
page = r.text
print(f"Dashboard: {len(page)} bytes")

test_js = """
<script>
var R=[], P=0, F=0;
function ok(n,c,d){if(c){P++;}else{F++;R.push('FAIL: '+n+' -- '+(d||'').substring(0,80));}}

async function run(){
    var token='""" + token + """';
    var H={'Authorization':'Bearer '+token,'Content-Type':'application/json'};

    // Load ALL data
    var batch = await fetch('/api/execute/batch',{method:'POST',headers:H,body:JSON.stringify({commands:[
        {action:'get_server_info',parameters:{}},{action:'get_processors',parameters:{}},
        {action:'get_memory',parameters:{}},{action:'get_power_supplies',parameters:{}},
        {action:'get_temperature_sensors',parameters:{}},{action:'get_fans',parameters:{}},
        {action:'get_storage_devices',parameters:{}},{action:'get_network_interfaces',parameters:{}},
        {action:'health_check',parameters:{}},{action:'collect_logs',parameters:{}},
        {action:'get_bios_attributes',parameters:{}},{action:'get_idrac_info',parameters:{}},
        {action:'get_firmware_inventory',parameters:{}},{action:'get_lifecycle_logs',parameters:{}},
        {action:'performance_analysis',parameters:{}},{action:'get_post_codes',parameters:{}},
        {action:'get_jobs',parameters:{}},{action:'get_boot_order',parameters:{}},
        {action:'get_idrac_network_config',parameters:{}},{action:'get_lifecycle_status',parameters:{}}
    ]})});
    var bd=await batch.json();
    var loadedCmds=0;
    for(var k in bd.results){
        if(bd.results[k].status==='success'&&bd.results[k].result){
            loadedCmds++;
            window.app.handleActionResponse(bd.results[k].result);
        }
    }
    R.push('DATA: '+loadedCmds+'/20 commands loaded');
    await new Promise(r=>setTimeout(r,2000));

    // ── Check EVERY container that should have data ──
    var containers = [
        // Overview
        ['overviewContent', 'Overview tab'],
        // System sub-tabs
        ['systemInfoContainer', 'System General'],
        ['processorsContainer', 'Processors'],
        ['memoryContainer', 'Memory'],
        ['storageContainer', 'Storage'],
        ['networkContainer', 'Network'],
        ['biosContainer', 'BIOS Settings'],
        ['firmwareContainer', 'Firmware'],
        ['idracContainer', 'iDRAC Info'],
        // Health
        ['healthStatusContainer', 'Health Status'],
        ['thermalContainer', 'Thermal'],
        ['powerContainer', 'Power'],
        // Logs
        ['logsContainer', 'Event Logs'],
        // Lifecycle logs
        ['lifecycleLogsContainer', 'Lifecycle Logs'],
    ];

    R.push('');
    R.push('=== DATA CONTAINERS ===');
    var dataOk=0, dataFail=0;
    for(var i=0;i<containers.length;i++){
        var id=containers[i][0], label=containers[i][1];
        var el=document.getElementById(id);
        if(!el){ok(label+' exists',false,'element #'+id+' not found');dataFail++;continue;}
        var text=el.innerText.trim();
        var hasPlaceholder=text.includes('Connect to a server') || text.includes('placeholder');
        var hasData=text.length>30 && !hasPlaceholder;
        ok(label+' has real data',hasData,'len='+text.length+(hasPlaceholder?' (placeholder)':''));
        if(hasData)dataOk++; else dataFail++;
    }
    R.push('Data containers: '+dataOk+' populated, '+dataFail+' empty');

    // ── Check every tab switches correctly ──
    R.push('');
    R.push('=== TAB SWITCHING ===');
    var tabs=['overview','system','health','logs','troubleshooting','operations','advanced'];
    for(var i=0;i<tabs.length;i++){
        var link=document.querySelector('[data-tab="'+tabs[i]+'"]');
        if(link)link.click();
        await new Promise(r=>setTimeout(r,200));
        var content=document.getElementById(tabs[i]+'Content');
        ok(tabs[i]+' tab switches',content&&content.classList.contains('active')&&getComputedStyle(content).display==='block');
    }

    // ── Check Operations sub-tabs + buttons ──
    R.push('');
    R.push('=== OPERATIONS ===');
    document.querySelector('[data-tab="operations"]')?.click();
    await new Promise(r=>setTimeout(r,200));
    var opsSubs=['ops-bios','ops-raid','ops-drives','ops-power','ops-idrac','ops-firmware','ops-network','ops-os'];
    var totalOpsBtns=0;
    for(var i=0;i<opsSubs.length;i++){
        document.querySelector('[data-subtab="'+opsSubs[i]+'"]')?.click();
        await new Promise(r=>setTimeout(r,100));
        var sc=document.getElementById(opsSubs[i]);
        var btns=sc?sc.querySelectorAll('.ops-btn').length:0;
        totalOpsBtns+=btns;
        ok(opsSubs[i]+' ('+btns+' btns)',sc&&getComputedStyle(sc).display!=='none'&&btns>0);
    }
    R.push('Total ops buttons: '+totalOpsBtns);

    // ── Check Advanced sub-tabs ──
    R.push('');
    R.push('=== ADVANCED ===');
    document.querySelector('[data-tab="advanced"]')?.click();
    await new Promise(r=>setTimeout(r,200));
    var advSubs=['adv-lifecycle','adv-monitoring','adv-diagnostics','adv-health-score','adv-snapshot','adv-predictive','adv-audit'];
    for(var i=0;i<advSubs.length;i++){
        document.querySelector('[data-subtab="'+advSubs[i]+'"]')?.click();
        await new Promise(r=>setTimeout(r,100));
        var sc=document.getElementById(advSubs[i]);
        ok(advSubs[i],sc&&getComputedStyle(sc).display!=='none'&&sc.children.length>0);
    }

    // ── Check specific data values in rendered HTML ──
    R.push('');
    R.push('=== DATA ACCURACY ===');
    // Switch to overview and check rendered content
    document.querySelector('[data-tab="overview"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    var ovText = document.getElementById('overviewContent')?.textContent || '';
    ok('Overview shows F710', ovText.includes('F710') || ovText.includes('PowerScale'), 'ovLen='+ovText.length);
    
    // Check system tab
    document.querySelector('[data-tab="system"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    document.querySelector('[data-subtab="sys-general"]')?.click();
    await new Promise(r=>setTimeout(r,200));
    var sysText = document.getElementById('systemInfoContainer')?.textContent || '';
    ok('System shows model', sysText.includes('F710') || sysText.includes('PowerScale'), 'sysLen='+sysText.length);
    ok('System shows service tag', sysText.includes('3KQ38Y3'), 'sysLen='+sysText.length);
    
    // Check health tab has real temps
    document.querySelector('[data-tab="health"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    document.querySelector('[data-subtab="health-thermal"]')?.click();
    await new Promise(r=>setTimeout(r,200));
    var thermalText = document.getElementById('thermalContainer')?.textContent || '';
    ok('Thermal has temperature data', thermalText.includes('°C') || thermalText.includes('Inlet') || thermalText.length > 100, 'thermLen='+thermalText.length);
    
    // Check logs have entries
    document.querySelector('[data-tab="logs"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    var logText = document.getElementById('logsContainer')?.textContent || '';
    ok('Logs have entries', logText.length > 100, 'logLen='+logText.length);

    // SUMMARY
    R.push('');
    R.push('================================');
    R.push('TOTAL: '+P+' passed, '+F+' failed');
    R.push('================================');
    if(F>0){
        R.push('');
        R.push('FAILURES:');
    }
    document.body.innerHTML='<pre id="OUT">'+R.join('\\n')+'</pre>';
}
setTimeout(run,2000);
</script>
"""

page = page.replace('</body>', test_js + '</body>')
path = os.path.join(tmpdir, 'final.html')
with open(path, 'w') as f:
    f.write(page)
shutil.copy(path, '/opt/medi-ai-tor/static/_final.html')

print("\nRunning Chromium...")
result = subprocess.run([
    '/snap/bin/chromium', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--virtual-time-budget=40000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/static/_final.html'
], capture_output=True, text=True, timeout=55)

m = re.search(r'<pre id="OUT">(.*?)</pre>', result.stdout, re.DOTALL)
if m:
    print(m.group(1).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>'))
else:
    print(f"No output. DOM: {len(result.stdout)} chars")

os.remove('/opt/medi-ai-tor/static/_final.html')
shutil.rmtree(tmpdir, ignore_errors=True)
S.post('http://localhost/monitoring/stop', headers=H)
S.post('http://localhost/api/disconnect', headers=H)
