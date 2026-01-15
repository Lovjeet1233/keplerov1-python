from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    def log_response(response):
        if "api" in response.url or "graphql" in response.url:
            print("API:", response.url)
            try:
                print(response.json())
            except:
                pass

    page.on("response", log_response)

    page.goto("https://www.enel.it/it-it/login")

    # Fill login (example)
    page.fill("#username", "gaetano.quarticelli@virgilio.it")
    page.fill("#password", "Asromoa1927@")
    page.click("button[type=submit]")

    page.wait_for_load_state("networkidle")
    page.goto("https://www.enel.com/investors")

    page.wait_for_timeout(60)
    browser.close()
