
/*
 * Dormora — System Functionality File 2
 * REPLACE: frontend/src/components/auth/ProtectedWorkspace.jsx
 *
 * Connects the shared Renter/Owner Home dashboard.
 * Preserves server-verified roles, sessions, CSRF-protected actions,
 * password changes, and the existing admin security dashboard.
 * No changes to App.jsx or FastAPI.
 */

import { useEffect, useRef, useState } from "react";
import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  House,
  KeyRound,
  LogOut,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
} from "lucide-react";

import AdminSecurityDashboard from "../admin/AdminSecurityDashboard";
import PasswordChangeForm from "../account/PasswordChangeForm";
import RoleHome from "../home/RoleHome";

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

async function apiGetMe(signal) {
  const response = await fetch(`${API_BASE}/api/auth/me`, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    mode: "cors",
    redirect: "error",
    signal,
  });

  if (response.status === 401) {
    return { kind: "signed-out" };
  }

  if (response.status !== 200) {
    return { kind: "unavailable" };
  }

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
    return {
      kind: "denied",
      account: result.account,
    };
  }

  return result;
}

async function postWithCsrf(path, payload = null) {
  // File 56 verifies the signed CSRF token.
  // Never place passwords in URLs or browser storage.

  const csrfResponse = await fetch(`${API_BASE}/api/csrf`, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    mode: "cors",
    redirect: "error",
  });

  if (!csrfResponse.ok) {
    throw new Error("csrf_unavailable");
  }

  const csrf = await csrfResponse.json();

  if (
    typeof csrf?.csrf_token !== "string" ||
    !csrf.csrf_token
  ) {
    throw new Error("csrf_unavailable");
  }

  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    mode: "cors",
    redirect: "error",
    headers: {
      "X-CSRF-Token": csrf.csrf_token,
      ...(payload === null
        ? {}
        : { "Content-Type": "application/json" }),
    },
    ...(payload === null
      ? {}
      : { body: JSON.stringify(payload) }),
  });
}

function ProtectedWorkspace({
  requiredRole = null,
  darkMode,
  onToggleTheme,
}) {
  const navigate = useNavigate();
  const location = useLocation();

  const [revision, setRevision] = useState(0);
  const [state, setState] = useState({ kind: "checking" });
  const [busy, setBusy] = useState(false);
  const [passwordChangeOpen, setPasswordChangeOpen] = useState(false);
  const [message, setMessage] = useState(null);
  const [clock, setClock] = useState(Date.now);

  const actionInFlight = useRef(false);
  const userRequestedCheck = useRef(false);

  // Confirm session and role against FastAPI.
  useEffect(() => {
    if (!LOCAL_LOGIN_ENABLED) {
      setState({ kind: "disabled" });
      return undefined;
    }

    const controller = new AbortController();

    setState({ kind: "checking" });

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
        if (
          !controller.signal.aborted &&
          error?.name !== "AbortError"
        ) {
          setState({ kind: "unavailable" });
          setMessage({
            kind: "error",
            text: "FastAPI could not confirm your session. Access is not granted.",
          });
        }
      });

    return () => controller.abort();
  }, [requiredRole, revision]);

  // Preserve the existing session-expiry checks.
  useEffect(() => {
    if (!LOCAL_LOGIN_ENABLED) return undefined;

    if (
      state.kind !== "ready" &&
      state.kind !== "denied"
    ) {
      return undefined;
    }

    const expiresMs = Date.parse(state.account.expires_at);

    const timeoutMs = Math.max(
      100,
      Math.min(expiresMs - Date.now() + 100, 2147483647)
    );

    const deadlineTimer = window.setTimeout(() => {
      if (!actionInFlight.current) {
        setRevision((value) => value + 1);
      }
    }, timeoutMs);

    function onReturnToPage() {
      if (
        !actionInFlight.current &&
        document.visibilityState !== "hidden"
      ) {
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

    const tick = window.setInterval(() => {
      setClock(Date.now());
    }, 1000);

    return () => window.clearInterval(tick);
  }, [state.kind]);

  function checkSession() {
    if (
      actionInFlight.current ||
      state.kind !== "ready"
    ) {
      return;
    }

    userRequestedCheck.current = true;
    setMessage(null);
    setRevision((value) => value + 1);
  }

  async function refreshSession() {
    if (
      actionInFlight.current ||
      state.kind !== "ready"
    ) {
      return;
    }

    actionInFlight.current = true;
    setBusy(true);
    setMessage(null);

    try {
      const response = await postWithCsrf(
        "/api/auth/session/refresh"
      );

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

      setState({ kind: "checking" });

      const verified = accountAccess(
        await apiGetMe(),
        requiredRole
      );

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
    if (
      actionInFlight.current ||
      state.kind !== "ready"
    ) {
      return;
    }

    actionInFlight.current = true;
    setBusy(true);
    setMessage(null);

    try {
      const response = await postWithCsrf(
        "/api/auth/logout"
      );

      if (response.status !== 200) {
        throw new Error("logout_failed");
      }

      const body = await response.json();

      if (body?.authenticated !== false) {
        throw new Error("logout_unconfirmed");
      }

      setState({ kind: "signed-out" });
      navigate("/login", { replace: true });
    } catch {
      setMessage({
        kind: "error",
        text: "Logout was not confirmed. Your session may still be active; retry or inspect FastAPI.",
      });
    } finally {
      actionInFlight.current = false;
      setBusy(false);
    }
  }

  if (state.kind === "signed-out") {
    return <Navigate to="/login" replace />;
  }

  const ready =
    state.kind === "ready" &&
    Date.parse(state.account.expires_at) > clock;

  const account = ready ? state.account : null;

  const workspace = account
    ? WORKSPACES[account.role]
    : null;

  const remaining = account
    ? Math.max(
        0,
        Math.ceil(
          (Date.parse(account.expires_at) - clock) / 1000
        )
      )
    : 0;

  const themeClass = darkMode
    ? "dormora dark-mode"
    : "dormora light-mode";

  /*
   * FILE 2 — NEW HOME DASHBOARD INTEGRATION
   *
   * Renter and property-owner accounts now see RoleHome.
   * Admins continue using the existing monitoring dashboard.
   * Session checks and role restrictions remain unchanged.
   *
   * Existing account and security controls stay accessible
   * through ?view=account.
   */

  const accountView =
    new URLSearchParams(location.search).get("view") === "account";

  if (
    ready &&
    account &&
    (account.role === "renter" ||
      account.role === "property_owner") &&
    !accountView
  ) {
    return (
      <div className={themeClass}>
        <RoleHome
          account={account}
          darkMode={darkMode}
          onToggleTheme={onToggleTheme}
          onLogout={() => {
            // Open the existing account screen first so that any
            // logout error remains visible.
            navigate(`${location.pathname}?view=account`);
            signOut();
          }}
        />

        <div
          style={{
            position: "fixed",
            right: 20,
            bottom: 20,
            zIndex: 10,
          }}
        >
          <button
            type="button"
            style={{
              ...ACTION_BUTTON_STYLE,
              background: "var(--card)",
              boxShadow: "var(--shadow)",
              fontWeight: 700,
            }}
            onClick={() =>
              navigate(`${location.pathname}?view=account`)
            }
          >
            Account &amp; Security
          </button>
        </div>
      </div>
    );
  }

  // Original authenticated workspace and admin dashboard.
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

            {ready && (
              <Link
                to={
                  account?.role === "admin"
                    ? "/dashboard"
                    : location.pathname
                }
              >
                Dashboard
              </Link>
            )}

            <button
              className="theme-button"
              type="button"
              onClick={onToggleTheme}
              aria-label={
                darkMode
                  ? "Switch to light mode"
                  : "Switch to dark mode"
              }
            >
              {darkMode ? (
                <Sun size={19} />
              ) : (
                <Moon size={19} />
              )}
            </button>
          </nav>
        </div>
      </header>

      <main
        className="page-container"
        style={{
          maxWidth: 980,
          paddingBlock: 60,
          minHeight: "65vh",
        }}
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
                This route is enabled only during explicit localhost
                login testing.
              </p>
              <Link to="/login">Return to login</Link>
            </>
          )}

          {state.kind === "unavailable" && (
            <>
              <h1>Unable to verify session</h1>
              <p>
                Protected content is hidden because the backend
                could not confirm access.
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
              Your displayed session deadline has passed.
              Rechecking with FastAPI…
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
                <ShieldCheck size={20} />
                Server-verified access
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
                Role: <strong>{account.role}</strong>
                {" "}· Session deadline:{" "}
                {new Date(account.expires_at).toLocaleTimeString()}
              </p>

              <p
                role="timer"
                aria-live="off"
                style={{
                  color: "var(--muted)",
                  fontSize: 13,
                }}
              >
                Idle session remaining:{" "}
                {Math.floor(remaining / 60)}m{" "}
                {String(remaining % 60).padStart(2, "0")}s
                {" "}· Only the Refresh session button
                renews the deadline.
              </p>

              {account.role === "admin" ? (
                <AdminSecurityDashboard
                  onAccessLost={(httpStatus) => {
                    setState({
                      kind:
                        httpStatus === 401
                          ? "signed-out"
                          : "unavailable",
                    });
                    setMessage({
                      kind: "error",
                      text: "Administrator access is no longer verified. Protected data has been hidden.",
                    });
                  }}
                />
              ) : (
                <>
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
                    This is a protected navigation preview.
                    Future rental and listing APIs require
                    backend role checks.
                  </p>
                </>
              )}

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
                  />
                  {" "}Check session
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
                  />
                  {" "}Refresh session
                </button>

                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    setPasswordChangeOpen((open) => !open)
                  }
                  style={ACTION_BUTTON_STYLE}
                  aria-expanded={passwordChangeOpen}
                  aria-controls="dormora-account-password-panel"
                >
                  <KeyRound
                    size={16}
                    style={{ verticalAlign: "middle" }}
                  />
                  {" "}
                  {passwordChangeOpen
                    ? "Close password form"
                    : "Change password"}
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
                  />
                  {" "}Sign out
                </button>
              </div>

              {passwordChangeOpen && (
                <div id="dormora-account-password-panel">
                  <PasswordChangeForm
                    postWithCsrf={postWithCsrf}
                    busy={busy}
                    actionInFlight={actionInFlight}
                    setBusy={setBusy}
                    onSuccess={() => {
                      setPasswordChangeOpen(false);
                      setState({ kind: "signed-out" });
                      navigate("/login", { replace: true });
                    }}
                    onSessionLost={() => {
                      setPasswordChangeOpen(false);
                      setState({ kind: "signed-out" });
                    }}
                    onUncertain={() => {
                      setPasswordChangeOpen(false);
                      setState({ kind: "unavailable" });
                      setMessage({
                        kind: "error",
                        text: "Password-change result could not be confirmed. Do not resubmit yet; check whether your new password works at sign-in.",
                      });
                    }}
                  />
                </div>
              )}
            </>
          )}

          {message && (
            <p
              role={
                message.kind === "error"
                  ? "alert"
                  : "status"
              }
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
          <span>
            © 2026 Dormora. All rights reserved.
          </span>
          <Link to="/">Back to Home</Link>
        </div>
      </footer>
    </div>
  );
}

export default ProtectedWorkspace;
