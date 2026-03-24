#!/usr/bin/env python3
"""Test with real Chromium browser - check if JS loads and tabs work."""
import subprocess, os, tempfile, shutil, json

tmpdir = tempfile.mkdtemp()
print(f"Temp dir: {tmpdir}")

# Create a test HTML file that does everything
test_html = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<div id="result">Running...</div>
<script>
(async () => {
    const results = [];
    try {
        // 1. Login
        const loginR = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: 'admin', password: 'admin123'})
        });
        const loginD = await loginR.json();
        results.push('Login: ' + loginD.status);
        
        // 2. Fetch technician page HTML
        const pageR = await fetch('/technician');
        const pageHTML = await pageR.text();
        results.push('Page size: ' + pageHTML.length);
        results.push('Has operationsContent: ' + pageHTML.includes('operationsContent'));
        results.push('ops-btn count: ' + (pageHTML.match(/class="ops-btn"/g) || []).length);
        results.push('Has advancedContent: ' + pageHTML.includes('advancedContent'));
        
        // 3. Fetch and parse JS
        const jsR = await fetch('/static/js/app.js');
        const jsText = await jsR.text();
        results.push('JS size: ' + jsText.length + ' chars');
        results.push('JS has class DellAIAgent: ' + jsText.includes('class DellAIAgent'));
        
        // 4. Try to parse the JS
        try {
            new Function(jsText);
            results.push('JS PARSE: OK');
        } catch (e) {
            results.push('JS PARSE ERROR: ' + e.message);
            // Find the line number
            const match = e.message.match(/position (\\d+)/);
            if (match) {
                const pos = parseInt(match[1]);
                const before = jsText.substring(Math.max(0, pos - 50), pos);
                const after = jsText.substring(pos, pos + 50);
                results.push('Context: ...' + before + '>>HERE<<' + after + '...');
            }
        }
        
        // 5. Actually load the page in an iframe and test
        results.push('');
        results.push('=== IFRAME TEST ===');
        
        // Create an iframe with the technician page
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        document.body.appendChild(iframe);
        iframe.srcdoc = pageHTML;
        
        await new Promise(r => setTimeout(r, 2000));
        
        const iframeDoc = iframe.contentDocument;
        if (iframeDoc) {
            const opsContent = iframeDoc.getElementById('operationsContent');
            results.push('operationsContent found: ' + !!opsContent);
            if (opsContent) {
                results.push('operationsContent display: ' + getComputedStyle(opsContent).display);
                results.push('operationsContent class: ' + opsContent.className);
                
                // Try adding active class
                opsContent.classList.add('active');
                results.push('After adding active - display: ' + getComputedStyle(opsContent).display);
                
                // Check ops buttons
                const btns = opsContent.querySelectorAll('.ops-btn');
                results.push('ops-btn found in DOM: ' + btns.length);
                if (btns.length > 0) {
                    results.push('First btn visible: ' + (getComputedStyle(btns[0]).display !== 'none'));
                    results.push('First btn text: ' + btns[0].textContent.trim().substring(0, 40));
                }
            }
            
            // Check for JS errors
            const scripts = iframeDoc.querySelectorAll('script');
            results.push('Script tags in page: ' + scripts.length);
            
            // Check if app object exists
            results.push('iframe window.app: ' + typeof iframe.contentWindow.app);
        }
        
    } catch (e) {
        results.push('ERROR: ' + e.message);
        results.push('Stack: ' + e.stack);
    }
    
    document.getElementById('result').textContent = results.join('\\n');
})();
</script>
</body>
</html>"""

# Write test file
test_path = os.path.join(tmpdir, 'test.html')
with open(test_path, 'w') as f:
    f.write(test_html)

# Serve it via the app (copy to static)
import shutil
shutil.copy(test_path, '/opt/medi-ai-tor/static/browser_test.html')

# Run chromium headless
print("\n=== Running Chromium headless ===")
env = {**os.environ, 'HOME': tmpdir, 'DISPLAY': ''}
result = subprocess.run([
    'chromium-browser', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--disable-software-rasterizer',
    '--virtual-time-budget=10000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/static/browser_test.html'
], capture_output=True, text=True, timeout=20, env=env)

# Extract result text
dom = result.stdout
import re
match = re.search(r'<div id="result">(.*?)</div>', dom, re.DOTALL)
if match:
    print(match.group(1).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>'))
else:
    print(f"DOM ({len(dom)} chars): {dom[:500]}")

if result.stderr:
    errors = [l for l in result.stderr.split('\n') 
              if any(x in l.lower() for x in ['error', 'uncaught', 'syntaxerror'])
              and not any(x in l.lower() for x in ['vaapi', 'dbus', 'gpu', 'shared_memory', 'zygote', 'sandbox', 'viz'])]
    if errors:
        print(f"\nBrowser errors:")
        for e in errors[:5]:
            print(f"  {e[:150]}")

# Cleanup
os.remove('/opt/medi-ai-tor/static/browser_test.html')
shutil.rmtree(tmpdir, ignore_errors=True)
