
"""Dormora Frontend File 04 — guarded LoginPage update.

MODIFIES ONLY: frontend/src/pages/LoginPage.jsx

Run from the frontend folder or project root:
    python Dormora_File04_LoginLockout_UI_Apply.py

Preserves the current installed component, changes only expected
blocks, and creates a backup outside the repository.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
import shutil
import sys

MARKER = "DORMORA_LOGIN_UI_LOCKOUT_V1"

CANDIDATES = (
    Path("src/pages/LoginPage.jsx"),
    Path("frontend/src/pages/LoginPage.jsx"),
)


def patch(source: str) -> str:
    if MARKER in source:
        print("FILE 04 ALREADY APPLIED — no changes made.")
        return source

    def replace_once(old: str, new: str, name: str) -> None:
        nonlocal source
        found = source.count(old)
        if found != 1:
            raise ValueError(
                f"STOP: {name}: expected one matching block, "
                f"found {found}. No files changed."
            )
        source = source.replace(old, new, 1)

    replace_once(
        '  const [expiresAt, setExpiresAt] = useState("");\n'
        '  const otpRef = useRef(null);',
        '''  const [expiresAt, setExpiresAt] = useState("");
  // DORMORA_LOGIN_UI_LOCKOUT_V1
  // Browser feedback, not an authoritative account tally.
  const [rejectedHere, setRejectedHere] = useState(0);
  const [loginWaitUntil, setLoginWaitUntil] = useState(0);
  const [loginClock, setLoginClock] = useState(Date.now);
  const otpRef = useRef(null);''',
        "login UI state",
    )

    replace_once(
        '''  useEffect(() => {
    if (stage === "otp") otpRef.current?.focus();
  }, [stage]);

  const secondsLeft = Math.max(0, Math.ceil((resendAfter - clock) / 1000));''',
        '''  useEffect(() => {
    if (stage === "otp") otpRef.current?.focus();
  }, [stage]);

  // Server-provided countdown, not a fabricated duration.
  useEffect(() => {
    if (!loginWaitUntil) return undefined;

    const timer = window.setInterval(() => {
      const now = Date.now();
      setLoginClock(now);

      if (now >= loginWaitUntil) {
        setLoginWaitUntil(0);
      }
    }, 1000);

    return () => window.clearInterval(timer);
  }, [loginWaitUntil]);

  const secondsLeft = Math.max(
    0,
    Math.ceil((resendAfter - clock) / 1000)
  );

  const loginWaitSeconds = Math.max(
    0,
    Math.ceil((loginWaitUntil - loginClock) / 1000)
  );

  const loginRestricted = loginWaitSeconds > 0;''',
        "countdown effect",
    )

    replace_once(
        '''    if (pending.current || !LOCAL_LOGIN_ENABLED) return;
    const form = event.currentTarget;''',
        '''    if (
      pending.current ||
      !LOCAL_LOGIN_ENABLED ||
      loginRestricted
    ) return;

    const form = event.currentTarget;''',
        "password submit guard",
    )

    replace_once(
        '''        setStage("otp");
        setCode("");
        setClock(Date.now());''',
        '''        setStage("otp");
        setRejectedHere(0);
        setLoginWaitUntil(0);
        setCode("");
        setClock(Date.now());''',
        "password step accepted",
    )

    replace_once(
        '        showSuccess("A six-digit login code was requested by email. Enter it within three minutes.");',
        '        showSuccess("A six-digit login code was requested by email. Enter it within five minutes.");',
        "login OTP text",
    )

    replace_once(
        '''      } else if (response.status === 401) {
        showError("Invalid username or password.");
      } else if (response.status === 429) {
        const wait = waitSeconds(response);
        showError(`Too many login attempts. ${wait ? `Try again in ${wait} seconds.` : "Please try again later."}`);''',
        '''      } else if (response.status === 401) {
        setRejectedHere((number) => number + 1);
        showError("Invalid username or password.");
      } else if (response.status === 429) {
        // 429 may represent account lockout, IP blocking,
        // or another backend rate limit.
        setRejectedHere((number) => number + 1);

        const wait = waitSeconds(response);

        if (wait > 0) {
          const now = Date.now();
          setLoginClock(now);
          setLoginWaitUntil(now + wait * 1000);
        }

        showError(
          wait > 0
            ? "Sign-in is temporarily restricted. Follow the countdown below."
            : "Sign-in is temporarily restricted. Please try again later."
        );''',
        "password failure handling",
    )

    replace_once(
        '''                    disabled={busy}
                    title="Recover your Dormora account securely">''',
        '''                    disabled={busy || loginRestricted}
                    title={
                      loginRestricted
                        ? "Unavailable during a temporary login restriction"
                        : "Recover your Dormora account securely"
                    }>''',
        "Forgot Password disabled state",
    )

    replace_once(
        '''                </div>
                {LOCAL_LOGIN_ENABLED ? (
                  SITE_KEY ? <LoginCaptcha''',
        '''                </div>
                <div
                  className="dormora-login-note"
                  role="status"
                  aria-live="polite"
                  style={{
                    padding: "12px 14px",
                    border: "1px solid var(--border)",
                    borderRadius: 10,
                    background: "var(--soft)",
                    margin: "10px 0",
                    lineHeight: 1.6,
                  }}
                >
                  <strong>
                    Rejected sign-in requests on this page: {rejectedHere}
                  </strong>

                  <div style={{
                    fontSize: 12,
                    color: "var(--muted)",
                  }}>
                    This is a browser-view count, not the
                    account's database total.
                  </div>

                  {loginRestricted && (
                    <div style={{
                      marginTop: 7,
                      fontWeight: 700,
                      color: "#b45309",
                    }}>
                      Temporarily restricted — try again in
                      {" "}{loginWaitSeconds}s.
                      Login and Forgot Password are disabled
                      on this screen.
                    </div>
                  )}
                </div>
                {LOCAL_LOGIN_ENABLED ? (
                  SITE_KEY ? <LoginCaptcha''',
        "visible attempt/cooldown feedback",
    )

    replace_once(
        '''disabled={!LOCAL_LOGIN_ENABLED || !SITE_KEY || !captchaToken || busy}>''',
        '''disabled={!LOCAL_LOGIN_ENABLED || !SITE_KEY || !captchaToken || busy || loginRestricted}>''',
        "login button disabled state",
    )

    replace_once(
        "Codes expire after three minutes, and an updated code invalidates the previous one.",
        "Codes expire after five minutes, and an updated code invalidates the previous one.",
        "OTP expiry information",
    )

    if source.count(MARKER) != 1:
        raise ValueError(
            "STOP: Marker verification failed. No changes made."
        )

    return source


def main() -> None:
    target = next(
        (path for path in CANDIDATES if path.is_file()),
        None,
    )

    if target is None:
        sys.exit(
            "STOP: Could not find LoginPage.jsx. "
            "Run from the frontend folder or project root."
        )

    raw = target.read_bytes()
    bom = b"\xef\xbb\xbf"

    try:
        content = (
            raw[len(bom):] if raw.startswith(bom) else raw
        ).decode("utf-8")
    except UnicodeDecodeError:
        sys.exit(
            "STOP: LoginPage.jsx is not UTF-8. No changes made."
        )

    line_ending = "\r\n" if "\r\n" in content else "\n"
    normalized = content.replace("\r\n", "\n")

    try:
        changed = patch(normalized)
    except ValueError as exc:
        sys.exit(str(exc))

    if changed == normalized:
        return

    if (
        changed.count("function LoginPage(") != 1 or
        changed.count("export default LoginPage;") != 1
    ):
        sys.exit(
            "STOP: Component/export integrity check failed. "
            "No changes made."
        )

    backup = Path(gettempdir()) / (
        "Dormora_LoginPage_before_File04_"
        f"{datetime.now():%Y%m%d_%H%M%S_%f}.jsx"
    )

    shutil.copy2(target, backup)

    result = (
        (bom if raw.startswith(bom) else b"") +
        changed.replace("\n", line_ending).encode("utf-8")
    )

    try:
        target.write_bytes(result)
    except Exception:
        shutil.copy2(backup, target)
        raise

    print("DORMORA FILE 04: LOGIN UI FEEDBACK PATCH APPLIED")
    print(f"Updated only: {target}")
    print(f"Backup outside project: {backup}")
    print("Added server-driven countdown and disabled controls.")
    print("NEXT: npm run build, then controlled localhost testing.")


if __name__ == "__main__":
    main()
