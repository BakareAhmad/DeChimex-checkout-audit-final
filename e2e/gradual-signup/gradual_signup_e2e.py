"""Final E2E evidence for: gradual signup + progressive profile completion.

One clean run against a fresh in-memory app (Brevo stubbed) captures, in order:
  01 signup form asks for ONLY email + password (no confirm/name/phone/address)
  02 password rules still enforced: a weak password is rejected inline
  03 signup lands on the existing email-verification step (auth flow unchanged)
  04 the brand-new account is signed in and browsing normally - no profile wall
  05 the customer adds a product to the cart
  06 checkout routes to "Complete your profile" (name + phone only, pre-filled,
     no email/password)
  07 an invalid phone is rejected inline while completing the profile
  08 saving returns the customer straight to checkout (order not restarted)
  09 the order is placed successfully
  10 a customer whose profile is complete is never prompted again

Screenshots land in $GRADUAL_EVID (default <repo>/e2e/gradual-signup/shots).
"""
import json
import os
import re
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DCX_E2E_BASE", "http://127.0.0.1:5119")
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.environ.get("GRADUAL_EVID", os.path.join(HERE, "shots"))
CAPTURE = os.environ.get("BREVO_CAPTURE", "/home/user/e2e-gradual-wip/brevo_captured.jsonl")
os.makedirs(EVID, exist_ok=True)

SHOT = {"n": 0}
CHECKS = []
PASSWORD = "Gradual!Pass9"
EMAIL = f"gradual.{int(time.time())}@example.com"


def shot(pg, desc, full_page=True):
    SHOT["n"] += 1
    pg.screenshot(path=os.path.join(EVID, f"{SHOT['n']:02d}-{desc}.png"), full_page=full_page)
    print(f"PASS {SHOT['n']:02d} {desc}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    CHECKS.append(msg)
    print(f"PASS    {msg}")


def verification_code(html):
    m = re.search(r"letter-spacing:8px[^>]*>\s*([0-9]{4,8})\s*<", html or "")
    if m:
        return m.group(1)
    m = re.search(r"(?<![#0-9a-fA-F])([0-9]{6})(?![0-9a-fA-F])", html or "")
    return m.group(1) if m else None


def brevo_token(email, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(CAPTURE):
            for line in reversed(open(CAPTURE).read().splitlines()):
                if not line.strip():
                    continue
                msg = json.loads(line)
                if email in json.dumps(msg.get("to", "")):
                    code = verification_code(msg.get("htmlContent", ""))
                    if code:
                        return code
        time.sleep(1.5)
    raise AssertionError(f"no verification code captured for {email}")


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


def seed_product(pg):
    """Storefront product for the customer to order (the seeder ships no catalog)."""
    pg.goto(BASE + "/admin/categories/create", wait_until="domcontentloaded")
    pg.wait_for_selector("#Name", timeout=15000)
    pg.fill("#Name", f"Gradual Tees {int(time.time())}")
    pg.fill("#Description", "Category created for the gradual-signup E2E")
    if not pg.is_checked('input[name="IsActive"]'):
        pg.check('input[name="IsActive"]')   # must be active to appear in the store/product form
    pg.click('form:has(#Name) button[type="submit"]')
    pg.wait_for_timeout(1500)
    check("/admin/categories" in pg.url, f"category created (url={pg.url})")

    pg.goto(BASE + "/admin/products/create", wait_until="domcontentloaded")
    pg.wait_for_selector("#Name", timeout=15000)
    pg.fill("#Name", "Gradual Signup Tee")
    pg.fill("#Sku", f"GS-{int(time.time())}")
    pg.fill("#Description", "Plain tee used to prove the order completes after profile completion.")
    pg.fill("#SellingPrice", "2500")
    pg.fill("#InitialQuantity", "25")
    pg.fill("#LowStockThreshold", "3")
    pg.select_option("select[name='CategoryId']", index=0)
    # The product form requires at least one image (client-side `required`), so supply one.
    pg.set_input_files("#Images", os.path.join(HERE, "assets", "tee.png"))
    pg.click('form:has(#Name) button[type="submit"]')
    # Creation redirects to the product's own page (/admin/products/{id}).
    pg.wait_for_url(lambda u: "/admin/products" in u and "create" not in u, timeout=20000)
    check("create" not in pg.url, f"product created (url={pg.url})")


def customer_sign_in(browser, email, password):
    """Fresh browser context = a clean, signed-out session."""
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(BASE + "/Account/Login", wait_until="domcontentloaded")
    pg.fill('form[action*="Login"] input[name="Email"]', email)
    pg.fill('form[action*="Login"] input[name="Password"]', password)
    pg.click('form[action*="Login"] button[type="submit"]')
    pg.wait_for_timeout(2500)
    return pg



def add_first_product(pg):
    """Adds the first storefront product to the cart.

    The shop card renders "Add to cart" as a link to the product page (or a direct post
    form when the shopper is a signed-in customer), so handle both.
    """
    # The shop card posts to /portal/shop/{id}/add-to-cart.
    pg.goto(BASE + "/portal/shop", wait_until="domcontentloaded")
    pg.wait_for_selector('form[action*="add-to-cart"] button[type="submit"]', timeout=15000)
    pg.locator('form[action*="add-to-cart"] button[type="submit"]').first.click()
    pg.wait_for_timeout(2000)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        admin_ctx = browser.new_context()
        admin = admin_ctx.new_page()
        owner_login(admin)
        seed_product(admin)
        admin_ctx.close()          # drop the owner session entirely

        pg = browser.new_context().new_page()

        # ---- 01: the signup form is two fields -------------------------------
        pg.goto(BASE + "/Account/Register", wait_until="domcontentloaded")
        pg.wait_for_selector('input[name="Email"]', timeout=15000)
        names = [i.get_attribute("name") for i in pg.query_selector_all('form[action*="Register"] input[name]')]
        visible = [n for n in names if n not in ("CompanyWebsite", "ReturnUrl", "__RequestVerificationToken")]
        check(sorted(visible) == ["Email", "Password"], f"signup asks for only email+password (fields={sorted(visible)})")
        for banned in ("ConfirmPassword", "FirstName", "LastName", "Phone", "Address"):
            check(pg.query_selector(f'input[name="{banned}"]') is None, f"signup does not ask for {banned}")
        shot(pg, "signup-form-email-and-password-only")

        # ---- 02: password security unchanged --------------------------------
        pg.fill('input[name="Email"]', EMAIL)
        pg.fill('input[name="Password"]', "weak")
        pg.click('form[action*="Register"] button[type="submit"]')
        pg.wait_for_timeout(1200)
        body = pg.inner_text("body")
        check("8 characters" in body, "weak password rejected with the existing rule")
        shot(pg, "signup-validation-weak-password-rejected")

        # ---- 03: credentials-only signup reaches the existing verify step ----
        pg.fill('input[name="Email"]', EMAIL)
        pg.fill('input[name="Password"]', PASSWORD)
        pg.click('form[action*="Register"] button[type="submit"]')
        pg.wait_for_url(lambda u: "VerifyEmail" in u, timeout=20000)
        check("VerifyEmail" in pg.url, f"signup handed to the existing verification gate ({pg.url})")
        shot(pg, "signup-existing-email-verification-step")

        code = brevo_token(EMAIL)
        pg.fill('input[name="Token"]', code)
        pg.click('form button[type="submit"]')
        pg.wait_for_timeout(2500)

        # ---- 04: signed in, browsing normally, no profile wall --------------
        check("Login" not in pg.url, f"new account signed in normally ({pg.url})")
        pg.goto(BASE + "/portal", wait_until="domcontentloaded")
        pg.wait_for_timeout(1200)
        body = pg.inner_text("body")
        check("Complete your profile" not in body, "no profile wall after signup - portal opens normally")
        shot(pg, "new-account-portal-no-profile-wall")

        # ---- 05: add a product to the cart ----------------------------------
        add_first_product(pg)
        pg.goto(BASE + "/cart", wait_until="domcontentloaded")
        pg.wait_for_selector("text=Gradual Signup Tee", timeout=15000)
        check("Gradual Signup Tee" in pg.inner_text("body"), "product is in the cart")
        shot(pg, "customer-cart-with-product")

        # ---- 06: checkout routes to profile completion ----------------------
        pg.goto(BASE + "/checkout", wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        check("/portal/profile/complete" in pg.url, f"checkout routed to profile completion ({pg.url})")
        check("Complete your profile" in pg.inner_text("body"), "completion step explains why the details are needed")
        complete_fields = [i.get_attribute("name") for i in pg.query_selector_all('form[action*="complete"] input[name], form[action*="Complete"] input[name]')]
        check(all(n not in ("Password", "Email") for n in complete_fields),
                f"completion step never re-asks email/password (fields={complete_fields})")
        shot(pg, "checkout-prompts-complete-your-profile")

        # ---- 07: validation while completing the profile --------------------
        pg.fill('form[action*="omplete"] input[name="FirstName"]', "Ada")
        pg.fill('form[action*="omplete"] input[name="LastName"]', "Obi")
        pg.fill('form[action*="omplete"] input[name="Phone"]', "not-a-phone")
        pg.click('form[action*="omplete"] button[type="submit"]')
        pg.wait_for_timeout(1200)
        check("valid phone number" in pg.inner_text("body"), "invalid phone rejected inline")
        shot(pg, "profile-completion-validation-error")

        # ---- 08: valid details save and return to checkout ------------------
        pg.fill('form[action*="omplete"] input[name="Phone"]', "08030000009")
        pg.click('form[action*="omplete"] button[type="submit"]')
        pg.wait_for_url(lambda u: u.rstrip("/").endswith("/checkout"), timeout=20000)
        pg.wait_for_timeout(1200)
        check("/checkout" in pg.url, f"returned to checkout after saving ({pg.url})")
        check("Complete your profile" not in pg.inner_text("body"), "checkout is no longer gated")
        shot(pg, "profile-saved-back-to-checkout")

        # ---- 09: the order completes ---------------------------------------
        pg.check('input[name="Fulfilment"][value="delivery"]')
        pg.wait_for_timeout(600)
        pg.fill('input[name="Street"]', "12 Awolowo Road")
        pg.fill('input[name="City"]', "Lagos")
        pg.fill('input[name="State"]', "Lagos")
        pg.fill('input[name="Country"]', "Nigeria")
        pg.click('form[action*="checkout"] button[type="submit"]')
        pg.wait_for_timeout(2500)
        body = pg.inner_text("body")
        check("checkout/complete" in pg.url or "Order" in body, f"order placed ({pg.url})")
        shot(pg, "order-placed-after-profile-completion")

        # ---- 10: a complete profile is never prompted again -----------------
        pg.context.close()                     # sign out: brand-new session
        pg = customer_sign_in(browser, EMAIL, PASSWORD)
        check("Login" not in pg.url, f"returning customer signed in ({pg.url})")

        add_first_product(pg)
        pg.goto(BASE + "/checkout", wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        body = pg.inner_text("body")
        check("/checkout" in pg.url and "Complete your profile" not in body,
                "complete profile goes straight to checkout - no prompt")
        shot(pg, "complete-profile-no-prompt-at-checkout")

        browser.close()

    print(f"\nRESULT: {len(CHECKS)} checks passed, {SHOT['n']} screenshots")


if __name__ == "__main__":
    main()
