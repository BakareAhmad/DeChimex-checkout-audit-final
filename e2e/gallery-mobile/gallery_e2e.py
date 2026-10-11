"""Final clean E2E for the mobile gallery fix (2026-10-06).

One run = the only evidence source. Covers:
  A. admin desktop: owner login, accept attr (video-capable, no capture), image post,
     video post, unsupported / oversized / mixed rejections.
  B. public desktop: grid visible, no h-overflow, video tile opens <video> viewer and plays.
  C. public mobile (iPhone 13): Gallery entry in the bottom nav, tap-through to /gallery,
     grid visible + active nav, video plays, tablet width, resize cycle desktop<->mobile.
  D. admin mobile: existing video picked from the file input shows the video preview card,
     uploads, lands in the admin index; mobile image upload still works.
  E. public mobile final: every post (desktop + mobile uploaded) visible; newest video plays.

Evidence screenshots land in $GALLERY_EVID (default: <repo>/evidence), ordered 01..NN.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5119"
HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(HERE, "media")
# huge.mp4 is a throwaway >10MB probe for the size-limit check - regenerate on demand
# instead of committing an 11MB binary (it blew the workspace snapshot budget once).
_HUGE = os.path.join(MEDIA, "huge.mp4")
if not os.path.exists(_HUGE):
    os.makedirs(MEDIA, exist_ok=True)
    with open(_HUGE, "wb") as _f:
        _f.seek(11 * 1024 * 1024 - 1)
        _f.write(b"\0")
EVID = os.environ.get("GALLERY_EVID", os.path.abspath(os.path.join(HERE, "..", "..", "evidence")))
os.makedirs(EVID, exist_ok=True)
# Optional TAG (argv[1] or $GALLERY_TAG) only labels the summary line; the run itself
# is identical either way, so the standalone harness and the provider-keys regression
# stage share one journey script.
TAG = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GALLERY_TAG", "gallery")

SHOT = {"n": 0}
CHECKS = []


def shot(pg, desc, full_page=False):
    SHOT["n"] += 1
    path = os.path.join(EVID, f"{SHOT['n']:02d}-{desc}.png")
    pg.screenshot(path=path, full_page=full_page)
    print(f"PASS {SHOT['n']:02d} {desc} -> {os.path.basename(path)}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    CHECKS.append(msg)
    print(f"PASS    {msg}")


def owner_login(pg):
    """Owner sign-in covering the seeded forced-password-change gate."""
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
    check("/admin" in pg.url, f"owner signed in (url={pg.url})")


def submit_gallery_form(pg):
    """Scoped submit: the admin layout's logout button precedes page forms in DOM order."""
    pg.click('form[method="post"][enctype="multipart/form-data"] button[type="submit"]')
    pg.wait_for_timeout(2500)


def grid_state(pg):
    grid = pg.query_selector("#grid")
    if grid is None:
        return {"present": False}
    items = pg.query_selector_all("#grid .gitem")
    return {
        "present": True,
        "visible": grid.is_visible(),
        "display": grid.evaluate("el => getComputedStyle(el).display"),
        "items": len(items),
        "items_visible": sum(1 for g in items if g.is_visible()),
        "video_tiles": len(pg.query_selector_all('#grid .gitem[data-type="Video"]')),
        "box": grid.bounding_box(),
        "h_overflow": pg.evaluate(
            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"),
    }


def play_modal_video(pg):
    """Opens nothing - assumes the viewer is open; returns video diagnostics after a play try."""
    pg.wait_for_selector("#dcxModal video", timeout=10000)
    pg.wait_for_timeout(600)
    info = pg.evaluate("""async () => {
        const v = document.querySelector('#dcxModal video');
        if (!v) return {found: false};
        v.muted = true;
        try { await v.play(); } catch (e) { return {found: true, error: String(e)}; }
        await new Promise(r => setTimeout(r, 1400));
        return {found: true, readyState: v.readyState, currentTime: v.currentTime,
                paused: v.paused, duration: v.duration, src: v.currentSrc.split('/').pop()};
    }""")
    return info


def create_post(pg, title, files, expect_ok=True):
    pg.goto(BASE + "/admin/gallery/create", wait_until="domcontentloaded")
    pg.wait_for_selector("#Title", timeout=15000)
    pg.fill("#Title", title)
    pg.set_input_files("#MediaFiles", files)
    pg.wait_for_timeout(700)
    submit_gallery_form(pg)
    if expect_ok:
        check(pg.url.rstrip("/").endswith("/admin/gallery"),
              f"'{title}' saved -> redirected to admin index ({pg.url})")
        check(pg.query_selector(f'[data-title="{title}"]') is not None,
              f"'{title}' tile listed in admin index")
    return pg.content()


def main():
    summary = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        iphone = p.devices["iPhone 13"]

        # ---------------- Phase A: admin, desktop ----------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        owner_login(pg)
        shot(pg, "admin-owner-signed-in")

        pg.goto(BASE + "/admin/gallery", wait_until="domcontentloaded")
        pg.wait_for_timeout(1000)
        shot(pg, "admin-gallery-index-start", full_page=True)

        pg.goto(BASE + "/admin/gallery/create", wait_until="domcontentloaded")
        pg.wait_for_selector("#MediaFiles", timeout=15000)
        accept = pg.get_attribute("#MediaFiles", "accept") or ""
        check(all(t in accept for t in (".jpg", ".png", ".mp4", ".webm", "video/mp4", "video/webm")),
              f"media input accept offers images AND videos to mobile pickers ({accept})")
        check("capture" not in (pg.content()), "no capture attribute anywhere - phone library stays selectable")
        shot(pg, "admin-create-form-video-capable", full_page=True)

        create_post(pg, "Sunrise mugs", [f"{MEDIA}/shot-a.png", f"{MEDIA}/shot-b.png"])
        shot(pg, "admin-desktop-image-post-saved", full_page=True)

        create_post(pg, "Studio reel", [f"{MEDIA}/clip.mp4"])
        shot(pg, "admin-desktop-video-post-saved", full_page=True)

        body = create_post(pg, "Bad type", [f"{MEDIA}/bad.exe"], expect_ok=False)
        check("not allowed" in body, "unsupported extension rejected server-side")
        shot(pg, "admin-rejected-unsupported-type", full_page=True)

        body = create_post(pg, "Too big", [f"{MEDIA}/huge.mp4"], expect_ok=False)
        check("File size must be between" in body, "oversized video rejected server-side")
        shot(pg, "admin-rejected-oversized-video", full_page=True)

        # Mixed pick: the form normalizes client-side (the strip previews exactly what will be
        # submitted - images only). Server-side mixed rejection for no-JS/legacy clients is
        # covered by GalleryMobileSurfaceTests. Nothing is submitted here, so the post count
        # stays clean for the public phases.
        pg.goto(BASE + "/admin/gallery/create", wait_until="domcontentloaded")
        pg.wait_for_selector("#MediaFiles", timeout=15000)
        pg.set_input_files("#MediaFiles", [f"{MEDIA}/shot-a.png", f"{MEDIA}/clip.mp4"])
        pg.wait_for_timeout(800)
        cards = pg.query_selector_all("#strip .gcard")
        check(len(cards) == 1 and pg.query_selector("#strip .gcard .gcard-vid") is None,
              "mixed image+video pick is normalized: only the image stays in the submit preview")
        shot(pg, "admin-mixed-selection-normalized", full_page=True)
        ctx.close()

        # ---------------- Phase B: public, desktop ----------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.goto(BASE + "/gallery", wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        g = grid_state(pg)
        summary["public_desktop"] = g
        check(g["present"] and g["visible"] and g["items_visible"] == 2 and not g["h_overflow"],
              f"desktop /gallery grid visible, 2/2 items, no h-overflow ({json.dumps(g)})")
        shot(pg, "public-gallery-desktop")

        pg.click('#grid .gitem[data-type="Video"]')
        v = play_modal_video(pg)
        summary["desktop_video"] = v
        check(v.get("found") and v.get("currentTime", 0) > 0 and not v.get("paused", True),
              f"desktop viewer plays the uploaded video ({json.dumps(v)})")
        shot(pg, "public-desktop-video-viewer-playing")
        ctx.close()

        # ---------------- Phase C: public, mobile (iPhone 13) ----------------
        ctx = browser.new_context(**iphone)
        pg = ctx.new_page()
        pg.goto(BASE + "/", wait_until="domcontentloaded")
        pg.wait_for_timeout(1200)
        nav = pg.query_selector('nav.cs-bottom a[href="/gallery"]')
        check(nav is not None and nav.is_visible(), "Gallery entry visible in the mobile bottom nav")
        check(not pg.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth"),
              "home has no horizontal overflow on mobile")
        shot(pg, "mobile-home-bottom-nav-gallery")

        nav.tap()
        pg.wait_for_url("**/gallery", timeout=15000)
        pg.wait_for_timeout(1500)
        g = grid_state(pg)
        summary["public_mobile"] = g
        check(g["present"] and g["visible"] and g["items_visible"] == 2 and g["video_tiles"] == 1
              and not g["h_overflow"],
              f"mobile /gallery (via bottom nav tap) grid visible, 2/2 items, video tile present ({json.dumps(g)})")
        active = pg.query_selector('nav.cs-bottom a[href="/gallery"].is-active')
        check(active is not None, "bottom nav marks Gallery active on the gallery page")
        shot(pg, "mobile-gallery-via-bottom-nav")

        pg.tap('#grid .gitem[data-type="Video"]')
        v = play_modal_video(pg)
        summary["mobile_video"] = v
        check(v.get("found") and v.get("currentTime", 0) > 0 and not v.get("paused", True),
              f"mobile viewer plays the uploaded video ({json.dumps(v)})")
        shot(pg, "mobile-video-viewer-playing")
        pg.goto(BASE + "/gallery", wait_until="domcontentloaded")
        ctx.close()

        ctx = browser.new_context(viewport={"width": 768, "height": 1024})
        pg = ctx.new_page()
        pg.goto(BASE + "/gallery", wait_until="domcontentloaded")
        pg.wait_for_timeout(1200)
        g = grid_state(pg)
        summary["public_tablet"] = g
        check(g["visible"] and g["items_visible"] == 2 and not g["h_overflow"],
              f"tablet /gallery grid visible ({json.dumps(g)})")
        shot(pg, "public-gallery-tablet-768")
        ctx.close()

        # resize cycle: desktop -> mobile -> desktop, grid must survive every change
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.goto(BASE + "/gallery", wait_until="domcontentloaded")
        pg.wait_for_timeout(1000)
        cycle = {}
        for label, size in [("wide", {"width": 1440, "height": 900}),
                            ("narrow", {"width": 390, "height": 844}),
                            ("wide-again", {"width": 1440, "height": 900})]:
            pg.set_viewport_size(size)
            pg.wait_for_timeout(900)
            g = grid_state(pg)
            cycle[label] = {"visible": g["visible"], "items_visible": g["items_visible"],
                            "h_overflow": g["h_overflow"]}
            check(g["visible"] and g["items_visible"] == 2 and not g["h_overflow"],
                  f"grid survives resize to {label} ({json.dumps(cycle[label])})")
        summary["resize_cycle"] = cycle
        shot(pg, "public-gallery-after-resize-cycle")
        ctx.close()

        # ---------------- Phase D: admin, mobile (iPhone 13) ----------------
        ctx = browser.new_context(**iphone)
        pg = ctx.new_page()
        owner_login(pg)
        pg.goto(BASE + "/admin/gallery/create", wait_until="domcontentloaded")
        pg.wait_for_selector("#MediaFiles", timeout=20000)
        pg.locator("#MediaFiles").scroll_into_view_if_needed()
        shot(pg, "admin-mobile-create-form", full_page=True)

        pg.fill("#Title", "Mobile reel")
        pg.set_input_files("#MediaFiles", [f"{MEDIA}/clip.mp4"])   # existing video from the phone library
        pg.wait_for_selector(".gcard .gcard-vid", timeout=8000)
        check(pg.is_visible(".gcard .gcard-vid"),
              "picked video shows the dark video preview card before submit")
        shot(pg, "admin-mobile-video-picked-preview", full_page=True)

        submit_gallery_form(pg)
        check(pg.url.rstrip("/").endswith("/admin/gallery"), f"mobile video upload saved ({pg.url})")
        check(pg.query_selector('[data-title="Mobile reel"]') is not None,
              "mobile-uploaded video listed in admin index")
        shot(pg, "admin-mobile-video-post-saved", full_page=True)

        create_post(pg, "Mobile print", [f"{MEDIA}/shot-b.png"])
        shot(pg, "admin-mobile-image-post-saved", full_page=True)
        ctx.close()

        # ---------------- Phase E: public, mobile, final state ----------------
        ctx = browser.new_context(**iphone)
        pg = ctx.new_page()
        pg.goto(BASE + "/gallery", wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        g = grid_state(pg)
        summary["public_mobile_final"] = g
        check(g["visible"] and g["items_visible"] == 4 and g["video_tiles"] == 2 and not g["h_overflow"],
              f"mobile /gallery shows all 4 posts incl. 2 videos, no h-overflow ({json.dumps(g)})")
        shot(pg, "public-mobile-all-posts")

        pg.tap('.gitem[data-title="Mobile reel"]')
        v = play_modal_video(pg)
        summary["mobile_uploaded_video"] = v
        check(v.get("found") and v.get("currentTime", 0) > 0 and not v.get("paused", True),
              f"video uploaded FROM mobile plays on the public mobile page ({json.dumps(v)})")
        shot(pg, "public-mobile-uploaded-video-playing")
        ctx.close()

        browser.close()

    summary["checks"] = len(CHECKS)
    summary["screenshots"] = SHOT["n"]
    with open(os.path.join(EVID, "journey-summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("GALLERY E2E DONE:", json.dumps(summary))
    print(f"\nRESULT: {len(CHECKS)} passed, 0 failed (TAG={TAG}), {SHOT['n']} screenshots")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}")
        print(f"\nRESULT: {len(CHECKS)} passed, 1 failed (TAG={TAG})")
        sys.exit(1)
