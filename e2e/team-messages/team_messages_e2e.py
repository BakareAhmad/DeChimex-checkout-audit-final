"""Final E2E evidence for internal (work) messaging.

One clean run against a fresh in-memory app verifies the whole feature in browsers:
  01 owner's Team messages page: contact list follows the role matrix
  02 owner->manager conversation with a sent message
  03 manager's sidebar badge appears LIVE after a new send (no reload)
  04 manager's open conversation receives the next message LIVE over SignalR
  05 staff restrictions: only management offered (no colleagues, no developer)
  06 developer portal Messages side: owner/manager contacts, dev->owner message

Screenshots land in e2e/team-messages/shots (ordered, single run).
"""
import os
import re

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DCX_E2E_BASE", "http://127.0.0.1:5119")
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(HERE, "shots")
os.makedirs(EVID, exist_ok=True)

SHOT = {"n": 0}
CHECKS = []
DESKTOP = {"width": 1366, "height": 900}

OWNER_PW = "OwnerE2E!2026xY"
DEV_BOOT = "DevPortal#2026!"
STAFF_PW = "StaffE2E!2026x"


def shot(pg, desc, full_page=False):
    SHOT["n"] += 1
    pg.screenshot(path=os.path.join(EVID, f"{SHOT['n']:02d}-{desc}.png"), full_page=full_page)
    print(f"PASS {SHOT['n']:02d} {desc}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    CHECKS.append(msg)
    print(f"PASS    {msg}")


def login(pg, email, password):
    pg.goto(BASE + "/Account/Login", wait_until="domcontentloaded")
    pg.fill('input[name="Email"]', email)
    pg.fill('input[name="Password"]', password)
    pg.click('button[type="submit"]')
    pg.wait_for_timeout(2000)


def owner_login(browser):
    pg = browser.new_context(viewport=DESKTOP).new_page()
    login(pg, "owner@dechimexprinthub.com", "ChangeMe123!")
    if "Login" in pg.url and "password" not in pg.url.lower():
        # App instance from an earlier run: bootstrap password already changed.
        login(pg, "owner@dechimexprinthub.com", OWNER_PW)
    if "password" in pg.url.lower():
        pg.fill('input[name="CurrentPassword"]', "ChangeMe123!")
        pg.fill('input[name="NewPassword"]', OWNER_PW)
        pg.fill('input[name="ConfirmPassword"]', OWNER_PW)
        pg.click('form[action*="password"] button[type="submit"]')
        pg.wait_for_timeout(2200)
        # The forced change invalidates the session: sign back in with the new password.
        if "Login" in pg.url:
            login(pg, "owner@dechimexprinthub.com", OWNER_PW)
    check("/admin" in pg.url, "owner signed in")
    return pg


def create_staff(owner, first, last, email, username, role_label):
    owner.goto(BASE + "/admin/users/create", wait_until="domcontentloaded")
    owner.fill('input[name="FirstName"]', first)
    owner.fill('input[name="LastName"]', last)
    owner.fill('input[name="Email"]', email)
    owner.fill('input[name="Password"]', STAFF_PW)
    owner.fill('input[name="Username"]', username)
    owner.select_option('select[name="RoleIds"]', label=role_label)
    owner.click('form:has(input[name="FirstName"]) button[type="submit"]')
    owner.wait_for_timeout(1800)
    check("/admin/users" in owner.url and "create" not in owner.url, f"created {role_label} {email}")


def option_texts(pg):
    return pg.eval_on_selector_all('select[name="otherUserId"] option', "els => els.map(e => e.textContent)")


def pick(pg, fragment):
    label = next(o for o in option_texts(pg) if fragment in (o or "")).strip()
    pg.select_option('select[name="otherUserId"]', label=label)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        owner = owner_login(browser)

        # Seed the team through the real user-management form.
        create_staff(owner, "Mary", "Manager", "manager@e2e.test", "mary", "Manager")
        create_staff(owner, "Sam", "Staff", "staff@e2e.test", "sam", "SalesStaff")
        create_staff(owner, "Sue", "Staff", "staff2@e2e.test", "sue", "SalesStaff")

        # 01 owner contact list follows the matrix.
        owner.goto(BASE + "/admin/team-messages", wait_until="domcontentloaded")
        owner.wait_for_selector('select[name="otherUserId"]', timeout=15000)
        options = option_texts(owner)
        check(any("Mary Manager" in (o or "") for o in options), "owner sees the manager")
        check(any("Sam Staff" in (o or "") for o in options), "owner sees staff")
        check(any("Platform Developer" in (o or "") for o in options), "owner sees the developer")
        shot(owner, "owner-team-contacts", full_page=True)

        # Staff + manager browsers.
        manager = browser.new_context(viewport=DESKTOP).new_page()
        login(manager, "manager@e2e.test", STAFF_PW)
        check("Login" not in manager.url, "manager signed in")
        staff = browser.new_context(viewport=DESKTOP).new_page()
        login(staff, "staff@e2e.test", STAFF_PW)
        check("Login" not in staff.url, "staff signed in")

        # 02 owner starts a conversation and sends.
        pick(owner, "Mary Manager")
        owner.click('form[action$="/start"] button[type="submit"]')
        owner.wait_for_url(lambda u: re.search(r"/admin/team-messages/[0-9a-f-]{36}$", u), timeout=15000)
        conv_path = owner.url.replace(BASE, "")
        owner.fill('textarea[name="body"]', "Mary, are the weekly reports ready?")
        owner.click('form[action$="/send"] button[type="submit"]')
        owner.wait_for_timeout(1500)
        check("Mary, are the weekly reports ready?" in owner.inner_text("body"), "owner message rendered")
        shot(owner, "owner-conversation-sent", full_page=True)

        # 03 manager badge appears live (manager never reloaded after the send).
        manager.goto(BASE + "/admin/team-messages", wait_until="domcontentloaded")
        manager.wait_for_selector('select[name="otherUserId"]', timeout=15000)
        # Hide the badge client-side, then a NEW send must bring it back over the hub.
        manager.evaluate("(() => { const b = document.getElementById('teamMsgBadge'); if (b) b.hidden = true; })()")
        owner.fill('textarea[name="body"]', "Ping: badge check.")
        owner.click('form[action$="/send"] button[type="submit"]')
        manager.wait_for_function(
            "() => { const b = document.getElementById('teamMsgBadge'); return b && !b.hidden && b.textContent.trim() !== '0'; }",
            timeout=15000)
        check("Ping: badge check." in manager.inner_text("body"), "manager inbox preview shows the message live")
        shot(manager, "manager-unread-badge-live", full_page=True)

        # 04 open conversation receives the next message live over SignalR.
        manager.click(f'a[href="{conv_path}"]')
        manager.wait_for_selector('[data-team-conversation]', timeout=15000)
        owner.fill('textarea[name="body"]', "Live delivery check over the hub.")
        owner.click('form[action$="/send"] button[type="submit"]')
        manager.wait_for_selector('[data-team-msg]:has-text("Live delivery check over the hub.")', timeout=15000)
        check(True, "open conversation appended the message without a reload")
        shot(manager, "manager-live-message", full_page=True)

        # 05 staff restrictions.
        staff.goto(BASE + "/admin/team-messages", wait_until="domcontentloaded")
        staff.wait_for_selector('select[name="otherUserId"]', timeout=15000)
        sopts = option_texts(staff)
        check(any("Mary Manager" in (o or "") for o in sopts), "staff sees the manager")
        check(any("System Owner" in (o or "") for o in sopts), "staff sees the owner")
        check(not any("Sue Staff" in (o or "") for o in sopts), "staff is NOT offered colleagues")
        check(not any("Platform Developer" in (o or "") for o in sopts), "staff is NOT offered the developer")
        shot(staff, "staff-restricted-contacts", full_page=True)

        # 06 developer side.
        dev = browser.new_context(viewport=DESKTOP).new_page()
        login(dev, "developer@dechimexprinthub.local", DEV_BOOT)
        dev.goto(BASE + "/dev/messages", wait_until="domcontentloaded")
        dev.wait_for_selector('select[name="otherUserId"]', timeout=15000)
        dopts = option_texts(dev)
        check(any("System Owner" in (o or "") for o in dopts), "developer sees the owner")
        check(any("Mary Manager" in (o or "") for o in dopts), "developer sees the manager")
        check(not any("Sam Staff" in (o or "") or "Sue Staff" in (o or "") for o in dopts), "developer is NOT offered staff")
        pick(dev, "System Owner")
        dev.click('form[action$="/start"] button[type="submit"]')
        dev.wait_for_url(lambda u: re.search(r"/dev/messages/[0-9a-f-]{36}$", u), timeout=15000)
        dev.fill('textarea[name="body"]', "Deployment window confirmed for tonight.")
        dev.click('form[action$="/send"] button[type="submit"]')
        dev.wait_for_timeout(1500)
        check("Deployment window confirmed" in dev.inner_text("body"), "developer message rendered on the portal side")
        shot(dev, "dev-portal-messages", full_page=True)

        # Owner receives the developer's message on the admin side.
        owner.goto(BASE + "/admin/team-messages", wait_until="domcontentloaded")
        owner.wait_for_timeout(1200)
        check("Platform Developer" in owner.inner_text("body"), "owner inbox shows the developer conversation")

        browser.close()

    print(f"\nRESULT: {len(CHECKS)} checks passed, {SHOT['n']} screenshots")


if __name__ == "__main__":
    main()
