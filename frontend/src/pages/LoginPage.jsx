
/*
  Dormora Frontend File 90 -- automatic server-verified role navigation.

  REPLACE: frontend/src/pages/LoginPage.jsx (previously File 87).

  Preserves File 27's two-column layout, theme, navbar, and footer; connects
  File 83 password + CAPTCHA, File 84 email OTP verification, File 85 resend,
  and File 88's /api/auth/me account role, plus File 89 protected workspaces.

  Explicit test opt-in (frontend/.env.local):
      VITE_DORMORA_LOCAL_LOGIN=true
      VITE_DORMORA_RECAPTCHA_V2_SITE_KEY=<existing public site key>
  Works ONLY with Vite development at http://localhost:5173 and the explicit
  backend File 86 local runner at http://localhost:8000.

  The pre-authentication challenge and authenticated session are HttpOnly
  browser cookies. Never read, store, or expose them in React/JavaScript.
  Never include user IDs, OTP IDs, passwords or OTPs in URLs or logs.
  A successful OTP response is NOT enough to redirect. The page calls
  GET /api/auth/me to verify the HttpOnly database session and current role,
  then navigates to File 89's matching role-protected workspace. The backend
  remains the authority for authentication and role authorization.
*/

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Eye,
  EyeOff,
  House,
  KeyRound,
  LockKeyhole,
  MailCheck,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
  UserRound,
  Wallet,
} from "lucide-react";
import "../App.css";

const API_BASE = "http://localhost:8000";
const SITE_KEY = String(import.meta.env.VITE_DORMORA_RECAPTCHA_V2_SITE_KEY || "").trim();
const LOCAL_LOGIN_ENABLED =
  import.meta.env.DEV === true &&
  import.meta.env.VITE_DORMORA_LOCAL_LOGIN === "true" &&
  typeof window !== "undefined" &&
  window.location.protocol === "http:" &&
  window.location.hostname === "localhost" &&
  window.location.port === "5173";

// UI navigation only: the protected routes in File 89 independently verify
// the session and role using the backend. Never accept a role from form input.
const ROLE_WORKSPACE_PATHS = Object.freeze({
  renter: "/renter",
  property_owner: "/owner",
  admin: "/admin",
});

// Called ONLY after an OTP-accepted response, or from the explicit Retry
// session-check control. An unverified, invalid, or expired session cannot
// cause navigation; an unknown role never falls back to a privileged route.
async function resolveVerifiedWorkspace() {
  const { response, body } = await requestJson("/api/auth/me");
  if (response.status === 401) return { kind: "signed-out" };
  if (response.status !== 200) return { kind: "unavailable" };
  const expiry = Date.parse(body?.expires_at);
  if (
    body?.authenticated !== true ||
    typeof body?.username !== "string" ||
    !body.username.trim() ||
    typeof body?.role !== "string" ||
    !Object.prototype.hasOwnProperty.call(ROLE_WORKSPACE_PATHS, body.role) ||
    !Number.isFinite(expiry) ||
    expiry <= Date.now()
  ) {
    return { kind: "unavailable" };
  }
  return {
    kind: "ready",
    path: ROLE_WORKSPACE_PATHS[body.role],
    expiresAt: body.expires_at,
  };
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    mode: "cors",
    credentials: "include",
    cache: "no-store",
    redirect: "error",
    ...options,
  });
  let body = null;
  try {
    body = await response.json();
  } catch {
    // Never display raw HTML or unexpected server exception details.
  }
  return { response, body };
}

// Every state-changing request obtains a fresh, signed CSRF cookie + header.
// File 56 validates the pair; this client-side code is not a CSRF verifier.
async function postWithCsrf(path, payload) {
  const { response: csrfResponse, body: csrfBody } = await requestJson("/api/csrf");
  if (!csrfResponse.ok || typeof csrfBody?.csrf_token !== "string" || !csrfBody.csrf_token) {
    throw new Error("csrf_unavailable");
  }
  const headers = { "X-CSRF-Token": csrfBody.csrf_token };
  const options = { method: "POST", headers };
  if (payload !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }
  return requestJson(path, options);
}

function waitSeconds(response) {
  const raw = Number(response.headers.get("Retry-After"));
  return Number.isFinite(raw) && raw > 0 ? Math.min(Math.ceil(raw), 86400) : 0;
}

// Follow File 65's React StrictMode-safe reCAPTCHA lifecycle. Never reuse a
// Google-rendered DOM node after cleanup, refresh, or a failed submission.
function LoginCaptcha({ siteKey, onToken, revision }) {
  const hostRef = useRef(null);
  const callbackRef = useRef(onToken);
  callbackRef.current = onToken;
  const [status, setStatus] = useState("loading");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !siteKey) return undefined;
    let active = true;
    let rendered = false;
    let widgetId = null;
    const mountTarget = document.createElement("div");
    host.replaceChildren(mountTarget);
    callbackRef.current("");
    setStatus("loading");

    let script = document.querySelector('script[src*="recaptcha/api.js"]');
    if (script?.dataset.dormoraLoadState === "failed") {
      script.remove();
      script = null;
    }

    function mount() {
      if (!active || rendered || !mountTarget.isConnected) return;
      if (typeof window.grecaptcha?.render !== "function") return;
      rendered = true;
      try {
        widgetId = window.grecaptcha.render(mountTarget, {
          sitekey: siteKey,
          theme: "light",
          callback: (token) => {
            if (!active) return;
            callbackRef.current(String(token || ""));
            setStatus("ready");
          },
          "expired-callback": () => {
            if (active) callbackRef.current("");
          },
          "error-callback": () => {
            if (active) {
              callbackRef.current("");
              setStatus("error");
            }
          },
        });
        if (active) setStatus("ready");
      } catch {
        if (active) {
          callbackRef.current("");
          setStatus("error");
        }
      }
    }

    function onScriptError() {
      if (!active || rendered) return;
      if (script) script.dataset.dormoraLoadState = "failed";
      setStatus("error");
    }

    if (!script) {
      script = document.createElement("script");
      script.src = "https://www.google.com/recaptcha/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      script.dataset.dormoraRecaptcha = "v2";
      script.addEventListener("load", mount);
      script.addEventListener("error", onScriptError);
      document.head.appendChild(script);
    } else {
      script.addEventListener("load", mount);
      script.addEventListener("error", onScriptError);
    }

    const poll = window.setInterval(mount, 200);
    const timeout = window.setTimeout(() => {
      if (active && !rendered) setStatus("error");
    }, 15000);
    mount();

    return () => {
      active = false;
      window.clearInterval(poll);
      window.clearTimeout(timeout);
      script?.removeEventListener("load", mount);
      script?.removeEventListener("error", onScriptError);
      if (widgetId !== null && typeof window.grecaptcha?.reset === "function") {
        try { window.grecaptcha.reset(widgetId); } catch { /* retired widget */ }
      }
      mountTarget.remove();
    };
  }, [siteKey, revision, retry]);

  return (
    <div className="dormora-login-captcha" aria-label="Google reCAPTCHA verification">
      <div ref={hostRef} />
      {status === "loading" && <small role="status">Loading Google reCAPTCHA…</small>}
      {status === "error" && (
        <div role="alert">
          <small>CAPTCHA could not load. Check your internet connection or browser shields.</small>
          <button type="button" onClick={() => setRetry((value) => value + 1)}>
            Retry CAPTCHA
          </button>
        </div>
      )}
    </div>
  );
}

function LoginPage({ darkMode, onToggleTheme }) {
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("");
  const [captchaRevision, setCaptchaRevision] = useState(0);
  const [stage, setStage] = useState("password"); // password | otp | confirming | authenticated
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [feedback, setFeedback] = useState(null);
  const [resendAfter, setResendAfter] = useState(0);
  const [clock, setClock] = useState(Date.now);
  const [expiresAt, setExpiresAt] = useState("");
  const otpRef = useRef(null);

  useEffect(() => {
    if (stage !== "otp" || resendAfter === 0) return undefined;
    const interval = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [stage, resendAfter]);

  useEffect(() => {
    if (stage === "otp") otpRef.current?.focus();
  }, [stage]);

  const secondsLeft = Math.max(0, Math.ceil((resendAfter - clock) / 1000));

  function showError(message) {
    setFeedback({ type: "error", message });
  }

  function showSuccess(message) {
    setFeedback({ type: "success", message });
  }

  function resetCaptcha() {
    setCaptchaToken("");
    setCaptchaRevision((value) => value + 1);
  }

  function backToPassword() {
    if (pending.current) return;
    setStage("password");
    setCode("");
    setExpiresAt("");
    setFeedback(null);
    resetCaptcha();
  }

  async function handlePasswordSubmit(event) {
    event.preventDefault();
    if (pending.current || !LOCAL_LOGIN_ENABLED) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const identifier = String(data.get("identifier") || "").trim();
    const password = String(data.get("password") || "");
    if (!identifier || !password) {
      showError("Enter your username or email and password.");
      return;
    }
    if (!SITE_KEY || !captchaToken) {
      showError("Complete the Google reCAPTCHA checkbox before logging in.");
      return;
    }
    pending.current = true;
    setBusy(true);
    setFeedback(null);
    try {
      const { response, body } = await postWithCsrf("/api/auth/login", {
        identifier,
        password,
        captchaToken,
      });
      // Clear sensitive input even when login is rejected. No local storage.
      form.reset();
      if (response.status === 202 && body?.verification_required === true) {
        setStage("otp");
        setCode("");
        setClock(Date.now());
        setResendAfter(Date.now() + 60_000);
        showSuccess("A six-digit login code was requested by email. Enter it within three minutes.");
      } else if (response.status === 401) {
        showError("Invalid username or password.");
      } else if (response.status === 429) {
        const wait = waitSeconds(response);
        showError(`Too many login attempts. ${wait ? `Try again in ${wait} seconds.` : "Please try again later."}`);
      } else if (response.status === 400) {
        showError("CAPTCHA verification failed. Please complete a new challenge.");
      } else if (response.status === 403) {
        showError("Login security rejected the Origin or CSRF token. Use http://localhost:5173.");
      } else if (response.status === 404) {
        showError("Login is disabled on the API. Start File 86 with --enable-local-login.");
      } else if (response.status === 503) {
        showError("The login service is unavailable. Check the backend logs before retrying; an email may have been sent.");
      } else {
        showError("Login could not be completed. Check the FastAPI terminal.");
      }
    } catch {
      showError("Could not reach the secure localhost login API. Check File 86 and /api/csrf.");
    } finally {
      pending.current = false;
      setBusy(false);
      resetCaptcha();
    }
  }

  async function handleOtpSubmit(event) {
    event.preventDefault();
    if (pending.current || !LOCAL_LOGIN_ENABLED || stage !== "otp") return;
    if (!/^\d{6}$/.test(code)) {
      showError("Enter the six digits from your login email.");
      return;
    }
    pending.current = true;
    setBusy(true);
    setFeedback(null);
    try {
      const { response, body } = await postWithCsrf("/api/auth/login/verify-otp", { code });
      if (response.status === 200 && body?.authenticated === true) {
        setCode("");
        // The OTP endpoint accepted the code and committed its transaction.
        // Verify CURRENT role and session independently before navigation.
        // File 89 will check both again when the protected page mounts.
        const identity = await resolveVerifiedWorkspace();
        if (identity.kind === "ready") {
          setExpiresAt(identity.expiresAt);
          setStage("authenticated");
          navigate(identity.path, { replace: true });
        } else {
          setStage("confirming");
          showError(
            identity.kind === "signed-out"
              ? "The OTP was accepted, but no active session was found. Do not resubmit the used code. Try checking the session or start a new login."
              : "The OTP was accepted, but your account role could not be confirmed. Use Retry session check; do not resubmit the used code."
          );
        }
      } else if (response.status === 401) {
        setCode("");
        showError("Invalid, expired, or already-used code. Check your email; after three incorrect entries, restart the login process.");
      } else if (response.status === 429) {
        const wait = waitSeconds(response);
        showError(`Verification is temporarily limited. ${wait ? `Try again in ${wait} seconds.` : "Please try later."}`);
      } else if (response.status === 404) {
        showError("The OTP endpoint is disabled. Start the File 86 local login runner.");
      } else if (response.status === 403) {
        showError("The request failed the signed CSRF or Origin check.");
      } else if (response.status === 503) {
        showError("Verification could not finish. Do not repeatedly submit the same code; check the FastAPI terminal.");
      } else {
        showError("Login verification failed. Check the FastAPI terminal.");
      }
    } catch {
      showError("Could not confirm the login response. Check the API and session before retrying.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  async function handleResend() {
    if (pending.current || stage !== "otp" || secondsLeft > 0 || !LOCAL_LOGIN_ENABLED) return;
    pending.current = true;
    setBusy(true);
    setFeedback(null);
    try {
      const { response } = await postWithCsrf("/api/auth/login/resend-otp");
      if (response.status === 200) {
        setCode("");
        setClock(Date.now());
        setResendAfter(Date.now() + 60_000);
        showSuccess("A new code was requested. The previous code is no longer valid.");
      } else if (response.status === 429) {
        const wait = waitSeconds(response);
        setResendAfter(Date.now() + Math.max(wait, 1) * 1000);
        setClock(Date.now());
        showError("You must wait before requesting another code.");
      } else if (response.status === 401) {
        showError("Your temporary login challenge has expired. Return to the login form and start again.");
      } else if (response.status === 404) {
        showError("OTP resend is disabled on this backend.");
      } else {
        showError("Could not resend the login code. Check the backend and your inbox before retrying.");
      }
    } catch {
      showError("Could not contact the OTP resend service. Check the backend terminal.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  async function handleSessionCheck(renewIdle = false) {
    if (pending.current || !["authenticated", "confirming"].includes(stage)) return;
    pending.current = true;
    setBusy(true);
    setFeedback(null);
    try {
      if (renewIdle) {
        const refresh = await postWithCsrf("/api/auth/session/refresh");
        if (refresh.response.status === 401) {
          setStage("password");
          setExpiresAt("");
          showError("Your session has expired or was revoked. Please log in again.");
          return;
        }
        if (refresh.response.status !== 200 || refresh.body?.authenticated !== true) {
          showError("Could not refresh the session. Check the backend terminal.");
          return;
        }
      }
      // Always use the current server-verified role for the destination.
      const identity = await resolveVerifiedWorkspace();
      if (identity.kind === "ready") {
        setExpiresAt(identity.expiresAt);
        setStage("authenticated");
        navigate(identity.path, { replace: true });
      } else if (identity.kind === "signed-out") {
        setStage("password");
        setExpiresAt("");
        showError("Your session has expired or was revoked. Please log in again.");
      } else {
        setStage("confirming");
        showError("The backend could not verify your account role. Please retry the session check.");
      }
    } catch {
      showError("Unable to reach the session endpoint.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  async function handleLogout() {
    if (pending.current || !LOCAL_LOGIN_ENABLED) return;
    pending.current = true;
    setBusy(true);
    setFeedback(null);
    try {
      const { response, body } = await postWithCsrf("/api/auth/logout");
      if (response.status === 200 && body?.authenticated === false) {
        setStage("password");
        setCode("");
        setExpiresAt("");
        showSuccess("Signed out. The PostgreSQL session was revoked.");
        resetCaptcha();
      } else {
        showError("Could not confirm logout. Retry or inspect the backend; do not assume the session was revoked.");
      }
    } catch {
      showError("Logout confirmation failed. Check your connection and the backend.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return (
    <div className={darkMode ? "dormora dark-mode login-page" : "dormora light-mode login-page"}>
      <style>{`
        .login-page .dormora-login-status { margin-top: 14px; padding: 12px 14px;
          border: 1px solid var(--border); border-radius: 12px; background: var(--soft);
          color: var(--text); font-size: 13px; line-height: 1.65; }
        .login-page .dormora-login-status[data-type="error"] { border-color: #cd6868; }
        .login-page .dormora-login-status[data-type="success"] { border-color: var(--primary); }
        .login-page .dormora-login-captcha { overflow-x: auto; min-height: 78px; margin: 12px 0; }
        .login-page .dormora-login-captcha small { color: var(--muted); }
        .login-page .dormora-login-captcha button { border: 0; background: transparent;
          color: var(--primary); cursor: pointer; font-weight: 700; margin: 6px 0; }
        .login-page .dormora-otp-input { width: 100%; padding: 12px 14px; margin-top: 8px;
          background: var(--background); color: var(--text); border: 1px solid var(--border);
          border-radius: 11px; font-size: 24px; font-weight: 700; text-align: center;
          letter-spacing: .25em; }
        .login-page .dormora-otp-input:focus-visible { outline: 3px solid var(--primary); }
        .login-page .dormora-login-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px; }
        .login-page .dormora-login-actions button { flex: 1; min-width: 130px;
          padding: 11px; border-radius: 10px; border: 1px solid var(--border);
          background: var(--soft); color: var(--text); font-weight: 700; cursor: pointer; }
        .login-page button:disabled { cursor: not-allowed; opacity: .6; }
        .login-page .dormora-login-note { color: var(--muted); font-size: 12px; line-height: 1.6; margin-top: 12px; }
        .login-page .dormora-logged-in { display: flex; flex-direction: column; gap: 12px; }
        .login-page .dormora-logged-in svg { color: var(--primary); }
        .login-page .dormora-logged-in h3 { color: var(--text); margin: 0; }
      `}</style>

      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>

      <header className="site-header">
        <div className="page-container header-content">
          <Link className="brand" to="/">
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </Link>
          <nav className="login-header-nav" aria-label="Login page navigation">
            <Link to="/">Home</Link>
            <Link to="/register" className="login-register-nav" style={{
              color: "var(--primary)", display: "inline-flex", alignItems: "center",
              justifyContent: "center",
            }}>
              Register
            </Link>
            <button type="button" className="theme-button" onClick={onToggleTheme}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              title={darkMode ? "Light mode" : "Dark mode"}>
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </nav>
        </div>
      </header>

      <main className="login-main">
        <div className="page-container login-layout">
          <section className="login-intro" aria-labelledby="login-intro-heading">
            <span className="login-eyebrow"><ShieldCheck size={17} /> Your Dormora workspace</span>
            <h1 id="login-intro-heading">Your rental life,<span> all in one place.</span></h1>
            <p>Log in securely to return to your rental records, payment history, and property management tools when available.</p>
            <div className="login-benefits">
              <div className="login-benefit">
                <div className="login-benefit-icon"><CalendarDays size={21} /></div>
                <div><h3>Stay on top of rent</h3><p>Keep due dates and recorded payments organized.</p></div>
              </div>
              <div className="login-benefit">
                <div className="login-benefit-icon"><Wallet size={21} /></div>
                <div><h3>Review your records</h3><p>Access your personal rental and deposit information.</p></div>
              </div>
              <div className="login-benefit">
                <div className="login-benefit-icon"><KeyRound size={21} /></div>
                <div><h3>Protected login</h3><p>Password, Google CAPTCHA, emailed OTP, and database-backed sessions.</p></div>
              </div>
            </div>
          </section>

          <section className="login-card" aria-labelledby="login-form-heading">
            <div className="login-card-icon">
              {stage === "otp" ? <MailCheck size={26} /> : stage === "authenticated" ? <CheckCircle2 size={26} /> : stage === "confirming" ? <ShieldCheck size={26} /> : <LockKeyhole size={26} />}
            </div>
            <h2 id="login-form-heading">
              {stage === "otp" ? "Verify your login" : stage === "authenticated" ? "Session verified" : stage === "confirming" ? "Confirm your session" : "Welcome back"}
            </h2>
            <p className="login-card-subtitle">
              {stage === "otp" ? "Enter the six-digit code sent to your email." :
                stage === "authenticated" ? "Your session is recognized by the Dormora backend." :
                stage === "confirming" ? "OTP was accepted; the session check still needs to finish." :
                "Enter your account details to continue."}
            </p>

            {stage === "password" && (
              <form className="login-form" onSubmit={handlePasswordSubmit}>
                <div className="login-field">
                  <label htmlFor="login-username">Username or Email <span className="login-required">*</span></label>
                  <div className="login-input-wrap">
                    <UserRound size={19} aria-hidden="true" />
                    <input id="login-username" name="identifier" type="text"
                      placeholder="Enter username or email" autoComplete="username"
                      spellCheck={false} maxLength={255} required disabled={busy} />
                  </div>
                </div>
                <div className="login-field">
                  <label htmlFor="login-password">Password <span className="login-required">*</span></label>
                  <div className="login-input-wrap">
                    <LockKeyhole size={19} aria-hidden="true" />
                    <input id="login-password" name="password"
                      type={showPassword ? "text" : "password"}
                      placeholder="Enter your password" autoComplete="current-password"
                      maxLength={512} required disabled={busy} />
                    <button className="login-password-toggle" type="button"
                      onClick={() => setShowPassword((value) => !value)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      title={showPassword ? "Hide password" : "Show password"}
                      aria-pressed={showPassword}>
                      {showPassword ? <EyeOff size={19} /> : <Eye size={19} />}
                    </button>
                  </div>
                </div>
                <div className="login-form-options">
                  <span>Fields marked * are required.</span>
                  <button
                    type="button"
                    className="login-forgot-button"
                    onClick={() => navigate("/forgot-password")}
                    disabled={busy}
                    title="Recover your Dormora account securely"
                  >
                    Forgot password?
                  </button>
                </div>
                {LOCAL_LOGIN_ENABLED ? (
                  SITE_KEY ? <LoginCaptcha siteKey={SITE_KEY} onToken={setCaptchaToken} revision={captchaRevision} /> :
                    <p className="dormora-login-note" role="alert">Set your public VITE_DORMORA_RECAPTCHA_V2_SITE_KEY in frontend/.env.local.</p>
                ) : (
                  <div className="login-captcha-note" role="note">
                    <ShieldCheck size={19} />
                    <span>Login is inactive. Enable local testing explicitly in frontend/.env.local.</span>
                  </div>
                )}
                <button type="submit" className="login-submit-button"
                  disabled={!LOCAL_LOGIN_ENABLED || !SITE_KEY || !captchaToken || busy}>
                  {busy ? "Verifying securely…" : "Log In"} <ArrowRight size={19} />
                </button>
              </form>
            )}

            {stage === "otp" && (
              <form className="login-form" onSubmit={handleOtpSubmit}>
                <div className="login-field">
                  <label htmlFor="login-otp">Email verification code <span className="login-required">*</span></label>
                  <input ref={otpRef} id="login-otp" className="dormora-otp-input"
                    type="text" name="loginOtp" value={code} inputMode="numeric"
                    autoComplete="one-time-code" maxLength={6}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="000000" disabled={busy} required />
                </div>
                <p className="dormora-login-note">Codes expire after three minutes, and an updated code invalidates the previous one. The original pending-login challenge expires after 15 minutes.</p>
                <button className="login-submit-button" type="submit"
                  disabled={busy || !/^\d{6}$/.test(code)}>
                  {busy ? "Verifying…" : "Verify & Log In"} <ArrowRight size={19} />
                </button>
                <div className="dormora-login-actions">
                  <button type="button" disabled={busy || secondsLeft > 0} onClick={handleResend}>
                    {secondsLeft > 0 ? `Resend in ${secondsLeft}s` : "Resend code"}
                  </button>
                  <button type="button" disabled={busy} onClick={backToPassword}>Start over</button>
                </div>
              </form>
            )}

            {["authenticated", "confirming"].includes(stage) && (
              <div className="dormora-logged-in" role="status">
                <CheckCircle2 size={32} />
                <h3>{stage === "authenticated" ? "Authenticated with FastAPI" : "Session confirmation pending"}</h3>
                <p className="dormora-login-note">
                  {stage === "authenticated" ? "A database-backed session was confirmed. The backend enforces a nine-minute idle timeout." : "The verification API accepted your code, but the server-side session has not been confirmed yet."}
                  {expiresAt && ` Current session deadline: ${new Date(expiresAt).toLocaleTimeString()}.`}
                </p>
                <div className="dormora-login-actions">
                  <button type="button" onClick={() => handleSessionCheck(false)} disabled={busy}>
                    <ShieldCheck size={16} /> {stage === "confirming" ? "Retry session check" : "Check session"}
                  </button>
                  {stage === "authenticated" && <button type="button" onClick={() => handleSessionCheck(true)} disabled={busy}>
                    <RefreshCw size={16} /> Refresh session
                  </button>}
                  <button type="button" onClick={handleLogout} disabled={busy}>Sign out</button>
                </div>
                <p className="dormora-login-note">Your account must be verified by FastAPI before opening its role-protected workspace.</p>
                {stage === "confirming" && (
                  <button type="button" onClick={backToPassword} disabled={busy}>
                    Start a new login
                  </button>
                )}
              </div>
            )}

            {feedback && (
              <div className="dormora-login-status" data-type={feedback.type}
                role={feedback.type === "error" ? "alert" : "status"}>
                {feedback.message}
              </div>
            )}

            <p className="login-preview-message">
              {LOCAL_LOGIN_ENABLED
                ? "LOCAL TEST MODE: This form can send real requests, Gmail OTP messages, and session activity to your development database."
                : "Frontend preview only. Start the File 86 local login runner and explicitly enable VITE_DORMORA_LOCAL_LOGIN=true to test real login."}
            </p>
            <div className="login-register-message">
              New to Dormora? <Link to="/register">Create an account</Link>
            </div>
          </section>
        </div>
      </main>

      <footer className="site-footer">
        <div className="page-container login-footer-content">
          <span>© 2026 Dormora. All rights reserved.</span>
          <Link to="/">Back to Home</Link>
        </div>
      </footer>
    </div>
  );
}

export default LoginPage;
