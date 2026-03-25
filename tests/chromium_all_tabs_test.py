#!/usr/bin/env python3
"""Test the ACTUAL /technician/app page — verify Operations AND Advanced tabs."""
import subprocess, tempfile, os, requests, re, shutil

tmpdir = tempfile.mkdtemp()
os.environ['HOME'] = tmpdir

S = requests.Session()
r = S.post('http://localhost/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['token']

# Fetch the ACTUAL served page
r = S.get('http://localhost/technician/app')
page = r.text
print(f"Page: {len(page)} bytes")

# Verify content exists in HTML
print(f"operationsContent in HTML: {'operationsContent' in page}")
print(f"advancedContent in HTML: {'advancedContent' in page}")
print(f"ops-btn in HTML: {page.count('class=\"ops-btn\"')}")
print(f"adv-lifecycle in HTML: {'adv-lifecycle' in page}")
print(f"adv-diagnostics in HTML: {'adv-diagnostics' in page}")

# Add a comprehensive test that clicks ALL tabs
test_js = """
<script>
setTimeout(function(){
    var r = [];
    r.push('=== INIT ===');
    r.push('app: ' + (typeof window.app));
    r.push('switchTab: ' + (typeof window.app?.switchTab));
    
    var links = document.querySelectorAll('.sidebar-link[data-tab]');
    r.push('sidebar links: ' + links.length);

    // Test EACH tab
    var tabs = ['overview','system','health','logs','troubleshooting','operations','advanced'];
    var idx = 0;
    
    function testTab() {
        if (idx >= tabs.length) {
            document.body.innerHTML = '<pre id="RESULT">' + r.join('\\n') + '</pre>';
            return;
        }
        var tabName = tabs[idx];
        var link = document.querySelector('[data-tab="' + tabName + '"]');
        if (link) {
            link.click();
            setTimeout(function() {
                var content = document.getElementById(tabName + 'Content');
                var display = content ? getComputedStyle(content).display : 'MISSING';
                var cls = content ? content.className : 'MISSING';
                var children = content ? content.children.length : 0;
                var text = content ? content.innerText.substring(0, 60) : '';
                r.push(tabName + ': display=' + display + ' class=' + cls + ' children=' + children + ' text="' + text.replace(/\\n/g,' ').substring(0,40) + '"');
                
                if (tabName === 'operations') {
                    var btns = document.querySelectorAll('#operationsContent .ops-btn');
                    r.push('  ops-btn: ' + btns.length + ' visible=' + Array.from(btns).filter(function(b){return getComputedStyle(b).display!=='none';}).length);
                    var subTabs = document.querySelectorAll('#operationsContent .sub-tab');
                    r.push('  sub-tabs: ' + subTabs.length);
                }
                if (tabName === 'advanced') {
                    var subTabs = document.querySelectorAll('#advancedContent .sub-tab');
                    r.push('  adv sub-tabs: ' + subTabs.length);
                    subTabs.forEach(function(st) { r.push('    ' + st.textContent.trim()); });
                    var subContents = document.querySelectorAll('#advancedContent .sub-tab-content');
                    r.push('  adv sub-contents: ' + subContents.length);
                    subContents.forEach(function(sc) {
                        r.push('    ' + sc.id + ': display=' + getComputedStyle(sc).display + ' children=' + sc.children.length);
                    });
                }
                
                idx++;
                testTab();
            }, 200);
        } else {
            r.push(tabName + ': NO LINK FOUND');
            idx++;
            testTab();
        }
    }
    testTab();
}, 2000);
</script>
"""

page = page.replace('</body>', test_js + '</body>')

path = os.path.join(tmpdir, 'test.html')
with open(path, 'w') as f:
    f.write(page)
shutil.copy(path, '/opt/medi-ai-tor/static/_advtest.html')

print("\n=== Chromium Test ===")
result = subprocess.run([
    '/snap/bin/chromium', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--virtual-time-budget=15000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/static/_advtest.html'
], capture_output=True, text=True, timeout=25)

m = re.search(r'<pre id="RESULT">(.*?)</pre>', result.stdout, re.DOTALL)
if m:
    print(m.group(1).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&#39;',"'"))
else:
    print(f"No result found. DOM: {len(result.stdout)} chars")

os.remove('/opt/medi-ai-tor/static/_advtest.html')
shutil.rmtree(tmpdir, ignore_errors=True)
