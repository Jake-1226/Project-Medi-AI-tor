#!/usr/bin/env python3
"""Full headless browser test - login, load page with JS, click tabs."""
import subprocess, os, tempfile, shutil, requests

tmpdir = tempfile.mkdtemp()

# Login to get cookie
S = requests.Session()
r = S.post('http://localhost/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['token']

# Fetch the page HTML
r = S.get('http://localhost/technician')
page_html = r.text

# Fetch the JS
r = S.get('http://localhost/static/js/app.js')
app_js = r.text

# Create a self-contained test page that embeds everything
test_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
{open('/opt/medi-ai-tor/static/css/style.css').read()}
</style>
</head>
<body class="tech-body" data-theme="dark">
"""

# Extract just the body content from the technician page
import re
body_match = re.search(r'<body[^>]*>(.*)</body>', page_html, re.DOTALL)
if body_match:
    body_content = body_match.group(1)
    # Remove the script tags - we'll add our own
    body_content = re.sub(r'<script[^>]*>.*?</script>', '', body_content, flags=re.DOTALL)
    test_html += body_content

test_html += f"""
<script>
// Inject auth token
sessionStorage.setItem('auth_token', '{token}');
</script>
<script>
{app_js}
</script>
<script>
// Test results
setTimeout(() => {{
    const results = [];
    results.push('app type: ' + typeof window.app);
    results.push('app.switchTab type: ' + typeof window.app?.switchTab);
    
    // Check tabs
    const sidebarLinks = document.querySelectorAll('.sidebar-link[data-tab]');
    results.push('sidebar links with data-tab: ' + sidebarLinks.length);
    sidebarLinks.forEach(l => results.push('  ' + l.dataset.tab + ' -> ' + l.textContent.trim().substring(0,20)));
    
    // Check current active tab
    const activeTab = document.querySelector('.tab-content.active');
    results.push('active tab: ' + (activeTab?.id || 'NONE'));
    
    // Click Operations
    const opsLink = document.querySelector('[data-tab="operations"]');
    results.push('operations link found: ' + !!opsLink);
    if (opsLink) {{
        opsLink.click();
        results.push('clicked operations');
    }}
    
    setTimeout(() => {{
        const activeTab2 = document.querySelector('.tab-content.active');
        results.push('active tab after click: ' + (activeTab2?.id || 'NONE'));
        
        const opsContent = document.getElementById('operationsContent');
        results.push('operationsContent display: ' + (opsContent ? getComputedStyle(opsContent).display : 'NOT FOUND'));
        results.push('operationsContent class: ' + (opsContent?.className || 'NOT FOUND'));
        
        const opsBtns = document.querySelectorAll('.ops-btn');
        results.push('ops-btn total: ' + opsBtns.length);
        
        const visibleBtns = Array.from(opsBtns).filter(b => getComputedStyle(b).display !== 'none');
        results.push('ops-btn visible: ' + visibleBtns.length);
        
        if (visibleBtns.length > 0) {{
            results.push('first visible btn: ' + visibleBtns[0].textContent.trim().substring(0,50));
        }}
        
        // Check console errors
        results.push('');
        results.push('=== DONE ===');
        
        document.body.innerHTML = '<pre id="testresults">' + results.join('\\n') + '</pre>';
    }}, 500);
}}, 2000);
</script>
</body>
</html>"""

# Write test file
test_path = os.path.join(tmpdir, 'fulltest.html')
with open(test_path, 'w') as f:
    f.write(test_html)

# Copy to static for serving
shutil.copy(test_path, '/opt/medi-ai-tor/static/fulltest.html')

print("=== Running full browser test ===")
result = subprocess.run([
    'chromium-browser', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--disable-software-rasterizer',
    '--virtual-time-budget=10000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/static/fulltest.html'
], capture_output=True, text=True, timeout=20, env={**os.environ, 'HOME': tmpdir})

dom = result.stdout
# Find results
match = re.search(r'<pre id="testresults">(.*?)</pre>', dom, re.DOTALL)
if match:
    print(match.group(1))
else:
    print(f"No results found. DOM length: {len(dom)}")
    # Check for errors
    if 'error' in dom.lower():
        for line in dom.split('\n'):
            if 'error' in line.lower():
                print(f"  ERR: {line[:150]}")

# Check stderr for JS errors
if result.stderr:
    for line in result.stderr.split('\n'):
        ll = line.lower()
        if any(x in ll for x in ['uncaught', 'syntaxerror', 'typeerror', 'referenceerror']) and 'vaapi' not in ll:
            print(f"  JS ERROR: {line[:150]}")

os.remove('/opt/medi-ai-tor/static/fulltest.html')
shutil.rmtree(tmpdir, ignore_errors=True)
