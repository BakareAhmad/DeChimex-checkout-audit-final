#!/usr/bin/env python3
"""Refined measurement pass (read-only): only flags icons sharing a text line
(stacked card layouts excluded), ignores count badges. App data from the seed
run is still live; contexts only re-login."""
import json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5121"
OWNER_EMAIL, OWNER_NEW = "owner@dechimexprinthub.com", "OwnerUi!2026zQ"
DEV_EMAIL, DEV_PW = "developer@dechimexprinthub.local", "DevPortal#2026!"
CUST_EMAIL, CUST_PW = "ui.customer@dechimex.test", "Customer!2026xY"

MEASURE = r"""
() => {
  const out = [];
  const push = (type, o) => out.push(Object.assign({type, page: location.pathname + location.search}, o));
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const BADGE = '.cs-count, .cart-badge, .notif-badge, .portal-notif-badge, .dv-badge';
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
          if (b.height) found = found ? merge(found, {top: b.top, bottom: b.bottom}) : {top: b.top, bottom: b.bottom};
        } else if (n.nodeType === 1 && !n.closest('svg') && n.tagName !== 'SVG' && !n.querySelector('svg')
                   && !n.matches(BADGE) && !n.closest(BADGE)) {
          if (n.textContent.trim() && vis(n)) { const b = n.getBoundingClientRect(); if (b.height) found = found ? merge(found, {top: b.top, bottom: b.bottom}) : {top: b.top, bottom: b.bottom}; }
        }
      }
    };
    walk(el);
    return found;
  };
  const sig = el => el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '');

  // 1) icon vs label centering — ONLY side-by-side (vertical overlap present)
  document.querySelectorAll('a, button, .flash').forEach(el => {
    if (el.closest('[hidden]') || el.closest('[aria-hidden="true"]') || !vis(el) || el.closest('svg')) return;
    const svgs = el.querySelectorAll('svg');
    if (!svgs.length || svgs.length > 2) return;
    const tb = textBox(el);
    if (!tb) return;
    const sb = svgs[0].getBoundingClientRect();
    if (!sb.height) return;
    const overlap = Math.min(sb.bottom, tb.bottom) - Math.max(sb.top, tb.top);
    if (overlap <= 0) return; // stacked layout (icon above text) -> intentional
    const dy = (sb.top + sb.height / 2) - (tb.top + (tb.bottom - tb.top) / 2);
    if (Math.abs(dy) > 1.5) push('icon-text-misalign', {sel: sig(el), text: el.textContent.trim().replace(/\s+/g, ' ').slice(0, 45), dy: Math.round(dy * 10) / 10, icon: Math.round(sb.height)});
  });

  // 2) sibling groups missing icons
  document.querySelectorAll('nav, .cs-menu, .cs-bottom, .ac-tabs, .cs-foot-socials, .dv-nav, .portal-notif-actions, .side-scroll nav, .cs-actions, .dv-side-foot').forEach(cont => {
    if (cont.closest('[hidden]') || !vis(cont)) return;
    const kids = [...cont.querySelectorAll(':scope > a, :scope > button, :scope > form > button, :scope > li > a')];
    if (kids.length < 3) return;
    const withIcon = kids.filter(k => k.querySelector('svg'));
    const noIcon = kids.filter(k => !k.querySelector('svg') && k.textContent.trim());
    if (withIcon.length >= 2 && noIcon.length >= 1 && withIcon.length >= noIcon.length) {
      noIcon.forEach(k => push('missing-icon', {container: sig(cont), text: k.textContent.trim().replace(/\s+/g, ' ').slice(0, 40), siblingsWithIcons: withIcon.length}));
    }
  });

  // 3) icon size consistency
  [['.side-link svg', 'admin sidebar'], ['.ac-tabs a svg', 'account tabs'], ['.cs-bottom a svg', 'bottom nav'],
   ['.cs-iconbtn > svg', 'topbar icon buttons'], ['.cs-menu a svg', 'account menu'], ['.cs-menu button svg', 'account menu'],
   ['.dv-nav a svg', 'dev nav'], ['.cs-foot-socials a svg', 'footer socials'], ['.btn svg', 'buttons'], ['.cs-cta svg', 'cta']].forEach(([sel, label]) => {
    const sizes = new Set();
    document.querySelectorAll(sel).forEach(s => { if (vis(s)) sizes.add(s.getAttribute('width') + 'x' + s.getAttribute('height')); });
    if (sizes.size > 1) push('icon-size-inconsistent', {group: label, sizes: [...sizes].join(', ')});
  });

  // 4) head vs actions
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

findings = []
def do_login(page, email, pw):
    page.goto(BASE + "/Account/Login")
    page.wait_for_selector("input[name=Email]", timeout=20000)
    page.fill("input[name=Email]", email)
    page.fill("input[name=Password]", pw)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")

def sweep(page, area, paths):
    for path in paths:
        try:
            page.goto(BASE + path, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print("  goto failed", path, e); continue
        try:
            for r in page.evaluate(MEASURE):
                r["page_ctx"] = area
                findings.append(r)
        except Exception as e:
            print("  measure failed", path, e)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)

    prod = "/products"
    ctx = b.new_context(viewport={"width": 1360, "height": 900}); pg = ctx.new_page()
    pg.goto(BASE + "/products"); pg.wait_for_load_state("networkidle")
    prod = pg.get_attribute("a[href^='/products/']", "href") or "/products"
    sweep(pg, "public", ["/", "/products", "/products?sort=price_asc", "/services", "/gallery", "/about",
                         "/contact", "/faq", "/cart", "/Account/Login", "/Account/Register",
                         "/privacy", "/terms", "/install-help", "/definitely-missing-404", prod])
    ctx.close()

    ctx = b.new_context(viewport={"width": 1360, "height": 900}); pg = ctx.new_page()
    do_login(pg, CUST_EMAIL, CUST_PW)
    sweep(pg, "customer", ["/portal", "/portal/orders", "/portal/orders/track", "/portal/wishlist",
                           "/portal/addresses", "/portal/addresses/add", "/portal/payments", "/portal/invoices",
                           "/portal/profile", "/portal/notifications", "/portal/shop", "/cart", prod])
    pg.goto(BASE + "/portal"); pg.wait_for_load_state("networkidle")
    pg.click("#csMenuBtn"); pg.wait_for_timeout(300)
    for r in pg.evaluate(MEASURE): r["page_ctx"] = "customer/menu-open"; findings.append(r)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    pg.click("#portalNotifBell"); pg.wait_for_timeout(500)
    for r in pg.evaluate(MEASURE): r["page_ctx"] = "customer/notif-open"; findings.append(r)
    ctx.close()

    ctx = b.new_context(viewport={"width": 1360, "height": 900}); pg = ctx.new_page()
    do_login(pg, OWNER_EMAIL, OWNER_NEW)
    pg.goto(BASE + "/admin/products"); pg.wait_for_load_state("networkidle")
    pdet = pg.get_attribute("a[href^='/admin/products/']", "href") or "/admin/products"
    pg.goto(BASE + "/admin/customers"); pg.wait_for_load_state("networkidle")
    cdet = pg.get_attribute("a[href^='/admin/customers/']", "href")
    sweep(pg, "admin", ["/admin/dashboard", "/admin/activity", "/admin/notifications", "/admin/reports",
                        "/admin/sales", "/admin/orders", "/admin/invoices", "/admin/receipts",
                        "/admin/products", "/admin/products/create", pdet, pdet + "/edit",
                        "/admin/categories", "/admin/categories/create", "/admin/services", "/admin/gallery",
                        "/admin/customers"] + ([cdet] if cdet else []) + [
                        "/admin/messages", "/admin/reviews", "/admin/marketing", "/admin/announcements",
                        "/admin/team-messages", "/admin/inventory", "/admin/procurement", "/admin/users",
                        "/admin/settings", "/admin/security/password", "/admin/major-categories"])
    ctx.close()

    ctx = b.new_context(viewport={"width": 1360, "height": 900}); pg = ctx.new_page()
    do_login(pg, DEV_EMAIL, DEV_PW)
    sweep(pg, "dev", ["/dev", "/dev/health", "/dev/performance", "/dev/jobs", "/dev/logs", "/dev/errors",
                      "/dev/audit", "/dev/integrations", "/dev/payments", "/dev/email", "/dev/service-fees",
                      "/dev/database", "/dev/configuration", "/dev/maintenance", "/dev/account/password"])
    ctx.close()

    ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True); pg = ctx.new_page()
    sweep(pg, "mobile", ["/", "/products", prod, "/cart", "/Account/Login", "/services", "/gallery"])
    do_login(pg, CUST_EMAIL, CUST_PW)
    sweep(pg, "mobile-customer", ["/portal", "/portal/orders", "/portal/orders/track", "/portal/profile", "/portal/addresses"])
    ctx.close()

    ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True); pg = ctx.new_page()
    do_login(pg, OWNER_EMAIL, OWNER_NEW)
    sweep(pg, "mobile-admin", ["/admin/dashboard", "/admin/products", "/admin/orders", "/admin/settings"])
    ctx.close()

    ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True); pg = ctx.new_page()
    do_login(pg, DEV_EMAIL, DEV_PW)
    sweep(pg, "mobile-dev", ["/dev", "/dev/logs"])
    ctx.close()

    json.dump(findings, open("/tmp/ui_audit_findings2.json", "w"), indent=1)
    from collections import Counter
    print("== refined summary ==")
    for t, n in Counter(x["type"] for x in findings).most_common():
        print("%-24s %d" % (t, n))
    print("total:", len(findings))
    b.close()
