# Evidence — gradual signup + progressive profile completion (2026-10-07)

One clean run against a fresh in-memory app (Brevo stubbed on :8899):
`python3 e2e/gradual-signup/gradual_signup_e2e.py` → **23 checks passed, 10 screenshots** in `shots/`.

Signup now asks for **email + password only**. No confirm-password, name, phone or address.
Password rules are unchanged (min 8 + upper + lower + digit, enforced server-side). The rest of
the profile is collected at the point it becomes relevant — when the customer reaches checkout.

| # | Shot | Shows |
|---|---|---|
| 01 | signup-form-email-and-password-only | the whole form: Email, Password, Create account |
| 02 | signup-validation-weak-password-rejected | "weak" rejected inline — security not weakened |
| 03 | signup-existing-email-verification-step | existing gated-signup verification preserved |
| 04 | new-account-portal-no-profile-wall | signed in and browsing; no forced profile form |
| 05 | customer-cart-with-product | adds a product to the cart normally |
| 06 | checkout-prompts-complete-your-profile | "Complete your profile — a few more details"; name + phone only, no email/password |
| 07 | profile-completion-validation-error | invalid phone rejected inline |
| 08 | profile-saved-back-to-checkout | saving returns to /checkout — order not restarted |
| 09 | order-placed-after-profile-completion | the order completes (`/checkout/complete/{id}`) |
| 10 | complete-profile-no-prompt-at-checkout | a complete profile is never prompted again |

Automated coverage: `GradualSignupTests` (6 tests) inside the 950-test suite.
