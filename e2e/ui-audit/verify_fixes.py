#!/usr/bin/env python3
"""Post-approval verification of UI audit fixes I-01,I-02,S-01,M-01,S-02,S-03,S-04.
Seeds demo data through the real UI (or reuses a live seeded app with NOSEED=1),
then measures each fixed spot and stores after-shots in shots-after/."""
import json, os, re, time, html as _html
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5121"
SHOTS = "/home/user/DeChimex-GalleryMobile/e2e/ui-audit/shots-after"
OWNER_EMAIL, OWNER_BOOT, OWNER_NEW = "owner@dechimexprinthub.com", "ChangeMe123!", "OwnerUi!2026zQ"
CUST_EMAIL, CUST_PW = "ui.customer@dechimex.test", "Customer!2026xY"
CAPTURE = "/tmp/brevo_nav_audit.jsonl"
SEED = not os.environ.get("NOSEED")

results = []
def check(ok, label):
    results.append((bool(ok), label))
    print(("PASS " if ok else "FAIL ") + label)

def do_login(page, email, pw):
    page.goto(BASE + "/Account/Login")
    page.wait_for_selector("input[name=Email]", timeout=20000)
    page.fill("input[name=Email]", email)
    page.fill("input[name=Password]", pw)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")

def login(page, email, pw, new_pw=None):
    do_login(page, email, pw)
    if "/admin/security/password" in page.url and new_pw:
        page.fill("input[name=CurrentPassword]", pw)
        page.fill("input[name=NewPassword]", new_pw)
        page.fill("input[name=ConfirmPassword]", new_pw)
        f = page.locator("form").filter(has=page.locator("input[name=NewPassword]"))
        f.locator("button[type=submit]").click()
        page.wait_for_load_state("networkidle")
    if "/Account/Login" in page.url:
        do_login(page, email, new_pw or pw)

def shot(page, name, clip=None):
    os.makedirs(SHOTS, exist_ok=True)
    page.screenshot(path=os.path.join(SHOTS, name), clip=clip)
    print("SHOT after/" + name)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)

    # ---------------- admin ----------------
    ctx = b.new_context(viewport={"width": 1360, "height": 900}); pg = ctx.new_page()
    if SEED:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (640, 480), (52, 88, 200))
        d = ImageDraw.Draw(img); d.rectangle([40, 40, 600, 440], outline=(255, 255, 255), width=8)
        img.save("/tmp/ui-tee.png")
        login(pg, OWNER_EMAIL, OWNER_BOOT, OWNER_NEW)
        pg.goto(BASE + "/admin/categories/create"); pg.wait_for_load_state("networkidle")
        pg.fill("input[name=Name]", "Apparel")
        pg.locator("form").filter(has=pg.locator("input[name=Name]")).locator("button[type=submit]").click()
        pg.wait_for_load_state("networkidle")
        pg.goto(BASE + "/admin/products/create"); pg.wait_for_load_state("networkidle")
        pg.fill("input[name=Name]", "Verify Tee")
        opts = pg.eval_on_selector_all("select[name=CategoryId] option", "els => els.map(e => e.value).filter(v => v)")
        pg.select_option("select[name=CategoryId]", opts[0])
        pg.fill("input[name=SellingPrice]", "5000")
        if pg.locator("input[name=InitialQuantity]").count():
            pg.fill("input[name=InitialQuantity]", "10")
        pg.set_input_files("input[name=Images]", "/tmp/ui-tee.png")
        pg.locator("form[data-guard] button[type=submit]").click()
        pg.wait_for_load_state("networkidle")
        assert "/admin/products" in pg.url
    else:
        do_login(pg, OWNER_EMAIL, OWNER_NEW)
    assert "/admin" in pg.url, "owner login failed"

    # I-02: sidebar Products icon path corrected (uppercase A arc)
    arc = pg.evaluate("""() => {
      const prod = [...document.querySelectorAll('.side-link')].find(a => a.textContent.includes('Products'));
      const path = prod && prod.querySelector('svg path');
      return path ? path.getAttribute('d') : null;
    }""")
    check(arc is not None and "l7 4A2 2 0 0 1 21 8z" in arc, "I-02 sidebar Products icon path corrected")
    box = pg.locator("#appSidebar").bounding_box()
    shot(pg, "01-sidebar-after.png", clip=box)

    # M-01: Reports quick action has an icon
    pg.goto(BASE + "/admin/dashboard"); pg.wait_for_load_state("networkidle")
    rep = pg.evaluate("""() => {
      const a = [...document.querySelectorAll('a.btn')].find(x => x.textContent.trim().includes('Reports'));
      return a ? {hasIcon: !!a.querySelector('svg'), w: a.querySelector('svg') && a.querySelector('svg').getAttribute('width')} : null;
    }""")
    check(rep and rep["hasIcon"] and rep["w"] == "15", "M-01 Reports quick action carries 15px icon")
    qa = pg.locator("a.btn", has_text="Reports").first.bounding_box()
    shot(pg, "02-dashboard-quickactions-after.png", clip={"x": qa["x"] - 420, "y": qa["y"] - 14, "width": 760, "height": qa["height"] + 28})

    # S-04: settings social preview icons equal (15/15)
    pg.goto(BASE + "/admin/settings"); pg.wait_for_load_state("networkidle")
    sizes = pg.evaluate("""() => {
      const btns = [...document.querySelectorAll('.btn')].filter(x => /Instagram|TikTok/.test(x.textContent));
      return btns.map(x => x.querySelector('svg') && x.querySelector('svg').getAttribute('width'));
    }""")
    check(len(sizes) == 2 and sizes[0] == sizes[1] == "15", "S-04 settings preview social icons equal at 15 (%s)" % sizes)
    ctx.close()

    # ---------------- customer ----------------
    ctx = b.new_context(viewport={"width": 1360, "height": 900}); pg = ctx.new_page()
    if SEED:
        pg.goto(BASE + "/Account/Register")
        pg.wait_for_selector("input[name=Email]")
        pg.fill("input[name=Email]", CUST_EMAIL); pg.fill("input[name=Password]", CUST_PW)
        pg.click("button[type=submit]"); pg.wait_for_load_state("networkidle")
        link = None
        for _ in range(30):
            try:
                for line in open(CAPTURE):
                    rec = json.loads(line)
                    if "ui.customer" not in json.dumps(rec): continue
                    m = re.search(r"(https?://[^'\"\s<>]+/Account/VerifyEmail[^'\"\s<>]+)", json.dumps(rec))
                    if m: link = m.group(1)
            except FileNotFoundError: pass
            if link: break
            time.sleep(1)
        assert link, "no verification email"
        link = _html.unescape(link); u = urlparse(link)
        pg.goto(BASE + u.path + (("?" + u.query) if u.query else "")); pg.wait_for_load_state("networkidle")
        assert "invalid verification token" not in pg.inner_text("body").lower()
    else:
        do_login(pg, CUST_EMAIL, CUST_PW)
    assert "/Account/Login" not in pg.url and "/Account/VerifyEmail" not in pg.url, "customer login failed"

    pg.goto(BASE + "/products"); pg.wait_for_load_state("networkidle")
    href = pg.get_attribute("a[href^='/products/']", "href")
    pg.goto(BASE + href); pg.wait_for_load_state("networkidle")

    # S-02: product action row heart now 18 (measured before any cart navigation)
    hearts = pg.evaluate("""() => [...document.querySelectorAll('.pd-wish svg')].map(s => s.getAttribute('width'))""")
    check(hearts == ["18"], "S-02 wishlist heart normalized to 18 (%s)" % hearts)
    row = pg.locator(".pd-wish").first.bounding_box()
    shot(pg, "03-product-actions-after.png", clip={"x": row["x"] - 10, "y": row["y"] - 12, "width": 560, "height": row["height"] + 24})

    btn = pg.locator("button", has_text="Add to cart")
    if btn.count(): btn.first.click(); pg.wait_for_load_state("networkidle")

    # S-03: hero arrows 18
    pg.goto(BASE + "/"); pg.wait_for_load_state("networkidle")
    arrows = pg.evaluate("""() => [...document.querySelectorAll('a.btn.btn-lg svg')].map(s => s.getAttribute('width'))""")
    check(len(arrows) >= 2 and all(w == "18" for w in arrows), "S-03 hero btn-lg arrows at 18 (%s)" % arrows)

    # I-01: cart continue-shopping icon inline
    pg.goto(BASE + "/cart"); pg.wait_for_load_state("networkidle")
    geo = pg.evaluate("""() => {
      const a = document.querySelector('a.cs-link[data-smart-back]');
      if (!a) return null;
      const cs = getComputedStyle(a);
      const svg = a.querySelector('svg');
      const r = document.createRange();
      const tn = [...a.childNodes].find(n => n.nodeType === 3 && n.textContent.trim());
      r.selectNodeContents(tn);
      const tb = r.getBoundingClientRect(), sb = svg.getBoundingClientRect();
      const dy = (sb.top + sb.height/2) - (tb.top + tb.height/2);
      return {display: cs.display, dy: Math.round(dy*10)/10};
    }""")
    check(geo and geo["display"] in ("inline-flex", "flex") and abs(geo["dy"]) <= 1.5, "I-01 continue-shopping inline (display=%s dy=%s)" % (geo and geo["display"], geo and geo["dy"]))
    cl = pg.locator("a.cs-link[data-smart-back]").bounding_box()
    shot(pg, "04-cart-continue-after.png", clip={"x": cl["x"] - 10, "y": cl["y"] - 10, "width": 320, "height": cl["height"] + 20})
    ctx.close()

    # ---------------- contact (anonymous) ----------------
    ctx = b.new_context(viewport={"width": 1360, "height": 900}); pg = ctx.new_page()
    pg.goto(BASE + "/contact"); pg.wait_for_load_state("networkidle")
    offs = pg.evaluate("""() => [...document.querySelectorAll('.pg-reach a')].map(a => {
      const s = a.querySelector('svg').getBoundingClientRect(), c = a.getBoundingClientRect();
      return Math.round(((s.top + s.height/2) - (c.top + c.height/2)) * 10) / 10;
    })""")
    check(len(offs) >= 4 and all(abs(o) <= 2 for o in offs), "S-01 contact card icons centered (offsets %s)" % offs)
    head = pg.locator("#reachHeading").bounding_box()
    shot(pg, "05-contact-cards-after.png", clip={"x": head["x"] - 10, "y": head["y"] - 10, "width": 430, "height": 660})
    ctx.close()

    print("\nRESULT: %d passed, %d failed" % (sum(1 for ok, _ in results if ok), sum(1 for ok, _ in results if not ok)))
    b.close()
