#!/usr/bin/env python3
import requests, re
S = requests.Session()
r = S.post("http://localhost/api/auth/login", json={"username":"admin","password":"admin123"})
r = S.get("http://localhost/technician/app")
html = r.text
print("Page size:", len(html))

# Find advancedContent
idx = html.find('id="advancedContent"')
print("advancedContent at position:", idx)

if idx > 0:
    # Count what's inside
    chunk = html[idx:idx+10000]
    print("sub-tab count:", chunk.count("sub-tab"))
    print("sub-tab-content count:", chunk.count("sub-tab-content"))
    print("adv-lifecycle:", "adv-lifecycle" in chunk)
    print("adv-monitoring:", "adv-monitoring" in chunk)
    print("adv-diagnostics:", "adv-diagnostics" in chunk)
    print("adv-health-score:", "adv-health-score" in chunk)
    print("adv-snapshot:", "adv-snapshot" in chunk)
    print("adv-predictive:", "adv-predictive" in chunk)
    print("adv-audit:", "adv-audit" in chunk)
    print("ops-btn in adv:", chunk.count("ops-btn"))
    print("buttons in adv:", chunk.count("<button"))
    
    # Show first 200 chars of the section
    print()
    print("First 300 chars of advancedContent:")
    print(chunk[:300])
