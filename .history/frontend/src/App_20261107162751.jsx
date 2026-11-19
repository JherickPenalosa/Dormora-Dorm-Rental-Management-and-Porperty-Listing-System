
/*
  Dormora Frontend File 89 -- server-verified protected navigation.

  REPLACE: frontend/src/App.jsx (previously File 31).

  Preserves the existing landing, login, registration, recovery and theme routes.
  Adds /dashboard, /renter, /owner and /admin as role-aware preview workspaces.

  Every protected entry fetches GET /api/auth/me with the HttpOnly cookie.
  No account identity/role/session token is saved in localStorage, passed in a
  query string, or accepted from browser-controlled role parameters.
  Production/API permissions MUST be enforced again in FastAPI on EVERY
  sensitive endpoint. A React route guard alone is NOT authorization.

  Live protection is allowed only with Vite at http://localhost:5173 and
  VITE_DORMORA_LOCAL_LOGIN=true, matching Files 86-88's local test mode.
  These are navigation previews, NOT implemented rental or admin features.
*/

import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { House, LogOut, Moon, RefreshCw, ShieldCheck, Sun } from "lucide-react";
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

const WORKSPACES = {
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
  const expiry = Date.parse(body?.expires_at);
  if (
    body?.authenticated !== true ||
    typeof body?.username !== "string" ||
    !body.username.trim() ||
    !Object.prototype.hasOwnProperty.call(WORKSPACES, body.role) ||
    !Number.isFinite(expiry) ||
    expiry <= Date.now()
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

async function postWithCsrf(path) {
  // File 56 verifies the signed cookie/header pair on every POST.
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
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!LOCAL_LOGIN_ENABLED) {
      setState({ kind: "disabled" });
      return undefined;
    }

    const controller = new AbortController();
    let mounted = true;
    setState({ kind: "checking" });

    apiGetMe(controller.signal)
      .then((result) => {
        if (!mounted) return;
        if (result.kind === "ready" && requiredRole && result.account.role !== requiredRole) {
          setState({ kind: "denied", account: result.account });
        } else {
          setState(result);
        }
      })
      .catch(() => {
        if (mounted) setState({ kind: "unavailable" });
      });

    return () => {
      mounted = false;
      controller.abort();
    };
  }, [requiredRole, revision]);

  // Expiry does not renew automatically. Check again once server expiry is due,
  // and whenever the browser regains focus after being idle.
  useEffect(() => {
    if (state.kind !== "ready" && state.kind !== "denied") return undefined;
    const expires = Date.parse(state.account.expires_at);
    const milliseconds = Math.max(100, Math.min(expires - Date.now() + 250, 2147483647));
    const timer = window.setTimeout(() => setRevision((n) => n + 1), milliseconds);
    const recheckOnFocus = () => setRevision((n) => n + 1);
    window.addEventListener("focus", recheckOnFocus);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("focus", recheckOnFocus);
    };
  }, [state]);

  async function signOut() {
    if (working || state.kind !== "ready") return;
    setWorking(true);
    setError("");
    try {
      const response = await postWithCsrf("/api/auth/logout");
      if (response.status !== 200) throw new Error("logout_failed");
      const body = await response.json();
      if (body?.authenticated !== false) throw new Error("logout_unconfirmed");
      navigate("/login", { replace: true });
    } catch {
      setError("Could not confirm logout. Your session may still be active; try again.");
    } finally {
      setWorking(false);
    }
  }

  async function refreshSession() {
    if (working || state.kind !== "ready") return;
    setWorking(true);
    setError("");
    try {
      const response = await postWithCsrf("/api/auth/session/refresh");
      if (response.status === 401) {
        setState({ kind: "signed-out" });
        return;
      }
      if (response.status !== 200) throw new Error("refresh_failed");
      const body = await response.json();
      if (body?.authenticated !== true) throw new Error("refresh_unconfirmed");
      setRevision((n) => n + 1); // Reconfirm account and role from the server.
    } catch {
      setError("Session refresh could not be confirmed. Check the backend connection.");
    } finally {
      setWorking(false);
    }
  }

  if (state.kind === "signed-out") {
    return <Navigate to="/login" replace />;
  }

  const themeClass = darkMode ? "dormora dark-mode" : "dormora light-mode";
  const ready = state.kind === "ready";
  const account = ready ? state.account : null;
  const workspace = account ? WORKSPACES[account.role] : null;

  return (
    <div className={themeClass} style={{ minHeight: "100vh", background: "var(--background)", color: "var(--text)" }}>
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>
      <header className="site-header">
        <div className="page-container header-content">
          <Link className="brand" to="/"><House size={29} strokeWidth={2.5} /><span>Dormora</span></Link>
          <nav className="login-header-nav" aria-label="Workspace navigation">
            <Link to="/">Home</Link>
            {ready && <Link to="/dashboard">Dashboard</Link>}
            <button className="theme-button" type="button" onClick={onToggleTheme}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}>
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </nav>
        </div>
      </header>
      <main className="page-container" style={{ maxWidth: 980, paddingBlock: 60, minHeight: "65vh" }}>
        <section style={{ border: "1px solid var(--border)", background: "var(--card)", borderRadius: 20, padding: "clamp(24px, 5vw, 42px)" }}>
          {state.kind === "checking" && <p role="status">Verifying your Dormora session…</p>}
          {state.kind === "disabled" && <>
            <h1>Protected workspace unavailable</h1>
            <p>This route is enabled only during explicit localhost login testing.</p>
            <Link to="/login">Return to login</Link>
          </>}
          {state.kind === "unavailable" && <>
            <h1>Unable to verify session</h1>
            <p>We could not confirm your session with FastAPI. Access has not been granted.</p>
            <button type="button" onClick={() => setRevision((n) => n + 1)}>Retry verification</button>
          </>}
          {state.kind === "denied" && <>
            <h1>Access denied</h1>
            <p>Your verified account role does not have access to this workspace.</p>
            <Link to={WORKSPACES[state.account.role].route}>Go to your workspace</Link>
          </>}
          {ready && <>
            <p style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--primary)", fontWeight: 700 }}>
              <ShieldCheck size={20} /> Server-verified access
            </p>
            <h1 style={{ marginBlock: "10px 16px", fontSize: "clamp(28px, 5vw, 43px)" }}>
              {workspace.title}
            </h1>
            <p style={{ color: "var(--muted)" }}>Welcome, {account.username}. {workspace.summary}</p>
            <p style={{ color: "var(--muted)" }}>
              Role: <strong>{account.role}</strong> · Session deadline: {new Date(account.expires_at).toLocaleTimeString()}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(175px, 1fr))", gap: 12, marginTop: 26 }}>
              {workspace.planned.map((item) => (
                <div key={item} style={{ padding: 18, border: "1px solid var(--border)", borderRadius: 12, background: "var(--soft)" }}>
                  <strong>{item}</strong>
                  <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 0 }}>Planned feature · Not active</p>
                </div>
              ))}
            </div>
            <p style={{ marginTop: 24, fontSize: 13, color: "var(--muted)" }}>
              This is a protected navigation preview. Every future rent, listing, or security-monitoring API must enforce account role server-side.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 22 }}>
              <button type="button" disabled={working} onClick={refreshSession}
                style={{ padding: "12px 18px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--soft)", color: "var(--text)", cursor: "pointer" }}>
                <RefreshCw size={16} style={{ verticalAlign: "middle" }} /> Refresh session
              </button>
              <button type="button" disabled={working} onClick={signOut}
                style={{ padding: "12px 18px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--soft)", color: "var(--text)", cursor: "pointer" }}>
                <LogOut size={16} style={{ verticalAlign: "middle" }} /> Sign out
              </button>
            </div>
          </>}
          {error && <p role="alert" style={{ color: "#cc5555", marginTop: 15 }}>{error}</p>}
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
      window.localStorage.setItem(THEME_STORAGE_KEY, darkMode ? "dark" : "light");
    } catch {
      // Theme switching works even if preference storage is unavailable.
    }
  }, [darkMode]);

  function toggleTheme() {
    setDarkMode((currentMode) => !currentMode);
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/login" element={<LoginPage darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/register" element={<RegisterPage darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/dashboard" element={<ProtectedWorkspace darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/renter" element={<ProtectedWorkspace requiredRole="renter" darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/owner" element={<ProtectedWorkspace requiredRole="property_owner" darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/admin" element={<ProtectedWorkspace requiredRole="admin" darkMode={darkMode} onToggleTheme={toggleTheme} />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
