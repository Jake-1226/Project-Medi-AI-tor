#!/usr/bin/env python3
"""Test the ACTUAL served /technician/app page with Chromium headless."""
import subprocess, tempfile, os, requests, re, shutil

tmpdir = tempfile.mkdtemp()
os.environ['HOME'] = tmpdir

S = requests.Session()
r = S.post('http://localhost/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['token']

# Fetch the ACTUAL page the browser gets
r = S.get('http://localhost/technician/app')
page_html = r.text
print(f"Page size: {len(page_html)}")
print(f"Has DellAIAgent: {'class DellAIAgent' in page_html}")
print(f"Has operationsContent: {'operationsContent' in page_html}")
print(f"ops-btn count: {page_html.count('class=\"ops-btn\"')}")

# Inject a test script at the end that clicks tabs and reports results
test_script = """
<script>
setTimeout(function(){
    var r=[];
    r.push('app: '+(typeof window.app));
    r.push('switchTab: '+(typeof window.app?.switchTab));
    var links=document.querySelectorAll('.sidebar-link[data-tab]');
    r.push('sidebar links: '+links.length);
    
    // Click operations
    var opsLink=document.querySelector('[data-tab="operations"]');
    if(opsLink){opsLink.click();r.push('clicked operations');}
    else{r.push('NO operations link');}
    
    setTimeout(function(){
        var ops=document.getElementById('operationsContent');
        r.push('opsContent class: '+(ops?ops.className:'MISSING'));
        r.push('opsContent display: '+(ops?getComputedStyle(ops).display:'MISSING'));
        var btns=document.querySelectorAll('#operationsContent .ops-btn');
        r.push('ops-btn: '+btns.length);
        var vis=0;
        btns.forEach(function(b){if(getComputedStyle(b).display!=='none')vis++;});
        r.push('ops-btn visible: '+vis);
        if(btns.length>0)r.push('first: '+btns[0].textContent.trim().substring(0,40));
        
        // Click advanced
        var advLink=document.querySelector('[data-tab="advanced"]');
        if(advLink){advLink.click();r.push('clicked advanced');}
        
        setTimeout(function(){
            var adv=document.getElementById('advancedContent');
            r.push('advContent class: '+(adv?adv.className:'MISSING'));
            r.push('advContent display: '+(adv?getComputedStyle(adv).display:'MISSING'));
            r.push('adv sub-tabs: '+document.querySelectorAll('#advancedContent .sub-tab').length);
            document.body.innerHTML='<pre id="TESTRESULT">'+r.join('\\n')+'</pre>';
        },300);
    },300);
},2000);
</script>
"""

# Insert test script before </body>
page_html = page_html.replace('</body>', test_script + '</body>')

# Write to file and serve
path = os.path.join(tmpdir, 'test.html')
with open(path, 'w') as f:
    f.write(page_html)
shutil.copy(path, '/opt/medi-ai-tor/static/_techtest.html')

print("\n=== Running Chromium ===")
result = subprocess.run([
    '/snap/bin/chromium', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--virtual-time-budget=10000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/static/_techtest.html'
], capture_output=True, text=True, timeout=20)

dom = result.stdout
m = re.search(r'<pre id="TESTRESULT">(.*?)</pre>', dom, re.DOTALL)
if m:
    print(m.group(1).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>'))
else:
    print(f"No TESTRESULT. DOM: {len(dom)} chars")
    # Check for errors
    if len(dom) < 500:
        print(dom)

os.remove('/opt/medi-ai-tor/static/_techtest.html')
shutil.rmtree(tmpdir, ignore_errors=True)
