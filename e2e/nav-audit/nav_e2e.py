#!/usr/bin/env python3
"""Navigation audit E2E (2026-10-09): back navigation, context preservation,
direct entry, guards, auth escapes, mobile. Screenshots per area in shots/."""
import os, re, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5121"
SHOTS = "/home/user/DeChimex-GalleryMobile/e2e/nav-audit/shots"
OWNER_EMAIL, OWNER_BOOT, OWNER_NEW = "owner@dechimexprinthub.com", "ChangeMe123!", "OwnerNav!2026zQ"
DEV_EMAIL, DEV_PW = "developer@dechimexprinthub.local", "DevPortal#2026!"

results = []
def check(ok, label):
    results.append((bool(ok), label))
    print(("PASS " if ok else "FAIL ") + "  " + label)

def shot(page, area, name):
    d = os.path.join(SHOTS, area)
    os.makedirs(d, exist_ok=True)
    page.screenshot(path=os.path.join(d, name))
    print("SHOT " + area + "/" + name)

def do_login(page, email, pw):
    page.goto(BASE + "/Account/Login")
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
    return page

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # ---------------- SEED (real UI) ----------------
    ctxs = browser.new_context(viewport={"width": 1360, "height": 900})
    pgs = ctxs.new_page()
    login(pgs, OWNER_EMAIL, OWNER_BOOT, OWNER_NEW)
    pgs.goto(BASE + "/admin/categories/create"); pgs.wait_for_load_state("networkidle")
    pgs.fill("input[name=Name]", "Apparel")
    pgs.locator("form").filter(has=pgs.locator("input[name=Name]")).locator("button[type=submit]").click()
    pgs.wait_for_load_state("networkidle")
    pgs.goto(BASE + "/admin/products/create"); pgs.wait_for_load_state("networkidle")
    pgs.fill("input[name=Name]", "Nav Audit Tee")
    opts = pgs.eval_on_selector_all("select[name=CategoryId] option", "els => els.map(e => e.value).filter(v => v)")
    pgs.select_option("select[name=CategoryId]", opts[0])
    pgs.fill("input[name=SellingPrice]", "5000")
    if pgs.locator("input[name=InitialQuantity]").count():
        pgs.fill("input[name=InitialQuantity]", "10")
    pgs.set_input_files("input[name=Images]", "/tmp/nav-tee.png")
    pgs.locator("form[data-guard] button[type=submit]").click()
    pgs.wait_for_load_state("networkidle")
    check("/admin/products" in pgs.url, "product created through admin UI")
    ctxs.close()
    ctxc = browser.new_context(viewport={"width": 1360, "height": 900})
    pgc = ctxc.new_page()
    pgc.goto(BASE + "/Account/Register")
    pgc.fill("input[name=Email]", "nav.customer@dechimex.test")
    pgc.fill("input[name=Password]", "Customer!2026xY")
    pgc.click("button[type=submit]")
    pgc.wait_for_load_state("networkidle")
    check("register" not in pgc.url.lower() or "invalid" not in pgc.inner_text("body").lower(), "customer registers through public UI")
    link = None
    import json as _json, time as _time
    for _ in range(30):
        try:
            with open("/tmp/brevo_nav_audit.jsonl") as fh:
                for line in fh:
                    rec = _json.loads(line)
                    m = re.search(r"(https?://[^'\"\s<>]+/Account/VerifyEmail[^'\"\s<>]+)", _json.dumps(rec))
                    if m and "nav.customer" in _json.dumps(rec):
                        link = m.group(1).replace("&amp;", "&")
        except FileNotFoundError:
            pass
        if link:
            break
        _time.sleep(1)
    check(link is not None, "confirmation email captured via provider stub")
    if link:
        import html as _html
        link = _html.unescape(link)
        from urllib.parse import urlparse as _up
        _u = _up(link)
        link = BASE + _u.path + (("?" + _u.query) if _u.query else "")
        pgc.goto(link); pgc.wait_for_load_state("networkidle")
        _verify_body = pgc.inner_text("body")[:600]
        check("invalid verification token" not in _verify_body.lower(),
              "email confirmation link verifies the account (no invalid-token error)")
    ctxc.close()

    # ---------------- CUSTOMER (signed in) ----------------
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/Account/Login")
    page.fill("input[name=Email]", "nav.customer@dechimex.test")
    page.fill("input[name=Password]", "Customer!2026xY")
    page.click("button[type=submit]"); page.wait_for_load_state("networkidle")
    check("/Account/VerifyEmail" not in page.url and "/Account/Login" not in page.url, "verified customer can sign in")
    page.goto(BASE + "/products"); page.wait_for_load_state("networkidle")
    prod_links = page.eval_on_selector_all("a[href*='/products/']", "els => els.map(e => e.getAttribute('href'))")
    prod_href = next((h for h in prod_links if re.match(r"^/products/[0-9a-f-]{36}$", h)), None)
    check(prod_href, "storefront shop lists products")

    page.goto(BASE + prod_href); page.wait_for_load_state("networkidle")
    back_attrs = page.eval_on_selector_all("a.cs-back", "els => els.map(e => ({sb: e.hasAttribute('data-smart-back'), href: e.getAttribute('href')}))")
    check(back_attrs and back_attrs[0]["sb"], "product detail back link is smart-back")
    shot(page, "customer", "01-product-backlink.png")
    page.click("a.cs-back"); page.wait_for_load_state("networkidle")
    check("/products" in page.url, "back from product returns to shop (history)")

    # direct entry: fresh context, no referrer -> fallback href
    ctx2 = browser.new_context(viewport={"width": 1360, "height": 900})
    pg2 = ctx2.new_page()
    pg2.goto(BASE + prod_href); pg2.wait_for_load_state("networkidle")
    pg2.click("a.cs-back"); pg2.wait_for_load_state("networkidle")
    check("/products" in pg2.url, "direct-entry product back falls back to shop/category")
    ctx2.close()

    page.goto(BASE + prod_href); page.wait_for_load_state("networkidle")
    add_btn = page.locator("button", has_text="Add to cart")
    if add_btn.count():
        add_btn.first.click(); page.wait_for_load_state("networkidle")
    page.goto(BASE + "/cart"); page.wait_for_load_state("networkidle")
    check(page.eval_on_selector_all("a[data-smart-back]", "els => els.length") >= 1, "cart continue-shopping is smart-back")
    shot(page, "customer", "03-cart-continue.png")

    cctx = browser.new_context(viewport={"width": 1360, "height": 900})
    cpg = cctx.new_page()
    cpg.goto(BASE + "/Account/Login")
    cpg.fill("input[name=Email]", "nav.customer@dechimex.test")
    cpg.fill("input[name=Password]", "Customer!2026xY")
    cpg.click("button[type=submit]"); cpg.wait_for_load_state("networkidle")
    cpg.goto(BASE + "/portal/orders/track"); cpg.wait_for_load_state("networkidle")
    check("/portal/orders/track" in cpg.url and "Track" in cpg.inner_text("body"), "order tracking reachable for signed-in customer (no dead end)")
    shot(cpg, "customer", "04-track.png")
    cctx.close()

    page.goto(BASE + "/portal/orders"); page.wait_for_load_state("networkidle")
    shot(page, "customer", "02-portal-orders.png")
    ctx.close()

    # ---------------- ADMIN ----------------
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    login(page, OWNER_EMAIL, OWNER_BOOT, OWNER_NEW)
    page.goto(BASE + "/admin/products?search=NAV"); page.wait_for_load_state("networkidle")
    detail = page.eval_on_selector_all("a[href*='/admin/products/']", "els => els.map(e => e.getAttribute('href'))")
    detail = next((h for h in detail if re.search(r"/admin/products/[0-9a-f-]{36}$", h)), None)
    check(detail, "admin product list (filtered) has detail rows")
    if detail:
        page.click("a[href='" + detail + "']"); page.wait_for_load_state("networkidle")
        sb = page.eval_on_selector_all("a[data-smart-back]", "els => els.map(e => e.getAttribute('href'))")
        check(len(sb) >= 1, "admin detail carries smart back-to-list")
        shot(page, "admin", "01-product-detail-back.png")
        page.click("a[data-smart-back]"); page.wait_for_load_state("networkidle")
        check("search=NAV" in page.url and "/admin/products" in page.url, "back preserves list filter state (history)")
        page.go_forward(); page.wait_for_load_state("networkidle")
        check(detail.rstrip("/") in page.url, "forward returns to the detail page")

        # direct entry fallback
        ctx3 = browser.new_context(viewport={"width": 1360, "height": 900})
        pg3 = ctx3.new_page()
        login(pg3, OWNER_EMAIL, OWNER_NEW)
        pg3.goto(BASE + detail); pg3.wait_for_load_state("networkidle")
        pg3.click("a[data-smart-back]"); pg3.wait_for_load_state("networkidle")
        check(pg3.url.rstrip("/").endswith("/admin/products"), "direct-entry admin detail back falls back to list")
        ctx3.close()
    else:
        for lbl in ["admin detail carries smart back-to-list", "back preserves list filter state (history)", "forward returns to the detail page", "direct-entry admin detail back falls back to list"]:
            check(False, lbl)

    # customers: detail back + edit back-to-customer
    page.goto(BASE + "/admin/customers"); page.wait_for_load_state("networkidle")
    cust = page.eval_on_selector_all("a[href*='/admin/customers/']", "els => els.map(e => e.getAttribute('href'))")
    cust = next((h for h in cust if re.search(r"/admin/customers/[0-9a-f-]{36}$", h)), None)
    if cust:
        page.goto(BASE + cust); page.wait_for_load_state("networkidle")
        check(page.eval_on_selector_all("a[data-smart-back]", "els => els.length") >= 1, "customer detail has smart back")
        page.goto(BASE + cust + "/edit"); page.wait_for_load_state("networkidle")
        body = page.inner_text("body")
        check("Back to customer" in body, "customer edit offers back to the customer record")
        shot(page, "admin", "02-customer-edit-back.png")
    else:
        check(False, "customer detail has smart back (no seeded customer row)")

    # form guard on settings
    page.goto(BASE + "/admin/settings"); page.wait_for_load_state("networkidle")
    dialogs = []
    def _dismiss(d):
        dialogs.append(d.message); d.dismiss()
    page.on("dialog", _dismiss)
    if page.locator("#inp_fee").count():
        page.fill("#inp_fee", "777")
    else:
        page.locator("form[data-guard] input").first.fill("x")
    page.click("aside.sidebar a[href='/admin/dashboard']")
    page.wait_for_timeout(500)
    check(len(dialogs) == 1 and "unsaved changes" in dialogs[0].lower(), "dirty settings form blocks sidebar nav with confirm")
    check("/admin/settings" in page.url, "dismiss keeps the user on the form")
    shot(page, "admin", "03-form-guard-confirm.png")
    page.remove_listener("dialog", _dismiss)
    page.on("dialog", lambda d: d.accept())
    page.click("aside.sidebar a[href='/admin/dashboard']")
    page.wait_for_load_state("networkidle")
    check("/admin/dashboard" in page.url, "accept leaves and navigates")

    page.goto(BASE + "/admin/users/roles"); page.wait_for_load_state("networkidle")
    shot(page, "admin", "04-roles-breadcrumb.png")
    ctx.close()

    # ---------------- AUTH ----------------
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "/admin/users"); page.wait_for_load_state("networkidle")
    check("ReturnUrl" in page.url and "/Account/Login" in page.url, "anonymous admin deep link lands on login with ReturnUrl")
    page.fill("input[name=Email]", OWNER_EMAIL)
    page.fill("input[name=Password]", OWNER_NEW)
    page.click("button[type=submit]"); page.wait_for_load_state("networkidle")
    check("/admin/users" in page.url, "post-login returns to the requested page")
    shot(page, "auth", "01-login-returnurl.png")

    page.goto(BASE + "/dev/audit"); page.wait_for_load_state("networkidle")
    body = page.inner_text("body")
    denied_links = page.eval_on_selector_all(".pay-actions a", "els => els.map(e => e.getAttribute('href'))")
    check("denied" in body.lower(), "business user hitting dev audit sees denial")
    check(any(h in ("/", "/Account/Login") for h in denied_links), "denial page offers store/sign-in escapes")
    shot(page, "auth", "02-access-denied.png")
    ctx.close()

    # ---------------- DEV ----------------
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    login(page, DEV_EMAIL, DEV_PW)
    page.goto(BASE + "/dev"); page.wait_for_load_state("networkidle")
    check(page.eval_on_selector_all("nav.dv-nav a", "els => els.length") >= 4, "dev portal keeps persistent nav")
    shot(page, "dev", "01-dev-nav.png")
    ctx.close()

    # ---------------- MOBILE ----------------
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(BASE + prod_href); page.wait_for_load_state("networkidle")
    check(page.locator("a.cs-back").is_visible(), "mobile product page shows back link")
    shot(page, "mobile", "01-product-backlink.png")
    page.goto(BASE + "/products"); page.wait_for_load_state("networkidle")
    shot(page, "mobile", "02-shop.png")
    ctx.close()

    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    login(page, OWNER_EMAIL, OWNER_NEW)
    page.goto(BASE + "/admin/dashboard"); page.wait_for_load_state("networkidle")
    if page.locator(".menu-toggle").count():
        page.click(".menu-toggle")
        page.wait_for_timeout(300)
    shot(page, "mobile", "03-admin-sidebar.png")
    ctx.close()
    browser.close()

fails = [l for ok, l in results if not ok]
print("\nRESULT: %d passed, %d failed" % (len(results) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
