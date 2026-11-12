/*
 * Dormora Frontend File 125 — real Forgot Password flow.
 * REPLACE: frontend/src/pages/ForgotPasswordPage.jsx
 *
 * Reuses the original File 29/30 two-column layout and existing forgot-* CSS.
 * Implements File 123's five API endpoints without exposing account IDs,
 * OTPs, reset grants, or cookies to JavaScript. All recovery permissions,
 * lockouts, CAPTCHA decisions, and password changes are backend-authorized.
 *
 * Local testing ONLY: Vite http://localhost:5173 with
 * VITE_DORMORA_LOCAL_LOGIN=true and VITE_DORMORA_RECAPTCHA_V2_SITE_KEY set.
 * Start File 124's --enable-local-recovery runner on localhost:8000.
 * This page alone does not enable recovery in a normal backend process.
 */

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  House,
  KeyRound,
  LockKeyhole,
  Mail,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
  UserRound,
} from "lucide-react";
import "../App.css";

const API_BASE = "http://localhost:8000";
const SITE_KEY = String(import.meta.env.VITE_DORMORA_RECAPTCHA_V2_SITE_KEY || "").trim();
const LOCAL_RECOVERY_ENABLED =
  import.meta.env.DEV === true &&
  import.meta.env.VITE_DORMORA_LOCAL_LOGIN === "true" &&
  typeof window !== "undefined" &&
  window.location.protocol === "http:" &&
  window.location.hostname === "localhost" &&
  window.location.port === "5173";

const STEPS = [
  { label: "Identify account", hint: "Username and CAPTCHA", icon: UserRound },
  { label: "Security question", hint: "Verify one registered answer", icon: ShieldCheck },
  { label: "Email verification", hint: "Enter the six-digit code", icon: Mail },
  { label: "New password", hint: "Complete your secure reset", icon: KeyRound },
];

const FIELD_STYLE = {
  width: "100%",
  minWidth: 0,
  boxSizing: "border-box",
  minHeight: 50,
  padding: "10px 13px",
  border: "1px solid var(--border)",
  borderRadius: 10,
  background: "var(--background)",
  color: "var(--text)",
  font: "inherit",
  fontSize: 13,
};

const SECONDARY_STYLE = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 7,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid var(--border)",
  background: "var(--soft)",
  color: "var(--text)",
  cursor: "pointer",
  font: "inherit",
  fontSize: 12,
  fontWeight: 700,
};

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    credentials: "include",
    mode: "cors",
    cache: "no-store",
    redirect: "error",
    ...options,
  });
  let body = null;
  try { body = await response.json(); } catch { /* Ignore malformed responses. */ }
  return { response, body };
}

// CSRF is verified by Dormora's File 56 middleware, never by this browser.
async function postWithCsrf(path, payload) {
  const { response: csrfResponse, body: csrfBody } = await requestJson("/api/csrf");
  if (csrfResponse.status !== 200 || typeof csrfBody?.csrf_token !== "string" || !csrfBody.csrf_token) {
    throw new Error("csrf_unavailable");
  }
  return requestJson(`/api/auth/password-recovery/${path}`, {
    method: "POST",
    headers: {
      "X-CSRF-Token": csrfBody.csrf_token,
      ...(payload === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
  });
}

function retrySeconds(response) {
  const seconds = Number(response.headers.get("Retry-After"));
  return Number.isFinite(seconds) && seconds > 0
    ? Math.min(86400, Math.ceil(seconds)) : 60;
}

function meetsPasswordPolicy(value) {
  return typeof value === "string" &&
    value.length >= 10 && value.length <= 64 &&
    /[a-z]/.test(value) && /[A-Z]/.test(value) &&
    /[0-9]/.test(value) && /[^A-Za-z0-9]/.test(value) &&
    !/[\x00-\x1f\x7f]/.test(value);
}

function passwordStrength(value) {
  if (!value) return "Not entered";
  if (!meetsPasswordPolicy(value)) return "Weak";
  return value.length >= 14 ? "Strong" : "Medium";
}

// Same StrictMode-safe explicit Google v2 lifecycle used by LoginPage (File 90).
function RecoveryCaptcha({ siteKey, onToken, revision }) {
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
            if (active) { callbackRef.current(String(token || "")); setStatus("ready"); }
          },
          "expired-callback": () => { if (active) callbackRef.current(""); },
          "error-callback": () => {
            if (active) { callbackRef.current(""); setStatus("error"); }
          },
        });
        if (active) setStatus("ready");
      } catch {
        if (active) { callbackRef.current(""); setStatus("error"); }
      }
    }

    function scriptError() {
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
      script.addEventListener("error", scriptError);
      document.head.appendChild(script);
    } else {
      script.addEventListener("load", mount);
      script.addEventListener("error", scriptError);
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
      script?.removeEventListener("error", scriptError);
      if (widgetId !== null && typeof window.grecaptcha?.reset === "function") {
        try { window.grecaptcha.reset(widgetId); } catch { /* Retired widget. */ }
      }
      mountTarget.remove();
    };
  }, [siteKey, revision, retry]);

  return (
    <div aria-label="Google reCAPTCHA verification">
      <div ref={hostRef} />
      {status === "loading" && <small role="status">Loading Google reCAPTCHA…</small>}
      {status === "error" && (
        <div role="alert" style={{ display: "grid", gap: 6 }}>
          <small>CAPTCHA could not load. Check your connection or browser shields.</small>
          <button type="button" style={SECONDARY_STYLE} onClick={() => setRetry((n) => n + 1)}>Retry CAPTCHA</button>
        </div>
      )}
    </div>
  );
}

function ForgotPasswordPage({ darkMode, onToggleTheme }) {
  const [step, setStep] = useState(0); // 0=identify 1=answer 2=OTP 3=reset 4=complete
  const [username, setUsername] = useState("");
  const [captchaToken, setCaptchaToken] = useState("");
  const [captchaRevision, setCaptchaRevision] = useState(0);
  const [questions, setQuestions] = useState([]);
  const [questionId, setQuestionId] = useState("");
  const [answer, setAnswer] = useState("");
  const [confirmAnswer, setConfirmAnswer] = useState("");
  const [otp, setOtp] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [resendAfter, setResendAfter] = useState(0);
  const [clock, setClock] = useState(Date.now);
  const actionInFlight = useRef(false);
  const otpRef = useRef(null);

  useEffect(() => {
    if (step !== 2 || !resendAfter) return undefined;
    const interval = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [step, resendAfter]);
  useEffect(() => { if (step === 2) otpRef.current?.focus(); }, [step]);

  const secondsLeft = Math.max(0, Math.ceil((resendAfter - clock) / 1000));
  const activeStep = Math.min(step, 3);
  const hasValidPassword = meetsPasswordPolicy(nextPassword);
  const themeClass = darkMode ? "dormora dark-mode forgot-page" : "dormora light-mode forgot-page";
  const recoveryReady = LOCAL_RECOVERY_ENABLED && Boolean(SITE_KEY);

  function errorText(response, body, path) {
    if (response.status === 404) return "Password recovery is not active. Start File 124's localhost recovery runner.";
    if (response.status === 403) return "Origin or CSRF verification failed. Use http://localhost:5173 and restart the recovery runner.";
    if (response.status === 429) return `Too many attempts. Try again after ${retrySeconds(response)} seconds.`;
    if (response.status === 503) return "Password recovery is temporarily unavailable. Check your FastAPI terminal.";
    if (response.status === 401) return path === "verify-otp"
      ? "That code was not accepted. Check the latest email and try again, or restart recovery if the challenge expired."
      : "The recovery information could not be verified.";
    if (response.status === 400 && path === "identify") return "Check your username and complete the Google CAPTCHA.";
    if (response.status === 400 && path === "reset" && typeof body?.detail === "string" && body.detail.length <= 180)
      return body.detail;
    if (response.status === 400) return "The provided information could not be accepted. Check the fields and retry.";
    if (response.status === 422) return "Check the required fields and try again.";
    return "The request was not confirmed. Check FastAPI before retrying.";
  }

  function restart() {
    if (actionInFlight.current) return;
    setStep(0);
    setUsername("");
    setQuestions([]);
    setQuestionId("");
    setAnswer("");
    setConfirmAnswer("");
    setOtp("");
    setNextPassword("");
    setConfirmPassword("");
    setShowPassword(false);
    setShowConfirm(false);
    setResendAfter(0);
    setFeedback(null);
    setCaptchaToken("");
    setCaptchaRevision((n) => n + 1);
  }

  async function run(path, payload, onAccepted, { uncertainMessage } = {}) {
    if (!recoveryReady || actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy(true);
    setFeedback(null);
    try {
      const { response, body } = await postWithCsrf(path, payload);
      if (response.status === 200) {
        const accepted = onAccepted(body);
        if (!accepted) setFeedback({ kind: "error", text: "The backend response was incomplete. Restart recovery before continuing." });
      } else {
        if (response.status === 429 && path === "resend-otp") {
          setResendAfter(Date.now() + retrySeconds(response) * 1000);
        }
        setFeedback({ kind: "error", text: errorText(response, body, path) });
        if (path === "identify") {
          setCaptchaToken("");
          setCaptchaRevision((n) => n + 1);
        }
      }
    } catch {
      setFeedback({ kind: "error", text: uncertainMessage || "Could not contact the localhost recovery API. Check File 124 and /api/csrf." });
    } finally {
      actionInFlight.current = false;
      setBusy(false);
    }
  }

  function identify(event) {
    event.preventDefault();
    const typed = username.trim();
    if (!/^[A-Za-z][A-Za-z0-9]{0,254}$/.test(typed)) {
      setFeedback({ kind: "error", text: "Enter the username you registered with (letters and numbers only)." });
      return;
    }
    if (!captchaToken) {
      setFeedback({ kind: "error", text: "Complete the Google CAPTCHA before continuing." });
      return;
    }
    run("identify", { username: typed, captcha_token: captchaToken }, (body) => {
      const choices = body?.questions;
      if (!Array.isArray(choices) || choices.length !== 3 ||
          !choices.every((q) => Number.isInteger(q?.question_id) && typeof q?.question_text === "string")) return false;
      setUsername(typed);
      setQuestions(choices);
      setQuestionId(String(choices[0].question_id));
      setStep(1);
      return true;
    });
  }

  function verifyAnswer(event) {
    event.preventDefault();
    if (!Number.isSafeInteger(Number(questionId)) || !questions.some((q) => q.question_id === Number(questionId))) {
      setFeedback({ kind: "error", text: "Choose one of the displayed security questions." });
      return;
    }
    if (!answer || answer !== confirmAnswer) {
      setFeedback({ kind: "error", text: "Your answer and re-entered answer must match exactly." });
      return;
    }
    run("answer", {
      question_id: Number(questionId), answer, confirm_answer: confirmAnswer,
    }, (body) => {
      if (typeof body?.message !== "string") return false;
      setAnswer("");
      setConfirmAnswer("");
      setStep(2);
      setResendAfter(Date.now() + 60_000);
      setClock(Date.now());
      setFeedback({ kind: "success", text: "If the account is eligible, an email code was sent. Check your inbox and spam folder." });
      return true;
    }, { uncertainMessage: "The verification result is uncertain. An email may have been issued. Check your inbox before restarting; do not repeatedly submit answers." });
  }

  function verifyOtp(event) {
    event.preventDefault();
    if (!/^[0-9]{6}$/.test(otp)) {
      setFeedback({ kind: "error", text: "Enter the six-digit verification code." });
      return;
    }
    run("verify-otp", { otp }, (body) => {
      if (typeof body?.message !== "string") return false;
      setOtp("");
      setStep(3);
      setFeedback(null);
      return true;
    }, { uncertainMessage: "OTP verification could not be confirmed. Check your connection and try verifying the latest code again." });
  }

  function resendOtp() {
    if (secondsLeft > 0 || actionInFlight.current) return;
    run("resend-otp", undefined, (body) => {
      if (typeof body?.message !== "string") return false;
      setOtp("");
      setResendAfter(Date.now() + 60_000);
      setClock(Date.now());
      setFeedback({ kind: "success", text: "If the recovery challenge is valid, a new code was requested. Use the latest email." });
      return true;
    }, { uncertainMessage: "The resend result is uncertain; a replacement code may have been issued. Check email before trying again." });
  }

  function resetPassword(event) {
    event.preventDefault();
    if (!hasValidPassword) {
      setFeedback({ kind: "error", text: "Use 10–64 characters with uppercase, lowercase, a number and a symbol." });
      return;
    }
    if (nextPassword !== confirmPassword) {
      setFeedback({ kind: "error", text: "Mismatch Password." });
      return;
    }
    run("reset", { new_password: nextPassword, confirm_password: confirmPassword }, (body) => {
      if (typeof body?.message !== "string") return false;
      setNextPassword("");
      setConfirmPassword("");
      setStep(4);
      setFeedback({ kind: "success", text: "Password reset confirmed. All prior sessions were revoked. Sign in with the new password." });
      return true;
    }, { uncertainMessage: "Password reset may have completed before the response was lost. Do not resubmit yet; try signing in with your new password." });
  }

  function passwordField({ label, value, setter, shown, toggle, id }) {
    return (
      <div className="forgot-field">
        <label htmlFor={id}>{label} <span className="forgot-required">*</span></label>
        <div className="forgot-input-wrap">
          <LockKeyhole size={18} aria-hidden="true" />
          <input
            id={id} type={shown ? "text" : "password"} value={value}
            onChange={(event) => { setter(event.target.value); setFeedback(null); }}
            autoComplete="new-password" minLength={10} maxLength={64}
            required disabled={busy}
          />
          <button type="button" style={{ ...SECONDARY_STYLE, padding: "7px" }}
            disabled={busy} onClick={toggle} aria-label={`${shown ? "Hide" : "Show"} ${label.toLowerCase()}`}
            aria-pressed={shown}>
            {shown ? <EyeOff size={17} /> : <Eye size={17} />}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={themeClass}>
      <div className="system-title-bar">Dormora: A Secure Web-Based Rental Management and Property Listing System</div>
      <header className="site-header">
        <div className="page-container header-content forgot-header-content">
          <Link className="brand" to="/"><House size={29} strokeWidth={2.5} /><span>Dormora</span></Link>
          <nav className="forgot-header-nav" aria-label="Recovery navigation">
            <Link to="/">Home</Link>
            <Link className="forgot-header-login" to="/login">Log In</Link>
            <button className="theme-button" type="button" onClick={onToggleTheme}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}>
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </nav>
        </div>
      </header>

      <main className="forgot-main">
        <div className="page-container forgot-layout">
          <section className="forgot-intro" aria-label="Recovery instructions">
            <span className="forgot-eyebrow"><ShieldCheck size={17} /> Secure account recovery</span>
            <h1>Recover your <span>Dormora account.</span></h1>
            <p className="forgot-description">
              Follow the four security steps to reset your password. Your account is protected
              by a registered security question, a short-lived email code, and password-history checks.
            </p>
            <ol className="forgot-steps">
              {STEPS.map(({ label, hint, icon: Icon }, index) => (
                <li className={`forgot-step ${activeStep === index ? "is-current" : ""}`} key={label}
                  aria-current={activeStep === index && step !== 4 ? "step" : undefined}>
                  <span className="forgot-step-number">0{index + 1}</span>
                  <span className="forgot-step-icon"><Icon size={19} /></span>
                  <span className="forgot-step-copy"><strong>{label}</strong><small>{hint}</small></span>
                  {step === 4 || index < step ? <CheckCircle2 size={18} color="var(--primary)" /> :
                    activeStep === index ? <span className="forgot-current-label">CURRENT</span> : null}
                </li>
              ))}
            </ol>
            <div className="forgot-info-note">
              <ShieldCheck size={19} />
              <span>For privacy, Dormora never reveals whether a username exists during account identification.
                Password changes require a verified, single-use backend authorization.</span>
            </div>
          </section>

          <section className="forgot-card" aria-label="Password recovery form">
            <div className="forgot-card-icon">
              {step === 4 ? <CheckCircle2 size={25} /> : step === 2 ? <Mail size={24} /> : <KeyRound size={24} />}
            </div>
            <div className="forgot-card-step">{step === 4 ? "RECOVERY COMPLETE" : `STEP ${step + 1} OF 4`}</div>
            <h2>{["Forgot your password?", "Choose your security question", "Verify your email code", "Set a new password", "Password updated"][step]}</h2>
            <p className="forgot-card-subtitle">{[
              "Enter your registered username and complete the CAPTCHA to begin.",
              "Choose one assigned question, then enter and confirm your answer.",
              "Check your registered email for the latest six-digit code. Codes expire after three minutes.",
              "Your verified reset permission is temporary and can be used only once.",
              "Your password change has been confirmed by Dormora. Sign in to continue.",
            ][step]}</p>

            {!LOCAL_RECOVERY_ENABLED && <p className="forgot-captcha-preview" role="note">
              Local recovery is inactive. Run Vite on http://localhost:5173 with
              VITE_DORMORA_LOCAL_LOGIN=true and start File 124's recovery runner.
            </p>}

            {step === 0 && (
              <form className="forgot-form" onSubmit={identify}>
                <div className="forgot-field">
                  <label htmlFor="recovery-username">Username <span className="forgot-required">*</span></label>
                  <div className="forgot-input-wrap">
                    <UserRound size={19} aria-hidden="true" />
                    <input id="recovery-username" name="username" value={username}
                      onChange={(event) => { setUsername(event.target.value); setFeedback(null); }}
                      autoComplete="username" maxLength={255} placeholder="Enter your registered username"
                      required disabled={busy || !LOCAL_RECOVERY_ENABLED} />
                  </div>
                </div>
                <div className="forgot-captcha-preview">
                  <ShieldCheck size={20} aria-hidden="true" />
                  <div style={{ minWidth: 0, width: "100%" }}>
                    <strong>CAPTCHA verification</strong>
                    {LOCAL_RECOVERY_ENABLED && SITE_KEY
                      ? <RecoveryCaptcha siteKey={SITE_KEY} onToken={setCaptchaToken} revision={captchaRevision} />
                      : <p>{!SITE_KEY
                          ? "Set VITE_DORMORA_RECAPTCHA_V2_SITE_KEY in frontend/.env.local."
                          : "Enable localhost testing to use Google CAPTCHA."}</p>}
                  </div>
                </div>
                <button className="forgot-submit-button" type="submit"
                  disabled={!recoveryReady || !captchaToken || busy || !username.trim()}>
                  {busy ? "Verifying…" : "Continue securely"} {!busy && <ArrowRight size={18} />}
                </button>
              </form>
            )}

            {step === 1 && (
              <form className="forgot-form" onSubmit={verifyAnswer}>
                <div className="forgot-field">
                  <label htmlFor="recovery-question">Choose the following question <span className="forgot-required">*</span></label>
                  <select id="recovery-question" style={FIELD_STYLE} value={questionId}
                    onChange={(event) => { setQuestionId(event.target.value); setFeedback(null); }} disabled={busy} required>
                    {questions.map(({ question_id, question_text }) => (
                      <option key={question_id} value={String(question_id)}>{question_text}</option>
                    ))}
                  </select>
                </div>
                <div className="forgot-field">
                  <label htmlFor="recovery-answer">Your Answer <span className="forgot-required">*</span></label>
                  <input id="recovery-answer" type="password" style={FIELD_STYLE} value={answer}
                    onChange={(event) => { setAnswer(event.target.value); setFeedback(null); }}
                    autoComplete="off" maxLength={100} required disabled={busy} />
                </div>
                <div className="forgot-field">
                  <label htmlFor="recovery-answer-confirm">Re-enter Answer <span className="forgot-required">*</span></label>
                  <input id="recovery-answer-confirm" type="password" style={FIELD_STYLE} value={confirmAnswer}
                    onChange={(event) => { setConfirmAnswer(event.target.value); setFeedback(null); }}
                    autoComplete="off" maxLength={100} required disabled={busy} />
                </div>
                <button className="forgot-submit-button" type="submit"
                  disabled={busy || !answer || !confirmAnswer || answer !== confirmAnswer}>
                  {busy ? "Checking answer…" : "Verify answer and send email code"} {!busy && <ArrowRight size={18} />}
                </button>
              </form>
            )}

            {step === 2 && (
              <form className="forgot-form" onSubmit={verifyOtp}>
                <div className="forgot-field">
                  <label htmlFor="recovery-otp">Six-digit email OTP <span className="forgot-required">*</span></label>
                  <div className="forgot-input-wrap">
                    <Mail size={19} aria-hidden="true" />
                    <input ref={otpRef} id="recovery-otp" inputMode="numeric" type="text"
                      autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6}
                      placeholder="000000" value={otp} required disabled={busy}
                      onChange={(event) => { setOtp(event.target.value.replace(/\D/g, "").slice(0, 6)); setFeedback(null); }} />
                  </div>
                  <small style={{ color: "var(--muted)" }}>Three-minute code expiry · Maximum three incorrect attempts.</small>
                </div>
                <button className="forgot-submit-button" type="submit" disabled={busy || otp.length !== 6}>
                  {busy ? "Verifying code…" : "Verify code"} {!busy && <ArrowRight size={18} />}
                </button>
                <button type="button" style={SECONDARY_STYLE} disabled={busy || secondsLeft > 0} onClick={resendOtp}>
                  <RefreshCw size={15} /> {secondsLeft > 0 ? `Resend available in ${secondsLeft}s` : "Resend verification code"}
                </button>
              </form>
            )}

            {step === 3 && (
              <form className="forgot-form" onSubmit={resetPassword}>
                {passwordField({ label: "Enter Password", value: nextPassword, setter: setNextPassword,
                  shown: showPassword, toggle: () => setShowPassword((v) => !v), id: "recovery-new-password" })}
                {passwordField({ label: "Re-enter Password", value: confirmPassword, setter: setConfirmPassword,
                  shown: showConfirm, toggle: () => setShowConfirm((v) => !v), id: "recovery-confirm-password" })}
                <small style={{ color: "var(--muted)" }}>
                  Password strength: <strong>{passwordStrength(nextPassword)}</strong>
                  {nextPassword && !hasValidPassword ? " · Requires 10–64 characters, uppercase, lowercase, number and symbol." : ""}
                </small>
                <small style={{ color: "var(--muted)" }}>Your current and two preceding passwords cannot be reused.</small>
                <button className="forgot-submit-button" type="submit"
                  disabled={busy || !hasValidPassword || nextPassword !== confirmPassword}>
                  {busy ? "Updating password…" : "Change password securely"} {!busy && <ArrowRight size={18} />}
                </button>
              </form>
            )}

            {step === 4 && (
              <div className="forgot-form">
                <p role="status" style={{ color: "var(--primary)", display: "flex", alignItems: "center", gap: 9 }}>
                  <CheckCircle2 size={20} /> Password reset confirmed.
                </p>
                <Link to="/login" className="forgot-submit-button">Go to Login <ArrowRight size={18} /></Link>
              </div>
            )}

            {feedback && <p role={feedback.kind === "error" ? "alert" : "status"}
              style={{ color: feedback.kind === "error" ? "#cc5555" : "var(--primary)", fontSize: 12, lineHeight: 1.6, marginTop: 13 }}>
              {feedback.text}
            </p>}
            {step !== 0 && step !== 4 && (
              <button type="button" onClick={restart} disabled={busy}
                style={{ ...SECONDARY_STYLE, width: "100%", marginTop: 13 }}>
                <ArrowLeft size={15} /> Restart recovery
              </button>
            )}
            <p className="forgot-preview-message">
              {recoveryReady
                ? "Security checks and password changes are validated by FastAPI, not the browser."
                : "Recovery requires the localhost-only File 124 backend runner."}
            </p>
            <div className="forgot-card-footer">
              <Link to="/login"><ArrowLeft size={16} /> Back to Login</Link>
              <Link to="/">Home <ArrowRight size={16} /></Link>
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

export default ForgotPasswordPage;
