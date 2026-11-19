r"""Dormora Frontend File 04 v2 - guarded local login UI update.

Changes ONLY frontend/src/pages/LoginPage.jsx, using its current contents.
Run from the frontend directory:
    python .\Dormora_File04_LoginLockout_UI_Apply_v2.py

This is a safer successor to File04 v1: it does not match large blocks of
whitespace-sensitive JSX. All changes are prepared in memory and are written
only when EVERY expected anchor is found exactly once. A backup is stored
outside the repository. No backend, OTP, CAPTCHA, CSS, or session code is
replaced. The browser-view rejection count is not a DB account counter.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
import re
import shutil
import sys

MARKER = "DORMORA_LOGIN_UI_LOCKOUT_V2"
CANDIDATES = [Path("src/pages/LoginPage.jsx"), Path("frontend/src/pages/LoginPage.jsx")]


def replace_one(text: str, expression: str, replacement: str | callable, label: str, flags: int = 0) -> str:
    pattern = re.compile(expression, flags)
    count = len(pattern.findall(text))
    if count != 1:
        raise ValueError(f"STOP: {label} - expected one matching anchor, found {count}. No changes made.")
    return pattern.sub(replacement, text, count=1)


def patch(source: str) -> str:
    if MARKER in source:
        print("FILE 04 v2 is already installed. No changes made.")
        return source
    if "DORMORA_LOGIN_UI_LOCKOUT_V1" in source:
        raise ValueError("STOP: An earlier File04 patch is already present. No changes made.")
    if "function LoginPage(" not in source or "export default LoginPage;" not in source:
        raise ValueError("STOP: Unexpected LoginPage component. No changes made.")

    # 1: Add local-only state alongside the existing ref (without changing old state).
    source = replace_one(
        source,
        r'(?m)^([ \t]*)const otpRef = useRef\(null\);[ \t]*$',
        lambda m: (
            f'{m.group(1)}// {MARKER}: local response feedback; backend remains authoritative.\n'
            f'{m.group(1)}const [rejectedHere, setRejectedHere] = useState(0);\n'
            f'{m.group(1)}const [loginWaitUntil, setLoginWaitUntil] = useState(0);\n'
            f'{m.group(1)}const [loginClock, setLoginClock] = useState(Date.now);\n'
            f'{m.group(1)}const otpRef = useRef(null);'
        ),
        "login component state",
    )

    # 2: Hook inserted before showError; avoids matching fragile existing effects.
    timer_block = '''  // The countdown is advisory UI; FastAPI still enforces every restriction.
  useEffect(() => {
    if (!loginWaitUntil) return undefined;
    const interval = window.setInterval(() => {
      const now = Date.now();
      setLoginClock(now);
      if (now >= loginWaitUntil) setLoginWaitUntil(0);
    }, 1000);
    return () => window.clearInterval(interval);
  }, [loginWaitUntil]);

  const loginWaitSeconds = Math.max(0,
    Math.ceil((loginWaitUntil - loginClock) / 1000));
  const loginRestricted = loginWaitSeconds > 0;

'''
    source = replace_one(
        source, r'(?m)^[ \t]*function showError\(message\)[ \t]*\{',
        lambda m: timer_block + m.group(0), "login countdown insertion",
    )

    # 3: Only change the password submit callback, never OTP submit/verification.
    start_marker = "async function handlePasswordSubmit(event)"
    end_marker = "async function handleOtpSubmit(event)"
    if source.count(start_marker) != 1 or source.count(end_marker) != 1:
        raise ValueError("STOP: Password/OTP handler boundaries differ. No changes made.")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    handler = source[start:end]
    handler = replace_one(
        handler,
        r'if\s*\(\s*pending\.current\s*\|\|\s*!LOCAL_LOGIN_ENABLED\s*\)\s*return;',
        'if (pending.current || !LOCAL_LOGIN_ENABLED || loginRestricted) return;',
        "password-submit restriction guard",
    )
    handler = replace_one(
        handler, r'setStage\("otp"\);',
        'setStage("otp");\n        setRejectedHere(0);\n        setLoginWaitUntil(0);',
        "successful password-step transition",
    )
    handler = replace_one(
        handler, r'showError\("Invalid username or password\."\);',
        'setRejectedHere((count) => count + 1);\n        showError("Invalid username or password.");',
        "wrong-password response",
    )
    handler = replace_one(
        handler, r'const wait\s*=\s*waitSeconds\(response\);',
        '''const wait = waitSeconds(response);
        // A 429 can also indicate IP/request/OTP limits, not just account lockout.
        setRejectedHere((count) => count + 1);
        if (wait > 0) {
          const now = Date.now();
          setLoginClock(now);
          setLoginWaitUntil(now + wait * 1000);
        }''',
        "password-step 429 response",
    )
    handler = handler.replace(
        'Enter it within three minutes.', 'Enter it within five minutes.'
    )
    source = source[:start] + handler + source[end:]

    # 4: Patch only the Forgot Password button's disabled prop.
    forgot_pattern = re.compile(
        r'(<button\b[^>]*className="login-forgot-button"[\s\S]*?)(disabled\s*=\s*\{busy\})',
        re.MULTILINE,
    )
    # Limit the search to its own opening tag, not later controls.
    forgot_matches = [m for m in forgot_pattern.finditer(source)
                      if "</button>" not in m.group(1)]
    if len(forgot_matches) != 1:
        raise ValueError(f"STOP: Forgot Password button - found {len(forgot_matches)} anchors. No changes made.")
    m = forgot_matches[0]
    a, b = m.span(2)
    source = source[:a] + 'disabled={busy || loginRestricted}' + source[b:]

    # 5: Patch ONLY the password-stage Log In button, not the OTP verify button.
    source = replace_one(
        source,
        r'disabled\s*=\s*\{\s*!LOCAL_LOGIN_ENABLED\s*\|\|\s*!SITE_KEY\s*\|\|\s*!captchaToken\s*\|\|\s*busy\s*\}',
        'disabled={!LOCAL_LOGIN_ENABLED || !SITE_KEY || !captchaToken || busy || loginRestricted}',
        "Log In button disabled state",
    )

    # 6: Add an unobtrusive feedback panel just above the existing CAPTCHA.
    panel = '''                <div className="dormora-login-note" role="status" aria-live="polite"
                  style={{ padding: "11px 13px", border: "1px solid var(--border)",
                    borderRadius: 10, background: "var(--soft)", margin: "10px 0",
                    lineHeight: 1.6 }}>
                  <strong>Rejected login requests on this page: {rejectedHere}</strong>
                  <div style={{ fontSize: 12, color: "var(--muted)" }}>
                    Browser-view count only; not the database account total.
                  </div>
                  {loginRestricted && (
                    <div style={{ marginTop: 7, fontWeight: 700, color: "#b45309" }}>
                      Sign-in restricted: {loginWaitSeconds}s remaining.
                      Login and Forgot Password are disabled on this page.
                    </div>
                  )}
                </div>
'''
    source = replace_one(
        source,
        r'(?m)^[ \t]*\{LOCAL_LOGIN_ENABLED\s*\?\s*\(\s*$',
        lambda m: panel + m.group(0),
        "CAPTCHA insertion point",
    )
    source = source.replace(
        'Codes expire after three minutes, and an updated code invalidates the previous one.',
        'Codes expire after five minutes, and an updated code invalidates the previous one.',
    )
    if source.count(MARKER) != 1 or source.count('export default LoginPage;') != 1:
        raise ValueError("STOP: Final integrity check failed. No changes made.")
    return source


def main() -> None:
    target = next((p for p in CANDIDATES if p.is_file()), None)
    if target is None:
        sys.exit("STOP: Run from the Dormora frontend folder or project root.")
    raw = target.read_bytes()
    bom = b"\xef\xbb\xbf"
    try:
        original = (raw[3:] if raw.startswith(bom) else raw).decode("utf-8")
    except UnicodeDecodeError:
        sys.exit("STOP: LoginPage.jsx is not UTF-8. No changes made.")
    newline = "\r\n" if "\r\n" in original else "\n"
    try:
        updated = patch(original.replace("\r\n", "\n"))
    except (ValueError, IndexError) as exc:
        sys.exit(str(exc))
    if updated == original.replace("\r\n", "\n"):
        return
    backup = Path(gettempdir()) / (
        f'Dormora_LoginPage_before_File04_v2_{datetime.now():%Y%m%d_%H%M%S_%f}.jsx'
    )
    shutil.copy2(target, backup)
    encoded = (bom if raw.startswith(bom) else b"") + updated.replace("\n", newline).encode("utf-8")
    try:
        target.write_bytes(encoded)
    except Exception:
        shutil.copy2(backup, target)
        raise
    print("DORMORA FILE 04 v2: APPLIED")
    print(f"Updated only: {target}")
    print(f"Backup stored outside project: {backup}")
    print("NEXT: npm run build")


if __name__ == "__main__":
    main()
