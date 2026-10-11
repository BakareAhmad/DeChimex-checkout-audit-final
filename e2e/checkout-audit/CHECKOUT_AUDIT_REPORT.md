# Direct Store Checkout vs Custom Order Flow - Audit & E2E Verification Report

Date: 2026-10-11 · Solution: `DeChimexPrints` · Final E2E run: **36 passed, 0 failed** (single fresh-boot clean run, headed Chromium under xvfb, real Paystack TEST-mode hosted page)

## 1. Original flow (as built)

- **Direct purchase**: Shop catalog → product page (`Add to cart` / `Buy now` for standard products) → cart (multi-product, per-line qty 1..10000) → `/checkout` (delivery or pickup, contact/address info, totals = items + service fee + optional delivery fee) → `Pay` → Paystack hosted page → server-side verification at `/checkout/return` → order Paid → stock reserved/deducted, invoice + receipt issued, customer notified, fulfilment stages (In Production → dispatch → delivery) with tracking page and notifications. No Sales chat, no assignment, no manual price approval anywhere on this path.
- **Custom order**: customizable product page (`Order / Customize` CTA) → custom request form → Order created with `Kind=Custom` in AwaitingReview → Sales assignment → order workspace conversation (requirements, files/proofs, design review) → requirements & pricing finalized by staff → customer approves quote → Paystack payment → same fulfilment pipeline.
- One Order aggregate for both kinds (`OrderKind Direct|Custom`); no duplicate order tables or parallel systems. Eligibility enforced server-side at AddToCart and CreateOrder (`!IsCustomizable && !CategoryHasActiveOptions`); stock validated at add and deducted post-payment in `ConfirmPaidOrderAsync`; RowVersion + ConflictException guard duplicate/concurrent payment; ownership-first payment verification (a reference belonging to another customer behaves like an unknown reference).

## 2. Problems found & root causes

The application's direct checkout was found **correct as built**. Every failure observed in earlier automated runs traced to the test harness or environment, not to product code:

1. **Headless Chromium is blocked by Cloudflare on checkout.paystack.com** (human-verify challenge), so the gateway never loaded. Root cause fix: run the browser headed under `xvfb-run`, which passes the challenge. The Paystack TEST-mode page then exposes one-click outcomes (Success / Bank Authentication / Declined) that charge the app's real initialized transaction.
2. **Paystack Charge API cannot confirm the app's order** (dead end, documented): `POST /charge` with an access code creates a brand-new transaction instead of binding to the initialized one, leaving the app's reference abandoned and the return verification correctly NotFound. Abandoned in favour of the hosted test-mode buttons.
3. **Harness clicked the "Success"/"Declined" labels but never the green "Pay NGN …" button** that actually submits the test-mode selection → payments never completed. Fixed: select the outcome row, then click the Pay button, then wait for `/checkout/return`.
4. **Paystack TEST mode does not auto-redirect on a Declined outcome.** The customer's app-side payment row stays "Not completed" until verified. The harness now surfaces that row on the customer Payments page, takes its `PAY-…` reference and drives `/checkout/return?trxref=…` exactly as a real gateway redirect would, proving the app's failure branch ("Payment failed … still awaiting payment") and that the order remains unpaid with retry available.
5. **Selector/context bugs in the harness**: the "Track" tab link was mistaken for an order link; the admin order search by customer name matched nothing (search covers order number/email); the stock check was run in the owner context against a customer page (Access denied); the customer conversation check opened the order detail page instead of the workspace (`/portal/orders/{id}/workspace`). All fixed with guid-scoped link filters and correct contexts/routes.
6. Earlier "passing" inventory/return assertions had been pattern-matching incidental digits/text; they were tightened to exact UI signals ("Only 3 left", "Payment failed", admin "Direct purchase" + "Paid"/"Succeeded").

**Production code changes required: none.** The audit verified the existing architecture satisfies every criterion; all fixes this task are in `e2e/checkout-audit/checkout_e2e.py`.

## 3. Direct vs Custom distinction (verified in UI + data)

| Aspect | Direct | Custom |
|---|---|---|
| Entry CTA | Add to cart / Buy now | Order / Customize |
| Cart | allowed | server-rejected |
| OrderKind badge (admin list + detail) | "Direct" / "Direct purchase" | "Custom" / "Custom order" |
| Sales involvement | none | assignment + workspace conversation, requirements & pricing, design review |
| Payment | Paystack at checkout | Paystack after quote approval |
| Post-payment | identical single fulfilment pipeline, tracking, notifications, invoices | same |

Admin order detail (evidence shot 13) shows the Ordering badge, Paystack payment with app reference `PAY-…`, paid-at, fee expected/charged, invoice (Paid) and receipt documents, and line items with quantities.

## 4. Final test results (single clean run, fresh boot)

36 passed, 0 failed. Coverage: owner setup (login+rotation, category, 4 products incl. zero-stock and customizable); customer registration + email verification + progressive profile gate; direct CTAs and custom CTA separation; custom product blocked from cart (server gate); multi-product multi-qty cart; zero-stock add disabled; invalid qty (10001) rejected; checkout totals/fees; no Sales step for direct; Paystack success return; paid history; tracking; notification; invoice paid; admin Direct + Paid; inventory 5→3 ("Only 3 left"); duplicate-pay safety (no pay button on paid order); unknown reference handled plainly; declined payment recorded as not-completed, return page shows Payment failed, order stays unpaid with retry; retry success; custom request → workspace; staff reply visible to customer in the custom conversation.

Remaining failures: **none**.

## 5. Evidence

Ordered screenshots of the final run: `e2e/checkout-audit/shots/01 … 23` (direct journey 01–18, custom journey 19–23), plus `debug-paystack.png` (reference capture of the Paystack TEST-mode panel). Harness: `e2e/checkout-audit/checkout_e2e.py` (run via `xvfb-run -a`).
