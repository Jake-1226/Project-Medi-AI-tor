#!/usr/bin/env python3
"""Build a self-contained HTML page with inline CSS+JS and test with Chromium."""
import subprocess, tempfile, os, requests, re, shutil

tmpdir = tempfile.mkdtemp()
os.environ['HOME'] = tmpdir

S = requests.Session()
r = S.post('http://localhost/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['token']

r = S.get('http://localhost/technician')
html = r.text

r = S.get('http://localhost/static/js/app.js')
js = r.text

r = S.get('http://localhost/static/css/style.css')
css = r.text

# Build standalone page
m = re.search(r'<body[^>]*>(.*)</body>', html, re.DOTALL)
body = m.group(1) if m else ''
body = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL)

test_js = """
setTimeout(function(){
  var r=[];
  r.push('app: '+(typeof window.app));
  r.push('switchTab: '+(typeof window.app?.switchTab));
  var links = document.querySelectorAll('.sidebar-link[data-tab]');
  r.push('sidebar links: '+links.length);
  
  var opsLink = document.querySelector('[data-tab="operations"]');
  if(opsLink){ opsLink.click(); r.push('clicked operations'); }
  else { r.push('NO operations link!'); }
  
  setTimeout(function(){
    var opsEl = document.getElementById('operationsContent');
    r.push('opsContent class: '+(opsEl?opsEl.className:'MISSING'));
    r.push('opsContent display: '+(opsEl?getComputedStyle(opsEl).display:'MISSING'));
    var btns = document.querySelectorAll('#operationsContent .ops-btn');
    r.push('ops-btn: '+btns.length);
    var vis = 0;
    for(var i=0;i<btns.length;i++){if(getComputedStyle(btns[i]).display!=='none')vis++;}
    r.push('ops-btn visible: '+vis);
    if(btns.length>0) r.push('first: '+btns[0].textContent.trim().substring(0,40));
    
    var advLink = document.querySelector('[data-tab="advanced"]');
    if(advLink){ advLink.click(); r.push('clicked advanced'); }
    
    setTimeout(function(){
      var advEl = document.getElementById('advancedContent');
      r.push('advContent class: '+(advEl?advEl.className:'MISSING'));
      r.push('advContent display: '+(advEl?getComputedStyle(advEl).display:'MISSING'));
      var advSubs = document.querySelectorAll('#advancedContent .sub-tab');
      r.push('adv sub-tabs: '+advSubs.length);
      
      document.body.innerHTML='<pre id="TESTRESULT">'+r.join('\\n')+'</pre>';
    },500);
  },500);
},2000);
"""

page = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><style>{css}</style></head>
<body class="tech-body" data-theme="dark">
{body}
<script>sessionStorage.setItem('auth_token','{token}');</script>
<script>{js}</script>
<script>{test_js}</script>
</body></html>"""

path = os.path.join(tmpdir, 'test.html')
with open(path, 'w') as f:
    f.write(page)

shutil.copy(path, '/opt/medi-ai-tor/static/_fulltest.html')
print(f"Test page: {len(page)} chars")

result = subprocess.run([
    '/snap/bin/chromium', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--virtual-time-budget=10000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/static/_fulltest.html'
], capture_output=True, text=True, timeout=20)

dom = result.stdout
m = re.search(r'<pre id="TESTRESULT">(.*?)</pre>', dom, re.DOTALL)
if m:
    text = m.group(1).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    print(text)
else:
    print(f"No TESTRESULT found. DOM: {len(dom)} chars")
    if len(dom) < 500:
        print(dom)
    else:
        print(dom[:300])
        print("...")
        print(dom[-200:])

os.remove('/opt/medi-ai-tor/static/_fulltest.html')
shutil.rmtree(tmpdir, ignore_errors=True)
