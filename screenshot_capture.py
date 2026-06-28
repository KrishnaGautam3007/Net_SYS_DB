#!/usr/bin/env python
"""
NetSysDB screenshot capture script.

This script automatically takes screenshots of all 4 dashboard pages
and saves them to the screenshots/ folder.

Prerequisites:
  pip install selenium

Make sure:
  1. docker-compose up --build is running
  2. http://localhost:5000 is accessible
  3. Chrome/Chromium browser is installed
"""

import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def setup_driver():
    """Initialize Chrome WebDriver."""
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")

    try:
        driver = webdriver.Chrome(options=options)
    except Exception:
        print("ERROR: Chrome WebDriver not found. Install chromedriver:")
        print("  Windows: choco install chromedriver")
        print("  macOS: brew install chromedriver")
        print("  Linux: sudo apt install chromium-chromedriver")
        exit(1)

    return driver


def wait_for_element(driver, by, value, timeout=10):
    """Wait for element to appear."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except Exception as e:
        print(f"WARNING: Element not found ({e})")


def screenshot_overview(driver):
    """Capture Overview page screenshot."""
    print("1. Capturing Overview page...")
    driver.get("http://localhost:5000")

    # Wait for machine cards to load
    wait_for_element(driver, By.CSS_SELECTOR, "[class*='card']")
    time.sleep(2)  # Let charts render

    path = "screenshots/overview.png"
    driver.save_screenshot(path)
    print(f"   Saved: {path}")


def screenshot_machine_detail(driver):
    """Capture Machine Detail page screenshot."""
    print("2. Capturing Machine Detail page...")

    # Click the first machine card
    try:
        card = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[class*='card']"))
        )
        card.click()
        time.sleep(2)  # Let detail page load and render
    except Exception as e:
        print(f"   WARNING: Could not click machine card ({e})")
        return

    path = "screenshots/machine_detail.png"
    driver.save_screenshot(path)
    print(f"   Saved: {path}")


def screenshot_query_console(driver):
    """Capture Query Console page screenshot."""
    print("3. Capturing Query Console page...")

    # Click Query in navbar
    try:
        query_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Query')]"))
        )
        query_link.click()
        time.sleep(2)  # Let page load
    except Exception as e:
        print(f"   WARNING: Could not click Query link ({e})")
        return

    # Type a simple query
    try:
        textarea = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea"))
        )
        textarea.click()
        textarea.clear()
        textarea.send_keys("SELECT machine_name, avg(cpu_percent) FROM metrics GROUP BY machine_name LIMIT 5")
        time.sleep(1)

        # Press Enter or click execute button
        execute_btn = driver.find_elements(By.XPATH, "//button[contains(text(), 'Execute') or contains(text(), 'Run')]")
        if execute_btn:
            execute_btn[0].click()
        else:
            textarea.send_keys("\n")

        time.sleep(2)  # Let query execute and results render
    except Exception as e:
        print(f"   WARNING: Could not enter query ({e})")

    path = "screenshots/query_console.png"
    driver.save_screenshot(path)
    print(f"   Saved: {path}")


def screenshot_alerts(driver):
    """Capture Alerts page screenshot."""
    print("4. Capturing Alerts page...")

    # Click Alerts in navbar
    try:
        alerts_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Alerts')]"))
        )
        alerts_link.click()
        time.sleep(2)  # Let page load
    except Exception as e:
        print(f"   WARNING: Could not click Alerts link ({e})")
        return

    path = "screenshots/alerts.png"
    driver.save_screenshot(path)
    print(f"   Saved: {path}")


def main():
    """Main capture workflow."""
    print("\n=== NetSysDB Screenshot Capture ===\n")

    # Create screenshots folder
    os.makedirs("screenshots", exist_ok=True)

    # Check if server is running
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("localhost", 5000))
    sock.close()

    if result != 0:
        print("ERROR: Dashboard not running. Start it with:")
        print("  docker-compose up --build")
        exit(1)

    print("Dashboard is running at http://localhost:5000\n")

    # Initialize driver
    driver = setup_driver()

    try:
        screenshot_overview(driver)
        screenshot_machine_detail(driver)
        screenshot_query_console(driver)
        screenshot_alerts(driver)

        print("\n✓ All screenshots captured!")
        print("  Location: screenshots/")
        print("  Files:")
        print("    - screenshots/overview.png")
        print("    - screenshots/machine_detail.png")
        print("    - screenshots/query_console.png")
        print("    - screenshots/alerts.png")
        print("\n✓ Ready to push to GitHub!")

    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
