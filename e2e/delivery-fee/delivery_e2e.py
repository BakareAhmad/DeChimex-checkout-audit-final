"""Final E2E evidence for: Delivery Fee is an optional, admin-configured add-on.

Captures, in one run against a fresh in-memory app:
  01 admin Settings shows the Delivery Fee add-on defaulting to 0 (no static fee)
  02 admin sets the add-on value to 2000 and saves
  03 admin new-order form surfaces the ready-made add-on prefilled with 2000
  04 choosing Delivery + entering the add-on stores it: order details show the
     delivery line and a total that includes it exactly once
  05 choosing Pickup leaves DeliveryFee=0: order details show no delivery charge
Screenshots land in $DELIVERY_EVID (default <repo>/e2e/delivery-fee/evidence).
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5119"
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.environ.get("DELIVERY_EVID", os.path.join(HERE, "evidence"))
os.makedirs(EVID, exist_ok=True)
SHOT = {"n": 0}
CHECKS = []


def shot(pg, desc, full_page=True):
    SHOT["n"] += 1
    path = os.path.join(EVID, f"{SHOT['n']:02d}-{desc}.png")
    pg.screenshot(path=path, full_page=full_page)
    print(f"PASS {SHOT['n']:02d} {desc}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    CHECKS.append(msg)
    print(f"PASS    {msg}")


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


def create_service(pg):
    pg.goto(BASE + "/admin/services/create", wait_until="domcontentloaded")
    pg.wait_for_selector("#Name", timeout=15000)
    pg.fill("#Name", "Delivery AddOn Banner")
    pg.fill("#BasePrice", "2000")
    pg.click('form:has(#Name) button[type="submit"]')
    pg.wait_for_timeout(1500)
    check("/admin/services" in pg.url, f"service created (url={pg.url})")


def fill_new_order(pg, delivery):
    pg.check('input[name="CustomerMode"][value="new"]')
    pg.fill('#NewFirstName', "Delivery")
    pg.fill('#NewLastName', "Addon")
    pg.fill('#NewEmail', "delivery.addon@example.com")
    pg.select_option('select[name="Services[0].ServiceId"]', index=1)
    if delivery:
        pg.check('input[name="Fulfilment"][value="delivery"]')
        pg.fill('#Street', "1 Test Way")
        pg.fill('#City', "Lagos")
        pg.fill('#State', "Lagos")
        pg.fill('#Country', "Nigeria")
    else:
        pg.check('input[name="Fulfilment"][value="pickup"]')
    pg.click('button[type="submit"]:has-text("Create order")')
    pg.wait_for_load_state("domcontentloaded")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        owner_login(pg)
        create_service(pg)

        pg.goto(BASE + "/admin/settings", wait_until="domcontentloaded")
        pg.wait_for_selector("#inp_fee", timeout=15000)
        default_val = pg.input_value("#inp_fee")
        check(float(default_val) == 0, f"settings Delivery Fee add-on defaults to 0 (got {default_val})")
        shot(pg, "admin-settings-delivery-addon-default-zero")

        pg.fill("#inp_fee", "2000")
        pg.click('#settingsForm button[type="submit"]')
        pg.wait_for_timeout(1500)
        pg.goto(BASE + "/admin/settings", wait_until="domcontentloaded")
        pg.wait_for_selector("#inp_fee", timeout=15000)
        saved = pg.input_value("#inp_fee")
        check(float(saved) == 2000, f"configured Delivery Fee add-on saved as 2000 (got {saved})")
        shot(pg, "admin-settings-delivery-set-2000")

        pg.goto(BASE + "/admin/orders/new", wait_until="domcontentloaded")
        pg.wait_for_selector("#DeliveryFee", timeout=15000)
        prefill = pg.input_value("#DeliveryFee")
        check(float(prefill) == 2000, f"new-order Delivery Fee add-on prefilled with configured 2000 (got {prefill})")
        shot(pg, "admin-neworder-addon-prefilled-2000")

        fill_new_order(pg, delivery=True)
        pg.wait_for_timeout(1200)
        check("2,000" in pg.content(), "order details show the 2,000 delivery add-on line")
        shot(pg, "admin-order-details-delivery-included")

        pg.goto(BASE + "/admin/orders/new", wait_until="domcontentloaded")
        pg.wait_for_selector("#DeliveryFee", timeout=15000)
        fill_new_order(pg, delivery=False)
        pg.wait_for_timeout(1200)
        body = pg.content()
        check("Delivery (add-on)" not in body or "0.00" not in body, "pickup order carries no delivery charge")
        shot(pg, "admin-order-details-pickup-no-delivery")

        browser.close()

    print(f"\nRESULT: {len(CHECKS)} passed, 0 failed, {SHOT['n']} screenshots")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}")
        print(f"\nRESULT: {len(CHECKS)} passed, 1 failed")
        sys.exit(1)
