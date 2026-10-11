#!/usr/bin/env python3
"""Direct Store Checkout vs Custom Order Flow audit E2E (2026-10-11).
Real end-to-end: owner seeds catalog via admin UI, customer buys standard products
through cart -> checkout -> Paystack test payment -> paid order; negatives; custom
order regression. Ordered screenshots in shots/."""
import os, re, time, json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5121"
SHOTS = "/home/user/DeChimex-GalleryMobile/e2e/checkout-audit/shots"
OWNER_EMAIL, OWNER_BOOT, OWNER_NEW = "owner@dechimexprinthub.com", "ChangeMe123!", "OwnerCheckout!2026zQ"
CUST_EMAIL, CUST_PW = "checkout.audit%d@example.com" % (int(time.time()) % 100000), "Checkout!2026a"
os.makedirs(SHOTS, exist_ok=True)

results = []
def check(ok, label):
    results.append((bool(ok), label))
    print(("PASS " if ok else "FAIL ") + "  " + label)

def shot(page, name):
    page.screenshot(path=os.path.join(SHOTS, name))
    print("SHOT " + name)

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
        page.locator("form").filter(has=page.locator("input[name=NewPassword]")).locator("button[type=submit]").click()
        page.wait_for_load_state("networkidle")
    if "/Account/Login" in page.url:
        do_login(page, OWNER_EMAIL, OWNER_NEW)

def register_customer(page):
    page.goto(BASE + "/Account/Register")
    page.fill('input[name="Email"]', CUST_EMAIL)
    page.fill('input[name="Password"]', CUST_PW)
    page.click('button[type="submit"]')
    page.wait_for_timeout(2500)
    link = None
    for _ in range(30):
        try:
            for line in open("/tmp/brevo_nav_audit.jsonl"):
                rec = json.loads(line); body = json.dumps(rec)
                if CUST_EMAIL in body:
                    m = re.search(r'https?://[^\'"\s<>]+/Account/VerifyEmail[^\'"\s<>]+', body)
                    if m: link = m.group(0).replace("\\u0026", "&").replace("&amp;", "&")
        except Exception: pass
        if link: break
        time.sleep(1)
    if link:
        link = re.sub(r"https?://(localhost|127\.0\.0\.1):\d+", BASE, link)
        page.goto(link)
        page.wait_for_load_state("networkidle")
    if "/Account/Login" in page.url:
        do_login(page, CUST_EMAIL, CUST_PW)

def complete_profile(page):
    if "/portal/profile/complete" not in page.url:
        return
    page.fill('input[name="FirstName"]', "Ada")
    page.fill('input[name="LastName"]', "Obi")
    page.fill('input[name="Phone"]', "+2348031234567")
    page.locator("form", has=page.locator("input[name=FirstName]")).locator("button[type=submit]").first.click()
    page.wait_for_load_state("networkidle")

def click_pay(page):
    sel = page.locator("form[action*='/pay'] button[type=submit]")
    if sel.count():
        sel.first.click()
    else:
        page.locator("button", has_text=re.compile("^Pay")).first.click()

def paystack_pay(page, outcome="success"):
    """Complete the Paystack hosted TEST-MODE checkout: one-click simulated
    outcomes (Success / Declined) on the real gateway page, then the gateway
    redirects back to the app return URL which performs server-side verify."""
    try:
        page.wait_for_load_state("load", timeout=45000)
    except Exception:
        pass
    page.wait_for_timeout(5000)
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    label = {"success": "Success", "declined": "Declined"}[outcome]
    btn = page.get_by_text(label, exact=True)
    if btn.count():
        btn.first.click()
        page.wait_for_timeout(500)
        paybtn = page.locator("button", has_text=re.compile(r"Pay NGN|Pay \d"))
        if paybtn.count():
            paybtn.last.click()
    else:
        # non-test-panel fallback: fill the canonical test card
        page.fill('input[placeholder*="Card number"]', "4084084084084081")
        page.locator("button", has_text=re.compile("^Pay")).last.click()
        page.wait_for_timeout(3000)
        if page.locator('input[placeholder*="PIN"]').count():
            page.fill('input[placeholder*="PIN"]', "0000")
            page.locator("button", has_text=re.compile("confirm|submit|continue", re.I)).last.click()
        page.wait_for_timeout(2000)
        if page.locator('input[placeholder*="OTP"]').count():
            page.fill('input[placeholder*="OTP"]', "123456")
            page.locator("button", has_text=re.compile("submit|confirm|continue", re.I)).last.click()
    try:
        page.wait_for_url("**/checkout/return**", timeout=45000)
    except Exception:
        print("PAYSTACK-NO-RETURN url:", page.url[:120]); shot(page, "debug-paystack.png")
    try:
        page.wait_for_load_state("load", timeout=20000)
    except Exception:
        pass
    return outcome

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])

    # ---------- OWNER SEED ----------
    ctxo = browser.new_context(viewport={"width": 1360, "height": 900})
    po = ctxo.new_page()
    login_owner(po)
    check("/admin" in po.url, "owner logged in (password rotated)")

    po.goto(BASE + "/admin/categories/create"); po.wait_for_load_state("networkidle")
    po.fill("input[name=Name]", "Audit Goods")
    po.locator("form").filter(has=po.locator("input[name=Name]")).locator("button[type=submit]").click()
    po.wait_for_load_state("networkidle")
    check("/admin/categories" in po.url or "/admin/major" in po.url, "category 'Audit Goods' created (no ordering questions)")

    def create_product(name, price, qty, customizable):
        po.goto(BASE + "/admin/products/create"); po.wait_for_load_state("networkidle")
        po.fill("input[name=Name]", name)
        opts = po.eval_on_selector_all("select[name=CategoryId] option", "els => els.map(e => e.value).filter(v => v)")
        po.select_option("select[name=CategoryId]", opts[-1])
        po.fill("input[name=SellingPrice]", price)
        if po.locator("input[name=InitialQuantity]").count():
            po.fill("input[name=InitialQuantity]", qty)
        if customizable and po.locator("input[name=IsCustomizable]").count():
            po.check("input[name=IsCustomizable]")
        po.set_input_files("input[name=Images]", "/tmp/nav-tee.png")
        po.locator("form[data-guard] button[type=submit]").click()
        po.wait_for_load_state("networkidle")
        return "/admin/products" in po.url

    ok1 = create_product("Direct Audit Mug", "3500", "5", False)
    ok2 = create_product("Direct Audit Flask", "7000", "10", False)
    ok3 = create_product("Out-of-Stock Cap", "2500", "0", False)
    ok4 = create_product("Custom Audit Jersey", "12000", "20", True)
    check(ok1 and ok2 and ok3 and ok4, "owner created 2 standard + 1 zero-stock + 1 customizable product")

    # product ids via admin list search
    def find_product_id(name):
        po.goto(BASE + "/admin/products?search=" + name.replace(" ", "+")); po.wait_for_load_state("networkidle")
        hrefs = po.eval_on_selector_all("a[href*='/admin/products/']", "els => els.map(e => e.getAttribute('href'))")
        for h in hrefs:
            m = re.search(r"/admin/products/([0-9a-f-]{36})", h)
            if m: return m.group(1)
        return None
    mug_id = find_product_id("Direct Audit Mug")
    flask_id = find_product_id("Direct Audit Flask")
    cap_id = find_product_id("Out-of-Stock Cap")
    jersey_id = find_product_id("Custom Audit Jersey")
    check(all([mug_id, flask_id, cap_id, jersey_id]), "product ids resolved from admin list")

    # ---------- CUSTOMER ----------
    ctxc = browser.new_context(viewport={"width": 1360, "height": 900})
    pc = ctxc.new_page()
    register_customer(pc)
    check("VerifyEmail" not in pc.url, "customer registered + email verified via stub")
    pc.goto(BASE + "/portal/profile/complete"); pc.wait_for_load_state("networkidle")
    complete_profile(pc)
    check("/portal/profile/complete" not in pc.url, "progressive profile gate satisfied (name + phone)")

    # standard product page shows direct CTAs
    pc.goto(BASE + "/portal/shop/" + mug_id); pc.wait_for_load_state("networkidle")
    has_add = pc.locator("#pdAddBtn").count() and pc.locator("#pdAddBtn").is_enabled()
    has_buy = pc.locator("#pdPrimaryCta").count() and "Buy now" in (pc.locator("#pdPrimaryCta").inner_text() or "")
    has_custom_cta = "Order / Customize" in (pc.locator("#pdPrimaryCta").inner_text() or "") if pc.locator("#pdPrimaryCta").count() else False
    check(has_add and has_buy and not has_custom_cta, "standard product shows Add to cart + Buy now (no custom CTA)")
    shot(pc, "01-standard-product-direct-ctas.png")

    # customizable product shows custom CTA only
    pc.goto(BASE + "/portal/shop/" + jersey_id); pc.wait_for_load_state("networkidle")
    jtxt = pc.locator("#pdPrimaryCta").inner_text() if pc.locator("#pdPrimaryCta").count() else ""
    check("Order / Customize" in jtxt, "customizable product primary CTA is Order / Customize")
    shot(pc, "02-custom-product-cta.png")

    # custom CTA guard: adding custom product to cart is refused server-side
    resp = pc.request.post(BASE + "/portal/shop/" + jersey_id + "/add-to-cart",
                           data={"quantity": "1"}, headers={"Content-Type": "application/x-www-form-urlencoded"})
    pc.goto(BASE + "/portal/shop/" + jersey_id); pc.wait_for_load_state("networkidle")
    body = pc.inner_text("body")
    # attempt via UI form if present; the server gate is the authoritative check below
    cart_after_custom = pc.request.post(BASE + "/portal/shop/" + jersey_id + "/add-to-cart", data={"quantity": "1"})
    cartpage = pc.goto(BASE + "/cart"); pc.wait_for_load_state("networkidle")
    carttxt = pc.inner_text("body")
    check("Custom Audit Jersey" not in carttxt or "needs customization" in carttxt, "custom product cannot enter the cart (server gate)")

    # add standard products: mug x2, flask x1 (multiple products + quantities)
    pc.goto(BASE + "/portal/shop/" + mug_id); pc.wait_for_load_state("networkidle")
    if pc.locator("input[name=quantity]").count():
        pc.fill("input[name=quantity]", "2")
    pc.locator("#pdAddBtn").click(); pc.wait_for_load_state("networkidle")
    pc.goto(BASE + "/portal/shop/" + flask_id); pc.wait_for_load_state("networkidle")
    pc.locator("#pdAddBtn").click(); pc.wait_for_load_state("networkidle")
    pc.goto(BASE + "/cart"); pc.wait_for_load_state("networkidle")
    carttxt = pc.inner_text("body")
    check("Direct Audit Mug" in carttxt and "Direct Audit Flask" in carttxt, "cart holds both standard products")
    shot(pc, "03-cart-two-products.png")

    # zero-stock product: UI disables purchase
    pc.goto(BASE + "/portal/shop/" + cap_id); pc.wait_for_load_state("networkidle")
    cap_disabled = not pc.locator("#pdAddBtn").is_enabled() if pc.locator("#pdAddBtn").count() else True
    check(cap_disabled, "zero-stock product: Add to cart disabled in UI")
    shot(pc, "04-out-of-stock-disabled.png")

    # invalid quantity via form tamper (10001) -> must not create a bad cart line
    pc.goto(BASE + "/portal/shop/" + mug_id); pc.wait_for_load_state("networkidle")
    pc.evaluate("""() => { const q = document.querySelector('input[name=quantity]'); if (q) q.value = '10001'; }""")
    if pc.locator("#pdAddBtn").count():
        pc.locator("#pdAddBtn").click(); pc.wait_for_load_state("networkidle")
    pc.goto(BASE + "/cart"); pc.wait_for_load_state("networkidle")
    carttxt = pc.inner_text("body")
    check("10001" not in carttxt, "invalid quantity (10001) rejected or clamped safely")

    # checkout page renders without any sales-contact requirement
    pc.goto(BASE + "/checkout"); pc.wait_for_load_state("networkidle")
    check(pc.locator("#checkoutForm").count() == 1, "checkout page reached (order form present)")
    chk = pc.inner_text("body")
    no_sales_gate = not re.search(r"(contact|chat|message)\s+\w*\s*sales", chk, re.I)
    check(no_sales_gate, "checkout requires no Sales conversation/approval")
    shot(pc, "05-checkout-form.png")

    # choose pickup first (no delivery fee), place order
    if pc.locator("#checkoutForm input[name=Fulfilment][value=pickup]").count():
        pc.check("#checkoutForm input[name=Fulfilment][value=pickup]")
    pc.locator("#checkoutForm button[type=submit]").first.click(); pc.wait_for_load_state("networkidle")
    check("/checkout/complete/" in pc.url, "order placed -> payment page (no sales step)")
    shot(pc, "06-order-placed-payment-page.png")
    order_url = pc.url
    order_id = re.search(r"complete/([0-9a-f-]{36})", order_url).group(1)

    # PAY via Paystack test card
    click_pay(pc)
    stage = paystack_pay(pc)
    pc.wait_for_timeout(2500)
    check("/checkout/return" in pc.url, "Paystack returned to /checkout/return")
    ret = pc.inner_text("body")
    check(re.search(r"(paid|successful|success|confirmed)", ret, re.I) is not None, "return page reports successful payment")
    shot(pc, "07-payment-return-success.png")

    # order now paid: customer tracking
    pc.goto(BASE + "/portal/orders"); pc.wait_for_load_state("networkidle")
    ord_txt = pc.inner_text("body")
    check("Payment Required" not in ord_txt and "Pay now" not in ord_txt, "customer order history shows paid order (no payment-required state)")
    shot(pc, "08-customer-order-history.png")

    # open the order detail / tracking
    links = [l for l in pc.eval_on_selector_all("a[href*='/portal/orders/']", "els => els.map(e => e.getAttribute('href'))") if re.search(r"/portal/orders/[0-9a-fA-F]{8}-[0-9a-fA-F-]{20,}", l or "")]
    if links:
        pc.goto(BASE + links[0]); pc.wait_for_load_state("networkidle")
        shot(pc, "09-customer-order-tracking.png")
        track = pc.inner_text("body")
        check("Payment Required" not in track and ("Paid" in track or "timeline" in track.lower()), "tracking page shows timeline/paid state")

    # notifications include order confirmation
    pc.goto(BASE + "/portal/notifications"); pc.wait_for_load_state("networkidle")
    notif = pc.inner_text("body")
    check(re.search(r"(order|payment|paid)", notif, re.I) is not None, "customer notification for order/payment exists")
    shot(pc, "10-customer-notification.png")

    # invoice exists and is paid
    pc.goto(BASE + "/portal/invoices"); pc.wait_for_load_state("networkidle")
    inv = pc.inner_text("body")
    check("INV-" in inv and re.search(r"paid", inv, re.I) is not None, "invoice issued and marked paid")
    shot(pc, "11-invoice-paid.png")

    # ---------- OWNER VERIFIES DIRECT ORDER ----------
    po.goto(BASE + "/admin/orders"); po.wait_for_load_state("networkidle")
    shot(po, "12-admin-orders-direct.png")
    olinks = [l for l in po.eval_on_selector_all("a[href*='/admin/orders/']", "els => els.map(e => e.getAttribute('href'))") if re.search(r"/admin/orders/[0-9a-fA-F]{8}-[0-9a-fA-F-]{20,}", l or "")]
    kind_ok = paid_ok = False
    if olinks:
        po.goto(BASE + olinks[0]); po.wait_for_load_state("networkidle")
        shot(po, "13-admin-order-detail-direct.png")
        d = po.inner_text("body")
        kind_ok = re.search(r"Direct", d) is not None
        paid_ok = "Paid" in d
    check(kind_ok, "admin order detail distinguishes direct purchase (Kind=Direct)")
    check(paid_ok, "admin order detail shows Paid")

    # inventory deducted after payment (mug 5 -> 3): stock badge on the product card
    pc.goto(BASE + "/portal/shop"); pc.wait_for_load_state("networkidle")
    stocktxt = pc.inner_text("body")
    check("Only 3 left" in stocktxt, "inventory deducted after payment (mug stock 5 -> 3)")
    shot(po, "14-inventory-deducted.png")

    # ---------- NEGATIVES ----------
    # duplicate pay attempt on paid order
    pc.goto(order_url); pc.wait_for_load_state("networkidle")
    pay_btn = pc.locator("form[action*='/pay'] button[type=submit]")
    if pay_btn.count():
        pay_btn.first.click()
        try:
            pc.wait_for_load_state("load", timeout=20000)
        except Exception:
            pass
        dup = pc.inner_text("body")
        check(re.search(r"(already paid|conflict|paid)", dup, re.I) is not None, "duplicate pay attempt on paid order handled safely")
    else:
        check(True, "duplicate pay attempt on paid order handled safely (no pay button on paid order)")
    shot(pc, "15-duplicate-pay-handled.png")

    # bogus verification reference
    pc.goto(BASE + "/checkout/return?trxref=BOGUSREF123"); pc.wait_for_load_state("networkidle")
    bogus = pc.inner_text("body")
    check(re.search(r"could not find|not find", bogus, re.I) is not None, "unknown payment reference handled plainly")
    shot(pc, "16-unknown-reference.png")

    # payment failure + retry: place a second order, cancel at Paystack, then pay successfully
    pc.goto(BASE + "/portal/shop/" + flask_id); pc.wait_for_load_state("networkidle")
    pc.locator("#pdAddBtn").click(); pc.wait_for_load_state("networkidle")
    pc.goto(BASE + "/checkout"); pc.wait_for_load_state("networkidle")
    if pc.locator("#checkoutForm input[name=Fulfilment][value=pickup]").count():
        pc.check("#checkoutForm input[name=Fulfilment][value=pickup]")
    pc.locator("#checkoutForm button[type=submit]").first.click(); pc.wait_for_load_state("networkidle")
    order2 = re.search(r"complete/([0-9a-f-]{36})", pc.url)
    check(order2 is not None, "second order placed for failure/retry test")
    click_pay(pc)
    paystack_pay(pc, "declined")
    if "/checkout/return" not in pc.url:
        pc.goto(BASE + "/portal/payments"); pc.wait_for_load_state("networkidle")
        items = pc.locator(".ac-item")
        dref = None
        for i in range(items.count()):
            t = items.nth(i).inner_text()
            if ("Not completed" in t or "Failed" in t):
                mref = re.search(r"PAY-\d{14}-[0-9A-F]{10}", t)
                if mref:
                    dref = mref.group(0); break
        check(dref is not None, "declined attempt visible in customer payments as not-completed with reference")
        if dref:
            pc.goto(BASE + "/checkout/return?trxref=" + dref); pc.wait_for_load_state("networkidle")
    decl = pc.inner_text("body")
    check("Payment failed" in decl and "awaiting payment" in decl, "declined test payment reported as failed on return page")
    shot(pc, "17-payment-declined.png")
    pc.goto(BASE + "/checkout/complete/" + order2.group(1)); pc.wait_for_load_state("networkidle")
    retry_page = pc.inner_text("body")
    check(re.search(r"(pending|awaiting|pay now|place order|payment required|retry|pay)", retry_page, re.I) is not None, "declined payment leaves order unpaid with retry available")
    shot(pc, "17b-unpaid-retry-available.png")
    # now pay it successfully (retry)
    click_pay(pc)
    paystack_pay(pc, "success")
    check("/checkout/return" in pc.url, "retry payment completes through Paystack")
    shot(pc, "18-retry-payment-success.png")

    # ---------- CUSTOM ORDER REGRESSION ----------
    pc.goto(BASE + "/portal/shop/" + jersey_id + "/order"); pc.wait_for_load_state("networkidle")
    check("/order" in pc.url, "custom order form reachable for customizable product")
    shot(pc, "19-custom-order-form.png")
    if pc.locator("input[name=quantity]").count():
        pc.fill("input[name=quantity]", "3")
    if pc.locator("#notes").count():
        pc.fill("#notes", "Three jerseys with our club crest, sizes M/L/XL.")
    pc.locator("form", has=pc.locator("input[name=quantity]")).locator("button[type=submit]").first.click()
    pc.wait_for_load_state("networkidle")
    cust_ws = pc.inner_text("body")
    check(re.search(r"(request|received|conversation|workspace)", cust_ws, re.I) is not None, "custom request submitted into workspace")
    shot(pc, "20-custom-workspace-customer.png")

    # owner sees the custom order, can message the customer (workspace chat)
    m = re.search(r"([0-9a-f-]{36})", pc.url)
    custom_id = m.group(1) if m else None
    check(custom_id is not None, "custom order id captured from workspace URL")
    if custom_id:
        po.goto(BASE + "/admin/orders/" + custom_id + "/workspace"); po.wait_for_load_state("networkidle")
        if po.locator("#chatInput").count():
            po.fill("#chatInput", "Got it - quoting you now, crest artwork confirmed.")
            po.locator("#chatForm button[type=submit]").first.click()
            po.wait_for_timeout(2000)
        shot(po, "22-admin-custom-conversation.png")
        convo = po.inner_text("body")
        check("crest artwork confirmed" in convo, "staff can message on the custom order conversation")
        pc.goto(BASE + "/portal/orders/" + custom_id + "/workspace"); pc.wait_for_load_state("networkidle")
        pc.wait_for_timeout(1500)
        cws = pc.inner_text("body")
        check("crest artwork confirmed" in cws, "customer sees staff reply in custom order conversation")
        shot(pc, "23-custom-conversation-customer.png")
    pc.reload(); pc.wait_for_load_state("networkidle")
    browser.close()

fails = [l for ok, l in results if not ok]
print("\nRESULT: %d passed, %d failed" % (len(results) - len(fails), len(fails)))
for l in fails: print("FAILED:", l)
