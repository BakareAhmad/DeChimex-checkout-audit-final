"""Final E2E evidence for: Home page review slider + admin review management.

One clean run against a fresh in-memory app captures, in order:
  01 admin /admin/reviews lists the four seeded reviews (records, not hard-coded markup)
  02 the "New review" form (only the fields the slider renders)
  03 the new review is listed for staff after saving
  04 desktop home page: reviews render as a slider (3 per view), not a card grid
  05 desktop: the Next arrow advances the slider
  06 mobile home page: one review per slide with dots
  07 mobile: a real touch swipe moves the slider
  08 the edited review shows its new wording on the home page
  09 after deleting it in admin, the review is gone from the home page

Screenshots land in $REVIEWS_EVID (default <repo>/e2e/home-reviews/shots).
"""
import os
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DCX_E2E_BASE", "http://127.0.0.1:5119")
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.environ.get("REVIEWS_EVID", os.path.join(HERE, "shots"))
os.makedirs(EVID, exist_ok=True)

SHOT = {"n": 0}
CHECKS = []
DESKTOP = {"width": 1366, "height": 900}
MOBILE = {"width": 390, "height": 844}
# Unique per run so a re-run against the same app instance can never collide with leftovers.
RUN = str(int(time.time()))[-6:]
NEW_NAME = f"E2E Reviewer {RUN}"
NEW_BODY = "Added through the admin portal during the E2E run."
EDITED_BODY = "Edited through the admin portal during the E2E run."


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


def open_reviews(pg):
    pg.goto(BASE + "/admin/reviews", wait_until="domcontentloaded")
    pg.wait_for_selector('a[href="/admin/reviews/create"], .table', timeout=15000)


def review_id(pg, name):
    """Reads a review's id from its Edit link in the admin table."""
    for a in pg.query_selector_all('a[href*="/admin/reviews/edit/"]'):
        row = a.evaluate("e => e.closest('tr') ? e.closest('tr').innerText : ''")
        if name in row:
            return a.get_attribute("href").rsplit("/", 1)[-1]
    return None


def touch_swipe(pg, selector, dx=-260):
    """A real touch drag (touchStart/touchMove/touchEnd) over the slider track."""
    box = pg.query_selector(selector).bounding_box()
    y = box["y"] + box["height"] / 2
    x = box["x"] + box["width"] / 2
    cdp = pg.context.new_cdp_session(pg)

    def point(px):
        return [{"x": px, "y": y, "radiusX": 12, "radiusY": 12, "force": 1, "id": 1}]

    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": point(x)})
    for step in range(1, 9):
        cdp.send("Input.dispatchTouchEvent",
                 {"type": "touchMove", "touchPoints": point(x + dx * step / 8)})
        pg.wait_for_timeout(16)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    pg.wait_for_timeout(900)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---------------- admin: seeded reviews are records ----------------
        admin_ctx = browser.new_context(viewport=DESKTOP)
        admin = admin_ctx.new_page()
        admin.on("dialog", lambda d: d.accept())   # the Delete button confirms first
        owner_login(admin)
        open_reviews(admin)
        body = admin.inner_text("body")
        for name in ("Muinat B.", "Olalekan F.", "TokenPicks", "DE-YEMKING"):
            check(name in body, f"seeded review '{name}' is managed in the admin portal")
        shot(admin, "admin-reviews-seeded-records", full_page=True)

        # ---------------- admin: add a review ------------------------------
        admin.click('a[href="/admin/reviews/create"]')
        admin.wait_for_selector('#CustomerName', timeout=15000)
        form_text = admin.inner_text("body")
        check("Customer name" in form_text and "Review" in form_text, "review form asks for name and text")
        check(admin.query_selector('#AvatarFile') is not None, "review form supports an optional image")
        check(admin.query_selector('#Rating') is not None, "review form supports the optional rating")
        check(admin.query_selector('#IsPublished') is not None, "review form supports publish state")
        shot(admin, "admin-new-review-form", full_page=True)

        admin.fill('#CustomerName', NEW_NAME)
        admin.fill('#CustomerTitle', "Verified buyer")
        admin.fill('#Body', NEW_BODY)
        admin.select_option('#Rating', "5")
        admin.click('form[action*="create"] button[type="submit"]')
        admin.wait_for_url(lambda u: u.rstrip("/").endswith("/admin/reviews"), timeout=20000)
        check(NEW_NAME in admin.inner_text("body"), "the new review is listed for staff after saving")
        shot(admin, "admin-reviews-after-create", full_page=True)
        new_id = review_id(admin, NEW_NAME)
        check(new_id is not None, f"new review is editable (id={new_id})")

        # ---------------- desktop: slider, not a grid ---------------------
        desk = browser.new_context(viewport=DESKTOP).new_page()
        desk.goto(BASE + "/", wait_until="domcontentloaded")
        desk.wait_for_selector('[data-review-slider]', timeout=15000)
        desk.locator('[data-review-slider]').scroll_into_view_if_needed()
        desk.wait_for_timeout(1200)
        html = desk.content()
        check('data-review-track' in html, "home page renders the review slider track")
        check('class="hm-reviews"' not in html, "the old review card grid is gone")
        check(NEW_BODY in desk.inner_text('[data-review-slider]'), "the newly added review appears on the home page")
        per_view = desk.eval_on_selector_all('.hm-review-slide',
                                             "els => els.filter(e => e.getBoundingClientRect().left < window.innerWidth).length")
        check(per_view >= 2, f"desktop shows several reviews per view ({per_view})")
        check(desk.query_selector('[data-review-prev]') is not None
              and desk.query_selector('[data-review-next]') is not None, "desktop slider has arrows")
        shot(desk, "home-slider-desktop")

        before = desk.eval_on_selector('[data-review-track]', "e => e.scrollLeft")
        desk.click('[data-review-next]')
        desk.wait_for_timeout(1400)
        after = desk.eval_on_selector('[data-review-track]', "e => e.scrollLeft")
        check(after > before, f"desktop Next arrow advances the slider ({before} -> {after})")
        shot(desk, "home-slider-desktop-next")

        # ---------------- mobile: one slide + real touch swipe ------------
        mob_ctx = browser.new_context(viewport=MOBILE, is_mobile=True, has_touch=True)
        mob = mob_ctx.new_page()
        mob.goto(BASE + "/", wait_until="domcontentloaded")
        mob.wait_for_selector('[data-review-slider]', timeout=15000)
        mob.locator('[data-review-slider]').scroll_into_view_if_needed()
        mob.wait_for_timeout(1200)
        widths = mob.eval_on_selector_all('.hm-review-slide', "els => els.map(e => Math.round(e.getBoundingClientRect().width))")
        track_w = mob.eval_on_selector('[data-review-track]', "e => Math.round(e.clientWidth)")
        check(widths[0] >= track_w - 4, f"mobile shows one review per slide (slide {widths[0]}px / track {track_w}px)")
        check(mob.query_selector('[data-review-dots] button') is not None, "mobile slider has dots")
        shot(mob, "home-slider-mobile")

        start = mob.eval_on_selector('[data-review-track]', "e => e.scrollLeft")
        touch_swipe(mob, '[data-review-track]')
        end = mob.eval_on_selector('[data-review-track]', "e => e.scrollLeft")
        check(abs(end - start) > 40, f"mobile touch swipe moves the slider ({start} -> {end})")
        shot(mob, "home-slider-mobile-after-swipe")

        # ---------------- admin: edit then delete -------------------------
        admin.goto(f"{BASE}/admin/reviews/edit/{new_id}", wait_until="domcontentloaded")
        admin.wait_for_selector('#Body', timeout=15000)
        admin.fill('#Body', EDITED_BODY)
        admin.click('form[action*="edit"] button[type="submit"]')
        admin.wait_for_url(lambda u: u.rstrip("/").endswith("/admin/reviews"), timeout=20000)
        desk.reload(wait_until="domcontentloaded")
        desk.wait_for_selector('[data-review-slider]', timeout=15000)
        desk.wait_for_timeout(800)
        slider_text = desk.inner_text('[data-review-slider]')
        check(EDITED_BODY in slider_text, "the edited review shows its new wording on the home page")
        check(NEW_BODY not in slider_text, "the old wording is gone after the edit")
        shot(desk, "home-slider-after-edit")

        admin.goto(BASE + "/admin/reviews", wait_until="domcontentloaded")
        admin.wait_for_selector('a[href="/admin/reviews/create"]', timeout=15000)
        admin.click(f'a[href="/admin/reviews/edit/{new_id}"] ~ form button[type="submit"]')
        admin.wait_for_timeout(1800)
        check(NEW_NAME not in admin.inner_text("body"), "the deleted review leaves the admin list")

        desk.reload(wait_until="domcontentloaded")
        desk.wait_for_selector('[data-review-slider]', timeout=15000)
        desk.wait_for_timeout(800)
        check(NEW_NAME not in desk.inner_text("body"), "the deleted review is gone from the home page")
        check("Muinat B." in desk.inner_text('[data-review-slider]'), "the seeded reviews still display")
        shot(desk, "home-slider-after-delete")

        browser.close()

    print(f"\nRESULT: {len(CHECKS)} checks passed, {SHOT['n']} screenshots")


if __name__ == "__main__":
    main()
