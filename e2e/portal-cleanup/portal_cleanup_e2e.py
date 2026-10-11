#!/usr/bin/env python3
"""E2E evidence for the 2026-10-08 admin portal cleanup (ADMIN_PORTAL_AUDIT.md).

Runs against a fresh app on :5121. Produces ordered screenshots in
e2e/portal-cleanup/shots/ plus PASS/FAIL checks for navigation, security and
absorbed-analytics behaviour.
"""
import os, re, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5121"
SHOTS = os.environ.get("PORTAL_SHOTS", "/home/user/DeChimex-GalleryMobile/e2e/portal-cleanup/shots")
OWNER_EMAIL = "owner@dechimexprinthub.com"
OWNER_BOOT = "ChangeMe123!"
OWNER_NEW = "OwnerE2E!2026xY"
DEV_EMAIL = "developer@dechimexprinthub.local"
DEV_PW = "DevPortal#2026!"

results = []
def check(ok, label):
    results.append((ok, label))
    print(("PASS " if ok else "FAIL ") + "  " + label)

def token(html):
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else re.search(r'value="([^"]+)"[^>]*name="__RequestVerificationToken"', html).group(1)

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
        pw_form = page.locator("form").filter(has=page.locator("input[name=NewPassword]"))
        pw_form.locator("button[type=submit]").click()
        page.wait_for_load_state("networkidle")
    if "/Account/Login" in page.url:  # forced change signs the session out; come back in
        do_login(page, email, new_pw or pw)
    return page

def shot(page, name):
    page.screenshot(path=os.path.join(SHOTS, name), full_page=False)
    print("SHOT " + name)

def sidebar_text(page):
    return page.eval_on_selector("aside.sidebar", "el => el.innerText")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # ---------- OWNER ----------
    ctx = browser.new_context(viewport={"width": 1360, "height": 1900})
    page = ctx.new_page()
    login(page, OWNER_EMAIL, OWNER_BOOT, OWNER_NEW)
    page.goto(BASE + "/admin/dashboard"); page.wait_for_load_state("networkidle")
    owner_nav = sidebar_text(page)
    shot(page, "01-owner-nav.png")
    shot(page, "07-dashboard.png")

    lines = [l.strip() for l in owner_nav.splitlines()]
    check("Enquiries" in lines and "Messages" not in lines, "owner nav shows Enquiries (not Messages)")
    check("Team chat" in lines and "Team messages" not in lines, "owner nav shows Team chat (not Team messages)")
    check("Major categories" not in lines, "owner nav has no Major categories item")
    check("Raw audit trail" not in lines, "owner nav has no Raw audit trail item")
    check("Analytics" not in lines, "owner nav has no Analytics item")
    check("Suppliers" not in lines, "owner nav has no standalone Suppliers item")
    for grp in ["Today", "Sell", "Catalogue", "Customers", "Growth", "Operations", "Team", "Administration"]:
        check(grp.upper() in lines, f"owner nav group '{grp}' present")

    # Categories merged tree
    page.goto(BASE + "/admin/categories"); page.wait_for_load_state("networkidle")
    cat = page.inner_text("body")
    shot(page, "03-categories.png")
    check("New top-level category" in cat and "New subcategory" in cat, "categories page manages both levels")

    # Procurement with suppliers tab
    page.goto(BASE + "/admin/procurement?view=suppliers"); page.wait_for_load_state("networkidle")
    sup = page.inner_text("body")
    shot(page, "04-procurement-suppliers.png")
    check("Purchase orders" in sup and "Suppliers" in sup, "procurement shows PO + Suppliers tabs")

    # Role permission editor (Manager)
    page.goto(BASE + "/admin/users/roles"); page.wait_for_load_state("networkidle")
    roles_html = page.content()
    m = re.search(r'href="(/admin/users/roles/[0-9a-f-]{36}/permissions)"[^>]*>[^<]*</a>\s*</td>', roles_html)
    mgr_link = None
    for row in re.split(r"<tr", roles_html):
        if ">Manager</td>" in row:
            mm = re.search(r'href="(/admin/users/roles/[0-9a-f-]{36}/permissions)"', row)
            mgr_link = mm.group(1) if mm else None
    page.goto(BASE + mgr_link); page.wait_for_load_state("networkidle")
    rp = page.inner_text("body")
    shot(page, "05-role-permissions.png")
    check("View orders" in rp and "orders.view" not in rp, "role editor shows human-readable capabilities, no raw claims")

    # Settings simplified
    page.goto(BASE + "/admin/settings"); page.wait_for_load_state("networkidle")
    st = page.inner_text("body").lower()
    shot(page, "06-settings.png")
    check("public site text" in st, "settings regroups homepage stats under Public site text")
    check("send test email" not in st and "authorised ips" not in st, "settings has no vendor email tooling")

    # Orders status summary
    page.goto(BASE + "/admin/orders"); page.wait_for_load_state("networkidle")
    od = page.content()
    shot(page, "08-orders-status.png")
    check("Order status summary" in od, "orders page carries the absorbed status mix")

    # Products report (top products home)
    page.goto(BASE + "/admin/reports/products"); page.wait_for_load_state("networkidle")
    pr = page.inner_text("body").lower()
    shot(page, "09-products-report.png")
    check("units" in pr and "revenue" in pr, "products report carries top-products data")

    # Security: business user vs technical audit
    r = page.request.get(BASE + "/admin/audit/raw")
    check(r.status == 404, "business route /admin/audit/raw is gone (404)")
    page.goto(BASE + "/dev/audit")
    denied = ("AccessDenied" in page.url) or page.evaluate("document.body.innerText").find("Audit trail") == -1
    shot(page, "12-business-denied-dev-audit.png")
    check(denied, "owner is denied the developer audit trail")

    # Manager + SalesStaff navs (created through the real Users UI form)
    def create_staff(email, first, last, username, pw, role_label):
        page.goto(BASE + "/admin/users/create"); page.wait_for_load_state("networkidle")
        page.fill("input[name=Email]", email)
        page.fill("input[name=FirstName]", first)
        page.fill("input[name=LastName]", last)
        page.fill("input[name=Username]", username)
        page.fill("input[name=Password]", pw)
        page.select_option("select[name=RoleIds]", label=role_label)
        page.locator("form").filter(has=page.locator("input[name=Username]")).locator("button[type=submit]").click()
        page.wait_for_load_state("networkidle")
        return page.url.endswith("/admin/users")
    check(create_staff("manager.e2e@dechimex.test", "Mana", "Ger", "mana.e2e", "Manager!2026xY", "Manager"),
          "manager account created through Users UI")
    check(create_staff("sales.e2e@dechimex.test", "Sa", "Les", "sales.e2e", "Sales!2026xY", "SalesStaff"),
          "sales account created through Users UI")
    ctx.close()

    ctx = browser.new_context(viewport={"width": 1360, "height": 1900})
    page = ctx.new_page()
    login(page, "manager.e2e@dechimex.test", "Manager!2026xY")
    page.goto(BASE + "/admin/dashboard"); page.wait_for_load_state("networkidle")
    mgr_nav = sidebar_text(page)
    shot(page, "02-manager-nav.png")
    check("Users" not in mgr_nav, "manager nav has no Users item")
    check("Enquiries" in mgr_nav and "Team chat" in mgr_nav, "manager nav uses the renamed items")
    check("Raw audit trail" not in mgr_nav and "Analytics" not in mgr_nav, "manager nav free of retired technical items")
    ctx.close()

    ctx = browser.new_context(viewport={"width": 1360, "height": 1900})
    page = ctx.new_page()
    login(page, "sales.e2e@dechimex.test", "Sales!2026xY")
    page.goto(BASE + "/admin/sales"); page.wait_for_load_state("networkidle")
    sales_nav = sidebar_text(page)
    check("Enquiries" in sales_nav and "Team chat" in sales_nav, "sales nav shows renamed items")
    check("Dashboard" not in sales_nav, "sales nav stays tight (no reports group)")
    ctx.close()

    # ---------- DEVELOPER ----------
    ctx = browser.new_context(viewport={"width": 1360, "height": 1900})
    page = ctx.new_page()
    login(page, DEV_EMAIL, DEV_PW)
    page.goto(BASE + "/dev"); page.wait_for_load_state("networkidle")
    dev_nav = page.eval_on_selector("nav.dv-nav", "el => el.innerText")
    shot(page, "10-dev-nav.png")
    check("Audit trail" in dev_nav, "developer nav offers the Audit trail")
    page.goto(BASE + "/dev/audit"); page.wait_for_load_state("networkidle")
    da = page.inner_text("body")
    shot(page, "11-dev-audit.png")
    check("forensic" in da or "before/after" in da, "developer audit page renders the forensic trail")
    page.goto(BASE + "/dev/email"); page.wait_for_load_state("networkidle")
    de = page.inner_text("body")
    check("Send test email to my address" in de, "provider test send lives in the developer portal")
    ctx.close()
    browser.close()

fails = [l for ok, l in results if not ok]
print(f"\nRESULT: {len(results) - len(fails)} checks passed, {len(fails)} failed; screenshots in {SHOTS}")
sys.exit(1 if fails else 0)
