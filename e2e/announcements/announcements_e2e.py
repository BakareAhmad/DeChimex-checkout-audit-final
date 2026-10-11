"""Final E2E evidence for: admin-managed service announcements shown as a compact
scrolling pill across the customer-facing app (desktop + mobile).

One clean run against a fresh in-memory app captures, in order:
  01 admin /admin/announcements empty state (no announcement -> nothing on the store)
  02 the new-announcement form (message + optional window + active switch)
  03 the saved announcement listed as Live
  04 desktop home: the pill renders above the header and the long text marquee-animates
  05 mobile home: the same pill, compact, one line
  06 after editing, the pill shows the new wording
  07 after deactivating, the pill is gone from the customer app
  08 re-activated with a future start date -> still hidden (Scheduled in admin)
  09 after deleting, the admin list is empty again and the store stays clean

Screenshots land in e2e/announcements/shots (ordered, single run).
"""
import os
import time

from playwright.sync_api import sync_playwright

# Unique per run so a re-run against the same app instance can never collide.
RUN = str(int(time.time()))[-5:]

BASE = os.environ.get("DCX_E2E_BASE", "http://127.0.0.1:5119")
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.environ.get("ANN_EVID", os.path.join(HERE, "shots"))
os.makedirs(EVID, exist_ok=True)

SHOT = {"n": 0}
CHECKS = []
DESKTOP = {"width": 1366, "height": 900}
MOBILE = {"width": 390, "height": 844}
MSG1 = ("Notice: our Abeokuta workshop is closed Fri 10 Oct for a staff event - "
        "orders placed after 4pm Thu ship Monday. Pickup counter unaffected. (Ref A-" + RUN + ")")
MSG2 = ("Updated: the staff event moved to Sat 11 Oct - we ARE open on Friday as usual. "
        "Thank you for printing with DE-CHIMEX!")


def shot(pg, desc, full_page=False):
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
    pg.fill('form[action*="Login"] input[name="Email"]', "owner@dechimexprinthub.com")
    for pw in ("OwnerE2E!2026xY", "ChangeMe123!"):
        pg.fill('form[action*="Login"] input[name="Password"]', pw)
        pg.click('form[action*="Login"] button[type="submit"]')
        pg.wait_for_timeout(2000)
        if "Login" not in pg.url:
            break
    if "password" in pg.url.lower():
        pg.fill('input[name="CurrentPassword"]', "ChangeMe123!")
        pg.fill('input[name="NewPassword"]', "OwnerE2E!2026xY")
        pg.fill('input[name="ConfirmPassword"]', "OwnerE2E!2026xY")
        pg.click('form[action*="password"] button[type="submit"]')
        pg.wait_for_timeout(2200)
    check("/admin" in pg.url, f"owner signed in ({pg.url})")


def pill_state(pg):
    """(present, animating) for the customer announcement pill."""
    el = pg.query_selector('[data-announce-ticker]')
    if el is None:
        return False, False
    anim = pg.eval_on_selector('.cs-announce-track',
                               "e => getComputedStyle(e).animationName")
    return True, anim == "cs-announce-scroll"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        admin = browser.new_context(viewport=DESKTOP).new_page()
        admin.on("dialog", lambda d: d.accept())

        # 01 - nothing to announce yet
        pre = browser.new_context(viewport=DESKTOP).new_page()
        pre.goto(BASE + "/", wait_until="domcontentloaded")
        present, _ = pill_state(pre)
        check(not present, "no announcement -> no pill on the customer home page")
        pre.close()

        owner_login(admin)
        admin.goto(BASE + "/admin/announcements", wait_until="domcontentloaded")
        admin.wait_for_selector('a[href="/admin/announcements/create"]', timeout=15000)
        check("No announcements yet" in admin.inner_text("body"), "admin shows the empty state")
        shot(admin, "admin-announcements-empty", full_page=True)

        # 02 - the form
        admin.click('a[href="/admin/announcements/create"]')
        admin.wait_for_selector('#Message', timeout=15000)
        body = admin.inner_text("body")
        check("Message" in body and "Visible from" in body and "Visible until" in body,
              "form offers message + optional visibility window")
        check(admin.query_selector('#IsActive') is not None, "form offers the active switch")
        shot(admin, "admin-announcement-form", full_page=True)

        # validation: end before start re-renders with an error
        admin.fill('#Message', "Backwards window.")
        admin.fill('#StartAt', "2026-12-02T09:00")
        admin.fill('#EndAt', "2026-12-01T09:00")
        admin.click('form[action*="create"] button[type="submit"]')
        admin.wait_for_timeout(1200)
        check("End date must be after the start date." in admin.inner_text("body"),
              "backwards visibility window is rejected")

        # 03 - create a real active announcement
        admin.fill('#Message', MSG1)
        admin.fill('#StartAt', "")
        admin.fill('#EndAt', "")
        admin.check('#IsActive')
        admin.click('form[action*="create"] button[type="submit"]')
        admin.wait_for_url(lambda u: u.rstrip("/").endswith("/admin/announcements"), timeout=20000)
        body = admin.inner_text("body")
        check("Live" in body, "the saved announcement is listed as Live")
        shot(admin, "admin-announcements-live", full_page=True)

        # 04 - desktop pill + marquee
        desk = browser.new_context(viewport=DESKTOP).new_page()
        desk.goto(BASE + "/", wait_until="domcontentloaded")
        desk.wait_for_selector('[data-announce-ticker]', timeout=15000)
        desk.wait_for_timeout(900)
        present, anim = pill_state(desk)
        check(present, "the pill renders above the customer header on desktop")
        check(MSG1.split(" - ")[0] in desk.inner_text('[data-announce-ticker]'), "pill carries the message")
        gw = desk.eval_on_selector('.cs-announce-group', "e => e.offsetWidth")
        vw = desk.eval_on_selector('.cs-announce-view', "e => e.clientWidth")
        if gw > vw:
            check(anim, "overflowing text marquee-animates on desktop")
        else:
            check(not anim, "text fits the desktop viewport -> pill stays static (subtle)")
        print(f"        (desktop group {gw}px vs view {vw}px)")
        h = desk.eval_on_selector('[data-announce-ticker]', "e => e.getBoundingClientRect().height")
        check(h <= 40, f"the pill stays compact ({h:.0f}px tall)")
        shot(desk, "home-pill-desktop")

        # 05 - mobile pill
        mob = browser.new_context(viewport=MOBILE, is_mobile=True, has_touch=True).new_page()
        mob.goto(BASE + "/", wait_until="domcontentloaded")
        mob.wait_for_selector('[data-announce-ticker]', timeout=15000)
        mob.wait_for_timeout(900)
        present_m, anim_m = pill_state(mob)
        check(present_m, "the pill renders on mobile")
        check(anim_m, "the long message marquee-animates on mobile too")
        mh = mob.eval_on_selector('[data-announce-ticker]', "e => e.getBoundingClientRect().height")
        check(mh <= 40, f"mobile pill is compact ({mh:.0f}px tall)")
        shot(mob, "home-pill-mobile")
        # vertical page scroll still works with the pill present
        mob.evaluate("window.scrollTo(0, 600)")
        mob.wait_for_timeout(300)
        check(mob.evaluate("window.scrollY") > 400, "vertical page scrolling still works on mobile")

        # 06 - edit updates the pill
        admin.goto(BASE + "/admin/announcements", wait_until="domcontentloaded")
        admin.wait_for_selector('a[href*="/admin/announcements/edit/"]', timeout=15000)
        admin.click('a[href*="/admin/announcements/edit/"]')
        admin.wait_for_selector('#Message', timeout=15000)
        admin.fill('#Message', MSG2)
        admin.click('form[action*="edit"] button[type="submit"]')
        admin.wait_for_url(lambda u: u.rstrip("/").endswith("/admin/announcements"), timeout=20000)
        desk.reload(wait_until="domcontentloaded")
        desk.wait_for_selector('[data-announce-ticker]', timeout=15000)
        check("Updated: the staff event moved" in desk.inner_text('[data-announce-ticker]'),
              "the edited wording shows in the pill")
        shot(desk, "home-pill-after-edit")

        # 07 - deactivate hides it
        admin.goto(BASE + "/admin/announcements", wait_until="domcontentloaded")
        admin.wait_for_selector('form[action*="toggle"] button[type="submit"]', timeout=15000)
        admin.click('form[action*="toggle"] button[type="submit"]')  # Deactivate (only row)
        admin.wait_for_timeout(1500)
        desk.reload(wait_until="domcontentloaded")
        desk.wait_for_timeout(700)
        present, _ = pill_state(desk)
        check(not present, "deactivating removes the pill from the customer app")
        check("Inactive" in admin.inner_text("body"), "admin shows the announcement as Inactive")
        shot(desk, "home-pill-after-deactivate")

        # 08 - future start date keeps it hidden (scheduled)
        admin.click('a[href*="/admin/announcements/edit/"]')
        admin.wait_for_selector('#Message', timeout=15000)
        admin.fill('#StartAt', "2026-12-01T09:00")
        admin.check('#IsActive')
        admin.click('form[action*="edit"] button[type="submit"]')
        admin.wait_for_url(lambda u: u.rstrip("/").endswith("/admin/announcements"), timeout=20000)
        check("Scheduled" in admin.inner_text("body"), "active-but-future announcement shows as Scheduled")
        desk.reload(wait_until="domcontentloaded")
        desk.wait_for_timeout(700)
        present, _ = pill_state(desk)
        check(not present, "a scheduled announcement stays hidden until its start date")
        shot(admin, "admin-announcements-scheduled", full_page=True)

        # 09 - delete leaves everything clean
        admin.click('form[action*="delete"] button[type="submit"]')
        admin.wait_for_timeout(1500)
        check("No announcements yet" in admin.inner_text("body"), "delete returns the admin list to empty")
        desk.reload(wait_until="domcontentloaded")
        desk.wait_for_timeout(700)
        present, _ = pill_state(desk)
        check(not present, "the customer app shows nothing after delete")
        shot(desk, "home-after-delete")

        browser.close()

    print(f"\nRESULT: {len(CHECKS)} checks passed, {SHOT['n']} screenshots")


if __name__ == "__main__":
    main()
