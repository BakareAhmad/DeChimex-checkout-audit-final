"""E2E evidence for direct image uploads in the marketing campaign builder.

One clean run against a fresh in-memory app captures, in order:
  01 compose page with an empty image block (Upload image + HTTPS URL alternative)
  02 uploaded image: editor preview shown, HTTPS public URL filled into the block
  03 invalid file type rejected client-side before any upload
  04 oversized image rejected client-side before any upload
  05 replacing the image: new URL in place, previously stored file removed (404)
  06 saved draft details: generated email references the public HTTPS URL (no base64)
  07 reopened editor: stored HTTPS URL and preview restored for the image block
  08 image removed from the block and the regenerated email no longer carries it
  09 externally hosted HTTPS URL alternative still works end to end

Screenshots land in EVID (ordered, single run).
"""
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DCX_E2E_BASE", "http://127.0.0.1:5119")
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.environ.get("MKTIMG_EVID", os.path.join(HERE, "shots"))
MEDIA = os.path.abspath(os.path.join(HERE, "..", "gallery-mobile", "media"))
os.makedirs(EVID, exist_ok=True)

SHOT = {"n": 0}
CHECKS = []
DESKTOP = {"width": 1366, "height": 900}
OWNER = "owner@dechimexprinthub.com"


def shot(pg, desc, full_page=False):
    SHOT["n"] += 1
    pg.screenshot(path=os.path.join(EVID, f"{SHOT['n']:02d}-{desc}.png"), full_page=full_page)
    print(f"PASS {SHOT['n']:02d} {desc}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    CHECKS.append(msg)
    print(f"PASS    {msg}")


def open_login(pg):
    for attempt in range(3):
        pg.goto(BASE + "/Account/Login", wait_until="domcontentloaded")
        try:
            pg.wait_for_selector('form[action*="Login"] input[name="Email"]', timeout=60000)
            return
        except Exception:
            if attempt == 2:
                raise
            pg.wait_for_timeout(2000)


def owner_login(pg):
    open_login(pg)
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
            # The admin forced-change flow re-issues the auth cookie: the session
            # stays signed in, so there is NO re-login step here.
            break
        if "Login" not in pg.url:
            break
    pg.goto(BASE + "/admin/dashboard", wait_until="domcontentloaded")
    check("Login" not in pg.url, "owner signed in")


def wait_for_status(pg, needle, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = pg.eval_on_selector(".campaign-image-panel .campaign-status", "el => el.textContent") or ""
        if needle in text:
            return text
        time.sleep(0.3)
    raise AssertionError(f"status '{needle}' never appeared (last: {text!r})")


def preview_src(pg):
    return pg.eval_on_selector(
        ".campaign-image-panel .campaign-image-preview",
        "el => (el.style.display === 'none' || !el.getAttribute('src')) ? '' : el.src")


def email_preview_html(pg, needle, timeout=15):
    deadline = time.time() + timeout
    html = ""
    while time.time() < deadline:
        html = pg.get_attribute("#previewFrame", "srcdoc") or ""
        if needle in html:
            return html
        time.sleep(0.4)
    return html


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_context(viewport=DESKTOP).new_page()
        owner_login(pg)

        # ---------- 01 compose: empty image block offers upload + URL ----------
        pg.goto(BASE + "/admin/marketing/compose", wait_until="domcontentloaded")
        pg.wait_for_selector("#blocksEditor", timeout=15000)
        pg.click('button[data-add="image"]')
        pg.wait_for_selector(".campaign-image-panel", timeout=10000)
        # find the image block index (blocks may start with a template heading/paragraph/button)
        idx = pg.eval_on_selector(".campaign-image-panel", "el => el.closest('.campaign-block').dataset.index")
        check(pg.query_selector(f"#campaign-block-{idx}-image-file") is not None,
              "image block offers a direct Upload Image control")
        check(pg.query_selector(f"#campaign-block-{idx}-url") is not None,
              "image block keeps the HTTPS URL field as an alternative")
        pg.locator(".campaign-block", has=pg.locator(".campaign-image-panel")).scroll_into_view_if_needed()
        shot(pg, "compose-image-block-empty")

        file_input = f"#campaign-block-{idx}-image-file"
        url_input = f"#campaign-block-{idx}-url"

        # ---------- 03/04 client-side validation before any upload ----------
        pg.set_input_files(file_input, os.path.join(MEDIA, "bad.exe"))
        wait_for_status(pg, "Use a JPG, PNG, WEBP, or GIF image")
        shot(pg, "upload-rejected-bad-type")
        big = os.path.join(EVID, "_oversized.png")
        with open(big, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * (10 * 1024 * 1024 + 64))
        pg.set_input_files(file_input, big)
        wait_for_status(pg, "Images must be 10 MB or smaller")
        shot(pg, "upload-rejected-oversized")
        os.remove(big)

        # ---------- 02 real upload: preview + public HTTPS URL ----------
        pg.set_input_files(file_input, os.path.join(MEDIA, "shot-a.png"))
        wait_for_status(pg, "Image uploaded and linked by its HTTPS address")
        url1 = pg.input_value(url_input)
        src1 = preview_src(pg)
        check(url1.startswith("https://") and "/uploads/marketingmedia/" in url1,
              f"uploaded image URL is a public HTTPS address ({url1})")
        check(src1.startswith(BASE + "/uploads/marketingmedia/"),
              "editor shows the uploaded image preview immediately")
        stored1 = url1.split("/uploads/")[-1]
        check(pg.request.get(BASE + "/uploads/" + stored1).status == 200,
              "stored image is publicly served for email delivery")
        shot(pg, "upload-success-preview-and-url")

        # ---------- 05 replace: old stored file cleaned up ----------
        pg.set_input_files(file_input, os.path.join(MEDIA, "shot-b.png"))
        wait_for_status(pg, "Image uploaded and linked by its HTTPS address")
        url2 = pg.input_value(url_input)
        check(url2 != url1 and "/uploads/marketingmedia/" in url2, "replacing the image stores a new HTTPS URL")
        check(pg.request.get(BASE + "/uploads/" + stored1).status == 404,
              "the replaced image file is removed from storage")
        check(pg.request.get(BASE + "/uploads/" + url2.split("/uploads/")[-1]).status == 200,
              "the replacement image is publicly served")
        shot(pg, "upload-replaced-old-removed")

        # live email preview references the HTTPS URL, never base64
        pg.fill(f"#campaign-block-{idx}-alt", "Studio banner")
        html = email_preview_html(pg, url2)
        check(url2 in html, "live email preview references the uploaded HTTPS URL")
        check("base64" not in html and "data:image" not in html, "email preview embeds no base64/blob image data")

        # ---------- 06 save the draft ----------
        pg.fill('input[name="Name"]', f"Upload proof {int(time.time())}")
        pg.fill('input[name="Subject"]', "See the new banner")
        pg.click('#saveCampaignButton')
        pg.wait_for_url(re.compile(r"/admin/marketing/[0-9a-f-]{36}$"), timeout=20000)
        detail_url = pg.url
        rendered = pg.get_attribute('iframe[title="Rendered campaign email"]', "srcdoc") or ""
        check(url2 in rendered, "saved campaign email references the public HTTPS image URL")
        check("base64" not in rendered, "saved campaign email embeds no base64 image data")
        pg.locator('iframe[title="Rendered campaign email"]').scroll_into_view_if_needed()
        shot(pg, "draft-saved-email-uses-https-url", full_page=True)

        # ---------- 07 reopen the editor: URL + preview restored ----------
        pg.goto(detail_url.replace("/admin/marketing/", "/admin/marketing/") + "/edit",
                wait_until="domcontentloaded")
        pg.wait_for_selector(".campaign-image-panel", timeout=15000)
        check(preview_src(pg) != "", "reopened editor restores the image preview")
        check("/uploads/marketingmedia/" in (pg.input_value(url_input)),
              "reopened editor keeps the stored HTTPS URL in the block")
        shot(pg, "editor-restores-uploaded-image")

        # ---------- 09 external HTTPS URL alternative ----------
        pg.fill(url_input, "https://dechimexprinthub.com/img/logo.png")
        html = email_preview_html(pg, "https://dechimexprinthub.com/img/logo.png")
        check("https://dechimexprinthub.com/img/logo.png" in html,
              "externally hosted HTTPS images still work in the email")
        pg.fill(url_input, "http://insecure.example.com/x.png")
        deadline = time.time() + 12
        status = ""
        while time.time() < deadline:
            status = pg.eval_on_selector("#previewStatus", "el => el.textContent") or ""
            if "HTTPS" in status:
                break
            time.sleep(0.3)
        check("HTTPS" in status, "non-HTTPS addresses are still rejected by the email renderer")
        pg.fill(url_input, url2)
        pg.wait_for_timeout(1200)
        shot(pg, "external-https-url-alternative")

        # ---------- 08 remove the image ----------
        pg.click(".campaign-image-panel .campaign-image-row button.btn-ghost")
        wait_for_status(pg, "Image removed from this block")
        check(preview_src(pg) == "" and pg.input_value(url_input) == "",
              "removing clears the preview and the stored URL from the block")
        time.sleep(0.5)
        check(pg.request.get(BASE + "/uploads/" + url2.split("/uploads/")[-1]).status == 404,
              "the removed image file is deleted from storage")
        pg.click(f".campaign-block[data-index='{idx}'] .campaign-block-tools button[aria-label^='Remove block']")
        pg.click('#saveCampaignButton')
        pg.wait_for_url(re.compile(r"/admin/marketing/[0-9a-f-]{36}$"), timeout=20000)
        rendered = pg.get_attribute('iframe[title="Rendered campaign email"]', "srcdoc") or ""
        check("/uploads/marketingmedia/" not in rendered,
              "the regenerated email no longer carries the removed image")
        shot(pg, "image-removed-email-regenerated", full_page=True)

        browser.close()

    print(f"\nRESULT: {len(CHECKS)} checks passed, {SHOT['n']} screenshots")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}")
        print(f"\nRESULT: {len(CHECKS)} checks passed, 1 failed")
        sys.exit(1)
