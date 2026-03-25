#!/usr/bin/env python3
"""EXHAUSTIVE browser test: every container, every sub-tab, every button, with real F710 data."""
import subprocess, tempfile, os, requests, re, shutil, time

tmpdir = tempfile.mkdtemp()
os.environ['HOME'] = tmpdir
S = requests.Session()

# Login + connect
r = S.post('http://localhost/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['token']
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
r = S.post('http://localhost/api/connect', json={'host':'100.71.148.195','username':'root','password':'calvin','port':443}, headers=H, timeout=30)
print(f"Login+Connect: {r.json().get('status')}")

# Start monitoring so monitoring tab has data
S.post('http://localhost/monitoring/start', headers=H)

# Get dashboard
r = S.get('http://localhost/technician/app')
page = r.text
print(f"Page: {len(page)} bytes")

test_js = r"""
<script>
var R=[], P=0, F=0;
function ok(n,c,d){if(c){P++;R.push('PASS: '+n);}else{F++;R.push('FAIL: '+n+' -- '+(d||'').substring(0,80));}}

async function run(){
    var token='""" + token + r"""';
    var H={'Authorization':'Bearer '+token,'Content-Type':'application/json'};

    // Fetch ALL data
    R.push('=== LOADING DATA ===');
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
    var bd = await batch.json();
    var okCmds=0, failCmds=[];
    for(var k in bd.results){
        if(bd.results[k].status==='success'){okCmds++;window.app.handleActionResponse(bd.results[k].result);}
        else failCmds.push(k);
    }
    R.push('Loaded: '+okCmds+'/20 commands OK' + (failCmds.length ? ', FAILED: '+failCmds.join(',') : ''));
    await new Promise(r=>setTimeout(r,1500));

    // === OVERVIEW ===
    R.push(''); R.push('=== OVERVIEW ===');
    document.querySelector('[data-tab="overview"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    var tiles=document.querySelectorAll('#overviewContent .metric-tile');
    ok('overview tiles', tiles.length>0, 'found '+tiles.length);
    var qabtns=document.querySelectorAll('.qa-btn');
    ok('quick action buttons', qabtns.length>=4, 'found '+qabtns.length);

    // === SYSTEM - every sub-tab ===
    R.push(''); R.push('=== SYSTEM INFO ===');
    document.querySelector('[data-tab="system"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    var sysSubs=['sys-general','sys-processors','sys-memory','sys-storage','sys-network','sys-bios','sys-bios-presets','sys-firmware','sys-idrac'];
    for(var i=0;i<sysSubs.length;i++){
        var st=document.querySelector('[data-subtab="'+sysSubs[i]+'"]');
        if(st){st.click(); await new Promise(r=>setTimeout(r,200));}
        var sc=document.getElementById(sysSubs[i]);
        var vis=sc?getComputedStyle(sc).display!=='none':false;
        var txt=sc?sc.innerText.trim().length:0;
        ok(sysSubs[i]+' visible', vis, 'display='+(sc?getComputedStyle(sc).display:'MISSING'));
        ok(sysSubs[i]+' has data', txt>20, 'text='+txt);
    }

    // === HEALTH - every sub-tab ===
    R.push(''); R.push('=== HEALTH ===');
    document.querySelector('[data-tab="health"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    var healthSubs=['health-overview','health-thermal','health-power','health-issues'];
    for(var i=0;i<healthSubs.length;i++){
        var st=document.querySelector('[data-subtab="'+healthSubs[i]+'"]');
        if(st){st.click(); await new Promise(r=>setTimeout(r,200));}
        var sc=document.getElementById(healthSubs[i]);
        var vis=sc?getComputedStyle(sc).display!=='none':false;
        ok(healthSubs[i]+' visible', vis);
    }

    // === LOGS ===
    R.push(''); R.push('=== LOGS ===');
    document.querySelector('[data-tab="logs"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    var logC=document.getElementById('logsContainer');
    ok('logs container has data', logC && logC.innerText.length>30, 'text='+(logC?.innerText?.length||0));
    ok('log severity filter', !!document.getElementById('logSeverityFilter'));
    ok('log search', !!document.getElementById('logSearchInput'));

    // === TROUBLESHOOTING ===
    R.push(''); R.push('=== TROUBLESHOOTING ===');
    document.querySelector('[data-tab="troubleshooting"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    ok('issue textarea', !!document.getElementById('issueDescription'));
    ok('start investigation btn', !!document.getElementById('startTroubleshootingBtn'));
    var tsSubs=['ts-recommendations','ts-tsr','ts-jobs','ts-postcode','ts-diagnostics','ts-supportassist'];
    for(var i=0;i<tsSubs.length;i++){
        var st=document.querySelector('[data-subtab="'+tsSubs[i]+'"]');
        if(st){st.click(); await new Promise(r=>setTimeout(r,100));}
        var sc=document.getElementById(tsSubs[i]);
        ok(tsSubs[i]+' visible', sc && getComputedStyle(sc).display!=='none');
    }

    // === OPERATIONS - every sub-tab ===
    R.push(''); R.push('=== OPERATIONS ===');
    document.querySelector('[data-tab="operations"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    var opsSubs=['ops-bios','ops-raid','ops-drives','ops-power','ops-idrac','ops-firmware','ops-network','ops-os'];
    for(var i=0;i<opsSubs.length;i++){
        var st=document.querySelector('[data-subtab="'+opsSubs[i]+'"]');
        if(st){st.click(); await new Promise(r=>setTimeout(r,150));}
        var sc=document.getElementById(opsSubs[i]);
        var vis=sc?getComputedStyle(sc).display!=='none':false;
        var btns=sc?sc.querySelectorAll('.ops-btn').length:0;
        ok(opsSubs[i]+' visible', vis);
        ok(opsSubs[i]+' has buttons', btns>0, 'buttons='+btns);
    }

    // === ADVANCED - every sub-tab ===
    R.push(''); R.push('=== ADVANCED ===');
    document.querySelector('[data-tab="advanced"]')?.click();
    await new Promise(r=>setTimeout(r,300));
    var advSubs=['adv-lifecycle','adv-monitoring','adv-diagnostics','adv-health-score','adv-snapshot','adv-predictive','adv-audit'];
    for(var i=0;i<advSubs.length;i++){
        var st=document.querySelector('[data-subtab="'+advSubs[i]+'"]');
        if(st){st.click(); await new Promise(r=>setTimeout(r,150));}
        var sc=document.getElementById(advSubs[i]);
        var vis=sc?getComputedStyle(sc).display!=='none':false;
        var children=sc?sc.children.length:0;
        ok(advSubs[i]+' visible', vis);
        ok(advSubs[i]+' has content', children>0, 'children='+children);
    }

    // === CHAT PANEL ===
    R.push(''); R.push('=== CHAT ===');
    ok('chat panel exists', !!document.getElementById('agentChatPanel'));
    ok('chat input exists', !!document.getElementById('agentChatInput'));

    // SUMMARY
    R.push(''); R.push('========================================');
    R.push('RESULTS: '+P+' passed, '+F+' failed out of '+(P+F));
    R.push('========================================');
    document.body.innerHTML='<pre id="RES">'+R.join('\n')+'</pre>';
}
setTimeout(run, 2000);
</script>
"""

page = page.replace('</body>', test_js + '</body>')
path = os.path.join(tmpdir, 'exhaust.html')
with open(path, 'w') as f:
    f.write(page)
shutil.copy(path, '/opt/medi-ai-tor/static/_exhaust.html')

print("Running exhaustive Chromium test...")
result = subprocess.run([
    '/snap/bin/chromium', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--virtual-time-budget=40000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/static/_exhaust.html'
], capture_output=True, text=True, timeout=50)

m = re.search(r'<pre id="RES">(.*?)</pre>', result.stdout, re.DOTALL)
if m:
    print(m.group(1).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>'))
else:
    print(f"No result. DOM: {len(result.stdout)} chars")

os.remove('/opt/medi-ai-tor/static/_exhaust.html')
shutil.rmtree(tmpdir, ignore_errors=True)
S.post('http://localhost/monitoring/stop', headers=H)
S.post('http://localhost/api/disconnect', headers=H)
