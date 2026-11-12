/*
  Dormora - Frontend File 133 (corrected): registration + live email OTP verification.

  One-file replacement of File 64. Preserves both account roles, name/address
  fields, Q7/Q2/Q4, local validation, theme, and Privacy Notice link.

  Real writes require Vite development mode, localhost:5173, explicit
  VITE_DORMORA_LOCAL_REGISTRATION=true, a public reCAPTCHA v2 site key,
  AND File 63's deliberately started loopback server. Never send actual
  identity numbers or recovery answers while the Privacy Notice is a draft.
  After HTTP 202, a signed HttpOnly pending cookie authorizes OTP verify/resend.
  The browser never reads this cookie or supplies a user ID.
  The API enforces CSRF, reCAPTCHA, rate limits, OTP and database policy.
*/

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Eye,
  EyeOff,
  House,
  LockKeyhole,
  Moon,
  ShieldCheck,
  Sun,
  UserRoundPlus,
} from "lucide-react";
import "../App.css";

// These are PUBLIC frontend settings, never the reCAPTCHA secret key.
// Production builds always disable registration requests through this page.
const API_BASE = "http://localhost:8000";
const SITE_KEY = String(import.meta.env.VITE_DORMORA_RECAPTCHA_V2_SITE_KEY || "").trim();
const LOCAL_SUBMISSION_OPT_IN =
  import.meta.env.DEV === true &&
  import.meta.env.VITE_DORMORA_LOCAL_REGISTRATION === "true" &&
  typeof window !== "undefined" &&
  window.location.hostname === "localhost" &&
  window.location.port === "5173" &&
  window.location.protocol === "http:";

// File 65 CAPTCHA lifecycle correction (React development/StrictMode safe).
// Google owns the iframe created by grecaptcha.render(). React must NEVER
// ask Google to render twice into the same DOM node. Each effect/retry gets
// a fresh inner element; cleanup removes it without disturbing React's ref.
// Only Google's completion callback supplies a token. No CAPTCHA bypass.
function RegistrationCaptcha({ siteKey, onToken }) {
  const holder = useRef(null);
  const latestOnToken = useRef(onToken);
  latestOnToken.current = onToken;
  const [status, setStatus] = useState("loading");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    const outer = holder.current;
    if (!siteKey || !outer) return undefined;

    let active = true;
    let widgetId = null;
    let renderAttempted = false;
    let script = document.querySelector('script[data-dormora-recaptcha="v2"]');

    // This fresh inner node fixes the "already been rendered" failure when
    // React StrictMode re-runs effects or the user presses Retry.
    const mountTarget = document.createElement("div");
    outer.replaceChildren(mountTarget);
    latestOnToken.current("");
    setStatus("loading");

    function mountWidget() {
      if (!active || renderAttempted || !mountTarget.isConnected) return;
      if (typeof window.grecaptcha?.render !== "function") return;
      renderAttempted = true;

      try {
        widgetId = window.grecaptcha.render(mountTarget, {
          sitekey: siteKey,
          theme: "light",
          callback: (token) => {
            if (!active) return;
            // The checked appearance alone is not proof. This callback
            // delivers the actual token that FastAPI verifies with Google.
            latestOnToken.current(String(token || ""));
            setStatus("ready");
          },
          "expired-callback": () => {
            if (!active) return;
            latestOnToken.current("");
            setStatus("ready");
          },
          "error-callback": () => {
            if (!active) return;
            latestOnToken.current("");
            setStatus("challenge-error");
          },
        });
        if (active) setStatus("ready");
      } catch (error) {
        // Don't report success if Google never issued a token.
        // This error commonly means a stale render target was reused.
        console.error("Dormora: reCAPTCHA render failed", error);
        if (active) {
          latestOnToken.current("");
          setStatus("render-error");
        }
      }
    }

    function scriptFailed() {
      if (!active || renderAttempted) return;
      if (script) script.dataset.dormoraLoadState = "failed";
      setStatus("network-error");
    }

    if (script?.dataset.dormoraLoadState === "failed") {
      script.remove();
      script = null;
    }
    if (!script) {
      script = document.createElement("script");
      script.src = "https://www.google.com/recaptcha/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      script.dataset.dormoraRecaptcha = "v2";
      script.addEventListener("error", scriptFailed);
      script.addEventListener("load", mountWidget);
      document.head.appendChild(script);
    } else {
      script.addEventListener("error", scriptFailed);
      script.addEventListener("load", mountWidget);
    }

    // Covers previously loaded scripts and APIs ready just after load.
    const readyPoll = window.setInterval(mountWidget, 200);
    const loadTimeout = window.setTimeout(() => {
      if (active && !renderAttempted) setStatus("timeout");
    }, 15000);
    mountWidget();

    return () => {
      active = false;
      window.clearInterval(readyPoll);
      window.clearTimeout(loadTimeout);
      script?.removeEventListener("error", scriptFailed);
      script?.removeEventListener("load", mountWidget);
      if (widgetId !== null && typeof window.grecaptcha?.reset === "function") {
        try { window.grecaptcha.reset(widgetId); } catch { /* widget retired */ }
      }
      // Do not just empty Google's rendered element and reuse it: Google
      // still tracks it internally. The next effect creates a NEW element.
      mountTarget.remove();
    };
  }, [siteKey, retryCount]);

  const loading = status === "loading";
  const errorText = {
    "network-error": "Google reCAPTCHA was blocked or could not load. Check browser Shields and your connection.",
    timeout: "Google reCAPTCHA did not initialize within 15 seconds. Check the browser Console.",
    "render-error": "Google reCAPTCHA could not initialize. Click Retry; if this continues, check the Console error.",
    "challenge-error": "The Google CAPTCHA challenge encountered a network error. Retry after checking your connection.",
  }[status];

  return (
    <div className="register-captcha-panel" aria-label="Google reCAPTCHA verification">
      <div ref={holder} />
      {loading && (
        <p className="register-inline-note" role="status">
          Loading Google reCAPTCHA checkbox…
        </p>
      )}
      {errorText && (
        <div role="alert">
          <p className="register-field-error">{errorText}</p>
          <button
            type="button"
            className="login-register-nav"
            onClick={() => {
              latestOnToken.current("");
              setRetryCount((count) => count + 1);
            }}
          >
            Retry loading CAPTCHA
          </button>
        </div>
      )}
    </div>
  );
}

function registrationPayload(form, accountType, privacyAccepted, captchaToken) {
  const data = new FormData(form);
  const read = (name) => String(data.get(name) ?? "");
  const optional = (name) => read(name) || null;
  const payload = {
    role: accountType === "owner" ? "property_owner" : "renter",
    id_number: read("idNumber"),
    first_name: read("firstName"),
    middle_name: optional("middleName"),
    family_name: read("familyName"),
    name_extension: optional("nameExtension"),
    other_extension: read("nameExtension") === "Other" ? optional("otherExtension") : null,
    birthdate: read("birthdate"),
    street: read("street"),
    barangay: read("barangay"),
    city: read("city"),
    province: read("province"),
    country: read("country"),
    zip_code: read("zipCode"),
    email: read("email"),
    username: read("username"),
    password: read("password"),
    confirm_password: read("confirmPassword"),
    security_answer_1: read("securityAnswer1"),
    security_answer_2: read("securityAnswer2"),
    security_answer_3: read("securityAnswer3"),
    privacy_consent: privacyAccepted === true,
    website: read("website"), // File 133: submit the actual honeypot field value.
    captchaToken,
  };
  if (accountType === "owner") {
    payload.primaryPropertyType = optional("primaryPropertyType");
    payload.primaryPropertyArea = optional("primaryPropertyArea");
    payload.expectedRent = optional("expectedRent");
    payload.expectedAvailableDate = optional("expectedAvailableDate");
  } else {
    payload.preferredRentalType = optional("preferredRentalType");
    payload.preferredRentalArea = optional("preferredRentalArea");
    payload.monthlyBudget = optional("monthlyBudget");
    payload.targetMoveInDate = optional("targetMoveInDate");
  }
  return payload;
}

const SERVER_TO_FORM_FIELD = {
  id_number: "idNumber", first_name: "firstName", middle_name: "middleName",
  family_name: "familyName", name_extension: "nameExtension",
  other_extension: "otherExtension", zip_code: "zipCode",
  confirm_password: "confirmPassword", privacy_consent: "privacyConsent",
  security_answer_1: "securityAnswer1", security_answer_2: "securityAnswer2",
  security_answer_3: "securityAnswer3", preferred_rental_type: "preferredRentalType",
  preferred_rental_area: "preferredRentalArea", maximum_monthly_budget: "monthlyBudget",
  target_move_in_date: "targetMoveInDate", primary_property_type: "primaryPropertyType",
  primary_property_area: "primaryPropertyArea", expected_monthly_rent: "expectedRent",
  expected_availability_date: "expectedAvailableDate",
};

function safeFieldErrors(serverBody) {
  if (!Array.isArray(serverBody?.errors)) return [];
  return serverBody.errors.slice(0, 20)
    .filter((item) => item && typeof item.message === "string")
    .map((item) => ({
      name: SERVER_TO_FORM_FIELD[item.field] || item.field || "privacyConsent",
      message: item.message.slice(0, 240),
    }));
}

async function requestJson(path, options = {}) {
  const result = await fetch(`${API_BASE}${path}`, {
    mode: "cors",
    credentials: "include",
    cache: "no-store",
    ...options,
  });
  let body = null;
  try { body = await result.json(); } catch { /* handled by status */ }
  return { result, body };
}

// Age is displayed for convenience. FastAPI must calculate and verify it again.
function calculateAge(birthdate) {
  if (!birthdate) return null;

  const birth = new Date(`${birthdate}T00:00:00`);
  if (Number.isNaN(birth.getTime())) return null;

  const today = new Date();
  if (birth > today) return null;

  let age = today.getFullYear() - birth.getFullYear();
  const monthDifference = today.getMonth() - birth.getMonth();

  if (
    monthDifference < 0 ||
    (monthDifference === 0 && today.getDate() < birth.getDate())
  ) {
    age -= 1;
  }

  return age;
}

// Mirrors the current File 51 schema for local testing. Only FastAPI's
// server-side checks are authoritative when registration is later activated.
// All submitted values are kept in the browser; secrets are not displayed.
const CHECKED_FIELD_ID = {
  idNumber: "register-id", firstName: "register-first-name",
  middleName: "register-middle-name", familyName: "register-family-name",
  nameExtension: "register-extension", otherExtension: "register-other-extension",
  birthdate: "register-birthdate", street: "register-street",
  barangay: "register-barangay", city: "register-city",
  province: "register-province", country: "register-country",
  zipCode: "register-zip", email: "register-email",
  username: "register-username", password: "register-password",
  confirmPassword: "register-confirm", securityAnswer1: "register-answer-1",
  securityAnswer2: "register-answer-2", securityAnswer3: "register-answer-3",
  privacyConsent: "register-privacy-consent",
  preferredRentalType: "renter-room-type", preferredRentalArea: "renter-area",
  monthlyBudget: "renter-budget", targetMoveInDate: "renter-move-in",
  primaryPropertyType: "owner-property-type", primaryPropertyArea: "owner-property-area",
  expectedRent: "owner-rent", expectedAvailableDate: "owner-available",
};

function localPasswordStrength(value) {
  const groups = [/[a-z]/.test(value), /[A-Z]/.test(value), /[0-9]/.test(value),
    /[^\p{L}\p{N}\s]/u.test(value)].filter(Boolean).length;
  if (groups < 3) return "Weak";
  return groups === 4 && value.length >= 12 ? "Strong" : "Medium";
}

function localAge(iso) {
  return calculateAge(iso);
}

function validateLocalRegistration(form, role, consent) {
  const data = new FormData(form);
  const val = (name) => String(data.get(name) ?? "");
  const errors = [];
  const fail = (name, message) => errors.push({ name, message });
  const nameValid = (value, min, max) => {
    if (value.length < min || value.length > max || value !== value.trim() ||
        value.includes("  ") || !/^[\p{L} ]+$/u.test(value) ||
        value.toUpperCase() === value || /([\p{L}])\1\1/iu.test(value)) return false;
    return value.split(" ").every((word) =>
      word.length > 0 && word[0] === word[0].toUpperCase() &&
      word.slice(1) === word.slice(1).toLowerCase());
  };
  const title = (name, label, min = 2, max = 50, optional = false) => {
    const value = val(name);
    if (optional && !value) return;
    if (!nameValid(value, min, max))
      fail(name, `${label} must be ${min}–${max} letters, Title Case, with single spaces.`);
  };

  if (!/^\d{4}-\d{4}$/.test(val("idNumber")))
    fail("idNumber", "Use the ID Number format 1234-5678.");
  title("firstName", "First name", 2, 26);
  title("middleName", "Middle name", 2, 26, true);
  title("familyName", "Family name", 2, 26);
  if (val("nameExtension") === "Other") {
    if (!["I", "II", "III", "IV", "IX", "X"].includes(val("otherExtension")))
      fail("otherExtension", "Enter I, II, III, IV, IX, or X.");
  } else if (!["", "Jr.", "Sr."].includes(val("nameExtension"))) {
    fail("nameExtension", "Select a valid name extension.");
  }
  if (localAge(val("birthdate")) === null || localAge(val("birthdate")) < 18)
    fail("birthdate", "You must enter a valid birthdate showing an age of at least 18.");

  const street = val("street");
  if (street.length < 3 || street.length > 50 || street !== street.trim() ||
      street.includes("  ") || !/^[\p{L}\p{N} ]+$/u.test(street))
    fail("street", "Street / purok must contain 3–50 letters, digits, or single spaces.");
  title("barangay", "Barangay");
  title("city", "Municipality / City");
  title("province", "Province");
  title("country", "Country", 2, 100);
  if (!/^\d{4}$/.test(val("zipCode")))
    fail("zipCode", "ZIP Code must contain exactly four digits.");

  const email = val("email");
  if (!email || email.length > 100 || /\s/.test(email) || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))
    fail("email", "Enter a valid email address (maximum 100 characters).");
  const username = val("username");
  if (!/^[A-Za-z][A-Za-z0-9]{5,16}$/.test(username))
    fail("username", "Username: 6–17 letters/digits, starting with a letter.");
  const password = val("password");
  if (password.length < 10 || password.length > 64 ||
      localPasswordStrength(password) === "Weak" ||
      (username && password.toLowerCase().includes(username.toLowerCase())))
    fail("password", "Password: 10–64 characters, 3 character groups, and no username.");
  if (password !== val("confirmPassword"))
    fail("confirmPassword", "Password confirmation must match exactly.");

  for (let i = 1; i <= 3; i += 1) {
    const name = `securityAnswer${i}`;
    const answer = val(name);
    if (answer.length < 2 || answer.length > 50 || answer !== answer.trim() ||
        answer.includes("  ") || !/^[\p{L} ]+$/u.test(answer))
      fail(name, `Security answer ${i}: 2–50 letters with single spaces only.`);
  }

  const location = (name, label) => {
    const value = val(name);
    if (!value) return;
    if (value.length < 3 || value.length > 100 || value !== value.trim() ||
        value.includes("  ") || !/^[\p{L}\p{N} .,'-]+$/u.test(value) ||
        !/[\p{L}]/u.test(value))
      fail(name, `${label}: 3–100 valid characters, without extra spaces or markup.`);
  };
  const amount = (name, label) => {
    const value = val(name);
    if (!value) return;
    if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(value) || Number(value) <= 0)
      fail(name, `${label} must be greater than ₱0 with at most two decimal places.`);
  };
  const futureDate = (name, label) => {
    const value = val(name);
    if (!value) return;
    const today = new Date();
    const localToday = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    const parsed = new Date(`${value}T00:00:00`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(parsed.getTime()) ||
        parsed.toLocaleDateString("en-CA") === "Invalid Date" || value < localToday)
      fail(name, `${label} cannot be in the past.`);
  };

  if (role === "renter") {
    if (val("preferredRentalType") && !["shared", "private", "either"].includes(val("preferredRentalType")))
      fail("preferredRentalType", "Select a valid rental type.");
    location("preferredRentalArea", "Preferred rental area");
    amount("monthlyBudget", "Monthly budget");
    futureDate("targetMoveInDate", "Target move-in date");
  } else {
    if (val("primaryPropertyType") && !["dormitory", "boarding-house", "apartment", "room"].includes(val("primaryPropertyType")))
      fail("primaryPropertyType", "Select a valid property type.");
    location("primaryPropertyArea", "Property area");
    amount("expectedRent", "Expected rent");
    futureDate("expectedAvailableDate", "Availability date");
  }
  if (!consent) fail("privacyConsent", "Read the Privacy Notice and check the consent box for this test.");
  return errors;
}

function RegisterPage({ darkMode, onToggleTheme }) {
  const [accountType, setAccountType] = useState("renter");
  const [birthdate, setBirthdate] = useState("");
  const [extension, setExtension] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [validationErrors, setValidationErrors] = useState([]);
  const [localTestPassed, setLocalTestPassed] = useState(false);
  const [testedAt, setTestedAt] = useState("");
  const [captchaToken, setCaptchaToken] = useState("");
  const [captchaRevision, setCaptchaRevision] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submissionSucceeded, setSubmissionSucceeded] = useState(false);
  const [submissionUncertain, setSubmissionUncertain] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitHint, setSubmitHint] = useState("");
  // File 65 OTP step: no passwords, user IDs, pending cookies or OTPs are persisted.
  const [otpStage, setOtpStage] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [otpBusy, setOtpBusy] = useState(false);
  const [otpVerified, setOtpVerified] = useState(false);
  const [otpFeedback, setOtpFeedback] = useState(null);
  const [otpResendAvailableAt, setOtpResendAvailableAt] = useState(0);
  const [otpClock, setOtpClock] = useState(() => Date.now());
  const otpActionInFlight = useRef(false);
  const otpFieldRef = useRef(null);

  const resendRemainingSeconds = Math.max(
    0, Math.ceil((otpResendAvailableAt - otpClock) / 1000)
  );
  useEffect(() => {
    if (!otpStage || otpVerified || !otpResendAvailableAt) return undefined;
    const interval = window.setInterval(() => setOtpClock(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [otpStage, otpVerified, otpResendAvailableAt]);

  async function otpRequest(path, body) {
    const { result: csrfResult, body: csrfBody } = await requestJson("/api/csrf");
    if (!csrfResult.ok || typeof csrfBody?.csrf_token !== "string") {
      return { csrfFailed: true, result: null, body: null };
    }
    const response = await requestJson(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfBody.csrf_token,
      },
      body: JSON.stringify(body),
    });
    return { csrfFailed: false, ...response };
  }

  function showOtpScreen() {
    if (!LOCAL_SUBMISSION_OPT_IN) return;
    setOtpCode("");
    setOtpFeedback(null);
    setOtpStage(true);
  }

  async function handleOtpVerify(event) {
    event.preventDefault();
    if (!LOCAL_SUBMISSION_OPT_IN || otpVerified || otpActionInFlight.current) return;
    if (!/^[0-9]{6}$/.test(otpCode)) {
      setOtpFeedback({ kind: "error", text: "Enter the six-digit code from your Dormora email." });
      otpFieldRef.current?.focus();
      return;
    }
    otpActionInFlight.current = true;
    setOtpBusy(true);
    setOtpFeedback(null);
    let posted = false;
    try {
      const codeToSubmit = otpCode;
      // The server identifies the pending user using its signed HttpOnly cookie.
      // No user ID or email is sent and the OTP is never put in a URL.
      posted = true;
      const { csrfFailed, result, body } = await otpRequest(
        "/api/auth/registration/verify", { code: codeToSubmit }
      );
      if (csrfFailed) {
        setOtpFeedback({ kind: "error", text: "Could not initialize secure verification. Confirm File 63 is running." });
      } else if (result.status === 200 && body?.verified === true) {
        setOtpVerified(true);
        setOtpCode("");
        setOtpFeedback({ kind: "success", text: "Email verified. Your pending account is now activated in Dormora. No login session was created." });
      } else if (result.status === 400) {
        setOtpCode("");
        setOtpFeedback({ kind: "error", text: "Incorrect, expired, or already-used code. Check your latest email. Too many incorrect attempts may invalidate it." });
      } else if (result.status === 403) {
        setOtpCode("");
        setOtpFeedback({ kind: "error", text: "Verification was rejected. Your pending-registration browser cookie may have expired (30 minutes) or the account may already be active. Check backend state before registering again." });
      } else if (result.status === 404) {
        setOtpFeedback({ kind: "error", text: "OTP verification is disabled. Start the File 63 localhost runner with --enable-local-registration." });
      } else if (result.status === 429) {
        setOtpFeedback({ kind: "error", text: "Too many attempts. Follow the server limit before trying again." });
      } else if (result.status === 503) {
        setOtpFeedback({ kind: "error", text: "Verification service is temporarily unavailable. Check backend logs and database before retrying." });
      } else {
        setOtpFeedback({ kind: "error", text: "Unexpected verification response. Confirm account status on the backend before retrying." });
      }
    } catch {
      setOtpFeedback({ kind: "error", text: posted
        ? "Connection lost during verification. Your account might already be active; check backend state before submitting again."
        : "Cannot reach the backend. Check that File 63 is running." });
    } finally {
      setOtpBusy(false);
      otpActionInFlight.current = false;
    }
  }

  async function handleOtpResend() {
    if (!LOCAL_SUBMISSION_OPT_IN || otpVerified || otpActionInFlight.current || resendRemainingSeconds > 0) return;
    otpActionInFlight.current = true;
    setOtpBusy(true);
    setOtpFeedback(null);
    let posted = false;
    try {
      posted = true;
      const { csrfFailed, result, body } = await otpRequest(
        "/api/auth/registration/resend", {}
      );
      if (csrfFailed) {
        setOtpFeedback({ kind: "error", text: "Could not initialize secure resend. Check the local backend connection." });
      } else if (result.status === 200 && typeof body?.resend_cooldown_seconds === "number") {
        const cooldown = Math.max(1, Math.min(900, Math.ceil(body.resend_cooldown_seconds)));
        setOtpResendAvailableAt(Date.now() + cooldown * 1000);
        setOtpClock(Date.now());
        setOtpCode("");
        setOtpFeedback({ kind: "success", text: `A replacement email was submitted. Use its new six-digit code; it expires in ${Number(body.expires_in_minutes) || 3} minutes. The old code is no longer valid.` });
      } else if (result.status === 429) {
        const retryAfter = Number(result.headers.get("Retry-After"));
        const wait = Number.isFinite(retryAfter) && retryAfter > 0 ? Math.min(900, Math.ceil(retryAfter)) : 60;
        setOtpResendAvailableAt(Date.now() + wait * 1000);
        setOtpClock(Date.now());
        setOtpFeedback({ kind: "error", text: `Resend is limited by the server. Try again after about ${wait} seconds.` });
      } else if (result.status === 403) {
        setOtpFeedback({ kind: "error", text: "Your pending-registration cookie has expired or the account cannot be verified. Do not create another account without checking PostgreSQL first." });
      } else if (result.status === 404) {
        setOtpFeedback({ kind: "error", text: "OTP resend is disabled. Start the File 63 localhost runner." });
      } else if (result.status === 503) {
        setOtpFeedback({ kind: "error", text: "Email delivery could not be confirmed. Check Gmail/backend logs and avoid repeated requests." });
      } else {
        setOtpFeedback({ kind: "error", text: "Could not request another code. Check backend status before trying again." });
      }
    } catch {
      setOtpFeedback({ kind: "error", text: posted
        ? "Connection lost while requesting a code. A replacement might already have been issued. Check your inbox and backend before trying again."
        : "Cannot reach the backend." });
    } finally {
      setOtpBusy(false);
      otpActionInFlight.current = false;
    }
  }

  const age = calculateAge(birthdate);
  const isOwner = accountType === "owner";

  // Local validation remains useful even when the real server isn't opted in.
  // The backend always revalidates; frontend checks are not a security boundary.
  async function handlePreviewSubmit(event) {
    event.preventDefault();
    if (submitting || submissionSucceeded || submissionUncertain) return;
    const form = event.currentTarget;
    const errors = validateLocalRegistration(form, accountType, privacyAccepted);
    setValidationErrors(errors);
    setSubmitError("");
    setSubmitHint("");
    setLocalTestPassed(false);
    if (errors.length > 0) {
      const target = form.elements.namedItem(errors[0].name);
      if (target && typeof target.focus === "function") target.focus();
      return;
    }
    if (!LOCAL_SUBMISSION_OPT_IN) {
      setLocalTestPassed(true);
      setTestedAt(new Date().toLocaleTimeString());
      return;
    }
    if (!SITE_KEY) {
      setSubmitError("Configure VITE_DORMORA_RECAPTCHA_V2_SITE_KEY to use real localhost registration.");
      return;
    }
    if (!captchaToken) {
      setSubmitError("Complete the Google reCAPTCHA checkbox before submitting.");
      return;
    }

    // Obtain a real signed CSRF token AND HttpOnly cookie first. If this
    // fails, no registration POST has been dispatched and a retry is safe.
    setSubmitting(true);
    let postDispatched = false;
    try {
      const { result: csrfResponse, body: csrfBody } = await requestJson("/api/csrf");
      if (!csrfResponse.ok || typeof csrfBody?.csrf_token !== "string") {
        setSubmitError("Could not start secure registration. Confirm File 63 is running on port 8000.");
        return;
      }
      // No PII is sent in URL parameters; secrets stay only in the HTTPS
      // body in production. This is a localhost-only HTTP development test.
      const payload = registrationPayload(form, accountType, privacyAccepted, captchaToken);
      postDispatched = true;
      const { result, body } = await requestJson("/api/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfBody.csrf_token,
        },
        body: JSON.stringify(payload),
      });
      if (result.status === 202 && body?.verification_required === true) {
        // The server sets an HttpOnly, signed pending-registration cookie.
        // No user_id/OTP is exposed to JavaScript. File 65 will verify it.
        setSubmissionSucceeded(true);
        setPrivacyAccepted(false);
        setBirthdate("");
        setExtension("");
        form.reset(); // Clear the secret inputs immediately after success.
        setSubmitHint("Pending account created. Enter the verification code from your Gmail inbox below.");
        showOtpScreen();
      } else if (result.status === 409) {
        setSubmitError("An account with these registration details already exists. Use different fictional test details; do not repeat the same registration.");
      } else if (result.status === 422) {
        setValidationErrors(safeFieldErrors(body));
        setSubmitError("FastAPI rejected one or more fields. Correct the highlighted details before trying again.");
      } else if (result.status === 429) {
        setSubmitError("Too many attempts. Follow the server rate limit before trying again.");
      } else if (result.status === 503) {
        // Some File 55 503 responses happen AFTER a database account was
        // committed. Never encourage an automatic retry or duplicate account.
        setSubmissionUncertain(true);
        setSubmitError("Registration may have been saved, but email or verification failed. Do not submit again with these details. Inspect the backend logs and database first.");
      } else if (result.status === 404) {
        setSubmitError("Registration is disabled on this backend. Start File 63 using --enable-local-registration, not normal uvicorn.");
      } else if (result.status === 403) {
        setSubmitError("The backend rejected the request origin or CSRF token. Use exactly http://localhost:5173 and the File 63 runner.");
      } else if (result.status === 400) {
        setSubmitError("Registration rejected. Check the CAPTCHA and your details before trying again.");
      } else {
        setSubmissionUncertain(true);
        setSubmitError("Unexpected server response after submission. Check PostgreSQL before any retry to avoid duplicate accounts.");
      }
    } catch {
      if (postDispatched) {
        setSubmissionUncertain(true);
        setSubmitError("Connection failed after registration was sent. It may have been saved. Do not resubmit until you check PostgreSQL and Gmail.");
      } else {
        setSubmitError("Cannot reach the local FastAPI server. Start File 63 and try again.");
      }
    } finally {
      setSubmitting(false);
      setCaptchaToken("");
      setCaptchaRevision((n) => n + 1);
    }
  }

  function clearFeedback() {
    if (validationErrors.length > 0) setValidationErrors([]);
    if (localTestPassed) setLocalTestPassed(false);
    if (submitError && !submissionUncertain) setSubmitError("");
  }

  return (
    <div
      className={
        darkMode
          ? "dormora dark-mode register-page"
          : "dormora light-mode register-page"
      }
    >
      <style>{`
        .register-test-result { border: 1px solid var(--border); background: var(--soft);
          border-radius: 13px; padding: 16px 18px; margin-top: 18px; }
        .register-test-result h3 { font-size: 15px; margin: 0 0 6px; color: var(--text); }
        .register-test-result p { font-size: 13px; margin: 0; color: var(--muted); }
        .register-test-errors { border-color: #d85e5e; }
        .register-test-errors ul { margin: 10px 0 0; padding-left: 20px; }
        .register-test-errors li { margin: 5px 0; font-size: 13px; }
        .register-test-errors a { color: var(--text); text-decoration: underline; }
        .register-test-success { border-color: var(--primary); }
        .register-test-disclaimer { font-size: 12px; margin: 10px 0 0; color: var(--muted); }
        .register-test-key { font-size: 12px; font-weight: 750; color: var(--primary); }
        .register-captcha-wrap { margin-top: 16px; overflow-x: auto; }
        .register-captcha-panel { min-height: 83px; }
        .register-submit-button:disabled { opacity: .68; cursor: not-allowed; }
        .register-page .dormora-otp-card { border: 1px solid var(--border);
          border-radius: 19px; background: var(--card); box-shadow: var(--shadow);
          padding: clamp(22px, 4vw, 36px); max-width: 640px; margin-inline: auto; }
        .register-page .dormora-otp-card h2 { margin: 8px 0; font-size: clamp(24px, 3vw, 29px); color: var(--text); }
        .register-page .dormora-otp-card .dormora-otp-subtitle { color: var(--muted); font-size: 13px; line-height: 1.7; }
        .register-page .dormora-otp-card .dormora-otp-mark { display: inline-flex; padding: 13px;
          background: var(--soft); color: var(--primary); border-radius: 14px; }
        .register-page .dormora-otp-field { width: 100%; max-width: 280px; padding: 12px 14px;
          border: 1px solid var(--border); border-radius: 12px; background: var(--background);
          color: var(--text); font: 700 25px/1.2 monospace; text-align: center;
          letter-spacing: .27em; margin: 10px 0 4px; }
        .register-page .dormora-otp-field:focus-visible { outline: 3px solid var(--primary); outline-offset: 2px; }
        .register-page .dormora-otp-resend { padding: 10px 5px; margin-top: 12px;
          color: var(--primary); background: transparent; border: 0; font: inherit;
          font-size: 13px; font-weight: 750; cursor: pointer; }
        .register-page .dormora-otp-resend:disabled { color: var(--muted); cursor: not-allowed; }
        .register-page .dormora-otp-open { border: 0; background: transparent;
          color: var(--primary); font-weight: 750; text-decoration: underline;
          padding: 5px 0; cursor: pointer; }
        .register-page .dormora-otp-feedback { margin-top: 14px; padding: 12px 14px;
          border-radius: 11px; font-size: 13px; line-height: 1.65; }
        .register-page .dormora-otp-feedback[data-kind="error"] { border: 1px solid #ce6464; background: var(--soft); }
        .register-page .dormora-otp-feedback[data-kind="success"] { border: 1px solid var(--primary); background: var(--soft); }
        .register-page .dormora-otp-step-note { color: var(--muted); font-size: 12px; line-height: 1.65; margin: 14px 0 0; }

      `}</style>
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>

      <header className="site-header">
        <div className="page-container header-content register-header-content">
          <Link className="brand" to="/">
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </Link>

          <nav className="register-header-nav" aria-label="Registration navigation">
            <Link to="/">Home</Link>
            {/* Reuse the Login Page navigation button styling. */}
            <Link
              className="login-register-nav"
              to="/login"
              aria-label="Go to Log In page"
            >
              Log In
            </Link>
            <button
              className="theme-button"
              type="button"
              onClick={onToggleTheme}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              title={darkMode ? "Light mode" : "Dark mode"}
            >
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </nav>
        </div>
      </header>

      <main className="register-main">
        <div className="page-container register-layout">
          <div className="register-intro">
            <div className="register-heading">
              <span className="register-eyebrow">
                <UserRoundPlus size={17} /> Join Dormora
              </span>
              <h1>{otpStage ? "Verify your email" : "Create your account"}</h1>
              <p>
                {otpStage
                  ? "Finish your Dormora registration using the six-digit code sent to your email."
                  : "Enter your details to register on the local FastAPI development server. Google reCAPTCHA and email verification protect new accounts."}
              </p>
            </div>

            <div className="register-security-note" role="note">
              <ShieldCheck size={21} />
              <div>
                <strong>Privacy and security first</strong>
                <p>
                  {otpStage
                    ? "Codes expire after 3 minutes. A resend invalidates the previous code."
                    : "For localhost tests, the backend validates details, checks reCAPTCHA, creates a pending account, and sends a 3-minute Gmail OTP."}
                </p>
              </div>
            </div>
          </div>

          {!otpStage && (
          <form className="register-form" onSubmit={handlePreviewSubmit}
            onChange={clearFeedback} noValidate>
            {/* File 133: genuine off-screen text honeypot. Keep its value intact
                so automated form fillers can be rejected by backend validation. */}
            <div
              aria-hidden="true"
              style={{
                position: "absolute",
                left: "-10000px",
                top: "auto",
                width: "1px",
                height: "1px",
                overflow: "hidden",
              }}
            >
              <label htmlFor="dormora-registration-website">Website (leave blank)</label>
              <input
                id="dormora-registration-website"
                name="website"
                type="text"
                autoComplete="off"
                defaultValue=""
                tabIndex={-1}
              />
            </div>
            <p className="register-inline-note" role="status">
              <strong>{LOCAL_SUBMISSION_OPT_IN ? "Live localhost test mode" : "Local validation mode"}:</strong>{" "}
              {LOCAL_SUBMISSION_OPT_IN
                ? "Submitting this form can create persistent PostgreSQL records and send an actual Gmail OTP. Use fictional ID numbers, addresses, and security answers; use an email inbox you control. The Privacy Notice remains a draft."
                : "No information is sent to FastAPI. To test real registration, opt in through frontend/.env.local, start the File 63 localhost runner, and use fictional details."}
            </p>
            {LOCAL_SUBMISSION_OPT_IN && (
              <p className="register-inline-note">
                Already received an email code?{" "}
                <button className="dormora-otp-open" type="button" onClick={showOtpScreen}>
                  Enter verification code
                </button>
                <small style={{ display: "block" }}>
                  Requires the signed pending-registration cookie from this browser,
                  which expires after 30 minutes. Do not register again to get a code.
                </small>
              </p>
            )}
            {/* 1. Account role */}
            <section className="register-section" aria-labelledby="register-role-title">
              <div className="register-section-heading">
                <span className="register-step-number">01</span>
                <div>
                  <h2 id="register-role-title">Choose your account type</h2>
                  <p>Select how you'll use Dormora.</p>
                </div>
              </div>

              <div className="register-role-options">
                <label className={`register-role-option ${!isOwner ? "is-selected" : ""}`}>
                  <input
                    type="radio"
                    name="accountType"
                    value="renter"
                    checked={!isOwner}
                    onChange={() => { setAccountType("renter"); clearFeedback(); }}
                  />
                  <span>
                    <strong>Renter</strong>
                    <small>Discover rentals and track rent and deposits</small>
                  </span>
                  {!isOwner && <CheckCircle2 size={19} aria-hidden="true" />}
                </label>

                <label className={`register-role-option ${isOwner ? "is-selected" : ""}`}>
                  <input
                    type="radio"
                    name="accountType"
                    value="owner"
                    checked={isOwner}
                    onChange={() => { setAccountType("owner"); clearFeedback(); }}
                  />
                  <span>
                    <strong>Property Owner</strong>
                    <small>Create and manage rental listings after approval</small>
                  </span>
                  {isOwner && <CheckCircle2 size={19} aria-hidden="true" />}
                </label>
              </div>
              {isOwner && (
                <p className="register-inline-note">
                  Property-owner accounts will require administrator review before
                  listing-management permissions are granted.
                </p>
              )}
            </section>

            {/* 2. Required identity details from the IT 107 handout */}
            <section className="register-section" aria-labelledby="register-personal-title">
              <div className="register-section-heading">
                <span className="register-step-number">02</span>
                <div>
                  <h2 id="register-personal-title">Personal information</h2>
                  <p>Fields marked <span className="register-required">*</span> are required.</p>
                </div>
              </div>

              <div className="register-fields-grid">
                <div className="register-field register-full-width">
                  <label htmlFor="register-id">ID Number <span className="register-required">*</span></label>
                  <input
                    id="register-id"
                    name="idNumber"
                    type="text"
                    inputMode="numeric"
                    placeholder="xxxx-xxxx"
                    maxLength={9}
                    autoComplete="off"
                  />
                  <small>Required instructor format: four digits, a hyphen, four digits.</small>
                </div>

                <div className="register-field">
                  <label htmlFor="register-first-name">First Name <span className="register-required">*</span></label>
                  <input id="register-first-name" name="firstName" type="text" placeholder="Juan" autoComplete="given-name" />
                </div>
                <div className="register-field">
                  <label htmlFor="register-middle-name">Middle Name <em>(Optional)</em></label>
                  <input id="register-middle-name" name="middleName" type="text" placeholder="Optional" autoComplete="additional-name" />
                </div>
                <div className="register-field">
                  <label htmlFor="register-family-name">Family Name <span className="register-required">*</span></label>
                  <input id="register-family-name" name="familyName" type="text" placeholder="Dela Cruz" autoComplete="family-name" />
                </div>
                <div className="register-field">
                  <label htmlFor="register-extension">Name Extension <em>(Optional)</em></label>
                  <select id="register-extension" name="nameExtension" value={extension} onChange={(event) => setExtension(event.target.value)}>
                    <option value="">None</option>
                    <option value="Jr.">Jr.</option>
                    <option value="Sr.">Sr.</option>
                    <option value="Other">Other</option>
                  </select>
                </div>
                {extension === "Other" && (
                  <div className="register-field register-full-width">
                    <label htmlFor="register-other-extension">Other Extension <span className="register-required">*</span></label>
                    <input id="register-other-extension" name="otherExtension" type="text" placeholder="I, II, III, IV, IX or X" />
                  </div>
                )}
                <div className="register-field">
                  <label htmlFor="register-birthdate">Birthdate <span className="register-required">*</span></label>
                  <input
                    id="register-birthdate"
                    name="birthdate"
                    type="date"
                    value={birthdate}
                    onChange={(event) => setBirthdate(event.target.value)}
                  />
                </div>
                <div className="register-field">
                  <label htmlFor="register-age">Age (calculated automatically)</label>
                  <input id="register-age" name="ageDisplay" type="text" value={age === null ? "" : String(age)} placeholder="Calculated from birthdate" readOnly />
                  {age !== null && age < 18 && (
                    <small className="register-field-error" role="alert">
                      You must be at least 18 years old to register.
                    </small>
                  )}
                </div>
              </div>
            </section>

            {/* 3. All six mandatory address fields */}
            <section className="register-section" aria-labelledby="register-address-title">
              <div className="register-section-heading">
                <span className="register-step-number">03</span>
                <div>
                  <h2 id="register-address-title">Home address</h2>
                  <p>Enter your residential address, not the property listing's address.</p>
                </div>
              </div>

              <div className="register-fields-grid">
                <div className="register-field register-full-width">
                  <label htmlFor="register-street">Purok / Street <span className="register-required">*</span></label>
                  <input id="register-street" name="street" type="text" placeholder="Purok 2" autoComplete="address-line1" />
                </div>
                <div className="register-field">
                  <label htmlFor="register-barangay">Barangay <span className="register-required">*</span></label>
                  <input id="register-barangay" name="barangay" type="text" placeholder="Your barangay" />
                </div>
                <div className="register-field">
                  <label htmlFor="register-city">Municipality / City <span className="register-required">*</span></label>
                  <input id="register-city" name="city" type="text" placeholder="Your city" autoComplete="address-level2" />
                </div>
                <div className="register-field">
                  <label htmlFor="register-province">Province <span className="register-required">*</span></label>
                  <input id="register-province" name="province" type="text" placeholder="Your province" autoComplete="address-level1" />
                </div>
                <div className="register-field">
                  <label htmlFor="register-country">Country <span className="register-required">*</span></label>
                  <input id="register-country" name="country" type="text" placeholder="Philippines" autoComplete="country-name" />
                </div>
                <div className="register-field">
                  <label htmlFor="register-zip">ZIP Code <span className="register-required">*</span></label>
                  <input id="register-zip" name="zipCode" type="text" inputMode="numeric" maxLength={4} placeholder="Four digits" autoComplete="postal-code" />
                </div>
              </div>
            </section>

            {/* 4. Four proposed system-specific fields per account role */}
            <section className="register-section" aria-labelledby="register-rental-title">
              <div className="register-section-heading">
                <span className="register-step-number">04</span>
                <div>
                  <h2 id="register-rental-title">
                    {isOwner ? "Property-owner details" : "Rental preferences"}
                  </h2>
                  <p>
                    Proposed Dormora-specific fields for your project. These are
                    optional profile details in this preview and must match your approved proposal.
                  </p>
                </div>
              </div>

              {isOwner ? (
                <div className="register-fields-grid" key="owner-fields">
                  <div className="register-field">
                    <label htmlFor="owner-property-type">Primary Property Type <em>(Optional)</em></label>
                    <select id="owner-property-type" name="primaryPropertyType" defaultValue="">
                      <option value="">Select property type</option>
                      <option value="dormitory">Dormitory</option>
                      <option value="boarding-house">Boarding house</option>
                      <option value="apartment">Apartment</option>
                      <option value="room">Room for rent</option>
                    </select>
                  </div>
                  <div className="register-field">
                    <label htmlFor="owner-property-area">Primary Property Area <em>(Optional)</em></label>
                    <input id="owner-property-area" name="primaryPropertyArea" type="text" placeholder="City or barangay" />
                  </div>
                  <div className="register-field">
                    <label htmlFor="owner-rent">Expected Monthly Rent (₱) <em>(Optional)</em></label>
                    <input id="owner-rent" name="expectedRent" type="number" min="0.01" step="0.01" placeholder="e.g. 4500" />
                  </div>
                  <div className="register-field">
                    <label htmlFor="owner-available">Expected Availability Date <em>(Optional)</em></label>
                    <input id="owner-available" name="expectedAvailableDate" type="date" />
                  </div>
                </div>
              ) : (
                <div className="register-fields-grid" key="renter-fields">
                  <div className="register-field">
                    <label htmlFor="renter-room-type">Preferred Rental Type <em>(Optional)</em></label>
                    <select id="renter-room-type" name="preferredRentalType" defaultValue="">
                      <option value="">Select preference</option>
                      <option value="shared">Shared room</option>
                      <option value="private">Private room</option>
                      <option value="either">Either</option>
                    </select>
                  </div>
                  <div className="register-field">
                    <label htmlFor="renter-area">Preferred Rental Area <em>(Optional)</em></label>
                    <input id="renter-area" name="preferredRentalArea" type="text" placeholder="City or barangay" />
                  </div>
                  <div className="register-field">
                    <label htmlFor="renter-budget">Maximum Monthly Budget (₱) <em>(Optional)</em></label>
                    <input id="renter-budget" name="monthlyBudget" type="number" min="0.01" step="0.01" placeholder="e.g. 5000" />
                  </div>
                  <div className="register-field">
                    <label htmlFor="renter-move-in">Target Move-in Date <em>(Optional)</em></label>
                    <input id="renter-move-in" name="targetMoveInDate" type="date" />
                  </div>
                </div>
              )}
            </section>

            {/* 5. Account credentials */}
            <section className="register-section" aria-labelledby="register-account-title">
              <div className="register-section-heading">
                <span className="register-step-number">05</span>
                <div>
                  <h2 id="register-account-title">Account credentials</h2>
                  <p>Your email will receive verification codes and security alerts.</p>
                </div>
              </div>

              <div className="register-fields-grid">
                <div className="register-field register-full-width">
                  <label htmlFor="register-email">Email Address <span className="register-required">*</span></label>
                  <input id="register-email" name="email" type="email" placeholder="you@example.com" autoComplete="email" />
                </div>
                <div className="register-field register-full-width">
                  <label htmlFor="register-username">Username <span className="register-required">*</span></label>
                  <input id="register-username" name="username" type="text" placeholder="Choose a username" autoComplete="username" spellCheck={false} />
                  <small>Length and availability checks will follow the assigned student seed and FastAPI validation.</small>
                </div>
                <div className="register-field">
                  <label htmlFor="register-password">Password <span className="register-required">*</span></label>
                  <div className="register-password-wrap">
                    <input id="register-password" name="password" type={showPassword ? "text" : "password"} placeholder="Create a password" autoComplete="new-password" />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"}>
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
                <div className="register-field">
                  <label htmlFor="register-confirm">Re-enter Password <span className="register-required">*</span></label>
                  <div className="register-password-wrap">
                    <input id="register-confirm" name="confirmPassword" type={showConfirmPassword ? "text" : "password"} placeholder="Confirm password" autoComplete="new-password" />
                    <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} aria-label={showConfirmPassword ? "Hide confirmation password" : "Show confirmation password"}>
                      {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
                <div className="register-field register-full-width">
                  <small>Password test rule: 10–64 characters, at least three of lowercase,
                    uppercase, numbers, and symbols; do not include your username.</small>
                </div>
              </div>
            </section>

            {/* 6. Three seed-assigned security questions */}
            <section className="register-section" aria-labelledby="register-questions-title">
              <div className="register-section-heading">
                <span className="register-step-number">06</span>
                <div>
                  <h2 id="register-questions-title">Account recovery questions</h2>
                  <p>Three required questions will be assigned using your IT 107 seed.</p>
                </div>
              </div>
              <div className="register-question-list">
                {[
                  { number: 1, label: "Q7", question: "What was the name of your elementary school?" },
                  { number: 2, label: "Q2", question: "Who was your best friend in elementary school?" },
                  { number: 3, label: "Q4", question: "What is your mother's maiden first name?" },
                ].map(({ number, label, question }) => (
                  <div className="register-field" key={label}>
                    <label htmlFor={`register-answer-${number}`}>
                      {label} — Question {number} <span className="register-required">*</span>
                    </label>
                    <p className="register-question-prompt">{question}</p>
                    <input
                      id={`register-answer-${number}`}
                      name={`securityAnswer${number}`}
                      type="password"
                      autoComplete="off"
                      placeholder="Use a sample answer for local testing"
                    />
                  </div>
                ))}
              </div>
              <p className="register-inline-note">
                In live localhost mode, the server hashes recovery answers and stores the
                hashes. Use fictional answers in this development test.
              </p>
            </section>

            {/* 7. Consent and future verification */}
            <section className="register-section" aria-labelledby="register-consent-title">
              <div className="register-section-heading">
                <span className="register-step-number">07</span>
                <div>
                  <h2 id="register-consent-title">Privacy and verification</h2>
                  <p>Review the privacy notice before creating a real account.</p>
                </div>
              </div>

              {/* Keep the consent label and navigation link separate:
                  reading the notice must never toggle the checkbox. */}
              <div className="register-consent">
                <input
                  id="register-privacy-consent"
                  name="privacyConsent"
                  type="checkbox"
                  required
                  checked={privacyAccepted}
                  onChange={(event) => setPrivacyAccepted(event.target.checked)}
                />
                <div>
                  <label htmlFor="register-privacy-consent">
                    I have read the Privacy Notice and agree to the collection and
                    processing of my personal data in accordance with the Data
                    Privacy Act of 2012 (RA 10173). <strong>*</strong>
                  </label>
                  <div style={{ marginTop: 6 }}>
                    <Link
                      to="/privacy"
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label="Read the Dormora Privacy Notice (opens in a new tab)"
                      style={{
                        color: "var(--primary)",
                        fontWeight: 700,
                        textDecoration: "underline",
                        textUnderlineOffset: 3,
                      }}
                    >
                      Read the Privacy Notice (opens in a new tab)
                    </Link>
                  </div>
                </div>
              </div>
              <p className="register-inline-note">
                The Privacy Notice is a development draft. In live localhost test mode,
                checked consent is sent to FastAPI and recorded. Use fictional profile details
                until the privacy terms, retention schedule, and contact are finalized.
              </p>

              <div className="register-verification-note" role="note">
                <LockKeyhole size={21} />
                <div>
                  <strong>CAPTCHA and 6-digit email OTP</strong>
                  <p>{LOCAL_SUBMISSION_OPT_IN
                    ? "Complete the real Google reCAPTCHA v2 checkbox. Gmail OTP is sent only after the backend accepts registration."
                    : "Google reCAPTCHA and Gmail OTP remain inactive in local validation mode."}</p>
                </div>
              </div>

              {LOCAL_SUBMISSION_OPT_IN && (
                <div className="register-captcha-wrap">
                  {SITE_KEY ? (
                    <RegistrationCaptcha
                      key={captchaRevision}
                      siteKey={SITE_KEY}
                      onToken={(token) => {
                        setCaptchaToken(token);
                        if (token) {
                          setSubmitError((message) =>
                            message === "Complete the Google reCAPTCHA checkbox before submitting."
                              ? ""
                              : message
                          );
                        }
                      }}
                    />
                  ) : (
                    <p className="register-field-error" role="alert">
                      Missing public CAPTCHA site key. Set VITE_DORMORA_RECAPTCHA_V2_SITE_KEY
                      in frontend/.env.local and restart Vite.
                    </p>
                  )}
                </div>
              )}
              <button className="register-submit-button" type="submit"
                disabled={submitting || submissionSucceeded || submissionUncertain}>
                {submitting ? "Submitting securely…" : LOCAL_SUBMISSION_OPT_IN
                  ? "Create Pending Account" : "Test Registration Fields"}
                {!submitting && <ArrowRight size={18} />}
              </button>
              {submitError && (
                <div className="register-test-result register-test-errors" role="alert">
                  <h3>Registration not completed</h3>
                  <p>{submitError}</p>
                </div>
              )}
              {submissionSucceeded && (
                <div className="register-test-result register-test-success" role="status">
                  <h3>Pending account created — verification required</h3>
                  <p>{submitHint}</p>
                  <p><strong>Do not register again.</strong> Keep this browser open so its
                    signed verification cookie is available to File 65.</p>
                </div>
              )}
              {validationErrors.length > 0 && (
                <div className="register-test-result register-test-errors" role="alert">
                  <h3>Validation needs attention — {validationErrors.length} field(s)</h3>
                  <p>Correct these inputs and run the test again:</p>
                  <ul>
                    {validationErrors.map((error, index) => (
                      <li key={`${error.name}-${index}`}>
                        <a href={`#${CHECKED_FIELD_ID[error.name] || "register-consent-title"}`}>
                          {error.message}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {localTestPassed && (
                <div className="register-test-result register-test-success" role="status">
                  <h3>Local registration validation passed</h3>
                  <p>Checked {isOwner ? "property-owner" : "renter"} fields at {testedAt}.
                    The sample data met the browser validation rules.</p>
                  <p><strong>No account was created, no email was sent, and no data was saved.</strong></p>
                </div>
              )}
              <p className="register-test-disclaimer">
                {LOCAL_SUBMISSION_OPT_IN
                  ? "Real local test: create an account, then enter the email OTP in the verification step on this same page. No login session is created."
                  : "Local validation only. No backend request, account, or OTP is created unless the localhost testing mode is explicitly enabled."}
              </p>
              <p className="register-login-prompt">
                Already have an account? <Link to="/login">Log In</Link>
              </p>
            </section>
          </form>
          )}

          {otpStage && LOCAL_SUBMISSION_OPT_IN && (
            <section className="dormora-otp-card" aria-label="Email verification" aria-live="polite">
              <div className="dormora-otp-mark"><LockKeyhole size={25} aria-hidden="true" /></div>
              {otpVerified ? (
                <>
                  <h2>Email verification successful</h2>
                  <p className="dormora-otp-subtitle">
                    Your account was activated by FastAPI after the code was accepted.
                    This does not sign you in. The Login page still requires its own backend integration.
                  </p>
                  <div className="dormora-otp-feedback" data-kind="success" role="status">
                    {otpFeedback?.text || "Your account has been verified."}
                  </div>
                  <Link to="/login" className="register-submit-button">
                    Go to Login <ArrowRight size={18} />
                  </Link>
                </>
              ) : (
                <>
                  <span className="register-test-key">STEP 2 OF 2 · EMAIL VERIFICATION</span>
                  <h2>Enter your 6-digit code</h2>
                  <p className="dormora-otp-subtitle">
                    Check the email address you registered with, including Spam or Junk.
                    Enter the latest code within 3 minutes of issue. Never share it.
                  </p>
                  <form onSubmit={handleOtpVerify} noValidate>
                    <label htmlFor="dormora-otp-code" style={{ display: "block", fontWeight: 750, marginTop: 19 }}>
                      Email verification code
                    </label>
                    <input
                      ref={otpFieldRef}
                      id="dormora-otp-code"
                      className="dormora-otp-field"
                      name="registrationOtp"
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="000000"
                      maxLength={6}
                      pattern="[0-9]{6}"
                      value={otpCode}
                      onChange={(event) => {
                        setOtpCode(event.target.value.replace(/\D/g, "").slice(0, 6));
                        setOtpFeedback(null);
                      }}
                      disabled={otpBusy}
                      required
                      aria-describedby="dormora-otp-help"
                    />
                    <p id="dormora-otp-help" className="dormora-otp-step-note">
                      File 63 must be running locally and this browser must still hold the
                      signed, HttpOnly pending-registration cookie (valid for 30 minutes).
                    </p>
                    <button className="register-submit-button" type="submit"
                      disabled={otpBusy || otpCode.length !== 6}>
                      {otpBusy ? "Checking verification code…" : "Verify email and activate account"}
                      {!otpBusy && <ArrowRight size={18} />}
                    </button>
                  </form>
                  <button className="dormora-otp-resend" type="button"
                    onClick={handleOtpResend}
                    disabled={otpBusy || resendRemainingSeconds > 0}>
                    {resendRemainingSeconds > 0
                      ? `Resend available in ${resendRemainingSeconds}s`
                      : "Didn't receive the code? Resend email"}
                  </button>
                  <p className="dormora-otp-step-note">
                    Resend: at most 3 per 15 minutes, with a 60-second cooldown.
                    Resending generates a replacement code; older codes stop working.
                  </p>
                  {otpFeedback && (
                    <div className="dormora-otp-feedback" data-kind={otpFeedback.kind}
                      role={otpFeedback.kind === "error" ? "alert" : "status"}>
                      {otpFeedback.text}
                    </div>
                  )}
                  <p className="dormora-otp-step-note">
                    Verification does not create a logged-in session. Avoid starting
                    registration again if a pending account already exists.
                  </p>
                </>
              )}
            </section>
          )}

          <div className="register-bottom-hint">
            <CalendarDays size={17} />
            <span>All users must be at least 18 years old.</span>
          </div>
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

export default RegisterPage;