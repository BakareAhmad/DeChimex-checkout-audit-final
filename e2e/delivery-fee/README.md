# Evidence — Delivery Fee as an optional admin-configured add-on (2026-10-07)

One clean run: `DELIVERY_EVID=e2e/delivery-fee/shots python3 e2e/delivery-fee/delivery_e2e.py`
against a fresh in-memory app. 7 checks / 5 screenshots in `shots/`.

There is NO static/hard-coded delivery fee: seeded `delivery.default_fee` is `0`, every old
`1500` fallback now defaults to `0`, and the fee is applied to an order only when the
delivery add-on is selected (exactly once, in the grand total that Paystack charges).

| # | Shot | Shows |
|---|---|---|
| 01 | admin-settings-delivery-addon-default-zero | add-on defaults to 0 (no static fee) |
| 02 | admin-settings-delivery-set-2000 | owner configures 2000 and it saves |
| 03 | admin-neworder-addon-prefilled-2000 | ready-made add-on prefilled with configured value |
| 04 | admin-order-details-delivery-included | Delivery ₦2,000 + Subtotal ₦2,000 = Grand ₦4,000 (once) |
| 05 | admin-order-details-pickup-no-delivery | pickup carries no delivery charge |

Automated: `DeliveryFeeAddOnTests` (4 tests) — part of the 944/944 suite.
