"""Runs every chat-feature E2E harness in order against the one fresh app,
pointing each harness's evidence dir at E2E-Evidence/Feature-XX-*.
Exits non-zero if any harness reports a failure."""
import os
import re
import subprocess
import sys

ROOT = "/home/user/DeChimex-GalleryMobile"
EV = os.path.join(ROOT, "E2E-Evidence")
CAP = os.path.join(ROOT, "e2e/verification/brevo_captured.jsonl")
ENV = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=os.path.expanduser("~/.cache/ms-playwright"))

RUNS = [
    ("Feature-01-GalleryMobile", "e2e/gallery-mobile/gallery_e2e.py", {"GALLERY_EVID": f"{EV}/Feature-01-GalleryMobile"}),
    ("Feature-02-DeliveryFee", "e2e/delivery-fee/delivery_e2e.py", {"DELIVERY_EVID": f"{EV}/Feature-02-DeliveryFee"}),
    ("Feature-03-GradualSignup", "e2e/gradual-signup/gradual_signup_e2e.py",
     {"GRADUAL_EVID": f"{EV}/Feature-03-GradualSignup", "BREVO_CAPTURE": CAP}),
    ("Feature-04-HomeReviews", "e2e/home-reviews/home_reviews_e2e.py", {"REVIEWS_EVID": f"{EV}/Feature-04-HomeReviews"}),
    ("Feature-05-Announcements", "e2e/announcements/announcements_e2e.py", {"ANN_EVID": f"{EV}/Feature-05-Announcements"}),
    ("Feature-06-UiPolish", "e2e/ui-polish/ui_polish_e2e.py",
     {"POLISH_EVID": f"{EV}/Feature-06-UiPolish", "BREVO_CAPTURE": CAP}),
    ("Feature-07-TeamMessages", "e2e/team-messages/team_messages_e2e.py", {}),
]

failed = []
for name, script, extra in RUNS:
    env = dict(ENV, **extra)
    print(f"\n===== {name} =====", flush=True)
    proc = subprocess.run([sys.executable, os.path.join(ROOT, script)], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=900)
    out = proc.stdout + proc.stderr
    with open(os.path.join(ROOT, "e2e/verification", name + ".log"), "w") as lf:
        lf.write(out)
    for line in out.splitlines():
        if re.search(r"PASS|FAIL|RESULT|Error", line):
            print(line, flush=True)
    result = [l for l in out.splitlines() if "RESULT" in l]
    last = result[-1] if result else ""
    bad = "failed" in last and "0 failed" not in last
    ok = proc.returncode == 0 and result and not bad
    if not ok:
        failed.append(name)

print("\n===== SUMMARY =====")
for name, _, _ in RUNS:
    print(("OK   " if name not in failed else "FAIL ") + name)
sys.exit(1 if failed else 0)
