#!/usr/bin/env python3
"""Headless Chromium test of the technician dashboard."""
import subprocess, json, time, os, tempfile, shutil, requests

tmpdir = tempfile.mkdtemp()

print("=== Headless Chromium Browser Test ===")

# Step 1: Login via API to get cookie
S = requests.Session()
r = S.post('http://localhost/api/auth/login', json={'username': 'admin', 'password': 'admin123'})
print(f"Login: {r.status_code}")
token = r.json().get('token', '')
set_cookie = r.headers.get('set-cookie', '')
print(f"Set-Cookie header: {set_cookie[:80]}...")

# Extract cookie value
cookie_val = ''
for part in set_cookie.split(';'):
    if part.strip().startswith('auth_token='):
        cookie_val = part.strip().split('=', 1)[1]
        break
print(f"Cookie value: {cookie_val[:30]}..." if cookie_val else "NO COOKIE EXTRACTED")

# Step 2: Write a cookie file for chromium
cookie_file = os.path.join(tmpdir, 'cookies.txt')

# Step 3: Use chromium to dump the rendered DOM with JavaScript executed
# First try fetching /technician directly (chromium will follow redirects)
print("\n=== Dumping /technician page DOM ===")
result = subprocess.run([
    'chromium-browser', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--disable-software-rasterizer',
    '--virtual-time-budget=8000',
    '--user-data-dir=' + tmpdir,
    '--dump-dom',
    'http://localhost/technician'
], capture_output=True, text=True, timeout=20, env={**os.environ, 'HOME': tmpdir})

dom = result.stdout
stderr_out = result.stderr

print(f"DOM length: {len(dom)} chars")

# Check if we got login page or dashboard
if 'loginForm' in dom and 'operationsContent' not in dom:
    print("*** Got LOGIN page (redirect) - no auth cookie ***")
    print("Trying with auth token in URL...")
    
    # Try direct dashboard fetch without cookie (won't work, need cookie)
    # Instead, let's check what the actual HTML contains
    r2 = S.get('http://localhost/technician')
    print(f"Requests lib /technician: {r2.status_code}, {len(r2.text)} chars")
    
    if 'operationsContent' in r2.text:
        print("HTML via requests HAS operationsContent - browser just lacks cookie")
        
        # Save HTML and analyze it
        html = r2.text
        
        # Check CSS visibility rules
        print("\n=== Analyzing tab visibility ===")
        
        # Count how many tab-content divs and which is active
        import re
        tab_contents = re.findall(r'<div id="(\w+)" class="tab-content(.*?)"', html)
        for tc_id, tc_classes in tab_contents:
            is_active = 'active' in tc_classes
            print(f"  {tc_id}: {'ACTIVE (visible)' if is_active else 'hidden'}")
        
        # Check sub-tab-content in operations
        ops_section = html[html.find('id="operationsContent"'):html.find('id="advancedContent"')]
        sub_tabs = re.findall(r'<div id="(ops-\w+)" class="sub-tab-content(.*?)"', ops_section)
        print(f"\nOperations sub-tabs ({len(sub_tabs)}):")
        for st_id, st_classes in sub_tabs:
            is_active = 'active' in st_classes
            print(f"  {st_id}: {'ACTIVE' if is_active else 'hidden'}")
        
        # Count buttons in ops-bios (the active one)
        ops_bios = html[html.find('id="ops-bios"'):html.find('id="ops-raid"')]
        btn_count = ops_bios.count('ops-btn')
        print(f"\nops-bios has {btn_count} ops-btn references")
        
        # Check the JS tag
        js_match = re.search(r'<script[^>]*app\.js[^>]*>', html)
        if js_match:
            print(f"JS tag: {js_match.group()}")
        
        # Now fetch the JS and check for syntax errors
        js_tag = js_match.group() if js_match else ''
        js_src = re.search(r'src="([^"]+)"', js_tag)
        if not js_src:
            # Dynamic script tag
            print("JS loaded dynamically via document.write")
            r3 = S.get('http://localhost/static/js/app.js')
            js = r3.text
        else:
            r3 = S.get(f"http://localhost{js_src.group(1)}")
            js = r3.text
        
        print(f"JS file: {len(js)} chars, {js.count(chr(10))} lines")
        
        # Check for common JS issues
        print(f"  Braces match: {js.count('{') == js.count('}')}")
        print(f"  Parens match: {js.count('(') == js.count(')')}")
        print(f"  Has try/catch init: {'INIT FAILED' in js}")
        print(f"  Has switchTab: {'switchTab' in js}")
        print(f"  Has runOperation: {'runOperation' in js}")
        
        # The REAL test: check for any JS that might HIDE operations content
        print("\n=== Checking for JS that hides operations ===")
        for i, line in enumerate(js.split('\n')):
            if 'operationsContent' in line and ('display' in line or 'hide' in line or 'none' in line):
                print(f"  Line {i+1}: {line.strip()[:100]}")
            if 'ops-btn' in line and ('display' in line or 'hide' in line or 'none' in line or 'disabled' in line):
                print(f"  Line {i+1}: {line.strip()[:100]}")

else:
    print("Got dashboard page!")
    # Check for errors
    for check in ['operationsContent', 'ops-btn', 'INIT FAILED', 'App Init Error']:
        print(f"  {check}: {dom.count(check)}")

if stderr_out:
    errors = [l for l in stderr_out.split('\n') if 'error' in l.lower() or 'uncaught' in l.lower()]
    if errors:
        print(f"\nBrowser errors ({len(errors)}):")
        for e in errors[:10]:
            print(f"  {e[:120]}")

shutil.rmtree(tmpdir, ignore_errors=True)
print("\n=== Test Complete ===")
