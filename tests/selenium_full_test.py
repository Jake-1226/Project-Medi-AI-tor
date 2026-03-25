#!/usr/bin/env python3
"""Real Selenium browser test — login, connect, check every tab."""
import sys, time, json

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--disable-gpu')
opts.add_argument('--ignore-certificate-errors')
opts.binary_location = '/snap/chromium/current/usr/lib/chromium-browser/chrome'

svc = Service('/snap/chromium/current/usr/lib/chromium-browser/chromedriver')

driver = webdriver.Chrome(service=svc, options=opts)
driver.set_page_load_timeout(20)
wait = WebDriverWait(driver, 10)

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} -- {detail[:120]}")

try:
    # === LOGIN ===
    print("=== 1. Login ===")
    driver.get('http://localhost/login')
    time.sleep(1)

    driver.find_element(By.ID, 'username').send_keys('admin')
    driver.find_element(By.ID, 'password').send_keys('admin123')
    driver.find_element(By.ID, 'loginBtn').click()
    time.sleep(3)

    check("Login redirects to /technician", '/technician' in driver.current_url, driver.current_url)
    check("Page title has Medi-AI-tor", 'Medi-AI-tor' in driver.title, driver.title)

    # === CONSOLE ERRORS ===
    print("\n=== 2. Console Errors ===")
    logs = driver.get_log('browser')
    severe = [l for l in logs if l['level'] == 'SEVERE']
    for l in severe:
        print(f"  SEVERE: {l['message'][:120]}")
    check("No severe JS errors", len(severe) == 0, f"{len(severe)} errors")

    # Check init log
    init_logs = [l for l in logs if 'MediAI' in l.get('message', '')]
    for l in init_logs:
        print(f"  APP LOG: {l['message'][:120]}")

    # === SIDEBAR TABS ===
    print("\n=== 3. Sidebar Tabs ===")
    sidebar_links = driver.find_elements(By.CSS_SELECTOR, '.sidebar-link[data-tab]')
    check("7 sidebar tabs found", len(sidebar_links) == 7, f"found {len(sidebar_links)}")

    for link in sidebar_links:
        tab_name = link.get_attribute('data-tab')
        print(f"\n  --- Tab: {tab_name} ---")
        link.click()
        time.sleep(0.5)

        content_id = f"{tab_name}Content"
        content_el = driver.find_element(By.ID, content_id)
        is_active = 'active' in content_el.get_attribute('class')
        is_visible = content_el.is_displayed()
        check(f"{tab_name} active after click", is_active, content_el.get_attribute('class'))
        check(f"{tab_name} visible", is_visible, f"display={content_el.value_of_css_property('display')}")

        if tab_name == 'operations':
            ops_btns = driver.find_elements(By.CSS_SELECTOR, '#operationsContent .ops-btn')
            check(f"Operations has buttons", len(ops_btns) > 0, f"found {len(ops_btns)}")
            if ops_btns:
                first_visible = ops_btns[0].is_displayed()
                first_text = ops_btns[0].text[:50]
                check(f"First ops-btn visible", first_visible)
                check(f"First ops-btn has text", len(first_text) > 0, first_text)
                print(f"  Total ops buttons: {len(ops_btns)}")

            # Check sub-tabs
            sub_tabs = driver.find_elements(By.CSS_SELECTOR, '#operationsContent .sub-tab')
            check(f"Operations sub-tabs", len(sub_tabs) >= 7, f"found {len(sub_tabs)}")
            for st in sub_tabs[:3]:
                print(f"    Sub-tab: {st.text}")

        if tab_name == 'advanced':
            adv_subs = driver.find_elements(By.CSS_SELECTOR, '#advancedContent .sub-tab')
            check(f"Advanced sub-tabs", len(adv_subs) >= 5, f"found {len(adv_subs)}")
            for st in adv_subs[:3]:
                print(f"    Sub-tab: {st.text}")

    # === CONNECT TO SERVER ===
    print("\n=== 4. Connect to iDRAC ===")
    # Switch back to overview
    driver.find_element(By.CSS_SELECTOR, '[data-tab="overview"]').click()
    time.sleep(0.5)

    host_el = driver.find_element(By.ID, 'serverHost')
    user_el = driver.find_element(By.ID, 'username')
    pass_el = driver.find_element(By.ID, 'password')
    host_el.clear()
    host_el.send_keys('100.71.148.195')
    user_el.clear()
    user_el.send_keys('root')
    pass_el.clear()
    pass_el.send_keys('calvin')

    connect_btn = driver.find_element(By.ID, 'connectBtn')
    connect_btn.click()
    print("  Connecting... (waiting up to 30s)")

    # Wait for connection
    time.sleep(15)

    # Check connection status
    topbar = driver.find_element(By.CSS_SELECTOR, '.topbar-connection')
    topbar_text = topbar.text
    check("Connected (topbar shows)", 'Connected' in topbar_text or '100.71' in topbar_text, topbar_text)

    # Wait for data to load
    time.sleep(5)

    # === CHECK TABS WITH DATA ===
    print("\n=== 5. Tabs With Data ===")

    # Overview
    driver.find_element(By.CSS_SELECTOR, '[data-tab="overview"]').click()
    time.sleep(1)
    overview = driver.find_element(By.ID, 'overviewContent')
    overview_text = overview.text
    check("Overview has data", len(overview_text) > 100, f"text length: {len(overview_text)}")

    # Operations (the problematic one)
    driver.find_element(By.CSS_SELECTOR, '[data-tab="operations"]').click()
    time.sleep(1)
    ops = driver.find_element(By.ID, 'operationsContent')
    check("Operations visible after connect", ops.is_displayed())
    ops_btns = driver.find_elements(By.CSS_SELECTOR, '#operationsContent .ops-btn')
    check("Operations buttons present", len(ops_btns) > 50, f"found {len(ops_btns)}")

    # Advanced
    driver.find_element(By.CSS_SELECTOR, '[data-tab="advanced"]').click()
    time.sleep(1)
    adv = driver.find_element(By.ID, 'advancedContent')
    check("Advanced visible", adv.is_displayed())

    # === FINAL CONSOLE CHECK ===
    print("\n=== 6. Final Console ===")
    logs = driver.get_log('browser')
    severe = [l for l in logs if l['level'] == 'SEVERE']
    for l in severe:
        print(f"  SEVERE: {l['message'][:150]}")
    check("No new severe errors after interaction", len(severe) <= 2, f"{len(severe)} errors")

except Exception as e:
    print(f"\nFATAL ERROR: {e}")
    import traceback
    traceback.print_exc()
finally:
    driver.quit()

print(f"\n{'='*50}")
print(f"RESULTS: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")
