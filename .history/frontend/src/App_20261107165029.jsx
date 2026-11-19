
/*
  Dormora Frontend File 91 -- protected session lifecycle verification.

  REPLACE: frontend/src/App.jsx (previously File 89).

  Preserves landing, login (File 90), registration, recovery, theme settings,
  and renter/owner/admin preview routes. Only protected-workspace behavior is
  tightened to support verifiable session checks, explicit idle renewal and
  database-backed logout. No backend route or database migration is needed.

  Every protected page reads GET /api/auth/me from File 88 and trusts only
  the server's current account role. No authentication data is stored in
  localStorage. Only the non-sensitive light/dark appearance is remembered.
  File 56's signed CSRF middleware protects POST refresh and logout requests.

  These are localhost-only preview routes, not completed rental/admin features.
  Future data APIs must implement their own backend role authorization.
*/

import { useEffect, useRef, useState } from "react";
import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import {
  House,
  LogOut,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
} from "lucide-react";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";

const THEME_STORAGE_KEY = "dormora-theme";
const API_BASE = "http://localhost:8000";
const LOCAL_LOGIN_ENABLED =
  import.meta.env.DEV === true &&
  import.meta.env.VITE_DORMORA_LOCAL_LOGIN === "true" &&
  typeof window !== "undefined" &&
  window.location.protocol === "http:" &&
  window.location.hostname === "localhost" &&
  window.location.port === "5173";

const WORKSPACES = Object.freeze({
  renter: {
    title: "Renter workspace",
    route: "/renter",
    summary: "Your protected area for rent records and dorm discovery.",
    planned: ["Rent Tracker", "Dorm Discovery", "Rental records"],
  },
  property_owner: {
    title: "Property owner workspace",
    route: "/owner",
    summary: "Your protected area for rental listings and property management.",
    planned: ["Manage dorm listings", "Listing photos", "Rental records"],
  },
  admin: {
    title: "Security monitor",
    route: "/admin",
    summary: "Read-only administrative security monitoring workspace.",
    planned: ["Security activity", "Lockout monitoring", "IP block review"],
  },
});

const ACTION_BUTTON_STYLE = {
  padding: "12px 18px",
  borderRadius: 10,
  border: "1px solid var(--border)",
  background: "var(--soft)",
  color: "var(--text)",
  cursor: "pointer",
};

function getSavedTheme() {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark";
  } catch {
    return false;
  }
}

async function apiGetMe(signal) {
  const response = await fetch(`${API_BASE}/api/auth/me`, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    mode: "cors",
    redirect: "error",
    signal,
  });

  if (response.status === 401) return { kind: "signed-out" };
  if (response.status !== 200) return { kind: "unavailable" };

  const body = await response.json();
  const expires = Date.parse(body?.expires_at);
  if (
    body?.authenticated !== true ||
    typeof body?.username !== "string" ||
    !body.username.trim() ||
    typeof body?.role !== "string" ||
    !Object.prototype.hasOwnProperty.call(WORKSPACES, body.role) ||
    !Number.isFinite(expires) ||
    expires <= Date.now()
  ) {
    return { kind: "unavailable" };
  }
  return {
    kind: "ready",
    account: {
      username: body.username,
      role: body.role,
      expires_at: body.expires_at,
    },
  };
}

function accountAccess(result, requiredRole) {
  if (
    result.kind === "ready" &&
    requiredRole !== null &&
    result.account.role !== requiredRole
  ) {
    return { kind: "denied", account: result.account };
  }
  return result;
}

async function postWithCsrf(path) {
  // File 56 verifies the signed token HEADER and cookie. This is only the
  // client handshake, not the CSRF security decision.
  const csrfResponse = await fetch(`${API_BASE}/api/csrf`, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    mode: "cors",
    redirect: "error",
  });
  if (!csrfResponse.ok) throw new Error("csrf_unavailable");

  const csrf = await csrfResponse.json();
  if (typeof csrf?.csrf_token !== "string" || !csrf.csrf_token) {
    throw new Error("csrf_unavailable");
  }
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    mode: "cors",
    redirect: "error",
    headers: { "X-CSRF-Token": csrf.csrf_token },
  });
}

function ProtectedWorkspace({ requiredRole = null, darkMode, onToggleTheme }) {
  const navigate = useNavigate();
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState({ kind: "checking" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [clock, setClock] = useState(Date.now);
  const actionInFlight = useRef(false);
  const userRequestedCheck = useRef(false);

  useEffect(() => {
    if (!LOCAL_LOGIN_ENABLED) {
      setState({ kind: "disabled" });
      return undefined;
    }

    const controller = new AbortController();
    setState({ kind: "checking" }); // Hide protected content during re-check.
    apiGetMe(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setState(accountAccess(result, requiredRole));
        if (userRequestedCheck.current) {
          userRequestedCheck.current = false;
          if (result.kind === "ready") {
            setMessage({
              kind: "success",
              text: "Session checked against PostgreSQL. No renewal was performed.",
            });
          } else if (result.kind !== "signed-out") {
            setMessage({
              kind: "error",
              text: "Session could not be verified. Protected content remains hidden.",
            });
          }
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted && error?.name !== "AbortError") {
          setState({ kind: "unavailable" });
          setMessage({
            kind: "error",
            text: "FastAPI could not confirm your session. Access is not granted.",
          });
        }
      });

    return () => controller.abort();
  }, [requiredRole, revision]);

  // File 78 is authoritative: these browser checks do NOT extend server idle
  // expiry. They only hide the preview and ask the backend to verify again.
  useEffect(() => {
    if (!LOCAL_LOGIN_ENABLED) return undefined;
    if (state.kind !== "ready" && state.kind !== "denied") return undefined;

    const expiresMs = Date.parse(state.account.expires_at);
    const timeoutMs = Math.max(
      100,
      Math.min(expiresMs - Date.now() + 100, 2147483647)
    );
    const deadlineTimer = window.setTimeout(() => {
      if (!actionInFlight.current) setRevision((value) => value + 1);
    }, timeoutMs);

    function onReturnToPage() {
      if (!actionInFlight.current && document.visibilityState !== "hidden") {
        setMessage(null);
        setRevision((value) => value + 1);
      }
    }
    window.addEventListener("focus", onReturnToPage);
    document.addEventListener("visibilitychange", onReturnToPage);
    return () => {
      window.clearTimeout(deadlineTimer);
      window.removeEventListener("focus", onReturnToPage);
      document.removeEventListener("visibilitychange", onReturnToPage);
    };
  }, [state]);

  useEffect(() => {
    if (state.kind !== "ready") return undefined;
    const tick = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, [state.kind]);

  function checkSession() {
    if (actionInFlight.current || state.kind !== "ready") return;
    userRequestedCheck.current = true;
    setMessage(null);
    setRevision((value) => value + 1);
  }

  async function refreshSession() {
    if (actionInFlight.current || state.kind !== "ready") return;
    actionInFlight.current = true;
    setBusy(true);
    setMessage(null);
    try {
      const response = await postWithCsrf("/api/auth/session/refresh");
      if (response.status === 401) {
        setState({ kind: "signed-out" });
        return;
      }
      if (response.status !== 200) {
        throw new Error("refresh_failed");
      }
      const body = await response.json();
      if (body?.authenticated !== true) {
        throw new Error("refresh_unconfirmed");
      }

      // Refresh is not accepted on faith: confirm the current role and new
      // expiry from /me before displaying protected content again.
      setState({ kind: "checking" });
      const verified = accountAccess(await apiGetMe(), requiredRole);
      setState(verified);
      if (verified.kind === "ready") {
        setClock(Date.now());
        setMessage({
          kind: "success",
          text: "Session refreshed and reconfirmed by FastAPI. The nine-minute idle deadline was renewed.",
        });
      } else if (verified.kind === "unavailable") {
        setMessage({
          kind: "error",
          text: "Refresh response received, but account verification failed. Protected content is hidden.",
        });
      }
    } catch {
      // A failed refresh is not a successful renewal. Fail closed rather
      // than displaying a potentially stale authenticated workspace.
      setState({ kind: "unavailable" });
      setMessage({
        kind: "error",
        text: "Session refresh could not be confirmed. Retry verification or check FastAPI.",
      });
    } finally {
      actionInFlight.current = false;
      setBusy(false);
    }
  }

  async function signOut() {
    if (actionInFlight.current || state.kind !== "ready") return;
    actionInFlight.current = true;
    setBusy(true);
    setMessage(null);
    try {
      const response = await postWithCsrf("/api/auth/logout");
      if (response.status !== 200) throw new Error("logout_failed");
      const body = await response.json();
      if (body?.authenticated !== false) {
        throw new Error("logout_unconfirmed");
      }

      // File 81 has committed DB revocation before the successful response.
      // This also hides the workspace immediately, including browser Back.
      setState({ kind: "signed-out" });
      navigate("/login", { replace: true });
    } catch {
      // Do not falsely claim logout if the server has not confirmed it.
      setMessage({
        kind: "error",
        text: "Logout was not confirmed. Your session may still be active; retry or inspect FastAPI.",
      });
    } finally {
      actionInFlight.current = false;
      setBusy(false);
    }
  }

  if (state.kind === "signed-out") return <Navigate to="/login" replace />;

  const ready =
    state.kind === "ready" &&
    Date.parse(state.account.expires_at) > clock;
  const account = ready ? state.account : null;
  const workspace = account ? WORKSPACES[account.role] : null;
  const remaining = account
    ? Math.max(0, Math.ceil((Date.parse(account.expires_at) - clock) / 1000))
    : 0;
  const themeClass = darkMode ? "dormora dark-mode" : "dormora light-mode";

  return (
    <div
      className={themeClass}
      style={{
        minHeight: "100vh",
        background: "var(--background)",
        color: "var(--text)",
      }}
    >
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>
      <header className="site-header">
        <div className="page-container header-content">
          <Link className="brand" to="/">
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </Link>
          <nav
            className="login-header-nav"
            aria-label="Workspace navigation"
          >
            <Link to="/">Home</Link>
            {ready && <Link to="/dashboard">Dashboard</Link>}
            <button
              className="theme-button"
              type="button"
              onClick={onToggleTheme}
              aria-label={
                darkMode ? "Switch to light mode" : "Switch to dark mode"
              }
            >
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </nav>
        </div>
      </header>

      <main
        className="page-container"
        style={{ maxWidth: 980, paddingBlock: 60, minHeight: "65vh" }}
      >
        <section
          style={{
            border: "1px solid var(--border)",
            background: "var(--card)",
            borderRadius: 20,
            padding: "clamp(24px, 5vw, 42px)",
          }}
        >
          {state.kind === "checking" && (
            <p role="status">
              Verifying your Dormora session with FastAPI…
            </p>
          )}

          {state.kind === "disabled" && (
            <>
              <h1>Protected workspace unavailable</h1>
              <p>
                This route is enabled only during explicit localhost login
                testing.
              </p>
              <Link to="/login">Return to login</Link>
            </>
          )}

          {state.kind === "unavailable" && (
            <>
              <h1>Unable to verify session</h1>
              <p>
                Protected content is hidden because the backend could not
                confirm access.
              </p>
              <button
                type="button"
                style={ACTION_BUTTON_STYLE}
                onClick={() => {
                  setMessage(null);
                  setRevision((value) => value + 1);
                }}
              >
                Retry verification
              </button>
            </>
          )}

          {state.kind === "denied" && (
            <>
              <h1>Access denied</h1>
              <p>
                Your verified account role cannot access this workspace.
              </p>
              <Link to={WORKSPACES[state.account.role].route}>
                Go to your workspace
              </Link>
            </>
          )}

          {state.kind === "ready" && !ready && (
            <p role="status">
              Your displayed session deadline has passed. Rechecking with
              FastAPI…
            </p>
          )}

          {ready && (
            <>
              <p
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 9,
                  color: "var(--primary)",
                  fontWeight: 700,
                }}
              >
                <ShieldCheck size={20} /> Server-verified access
              </p>

              <h1
                style={{
                  marginBlock: "10px 16px",
                  fontSize: "clamp(28px, 5vw, 43px)",
                }}
              >
                {workspace.title}
              </h1>

              <p style={{ color: "var(--muted)" }}>
                Welcome, {account.username}. {workspace.summary}
              </p>

              <p style={{ color: "var(--muted)" }}>
                Role: <strong>{account.role}</strong> · Session deadline:{" "}
                {new Date(account.expires_at).toLocaleTimeString()}
              </p>

              <p
                role="timer"
                aria-live="off"
                style={{ color: "var(--muted)", fontSize: 13 }}
              >
                Idle session remaining: {Math.floor(remaining / 60)}m{" "}
                {String(remaining % 60).padStart(2, "0")}s
                {" "}· Only the Refresh session button renews the deadline.
              </p>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(175px, 1fr))",
                  gap: 12,
                  marginTop: 26,
                }}
              >
                {workspace.planned.map((item) => (
                  <div
                    key={item}
                    style={{
                      padding: 18,
                      border: "1px solid var(--border)",
                      borderRadius: 12,
                      background: "var(--soft)",
                    }}
                  >
                    <strong>{item}</strong>
                    <p
                      style={{
                        fontSize: 12,
                        color: "var(--muted)",
                        marginBottom: 0,
                      }}
                    >
                      Planned feature · Not active
                    </p>
                  </div>
                ))}
              </div>

              <p
                style={{
                  marginTop: 24,
                  fontSize: 13,
                  color: "var(--muted)",
                }}
              >
                This is a protected navigation preview. Future rental,
                listing and security-monitoring APIs require backend role
                checks.
              </p>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 12,
                  marginTop: 22,
                }}
              >
                <button
                  type="button"
                  disabled={busy}
                  onClick={checkSession}
                  style={ACTION_BUTTON_STYLE}
                >
                  <ShieldCheck
                    size={16}
                    style={{ verticalAlign: "middle" }}
                  />{" "}
                  Check session
                </button>

                <button
                  type="button"
                  disabled={busy}
                  onClick={refreshSession}
                  style={ACTION_BUTTON_STYLE}
                >
                  <RefreshCw
                    size={16}
                    style={{ verticalAlign: "middle" }}
                  />{" "}
                  Refresh session
                </button>

                <button
                  type="button"
                  disabled={busy}
                  onClick={signOut}
                  style={ACTION_BUTTON_STYLE}
                >
                  <LogOut
                    size={16}
                    style={{ verticalAlign: "middle" }}
                  />{" "}
                  Sign out
                </button>
              </div>
            </>
          )}

          {message && (
            <p
              role={message.kind === "error" ? "alert" : "status"}
              style={{
                color:
                  message.kind === "error"
                    ? "#cc5555"
                    : "var(--text)",
                marginTop: 15,
              }}
            >
              {message.text}
            </p>
          )}
        </section>
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

function App() {
  const [darkMode, setDarkMode] = useState(getSavedTheme);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        THEME_STORAGE_KEY,
        darkMode ? "dark" : "light"
      );
    } catch {
      // Theme switching works even when preference storage is unavailable.
    }
  }, [darkMode]);

  function toggleTheme() {
    setDarkMode((currentMode) => !currentMode);
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            <LandingPage
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />
        <Route
          path="/login"
          element={
            <LoginPage
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />
        <Route
          path="/register"
          element={
            <RegisterPage
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />
        <Route
          path="/forgot-password"
          element={
            <ForgotPasswordPage
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedWorkspace
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />
        <Route
          path="/renter"
          element={
            <ProtectedWorkspace
              requiredRole="renter"
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />
        <Route
          path="/owner"
          element={
            <ProtectedWorkspace
              requiredRole="property_owner"
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedWorkspace
              requiredRole="admin"
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
