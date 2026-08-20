from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('file:///home/uplix/uplix/KImbela/test_dropdown.html')
    
    print("Initial hidden:", page.evaluate("document.querySelector('.dropdown-menu').classList.contains('hidden')"))
    page.click('button')
    print("After click hidden:", page.evaluate("document.querySelector('.dropdown-menu').classList.contains('hidden')"))
    
    browser.close()
