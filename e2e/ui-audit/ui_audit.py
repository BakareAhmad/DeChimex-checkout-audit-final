#!/usr/bin/env python3
"""UI Alignment & Icon Consistency Audit (read-only, 2026-10-09).
Seeds demo data through the real UI, then crawls every user area capturing
screenshots + objective layout measurements (icon/label centering, icon-size
consistency, sibling icon gaps, header alignment, mobile overflow).
App files are never modified; output goes to shots/ and /tmp/ui_audit_findings.json.
"""
import json, os, re, time, html as _html
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5121"
SHOTS = "/home/user/DeChimex-GalleryMobile/e2e/ui-audit/shots"
CAPTURE = "/tmp/brevo_nav_audit.jsonl"
OWNER_EMAIL, OWNER_BOOT, OWNER_NEW = "owner@dechimexprinthub.com", "ChangeMe123!", "OwnerUi!2026zQ"
DEV_EMAIL, DEV_PW = "developer@dechimexprinthub.local", "DevPortal#2026!"
CUST_EMAIL, CUST_PW = "ui.customer@dechimex.test", "Customer!2026xY"

findings = []
def shot(page, area, name, clip=None):
    d = os.path.join(SHOTS, area)
    os.makedirs(d, exist_ok=True)
    try:
        if clip:
            page.screenshot(path=os.path.join(d, name), clip=clip)
        else:
            page.screenshot(path=os.path.join(d, name), full_page=False)
    except Exception as e:
        print("  shot failed", area, name, e)

def do_login(page, email, pw):
    print("  [login]", email)
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

# ---------------------------------------------------------------- measurements
MEASURE = r"""
() => {
  const out = [];
  const push = (type, o) => out.push(Object.assign({type, page: location.pathname + location.search}, o));
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const merge = (a, b) => ({top: Math.min(a.top, b.top), bottom: Math.max(a.bottom, b.bottom)});
  const textBox = el => {
    let found = null;
    const r = document.createRange();
    const walk = node => {
      for (const n of node.childNodes) {
        if (n.nodeType === 3) {
          if (!n.textContent.trim()) continue;
          r.selectNodeContents(n);
          const b = r.getBoundingClientRect();
          if (b.height) found = found ? merge(found, b) : {top: b.top, bottom: b.bottom};
        } else if (n.nodeType === 1 && !n.closest('svg') && n.tagName !== 'svg'.toUpperCase() && !n.querySelector('svg')) {
          if (n.textContent.trim() && vis(n)) { const b = n.getBoundingClientRect(); if (b.height) found = found ? merge(found, {top: b.top, bottom: b.bottom}) : {top: b.top, bottom: b.bottom}; }
        }
      }
    };
    walk(el);
    return found;
  };
  const sig = el => el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '');

  // 1) icon vs label vertical centering on interactive items
  document.querySelectorAll('a, button, .flash').forEach(el => {
    if (el.closest('[hidden]') || el.closest('[aria-hidden="true"]') || !vis(el)) return;
    const svgs = el.querySelectorAll('svg');
    if (!svgs.length || svgs.length > 2) return;
    if (el.closest('svg')) return;
    const tb = textBox(el);
    if (!tb) return;
    const sb = svgs[0].getBoundingClientRect();
    if (!sb.height) return;
    const dy = (sb.top + sb.height / 2) - (tb.top + (tb.bottom - tb.top) / 2);
    if (Math.abs(dy) > 1.5) push('icon-text-misalign', {sel: sig(el), text: el.textContent.trim().replace(/\s+/g, ' ').slice(0, 45), dy: Math.round(dy * 10) / 10});
  });

  // 2) sibling groups: items lacking an icon while siblings have them
  const containers = document.querySelectorAll('nav, .cs-menu, .cs-bottom, .ac-tabs, .cs-foot-socials, .dv-nav, .portal-notif-actions, .side-scroll nav, .cs-actions, .dv-side-foot');
  containers.forEach(cont => {
    if (cont.closest('[hidden]') || !vis(cont)) return;
    const kids = [...cont.querySelectorAll(':scope > a, :scope > button, :scope > form > button, :scope > li > a')];
    if (kids.length < 3) return;
    const withIcon = kids.filter(k => k.querySelector('svg'));
    const noIcon = kids.filter(k => !k.querySelector('svg') && k.textContent.trim());
    if (withIcon.length >= 2 && noIcon.length >= 1 && withIcon.length >= noIcon.length) {
      noIcon.forEach(k => push('missing-icon', {container: sig(cont), text: k.textContent.trim().replace(/\s+/g, ' ').slice(0, 40), siblingsWithIcons: withIcon.length}));
    }
  });

  // 3) icon size consistency inside uniform groups
  [['.side-link svg', 'admin sidebar'], ['.ac-tabs a svg', 'account tabs'], ['.cs-bottom a svg', 'bottom nav'],
   ['.cs-iconbtn > svg', 'topbar icon buttons'], ['.cs-menu a svg', 'account menu'], ['.cs-menu button svg', 'account menu'],
   ['.dv-nav a svg', 'dev nav'], ['.cs-foot-socials a svg', 'footer socials']].forEach(([sel, label]) => {
    const sizes = new Set();
    document.querySelectorAll(sel).forEach(s => { if (vis(s)) sizes.add(s.getAttribute('width') + 'x' + s.getAttribute('height')); });
    if (sizes.size > 1) push('icon-size-inconsistent', {group: label, sizes: [...sizes].join(', ')});
  });

  // 4) page-head: heading vs action controls alignment
  document.querySelectorAll('.cs-page-head, .cs-section-head, .panel-head, .page-head').forEach(h => {
    if (!vis(h)) return;
    const title = h.querySelector('h1,h2,h3');
    const ctl = h.querySelector('a.btn, button, .btn, form button');
    if (!title || !ctl || !vis(ctl)) return;
    const a = title.getBoundingClientRect(), b = ctl.getBoundingClientRect();
    const dy = (a.top + a.height / 2) - (b.top + b.height / 2);
    if (Math.abs(dy) > 2.5) push('head-action-misalign', {sel: sig(h), title: title.textContent.trim().slice(0, 40), dy: Math.round(dy * 10) / 10});
  });

  // 5) horizontal overflow
  const ow = document.documentElement.scrollWidth - window.innerWidth;
  if (ow > 1) push('h-overflow', {px: ow});

  return out;
}
"""

def measure(page, label):
    try:
        rows = page.evaluate(MEASURE)
    except Exception as e:
        print("  measure failed", label, e)
        return
    for r in rows:
        r["screenshot"] = label
        findings.append(r)

def crawl(page, area, pages, prefix):
    for i, path in enumerate(pages):
        try:
            page.goto(BASE + path, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print("  goto failed", path, e)
            continue
        slug = (path.strip("/").replace("/", "-") or "home")[:48]
        name = "%s-%s.png" % (prefix + str(i).zfill(2), slug)
        shot(page, area, name)
        measure(page, area + "/" + name)
        if page.url != "about:blank":
            print("  %s %s (%s)" % (area, path, page.url.replace(BASE, "") or "/"))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # ------------------------------------------------ SEED (real UI, no direct DB)
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (640, 480), (226, 88, 56))
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 600, 440], outline=(255, 255, 255), width=8)
    d.text((60, 60), "UI AUDIT SAMPLE", fill=(255, 255, 255))
    img.save("/tmp/ui-tee.png")

    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    pg = ctx.new_page()
    login(pg, OWNER_EMAIL, OWNER_BOOT, OWNER_NEW)
    assert "/admin" in pg.url, "owner login failed"
    pg.goto(BASE + "/admin/categories/create"); pg.wait_for_load_state("networkidle")
    pg.fill("input[name=Name]", "Apparel")
    pg.locator("form").filter(has=pg.locator("input[name=Name]")).locator("button[type=submit]").click()
    pg.wait_for_load_state("networkidle")
    for pname, price in (("UI Audit Tee", "5000"), ("UI Audit Mug", "3500")):
        pg.goto(BASE + "/admin/products/create"); pg.wait_for_load_state("networkidle")
        pg.fill("input[name=Name]", pname)
        opts = pg.eval_on_selector_all("select[name=CategoryId] option", "els => els.map(e => e.value).filter(v => v)")
        pg.select_option("select[name=CategoryId]", opts[0])
        pg.fill("input[name=SellingPrice]", price)
        if pg.locator("input[name=InitialQuantity]").count():
            pg.fill("input[name=InitialQuantity]", "10")
        pg.set_input_files("input[name=Images]", "/tmp/ui-tee.png")
        pg.locator("form[data-guard] button[type=submit]").click()
        pg.wait_for_load_state("networkidle")
        assert "/admin/products" in pg.url, "product create failed: " + pname
    print("seeded: category + 2 products")
    ctx.close()

    # customer registration + email verification via stub capture
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    pg = ctx.new_page()
    pg.goto(BASE + "/Account/Register")
    pg.wait_for_selector("input[name=Email]", timeout=20000)
    pg.fill("input[name=Email]", CUST_EMAIL)
    pg.fill("input[name=Password]", CUST_PW)
    pg.click("button[type=submit]"); pg.wait_for_load_state("networkidle")
    link = None
    for _ in range(30):
        try:
            for line in open(CAPTURE):
                rec = json.loads(line)
                if "ui.customer" not in json.dumps(rec):
                    continue
                m = re.search(r"(https?://[^'\"\s<>]+/Account/VerifyEmail[^'\"\s<>]+)", json.dumps(rec))
                if m:
                    link = m.group(1)
        except FileNotFoundError:
            pass
        if link:
            break
        time.sleep(1)
    assert link, "verification email not captured"
    link = _html.unescape(link)
    u = urlparse(link)
    pg.goto(BASE + u.path + (("?" + u.query) if u.query else ""))
    pg.wait_for_load_state("networkidle")
    assert "invalid verification token" not in pg.inner_text("body").lower(), "verification failed"
    print("customer verified")
    # put one item in the cart
    pg.goto(BASE + "/products"); pg.wait_for_load_state("networkidle")
    prod_href = pg.get_attribute("a[href^='/products/']", "href")
    pg.goto(BASE + prod_href); pg.wait_for_load_state("networkidle")
    btn = pg.locator("button", has_text="Add to cart")
    if btn.count():
        btn.first.click(); pg.wait_for_load_state("networkidle")
    print("cart seeded; product href =", prod_href)
    cust_prod = prod_href
    ctx.close()

    # ------------------------------------------------ PUBLIC (anonymous)
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    pg = ctx.new_page()
    anon_pages = ["/", "/products", "/products?sort=price_asc", "/services", "/gallery", "/about",
                  "/contact", "/faq", "/cart", "/Account/Login", "/Account/Register",
                  "/privacy", "/terms", "/install-help", "/definitely-missing-404"]
    crawl(pg, "public", anon_pages, "")
    pg.goto(BASE + cust_prod); pg.wait_for_load_state("networkidle")
    shot(pg, "public", "15-product-detail.png"); measure(pg, "public/15-product-detail.png")
    ctx.close()

    # ------------------------------------------------ CUSTOMER (signed in)
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    pg = ctx.new_page()
    do_login(pg, CUST_EMAIL, CUST_PW)
    assert "/Account/Login" not in pg.url and "/Account/VerifyEmail" not in pg.url, "customer login failed"
    cust_pages = ["/portal", "/portal/orders", "/portal/orders/track", "/portal/wishlist",
                  "/portal/addresses", "/portal/addresses/add", "/portal/payments", "/portal/invoices",
                  "/portal/profile", "/portal/notifications", "/portal/shop", "/cart", cust_prod]
    crawl(pg, "customer", cust_pages, "")
    # dropdown states
    pg.goto(BASE + "/portal"); pg.wait_for_load_state("networkidle")
    try:
        pg.click("#csMenuBtn"); pg.wait_for_timeout(400)
        shot(pg, "customer", "90-account-menu-open.png"); measure(pg, "customer/90-account-menu-open.png")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        pg.click("#portalNotifBell"); pg.wait_for_timeout(600)
        shot(pg, "customer", "91-notif-dropdown-open.png"); measure(pg, "customer/91-notif-dropdown-open.png")
    except Exception as e:
        print("  dropdown capture failed:", e)
    ctx.close()

    # ------------------------------------------------ ADMIN (owner)
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    pg = ctx.new_page()
    login(pg, OWNER_EMAIL, OWNER_NEW)
    assert "/admin" in pg.url, "owner re-login failed"
    # discover a product id + customer id for detail pages
    pg.goto(BASE + "/admin/products"); pg.wait_for_load_state("networkidle")
    pdet = pg.get_attribute("a[href^='/admin/products/']", "href") or "/admin/products"
    pg.goto(BASE + "/admin/customers"); pg.wait_for_load_state("networkidle")
    cdet = pg.get_attribute("a[href^='/admin/customers/']", "href")
    admin_pages = ["/admin/dashboard", "/admin/activity", "/admin/notifications", "/admin/reports",
                   "/admin/sales", "/admin/orders", "/admin/invoices", "/admin/receipts",
                   "/admin/products", "/admin/products/create", pdet, pdet + "/edit",
                   "/admin/categories", "/admin/categories/create", "/admin/services", "/admin/gallery",
                   "/admin/customers"] + ([cdet] if cdet else []) + [
                   "/admin/messages", "/admin/reviews", "/admin/marketing", "/admin/announcements",
                   "/admin/team-messages", "/admin/inventory", "/admin/procurement", "/admin/users",
                   "/admin/settings", "/admin/security/password", "/admin/major-categories"]
    crawl(pg, "admin", admin_pages, "")
    # zoomed sidebar (icon rendering check)
    pg.goto(BASE + "/admin/dashboard"); pg.wait_for_load_state("networkidle")
    try:
        box = pg.locator("#appSidebar").bounding_box()
        if box:
            shot(pg, "admin", "90-sidebar-zoom.png", clip=box)
    except Exception as e:
        print("  sidebar shot failed:", e)
    ctx.close()

    # ------------------------------------------------ DEV PORTAL
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    pg = ctx.new_page()
    do_login(pg, DEV_EMAIL, DEV_PW)
    dev_pages = ["/dev", "/dev/health", "/dev/performance", "/dev/jobs", "/dev/logs", "/dev/errors",
                 "/dev/audit", "/dev/integrations", "/dev/payments", "/dev/email", "/dev/service-fees",
                 "/dev/database", "/dev/configuration", "/dev/maintenance", "/dev/account/password"]
    crawl(pg, "dev", dev_pages, "")
    ctx.close()

    # ------------------------------------------------ MOBILE 390x844
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    mobile_pages = ["/", "/products", cust_prod, "/cart", "/Account/Login", "/services", "/gallery"]
    crawl(pg, "mobile", mobile_pages, "")
    do_login(pg, CUST_EMAIL, CUST_PW)
    crawl(pg, "mobile", ["/portal", "/portal/orders", "/portal/orders/track", "/portal/profile", "/portal/addresses"], "c")
    # admin + dev mobile (hamburger) — fresh contexts (login redirects authenticated users)
    ctx.close()
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    login(pg, OWNER_EMAIL, OWNER_NEW)
    pg.goto(BASE + "/admin/dashboard"); pg.wait_for_load_state("networkidle")
    shot(pg, "mobile", "20-admin-dashboard.png"); measure(pg, "mobile/20-admin-dashboard.png")
    try:
        pg.click("#menuToggle"); pg.wait_for_timeout(500)
        shot(pg, "mobile", "21-admin-sidebar-open.png"); measure(pg, "mobile/21-admin-sidebar-open.png")
    except Exception as e:
        print("  admin mobile sidebar failed:", e)
    ctx.close()
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    do_login(pg, DEV_EMAIL, DEV_PW)
    pg.goto(BASE + "/dev"); pg.wait_for_load_state("networkidle")
    shot(pg, "mobile", "22-dev-dashboard.png"); measure(pg, "mobile/22-dev-dashboard.png")
    ctx.close()

    # ------------------------------------------------ summary
    with open("/tmp/ui_audit_findings.json", "w") as f:
        json.dump(findings, f, indent=1)
    from collections import Counter
    c = Counter(x["type"] for x in findings)
    print("\n== measurement summary ==")
    for t, n in c.most_common():
        print("%-24s %d" % (t, n))
    print("total findings:", len(findings), "-> /tmp/ui_audit_findings.json")
    browser.close()
