"""Final E2E evidence for the UI polish pass (enum words + eye password toggles).

One clean run against a fresh in-memory app captures, in order:
  01 desktop login: eye toggle present; clicking reveals the password and swaps to eye-slash
  02 mobile login: same toggle, compact and tappable
  03 admin orders: the status filter shows readable words (Pending Payment, In Production)
  04 admin change-password form: every field has the eye toggle
  05 portal change-password (real verified customer): every field has the eye toggle

Screenshots land in e2e/ui-polish/shots (ordered, single run).
"""
import json
import os
import re
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DCX_E2E_BASE", "http://127.0.0.1:5119")
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.environ.get("POLISH_EVID", os.path.join(HERE, "shots"))
CAPTURE = os.environ.get("BREVO_CAPTURE", os.path.join(HERE, "brevo_captured.jsonl"))
os.makedirs(EVID, exist_ok=True)

SHOT = {"n": 0}
CHECKS = []
DESKTOP = {"width": 1366, "height": 900}
MOBILE = {"width": 390, "height": 844}


def shot(pg, desc, full_page=False):
    SHOT["n"] += 1
    pg.screenshot(path=os.path.join(EVID, f"{SHOT['n']:02d}-{desc}.png"), full_page=full_page)
    print(f"PASS {SHOT['n']:02d} {desc}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    CHECKS.append(msg)
    print(f"PASS    {msg}")


def toggle_state(pg, selector='[data-pw-toggle]'):
    btn = pg.query_selector(selector)
    if btn is None:
        return None
    return {
        "pressed": btn.get_attribute("aria-pressed"),
        "shown": "is-shown" in (btn.get_attribute("class") or ""),
        "label": btn.get_attribute("aria-label"),
    }


def brevo_token(email, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(CAPTURE):
            for line in reversed(open(CAPTURE).read().splitlines()):
                if line.strip() and email in line:
                    m = re.search(r'letter-spacing:8px[^>]*>\s*([0-9]{4,8})',
                                  json.loads(line).get("htmlContent", ""))
                    if m:
                        return m.group(1)
        time.sleep(1.5)
    raise AssertionError(f"no verification code captured for {email}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # 01 desktop login: eye toggle reveals the password
        desk = browser.new_context(viewport=DESKTOP).new_page()
        desk.goto(BASE + "/Account/Login", wait_until="domcontentloaded")
        desk.wait_for_selector('[data-pw-toggle]', timeout=15000)
        st = toggle_state(desk)
        check(st is not None and st["pressed"] == "false", "login has an eye toggle (hidden by default)")
        check(desk.query_selector('.pw-ic-eye') is not None and desk.query_selector('.pw-ic-eye-off') is not None,
              "the toggle carries eye and eye-slash icons")
        check("Show</button>" not in desk.inner_text("form"), "no text Show/Hide control on login")
        desk.fill('input[name="Password"]', "S3cretPass!")
        desk.click('[data-pw-toggle]')
        desk.wait_for_timeout(300)
        check(desk.get_attribute('input[name="Password"]', "type") == "text", "clicking the eye reveals the password")
        st2 = toggle_state(desk)
        check(st2["pressed"] == "true" and st2["shown"] and st2["label"] == "Hide password",
              "the toggle state is clearly indicated (aria + eye-slash)")
        desk.click('[data-pw-toggle]')
        desk.wait_for_timeout(300)
        check(desk.get_attribute('input[name="Password"]', "type") == "password", "clicking again hides it")
        desk.click('[data-pw-toggle]')
        desk.wait_for_timeout(300)
        shot(desk, "login-eye-toggle-desktop")

        # 02 mobile login
        mob = browser.new_context(viewport=MOBILE, is_mobile=True, has_touch=True).new_page()
        mob.goto(BASE + "/Account/Login", wait_until="domcontentloaded")
        mob.wait_for_selector('[data-pw-toggle]', timeout=15000)
        mob.fill('input[name="Password"]', "S3cretPass!")
        mob.tap('[data-pw-toggle]')
        mob.wait_for_timeout(300)
        check(mob.get_attribute('input[name="Password"]', "type") == "text", "the eye toggle works on mobile")
        box = mob.query_selector('[data-pw-toggle]').bounding_box()
        check(box["width"] >= 24 and box["height"] >= 24,
              f"tap target is comfortable ({box['width']:.0f}x{box['height']:.0f})")
        shot(mob, "login-eye-toggle-mobile")

        # 03 admin orders: readable status words
        admin = browser.new_context(viewport=DESKTOP).new_page()
        admin.goto(BASE + "/Account/Login", wait_until="domcontentloaded")
        admin.fill('form[action*="Login"] input[name="Email"]', "owner@dechimexprinthub.com")
        for pw in ("OwnerE2E!2026xY", "ChangeMe123!"):
            admin.fill('form[action*="Login"] input[name="Password"]', pw)
            admin.click('form[action*="Login"] button[type="submit"]')
            admin.wait_for_timeout(2000)
            if "Login" not in admin.url:
                break
        if "password" in admin.url.lower():
            admin.fill('input[name="CurrentPassword"]', "ChangeMe123!")
            admin.fill('input[name="NewPassword"]', "OwnerE2E!2026xY")
            admin.fill('input[name="ConfirmPassword"]', "OwnerE2E!2026xY")
            admin.click('form[action*="password"] button[type="submit"]')
            admin.wait_for_timeout(2200)
        check("/admin" in admin.url, "owner signed in")

        admin.goto(BASE + "/admin/orders", wait_until="domcontentloaded")
        admin.wait_for_selector("select", timeout=15000)
        options = admin.eval_on_selector_all("select option", "els => els.map(e => e.textContent)")
        check(any("Pending Payment" in (o or "") for o in options), "order filter shows 'Pending Payment'")
        check(any("In Production" in (o or "") for o in options), "order filter shows 'In Production'")
        check(not any(o and o.strip() == "PendingPayment" for o in options), "no raw 'PendingPayment' option text")
        admin.select_option("select", "InProduction")
        admin.wait_for_timeout(400)
        check(admin.eval_on_selector("select", "e => e.selectedOptions[0].textContent").strip() == "In Production",
              "the collapsed filter reads 'In Production'")
        shot(admin, "admin-orders-readable-statuses")

        # 04 admin change-password: eye toggles everywhere
        admin.goto(BASE + "/admin/security/password", wait_until="domcontentloaded")
        admin.wait_for_selector('[data-pw-toggle]', timeout=15000)
        n = len(admin.query_selector_all('[data-pw-toggle]'))
        check(n == 3, f"admin change-password has an eye toggle per field ({n})")
        shot(admin, "admin-password-eye-toggles")

        # 05 portal change-password: eye toggles everywhere (real verified customer)
        email = f"polish-{int(time.time()) % 100000}@example.com"
        portal = browser.new_context(viewport=DESKTOP).new_page()
        portal.goto(BASE + "/Account/Register", wait_until="domcontentloaded")
        portal.fill('input[name="Email"]', email)
        portal.fill('input[name="Password"]', "PolishE2E!2026x")
        portal.click('form[action*="Register"] button[type="submit"]')
        portal.wait_for_url(lambda u: "VerifyEmail" in u, timeout=20000)
        code = brevo_token(email)
        portal.fill('input[name="Token"]', code)
        portal.click('form button[type="submit"]')
        portal.wait_for_timeout(2500)
        check("Login" not in portal.url, "new customer signed in")
        portal.goto(BASE + "/portal/profile/password", wait_until="domcontentloaded")
        portal.wait_for_selector('[data-pw-toggle]', timeout=15000)
        n2 = len(portal.query_selector_all('[data-pw-toggle]'))
        check(n2 == 3, f"portal change-password has an eye toggle per field ({n2})")
        shot(portal, "portal-password-eye-toggles")

        browser.close()

    print(f"\nRESULT: {len(CHECKS)} checks passed, {SHOT['n']} screenshots")


if __name__ == "__main__":
    main()
