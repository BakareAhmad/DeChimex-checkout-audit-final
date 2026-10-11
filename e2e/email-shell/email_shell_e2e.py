"""E2E evidence for the email shell redesign (logo-free + own dark mode).

Flow on a fresh in-memory app with the Brevo stub:
  - owner signs in (fresh seed -> forced password change keeps the session),
  - a draft campaign is saved and a TEST email is sent through the real send
    path (captured by the Brevo stub),
  - the captured HTML is rendered in a browser in light and dark colour
    schemes; screenshots show the delivered email as clients will display it.

Checks:
  - the sent email carries NO logo image (the sender avatar carries the brand),
  - it declares light+dark color-scheme and ships its own dark palette,
  - dark rendering keeps the indigo CTA with white text and readable copy
    (no pastelised theme wash),
  - light rendering is unchanged in structure.

Screenshots land in EVID (ordered, single run).
"""
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DCX_E2E_BASE", "http://127.0.0.1:5119")
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.environ.get("SHELL_EVID", os.path.join(HERE, "shots"))
CAPTURE = os.environ.get("BREVO_CAPTURE", os.path.join(HERE, "brevo_captured.jsonl"))
os.makedirs(EVID, exist_ok=True)

SHOT = {"n": 0}
CHECKS = []
OWNER = "owner@dechimexprinthub.com"


def shot(pg, desc, full_page=True):
    SHOT["n"] += 1
    pg.screenshot(path=os.path.join(EVID, f"{SHOT['n']:02d}-{desc}.png"), full_page=full_page)
    print(f"PASS {SHOT['n']:02d} {desc}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    CHECKS.append(msg)
    print(f"PASS    {msg}")


def owner_login(pg):
    pg.goto(BASE + "/Account/Login", wait_until="domcontentloaded")
    pg.wait_for_selector('form[action*="Login"] input[name="Email"]', timeout=60000)
    for password in ("OwnerE2E!2026xY", "ChangeMe123!"):
        pg.fill('form[action*="Login"] input[name="Email"]', OWNER)
        pg.fill('form[action*="Login"] input[name="Password"]', password)
        pg.click('form[action*="Login"] button[type="submit"]')
        pg.wait_for_load_state("domcontentloaded")
        if "/admin/security/password" in pg.url:
            pg.fill('form[action*="password"] input[name="CurrentPassword"]', password)
            pg.fill('form[action*="password"] input[name="NewPassword"]', "OwnerE2E!2026xY")
            pg.fill('form[action*="password"] input[name="ConfirmPassword"]', "OwnerE2E!2026xY")
            pg.click('form[action*="password"] button[type="submit"]')
            pg.wait_for_load_state("domcontentloaded")
            break  # admin forced change re-issues the cookie: session stays signed in
        if "Login" not in pg.url:
            break
    pg.goto(BASE + "/admin/dashboard", wait_until="domcontentloaded")
    check("Login" not in pg.url, "owner signed in")


def captured_html_for(email, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(CAPTURE):
            for line in reversed(open(CAPTURE).read().splitlines()):
                if line.strip() and email in line:
                    return json.loads(line).get("htmlContent", "")
        time.sleep(1)
    raise AssertionError("no email captured by the brevo stub")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_context(viewport={"width": 700, "height": 900}).new_page()
        owner_login(pg)

        # save a draft campaign, then send a test email through the real path
        token = pg.eval_on_selector('#campaignForm input[name="__RequestVerificationToken"]', "el => el.value") \
            if pg.query_selector('#campaignForm') else None
        pg.goto(BASE + "/admin/marketing/compose", wait_until="domcontentloaded")
        pg.wait_for_selector("#campaignForm", timeout=30000)
        token = pg.eval_on_selector('#campaignForm input[name="__RequestVerificationToken"]', "el => el.value")
        blocks = json.dumps({"blocks": [
            {"type": "heading", "text": "The new season is here"},
            {"type": "paragraph", "text": "Hi {{FirstName}}, fresh paper stocks and faster turnaround - see what changed this week."},
            {"type": "button", "text": "Browse the shop", "url": "https://dechimexprinthub.com/shop"},
        ]})
        resp = pg.request.post(BASE + "/admin/marketing/compose", form={
            "__RequestVerificationToken": token,
            "Name": "Shell proof", "Subject": "A quick look at the new season",
            "SenderName": "DE-CHIMEX PRINT HUB", "AudienceSegment": "0", "BlocksJson": blocks,
        })
        m = re.search(r"/admin/marketing/([0-9a-f-]{36})$", resp.url)
        check(resp.ok and m is not None, f"draft campaign saved (landed on {resp.url})")
        campaign_id = m.group(1)

        page = pg.goto(BASE + f"/admin/marketing/{campaign_id}", wait_until="domcontentloaded")
        token = pg.eval_on_selector('form[action*="test"] input[name="__RequestVerificationToken"]', "el => el.value")
        resp = pg.request.post(BASE + f"/admin/marketing/{campaign_id}/test", form={
            "__RequestVerificationToken": token, "TestEmail": "shellproof@e2e.test",
        })
        check(resp.ok, "test send accepted")

        html = captured_html_for("shellproof@e2e.test")
        check("/img/logo.png" not in html, "the sent email carries no logo image")
        check("name='color-scheme' content='light dark'" in html, "email declares light+dark color-scheme")
        check("prefers-color-scheme: dark" in html, "email ships its own dark palette")
        check("DE-CHIMEX" in html and "PRINT HUB" in html, "the text wordmark still brands the header")

        mail_file = os.path.join(EVID, "_captured-email.html")
        open(mail_file, "w").write(html)

        # light rendering
        view = browser.new_context(viewport={"width": 700, "height": 900}, color_scheme="light").new_page()
        view.goto("file://" + mail_file)
        view.wait_for_timeout(600)
        card_bg = view.eval_on_selector("table.dc-container", "el => getComputedStyle(el).backgroundColor")
        check(card_bg == "rgb(255, 255, 255)", f"light mode keeps the white card ({card_bg})")
        shot(view, "email-light")

        # dark rendering - OUR palette, not an auto-converted wash
        dark = browser.new_context(viewport={"width": 700, "height": 900}, color_scheme="dark").new_page()
        dark.goto("file://" + mail_file)
        dark.wait_for_timeout(600)
        card_bg = dark.eval_on_selector("table.dc-container", "el => getComputedStyle(el).backgroundColor")
        check(card_bg == "rgb(30, 41, 59)", f"dark mode uses the app's --n-800 card ({card_bg})")
        btn = dark.eval_on_selector(".dc-body a[style*='4338CA']", "el => getComputedStyle(el).backgroundColor + '|' + getComputedStyle(el).color")
        check(btn == "rgb(67, 56, 202)|rgb(255, 255, 255)", f"dark mode keeps the indigo CTA with white text ({btn})")
        h1c = dark.eval_on_selector(".dc-body h2", "el => getComputedStyle(el).color")
        check(h1c == "rgb(255, 255, 255)", f"dark mode heading is readable ({h1c})")
        shot(dark, "email-dark")

        browser.close()
    os.remove(mail_file)
    print(f"\nRESULT: {len(CHECKS)} checks passed, {SHOT['n']} screenshots")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}")
        print(f"\nRESULT: {len(CHECKS)} checks passed, 1 failed")
        sys.exit(1)
