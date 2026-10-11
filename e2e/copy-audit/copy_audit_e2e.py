"""Copy-audit E2E: removed strings absent, retained strings present, layout intact.

Run against a fresh seeded app on :5121 with the capturing Brevo stub on :8899
(stub stores decoded Brevo payloads in /tmp/brevo_copy_audit.jsonl).
"""
import base64
import html as _html
import json as _json
import os
import re
import time as _time
from urllib.parse import urlparse as _up

from playwright.sync_api import sync_playwright

BASE = os.environ.get("APP_BASE", "http://localhost:5121")
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(SHOT, exist_ok=True)

OWNER_EMAIL, OWNER_BOOT, OWNER_NEW = "owner@dechimexprinthub.com", "ChangeMe123!", "OwnerCopy!2026zQ"
CUST_EMAIL, CUST_PW = "copy.customer@dechimex.test", "Customer!2026xY"

PASSED = []
FAILED = []


def check(ok, label):
    (PASSED if ok else FAILED).append(label)
    print(("PASS " if ok else "FAIL ") + label)


def shot(page, name, full=False):
    page.screenshot(path=os.path.join(SHOT, name + ".png"), full_page=full)


def do_login(page, email, pw):
    page.goto(BASE + "/Account/Login")
    page.fill("input[name=Email]", email)
    page.fill("input[name=Password]", pw)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def login_owner(page):
    do_login(page, OWNER_EMAIL, OWNER_BOOT)
    if "/admin/security/password" in page.url:
        page.fill("input[name=CurrentPassword]", OWNER_BOOT)
        page.fill("input[name=NewPassword]", OWNER_NEW)
        page.fill("input[name=ConfirmPassword]", OWNER_NEW)
        f = page.locator("form").filter(has=page.locator("input[name=NewPassword]"))
        f.locator("button[type=submit]").click()
        page.wait_for_load_state("networkidle")
    if "/Account/Login" in page.url:
        do_login(page, OWNER_EMAIL, OWNER_NEW)


def _body(page, url):
    page.goto(BASE + url)
    page.wait_for_load_state("networkidle")
    body = page.inner_text("body")
    check("Page not found" not in body, f"{url} renders (not a 404)")
    return body


def absent(page, url, strings, label):
    body = _body(page, url)
    for s in strings:
        check(s not in body, f"{label}: removed — “{s[:52]}”")
    return body


def present(page, url, strings, label):
    body = _body(page, url)
    for s in strings:
        check(s in body, f"{label}: retained — “{s[:52]}”")
    return body


def no_empty_blocks(page, label):
    """No visible, fully-empty text elements left behind by copy removal."""
    n = page.evaluate(
        """() => {
        return Array.from(document.querySelectorAll('p, span, li')).filter(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return false;
            const cs = getComputedStyle(el);
            if (cs.display === 'none' || cs.visibility === 'hidden') return false;
            if (el.getAttribute('aria-hidden') === 'true') return false;
            if (el.textContent.trim().length > 0) return false;
            return !el.querySelector('img,svg,input,button,select,iframe');
        }).length;
    }"""
    )
    check(n == 0, f"{label}: no empty visible text blocks ({n})")


def no_hscroll(page, label):
    ok = page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
    check(ok, f"{label}: no horizontal scroll")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # ---------- OWNER ----------
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    login_owner(page)
    check("/admin" in page.url and "/Account/Login" not in page.url, "owner signs in (boot change flow)")

    PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    with open("/tmp/copy-tee.png", "wb") as f:
        f.write(PNG)
    page.goto(BASE + "/admin/categories/create"); page.wait_for_load_state("networkidle")
    page.fill("input[name=Name]", "Copy Audit Category")
    page.locator("form").filter(has=page.locator("input[name=Name]")).locator("button[type=submit]").click()
    page.wait_for_load_state("networkidle")
    page.goto(BASE + "/admin/products/create"); page.wait_for_load_state("networkidle")
    page.fill("input[name=Name]", "Copy Audit Tee")
    opts = page.eval_on_selector_all("select[name=CategoryId] option", "els => els.map(e => e.value).filter(v => v)")
    page.select_option("select[name=CategoryId]", opts[0])
    page.fill("input[name=SellingPrice]", "5000")
    if page.locator("input[name=InitialQuantity]").count():
        page.fill("input[name=InitialQuantity]", "10")
    page.set_input_files("input[name=Images]", "/tmp/copy-tee.png")
    page.locator("form[data-guard] button[type=submit]").click()
    page.wait_for_load_state("networkidle")
    check("/admin/products" in page.url, "product created through admin UI")

    absent(page, "/admin/dashboard", [
        "Live figures for the store, production floor, and cash.",
        "Orders needing attention",
        "Recent order activity",
        "Sales pipeline snapshot",
        "Latest enquiries and reviews",
    ], "admin dashboard")
    no_empty_blocks(page, "admin dashboard")
    shot(page, "admin-dashboard", full=True)

    absent(page, "/admin/activity", [
        "A cross-business view of committed actions.",
        "New business history starts when this feature is deployed.",
    ], "admin activity")
    no_empty_blocks(page, "admin activity")
    shot(page, "admin-activity", full=True)

    absent(page, "/admin/settings", [
        "Configure branding, payment, delivery, and notification settings.",
    ], "admin settings")
    no_empty_blocks(page, "admin settings")
    present(page, "/admin/announcements/create", [
        "Empty = stays visible until deactivated.",
    ], "announcement form")

    absent(page, "/admin/orders", ["Orders placed from the storefront will appear here."], "admin orders")
    absent(page, "/admin/messages", ["Submissions from the public contact form appear here."], "admin enquiries")
    absent(page, "/admin/products", ["Products you add will be available on the storefront."], "admin products")
    det = page.eval_on_selector_all("a[href*='/admin/products/']", "els => els.map(e => e.getAttribute('href')).filter(h => /\\/admin\\/products\\/[0-9a-f-]{36}/.test(h))")
    check(len(det) > 0, "admin products lists a detail link")
    if det:
        absent(page, det[0], [
            "Upload product photos to give this listing a real face.",
            "Customer reviews will appear here after the first one is submitted.",
        ], "admin product detail")
    absent(page, "/admin/services", ["Services you publish appear on the public Services page."], "admin services")
    absent(page, "/admin/invoices", ["Invoices are issued when orders are placed."], "admin invoices")
    present(page, "/admin/invoices", ["Quote invoices can be created for off-platform sales."], "admin invoices")
    absent(page, "/admin/receipts", ["Receipts are generated automatically after an order payment succeeds."], "admin receipts")
    present(page, "/admin/receipts", ["Generated automatically after payment succeeds."], "admin receipts")

    cbody = absent(page, "/admin/categories", ["— use “Add subcategory”"], "admin categories")
    check("No subcategories yet." in cbody or "No subcategories yet" not in cbody, "admin categories: shortened line")

    absent(page, "/admin/sales", ["New custom-order requests will appear here once assigned."], "admin sales")
    absent(page, "/admin/suppliers", ["Add the vendors you buy materials from to speed up procurement."], "admin suppliers")
    absent(page, "/admin/users", ["Team accounts appear here after they are created."], "admin users")
    absent(page, "/admin/users/roles", ["Roles define which permissions each team member has."], "admin roles")
    perm = page.locator("a", has_text="Permissions").first
    perm.click()
    page.wait_for_load_state("networkidle")
    check("Changes apply immediately to all users with this role." in page.inner_text("body"),
          "role permissions: retained consequence line")
    ctx.close()

    # ---------- ANONYMOUS ----------
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    absent(page, "/", [
        "Real orders, real photos, real reviews.",
        "Every product is photographed from a real job — what you see is what gets printed.",
        "Browse by what you need to make, or start from a proven job.",
        "Not sure which product? These paths cover most jobs.",
        "Real jobs from the print floor, with the products used to make them.",
        "From first enquiry to delivered job — here's how orders move through DeChimex.",
    ], "store home")
    present(page, "/", [
        "Branded mugs, jerseys, flasks",
        "How a custom order works",
    ], "store home")
    no_empty_blocks(page, "store home")
    shot(page, "home-desktop", full=True)

    absent(page, "/gallery", [
        "Real finished jobs photographed after delivery. Tap any job to see the products used.",
    ], "gallery")
    check(page.locator(".filter-pill").count() > 0, "gallery: grid renders")
    no_empty_blocks(page, "gallery")

    absent(page, "/account/login", ["Sign in to track orders, chat with our team and check out faster."], "login")
    absent(page, "/account/login", ["Sign in to track orders, reorder past jobs, and manage your details."], "login")
    present(page, "/account/register", [
        "Just an email and a password. Add your name and delivery details later, when you place your first order.",
    ], "register")
    no_empty_blocks(page, "login")
    no_empty_blocks(page, "register")

    page.goto(BASE + "/products")
    page.wait_for_load_state("networkidle")
    prod_links = page.eval_on_selector_all("a[href*='/products/']", "els => els.map(e => e.getAttribute('href'))")
    prod_href = next((h for h in prod_links if re.match(r"^/products/[0-9a-f-]{36}$", h)), None)
    check(prod_href is not None, "shop lists a product")
    if prod_href:
        present(page, prod_href, [
            "No quote or design approval needed. Sign in (free) to check out and pay online.",
        ], "product detail")

    present(page, "/products?search=zzzqqq", ["Try a different word, or browse by category."], "shop search fallback")

    page.goto(BASE + "/cart")
    page.wait_for_load_state("networkidle")
    check("Ready-to-buy products can be added straight to your cart." not in page.inner_text("body"), "cart: removed desc absent")
    no_empty_blocks(page, "cart")
    shot(page, "cart", full=True)

    for w, name in ((834, "home-tablet"), (390, "home-mobile")):
        ctxm = browser.new_context(viewport={"width": w, "height": 900})
        pagem = ctxm.new_page()
        pagem.goto(BASE + "/")
        pagem.wait_for_load_state("networkidle")
        no_hscroll(pagem, name)
        no_empty_blocks(pagem, name)
        shot(pagem, name, full=True)
        ctxm.close()

    # ---------- CUSTOMER ----------
    ctxc = browser.new_context(viewport={"width": 1360, "height": 900})
    pgc = ctxc.new_page()
    pgc.goto(BASE + "/Account/Register")
    pgc.fill("input[name=Email]", CUST_EMAIL)
    pgc.fill("input[name=Password]", CUST_PW)
    pgc.click("button[type=submit]")
    pgc.wait_for_load_state("networkidle")
    link = None
    for _ in range(30):
        try:
            with open("/tmp/brevo_copy_audit.jsonl") as fh:
                for line in fh:
                    rec = _json.loads(line)
                    if "copy.customer" not in _json.dumps(rec):
                        continue
                    body = rec.get("body")
                    text = _json.dumps(body) if isinstance(body, (dict, list)) else (body or "")
                    m = re.search(r"(https?://[^'\"\s<>]+/Account/VerifyEmail[^'\"\s<>]+)", text)
                    if m:
                        link = m.group(1).replace("&amp;", "&")
        except FileNotFoundError:
            pass
        if link:
            break
        _time.sleep(1)
    check(link is not None, "customer registers; confirmation email captured")
    if link:
        link = _html.unescape(link)
        _u = _up(link)
        link = BASE + _u.path + (("?" + _u.query) if _u.query else "")
        pgc.goto(link)
        pgc.wait_for_load_state("networkidle")
        check("invalid verification token" not in pgc.inner_text("body").lower(), "customer confirms email")
    ctxc.close()

    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    do_login(page, CUST_EMAIL, CUST_PW)
    check("/Account/" not in page.url, "customer signs in")

    absent(page, "/portal", ["Orders you place will appear here with live status updates."], "portal dashboard")
    no_empty_blocks(page, "portal dashboard")
    shot(page, "portal-dashboard", full=True)
    absent(page, "/portal/orders", ["Orders you place will appear here with live status updates."], "portal orders")
    absent(page, "/portal/wishlist", ["Tap the heart on any product to save it here for later."], "portal wishlist")
    absent(page, "/portal/addresses", ["Save a delivery address to check out faster next time."], "portal addresses")
    absent(page, "/portal/payments", ["Payments for your orders will appear here."], "portal payments")
    absent(page, "/portal/invoices", ["Invoices and receipts for your orders will appear here."], "portal invoices")
    ctx.close()

    # ---------- OWNER again: customer detail (customer now exists) ----------
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    do_login(page, OWNER_EMAIL, OWNER_NEW)
    check("/Account/Login" not in page.url, "owner re-signs in")
    page.goto(BASE + "/admin/customers"); page.wait_for_load_state("networkidle")
    check("Page not found" not in page.inner_text("body"), "/admin/customers renders (not a 404)")
    cdet = page.eval_on_selector_all("a[href*='/admin/customers/']", "els => els.map(e => e.getAttribute('href')).filter(h => /\\/admin\\/customers\\/[0-9a-f-]{36}/.test(h))")
    check(len(cdet) > 0, "admin customers lists a detail link")
    if cdet:
        absent(page, cdet[0], [
            "This customer has not saved any delivery addresses yet.",
            "Orders placed by this customer will appear here.",
        ], "admin customer detail")
    ctx.close()

    browser.close()

print()
print(f"{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    for f in FAILED:
        print("  FAILED: " + f)
    raise SystemExit(1)
