/*
 * DORMORA — SYSTEM FUNCTIONALITY FILE 68
 * REPLACE: frontend/src/components/auth/ProtectedWorkspace.jsx
 *
 * Adds a live read-only Admin Overview using the EXISTING Admin User Directory
 * and Admin Property Directory GET endpoints, plus quick navigation cards.
 * Preserves existing Security Monitoring, User Directory, Dorm Listings,
 * File 59 Settings, session, CSRF, password change, and Renter/Owner RoleHome.
 * No database changes, new routes, mutations, or new dependencies.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  House,
  ArrowLeft,
  UserRound,
  Eye,
  EyeOff,
  Palette,
  LockKeyhole,
  CheckCircle2,
  KeyRound,
  LogOut,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
  Users,
  Search,
  ChevronLeft,
  ChevronRight,
  Building2,
  AlertCircle,
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
    title: "Admin workspace",
    route: "/admin",
    summary: "Review security activity, user accounts, and dorm listings in one place.",
    planned: ["Security activity", "Lockout monitoring", "IP block review"],
  },
});

const SETTINGS_HIDE_DETAILS_KEY = "dormora-settings-hide-details";

function readHideDetailsSetting() {
  try {
    return window.localStorage.getItem(SETTINGS_HIDE_DETAILS_KEY) === "true";
  } catch {
    return false;
  }
}

// Scoped to the Settings view: no impact on existing dashboard/print styles.
const SETTINGS_STYLES = `
.ds-screen{min-height:100vh;background:var(--background);color:var(--text);font-family:Inter,"Segoe UI",sans-serif}
.ds-screen *{box-sizing:border-box}
.ds-screen button{font:inherit}
.ds-topbar{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;padding:18px max(22px,calc((100vw - 1100px)/2));background:var(--card);border-bottom:1px solid var(--border)}
.ds-brand{display:flex;align-items:center;gap:11px;font-size:21px;font-weight:850;letter-spacing:-.4px}
.ds-brand svg{color:var(--primary)}
.ds-top-actions{display:flex;gap:9px;align-items:center}
.ds-wrap{max-width:1050px;margin:0 auto;padding:33px 24px 65px}
.ds-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:26px}
.ds-eyebrow{font-size:12px;color:var(--primary);font-weight:750;margin-bottom:10px;letter-spacing:.3px}
.ds-heading h1{font-size:clamp(29px,3.8vw,40px);line-height:1.2;letter-spacing:-.9px;margin:0 0 9px;font-weight:850}
.ds-subtitle{font-size:14px;line-height:1.65;color:var(--muted);margin:0}
.ds-button{min-height:42px;padding:10px 15px;display:inline-flex;align-items:center;justify-content:center;gap:9px;background:var(--card);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:13px;font-weight:700;cursor:pointer}
.ds-button:hover:not(:disabled){background:var(--soft)}
.ds-button:disabled{opacity:.5;cursor:not-allowed}
.ds-button.primary{background:var(--primary);color:var(--background);border-color:var(--primary)}
.ds-button.primary:hover:not(:disabled){filter:brightness(.95);background:var(--primary)}
.ds-button.danger{color:#bd4444}
.ds-button:focus-visible{outline:3px solid var(--primary);outline-offset:3px}
.ds-grid{display:grid;gap:17px}
.ds-card{background:var(--card);border:1px solid var(--border);border-radius:17px;padding:24px;min-width:0}
.ds-section-head{display:flex;align-items:flex-start;gap:13px;margin-bottom:20px}
.ds-section-icon{display:grid;place-items:center;flex:0 0 44px;width:44px;height:44px;background:var(--soft);border-radius:12px;color:var(--primary)}
.ds-section-head h2{margin:0 0 4px;font-size:19px;font-weight:800}
.ds-section-head p{margin:0;color:var(--muted);font-size:12px;line-height:1.6}
.ds-identity{display:flex;gap:14px;align-items:center;padding:15px;background:var(--soft);border:1px solid var(--border);border-radius:13px;margin-bottom:15px}
.ds-avatar{flex:0 0 48px;width:48px;height:48px;display:grid;place-items:center;border-radius:14px;background:var(--card);color:var(--primary);font-size:22px;font-weight:850}
.ds-identity strong{display:block;font-size:16px;overflow-wrap:anywhere}
.ds-identity small{display:block;color:var(--muted);font-size:12px;margin-top:4px}
.ds-row{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;padding:14px 0;border-top:1px solid var(--border)}
.ds-row:first-of-type{border-top:0}
.ds-row-title{font-size:14px;font-weight:750;margin:0 0 4px}
.ds-row-sub{font-size:12px;line-height:1.6;color:var(--muted);margin:0}
.ds-row-value{font-size:13px;font-weight:750;overflow-wrap:anywhere;text-align:right}
.ds-theme-choices{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.ds-theme-choice{display:inline-flex;align-items:center;gap:8px;justify-content:center;padding:11px 17px;border-radius:10px;background:var(--background);color:var(--text);border:1px solid var(--border);cursor:pointer;font-size:13px;font-weight:750}
.ds-theme-choice[aria-pressed="true"]{border-color:var(--primary);background:var(--soft);color:var(--primary)}
.ds-theme-choice:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.ds-badge{display:inline-flex;align-items:center;gap:7px;border-radius:99px;padding:7px 11px;font-size:11px;font-weight:750;color:var(--primary);background:var(--soft)}
.ds-session{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:17px}
.ds-detail{border:1px solid var(--border);border-radius:12px;padding:15px;background:var(--background)}
.ds-detail small{color:var(--muted);font-size:12px;display:block;margin-bottom:7px}
.ds-detail strong{display:block;font-size:15px;overflow-wrap:anywhere}
.ds-actions{display:flex;gap:10px;flex-wrap:wrap}
.ds-help{font-size:12px;color:var(--muted);line-height:1.65;margin:12px 0 0}
.ds-feedback{display:flex;align-items:flex-start;gap:9px;padding:13px 15px;border-radius:11px;border:1px solid var(--border);background:var(--soft);font-size:13px;line-height:1.6}
.ds-feedback.error{color:#c44b4b}
.ds-feedback svg{flex:0 0 auto;margin-top:1px}
.ds-divider{height:1px;background:var(--border);margin:20px 0}
.ds-foot{text-align:center;margin-top:25px;color:var(--muted);font-size:12px}
@media(max-width:640px){.ds-topbar{padding:15px 18px}.ds-wrap{padding:26px 15px 45px}.ds-card{padding:18px}.ds-session{grid-template-columns:1fr}.ds-heading{margin-bottom:19px}}
@media print{.ds-topbar,.ds-screen button{display:none!important}}
`;

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

// FILE 63 — Admin-only User Directory, backed by File 61's GET endpoint.
// The existing AdminSecurityDashboard is not replaced or changed.
const ADMIN_DIRECTORY_STYLES = `
.ad-directory{margin-top:20px;color:var(--text)}
.ad-directory *{box-sizing:border-box}
.ad-head{display:flex;justify-content:space-between;align-items:flex-start;gap:15px;flex-wrap:wrap;margin-bottom:18px}
.ad-head h2{font-size:22px;font-weight:800;margin:0 0 5px}
.ad-help{color:var(--muted);font-size:13px;line-height:1.6;margin:0}
.ad-button{border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:10px;min-height:41px;padding:9px 14px;display:inline-flex;align-items:center;justify-content:center;gap:7px;font-size:13px;font-weight:700;cursor:pointer}
.ad-button:hover:not(:disabled){background:var(--soft)}
.ad-button:disabled{opacity:.5;cursor:not-allowed}
.ad-button:focus-visible,.ad-directory input:focus-visible,.ad-directory select:focus-visible,.ad-admin-tab:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.ad-admin-tabs{display:flex;gap:9px;flex-wrap:wrap;margin:24px 0 12px;padding-bottom:15px;border-bottom:1px solid var(--border)}
.ad-admin-tab{display:inline-flex;align-items:center;gap:9px;padding:11px 16px;border-radius:11px;border:1px solid var(--border);background:var(--background);color:var(--muted);font-size:13px;font-weight:700;cursor:pointer}
.ad-admin-tab[aria-selected="true"]{background:var(--soft);border-color:var(--primary);color:var(--primary)}
.ad-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;margin-bottom:18px}
.ad-stat{border:1px solid var(--border);border-radius:13px;background:var(--background);padding:16px;min-width:0}
.ad-stat-label{font-size:12px;line-height:1.4;color:var(--muted);display:flex;gap:8px;align-items:center}
.ad-stat-label svg{color:var(--primary)}
.ad-stat-value{margin:10px 0 0;font-size:26px;font-weight:850}
.ad-filters{display:flex;align-items:flex-end;flex-wrap:wrap;gap:12px;margin-bottom:16px}
.ad-field{flex:1 1 245px;min-width:0}
.ad-field.role{flex:0 1 200px}
.ad-label{display:block;font-size:12px;font-weight:700;margin-bottom:7px}
.ad-input{min-height:42px;width:100%;border:1px solid var(--border);border-radius:10px;background:var(--background);color:var(--text);font:inherit;font-size:13px;padding:10px 12px}
.ad-table-wrap{max-width:100%;overflow-x:auto;border:1px solid var(--border);border-radius:13px;background:var(--card)}
.ad-table{border-collapse:collapse;width:100%;min-width:650px;font-size:13px}
.ad-table th{text-align:left;font-weight:750;color:var(--muted);font-size:12px;padding:13px 16px;background:var(--soft);border-bottom:1px solid var(--border)}
.ad-table td{padding:14px 16px;border-bottom:1px solid var(--border);overflow-wrap:anywhere}
.ad-table tbody tr:last-child td{border-bottom:none}
.ad-username{font-weight:750}.ad-subtle{color:var(--muted);font-size:12px}
.ad-status{display:inline-block;font-size:11px;font-weight:750;border-radius:100px;padding:5px 9px;background:var(--soft);color:var(--muted)}
.ad-status.active{color:var(--primary)}
.ad-state{padding:25px 16px;text-align:center;line-height:1.65;color:var(--muted);font-size:13px}
.ad-error{border:1px solid var(--border);background:var(--soft);border-radius:12px;padding:14px;display:flex;align-items:flex-start;gap:10px;color:var(--text);font-size:13px;line-height:1.6}
.ad-error svg{flex-shrink:0;color:#b45309}
.ad-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:17px}
.ad-pagination-actions{display:flex;gap:8px}
.ad-note{margin:16px 0 0;font-size:12px;color:var(--muted);line-height:1.6}
@media(max-width:620px){.ad-stats{grid-template-columns:1fr}.ad-field.role{flex:1 1 180px}.ad-admin-tab{flex:1;justify-content:center}.ad-stat{padding:13px}}


/* FILE 68 — Admin overview: read-only statistics and section shortcuts. */
.ao-overview{margin:22px 0 12px;border:1px solid var(--border);border-radius:17px;background:linear-gradient(115deg,var(--soft),var(--card));padding:21px;min-width:0}
.ao-head{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:13px;margin-bottom:17px}
.ao-head h2{font-size:19px;font-weight:850;letter-spacing:-.3px;margin:0 0 4px}
.ao-head p{color:var(--muted);font-size:12px;line-height:1.65;margin:0}
.ao-eyebrow{display:flex;align-items:center;gap:7px;color:var(--primary);font-size:11px;font-weight:750;letter-spacing:.4px;margin-bottom:8px}
.ao-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px}
.ao-metric{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:15px;min-width:0}
.ao-label{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:12px;line-height:1.4}
.ao-label svg{color:var(--primary);flex:0 0 auto}
.ao-count{font-size:clamp(20px,2.6vw,28px);font-weight:850;margin-top:10px;line-height:1.25;overflow-wrap:anywhere}
.ao-links{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:13px}
.ao-link{background:var(--card);border:1px solid var(--border);border-radius:11px;padding:12px;display:flex;align-items:center;gap:9px;text-align:left;color:var(--text);font:inherit;font-size:12px;font-weight:750;min-width:0;cursor:pointer}
.ao-link svg:first-child{color:var(--primary);flex:0 0 auto}.ao-link svg:last-child{margin-left:auto;flex:0 0 auto}
.ao-link:hover{background:var(--soft)}.ao-link:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.ao-alert{font-size:12px;line-height:1.65;margin-top:13px;padding:10px 12px;background:var(--card);border:1px solid var(--border);border-radius:10px;color:var(--muted)}
@media(max-width:760px){.ao-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ao-links{grid-template-columns:1fr}}
@media(max-width:425px){.ao-overview{padding:15px}.ao-metric{padding:11px}}
@media print{.ao-overview{display:none!important}}

/* FILE 67 — Property cards instead of a wide table; responsive and read-only. */
.ap-list{display:grid;gap:13px;margin-top:5px}
.ap-card{border:1px solid var(--border);background:var(--background);border-radius:14px;padding:17px;min-width:0}
.ap-card-top{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;margin-bottom:13px}
.ap-title{font-weight:850;font-size:18px;line-height:1.3;margin:0 0 4px;overflow-wrap:anywhere}
.ap-meta{color:var(--muted);font-size:12px;line-height:1.65;overflow-wrap:anywhere}
.ap-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.ap-detail{padding:11px 12px;border:1px solid var(--border);background:var(--card);border-radius:10px;min-width:0}
.ap-detail-label{font-size:11px;color:var(--muted);margin-bottom:5px}
.ap-detail-value{font-size:13px;font-weight:750;overflow-wrap:anywhere}
.ap-address{margin:11px 0 0;color:var(--muted);font-size:12px;line-height:1.6;overflow-wrap:anywhere}
.ap-status{display:inline-flex;align-items:center;border-radius:99px;padding:7px 11px;background:var(--soft);color:var(--muted);font-size:11px;font-weight:800;white-space:nowrap}
.ap-status.published{color:var(--primary)}
@media(max-width:720px){.ap-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:420px){.ap-grid{grid-template-columns:1fr}}
@media print{.ad-admin-tabs,.ad-directory .ad-button,.ad-directory .ad-filters{display:none!important}}
`;

function AdminUserDirectory({ onAccessLost }) {
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setData(null);

    async function loadDirectory() {
      try {
        const params = new URLSearchParams({
          search,
          role: roleFilter,
          page: String(page),
          page_size: "20",
        });
        const response = await fetch(
          `${API_BASE}/api/admin/user-directory?${params.toString()}`,
          {
            method: "GET",
            credentials: "include",
            cache: "no-store",
            mode: "cors",
            redirect: "error",
            headers: { Accept: "application/json" },
            signal: controller.signal,
          }
        );

        if (response.status === 401 || response.status === 403) {
          if (!controller.signal.aborted) onAccessLost(response.status);
          return;
        }
        if (!response.ok) {
          throw new Error(
            response.status === 429
              ? "Too many requests. Please try again shortly."
              : `Unable to load accounts (HTTP ${response.status}).`
          );
        }

        const body = await response.json();
        if (
          body?.role !== "admin" ||
          !Array.isArray(body.users) ||
          !body.summary ||
          !body.pagination
        ) {
          throw new Error("The server returned an unexpected user directory response.");
        }
        if (!controller.signal.aborted) setData(body);
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Unable to load the user directory."
          );
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    loadDirectory();
    return () => controller.abort();
  }, [search, roleFilter, page, reload, onAccessLost]);

  const pagination = data?.pagination;
  const totalPages = Math.max(0, Number(pagination?.total_pages || 0));

  function applySearch(event) {
    event.preventDefault();
    setPage(1);
    setSearch(searchDraft.trim());
  }

  return (
    <div className="ad-directory" role="region" aria-label="Admin user directory">
      <style>{ADMIN_DIRECTORY_STYLES}</style>
      <div className="ad-head">
        <div>
          <h2>User Directory</h2>
          <p className="ad-help">
            Review registered renters and property owners. Records are read-only.
          </p>
        </div>
        <button
          className="ad-button"
          type="button"
          disabled={loading}
          onClick={() => setReload((value) => value + 1)}
        >
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {data && (
        <div className="ad-stats" aria-label="Account totals">
          <div className="ad-stat">
            <div className="ad-stat-label"><Users size={17} /> Total users</div>
            <p className="ad-stat-value">{data.summary.total_users ?? 0}</p>
          </div>
          <div className="ad-stat">
            <div className="ad-stat-label"><UserRound size={17} /> Renters</div>
            <p className="ad-stat-value">{data.summary.total_renters ?? 0}</p>
          </div>
          <div className="ad-stat">
            <div className="ad-stat-label"><Building2 size={17} /> Property owners</div>
            <p className="ad-stat-value">{data.summary.total_property_owners ?? 0}</p>
          </div>
        </div>
      )}

      <form className="ad-filters" onSubmit={applySearch}>
        <div className="ad-field">
          <label className="ad-label" htmlFor="ad-user-search">
            Search username
          </label>
          <input
            className="ad-input"
            id="ad-user-search"
            type="search"
            maxLength={60}
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Enter a username"
          />
        </div>
        <div className="ad-field role">
          <label className="ad-label" htmlFor="ad-user-role">Account role</label>
          <select
            className="ad-input"
            id="ad-user-role"
            value={roleFilter}
            onChange={(event) => {
              setRoleFilter(event.target.value);
              setPage(1);
            }}
          >
            <option value="all">All roles</option>
            <option value="renter">Renters</option>
            <option value="property_owner">Property owners</option>
          </select>
        </div>
        <button className="ad-button" type="submit" disabled={loading}>
          <Search size={16} /> Search
        </button>
      </form>

      {error && (
        <div className="ad-error" role="alert">
          <AlertCircle size={18} />
          <span>{error} You can try Refresh to request the data again.</span>
        </div>
      )}

      {loading ? (
        <div className="ad-state" role="status">Loading registered accounts…</div>
      ) : !error && data && data.users.length === 0 ? (
        <div className="ad-state" role="status">
          No renter or property-owner accounts match your filters.
        </div>
      ) : !error && data ? (
        <>
          <div className="ad-table-wrap">
            <table className="ad-table">
              <thead>
                <tr>
                  <th scope="col">Username</th>
                  <th scope="col">Account role</th>
                  <th scope="col">Account status</th>
                  <th scope="col">Email verified</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((user) => (
                  <tr key={user.user_id}>
                    <td>
                      <span className="ad-username">{user.username}</span>
                      <div className="ad-subtle">Account #{user.user_id}</div>
                    </td>
                    <td>{user.role === "property_owner" ? "Property Owner" : "Renter"}</td>
                    <td>
                      <span className={`ad-status ${user.account_status === "active" ? "active" : ""}`}>
                        {user.account_status || "Unknown"}
                      </span>
                    </td>
                    <td>{user.email_verified ? "Verified" : "Not verified"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="ad-pagination">
            <p className="ad-help">
              {pagination?.matched_users ?? 0} matching users · Page {pagination?.page ?? page} of {totalPages || 1}
            </p>
            <div className="ad-pagination-actions">
              <button
                type="button"
                className="ad-button"
                disabled={page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                <ChevronLeft size={16} /> Previous
              </button>
              <button
                type="button"
                className="ad-button"
                disabled={page >= totalPages}
                onClick={() => setPage((current) => current + 1)}
              >
                Next <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </>
      ) : null}

      <p className="ad-note">
        The directory does not expose email addresses, passwords, private contacts,
        security answers, or OTP data. Admin accounts are excluded. No edit or
        delete actions are available.
      </p>
    </div>
  );
}

// FILE 67 — Admin-only, read-only Dorm Listing Directory from File 65.
// Every value below comes from the existing authenticated property-directory API.
function AdminPropertyDirectory({ onAccessLost }) {
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setData(null);

    async function loadProperties() {
      try {
        const params = new URLSearchParams({
          search,
          status: statusFilter,
          page: String(page),
          page_size: "20",
        });
        const response = await fetch(
          `${API_BASE}/api/admin/property-directory?${params.toString()}`,
          {
            method: "GET",
            credentials: "include",
            mode: "cors",
            redirect: "error",
            cache: "no-store",
            headers: { Accept: "application/json" },
            signal: controller.signal,
          }
        );

        if (response.status === 401 || response.status === 403) {
          if (!controller.signal.aborted) onAccessLost(response.status);
          return;
        }
        if (!response.ok) {
          throw new Error(
            response.status === 429
              ? "Too many requests. Please try again shortly."
              : `Unable to load dorm listings (HTTP ${response.status}).`
          );
        }

        const body = await response.json();
        if (
          body?.role !== "admin" ||
          !Array.isArray(body.properties) ||
          !body.summary ||
          !body.pagination
        ) {
          throw new Error("The server returned an unexpected property directory response.");
        }
        if (!controller.signal.aborted) setData(body);
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "Unable to load property listings.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    loadProperties();
    return () => controller.abort();
  }, [search, statusFilter, page, reload, onAccessLost]);

  const pagination = data?.pagination;
  const totalPages = Math.max(0, Number(pagination?.total_pages || 0));
  const currency = new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  function peso(value) {
    if (value === null || value === undefined || value === "") return "Not specified";
    const amount = Number(value);
    return Number.isFinite(amount) && amount >= 0
      ? currency.format(amount)
      : "Not specified";
  }

  function applySearch(event) {
    event.preventDefault();
    setPage(1);
    setSearch(searchDraft.trim());
  }

  return (
    <div className="ad-directory" role="region" aria-label="Admin dorm listing directory">
      <div className="ad-head">
        <div>
          <h2>Dorm Listing Directory</h2>
          <p className="ad-help">
            View existing dorm properties and their owners. Listings are read-only.
          </p>
        </div>
        <button
          className="ad-button"
          type="button"
          disabled={loading}
          onClick={() => setReload((value) => value + 1)}
        >
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {data && (
        <div className="ad-stats" aria-label="Property directory totals">
          <div className="ad-stat">
            <div className="ad-stat-label"><Building2 size={17} /> Total listings</div>
            <p className="ad-stat-value">{data.summary.total_listings ?? 0}</p>
          </div>
          <div className="ad-stat">
            <div className="ad-stat-label"><CheckCircle2 size={17} /> Published</div>
            <p className="ad-stat-value">{data.summary.published_listings ?? 0}</p>
          </div>
          <div className="ad-stat">
            <div className="ad-stat-label"><House size={17} /> Available rooms</div>
            <p className="ad-stat-value">{data.summary.available_rooms ?? 0}</p>
          </div>
        </div>
      )}

      <form className="ad-filters" onSubmit={applySearch}>
        <div className="ad-field">
          <label className="ad-label" htmlFor="ad-property-search">
            Search property, address or owner
          </label>
          <input
            className="ad-input"
            id="ad-property-search"
            type="search"
            maxLength={60}
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Search dorm listings"
          />
        </div>
        <div className="ad-field role">
          <label className="ad-label" htmlFor="ad-property-status">Listing status</label>
          <select
            className="ad-input"
            id="ad-property-status"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value);
              setPage(1);
            }}
          >
            <option value="all">All statuses</option>
            <option value="published">Published</option>
            <option value="not_published">Not published</option>
          </select>
        </div>
        <button className="ad-button" type="submit" disabled={loading}>
          <Search size={16} /> Search
        </button>
      </form>

      {error && (
        <div className="ad-error" role="alert">
          <AlertCircle size={18} />
          <span>{error} Select Refresh to try again.</span>
        </div>
      )}

      {loading ? (
        <div className="ad-state" role="status">Loading dorm listings…</div>
      ) : !error && data && data.properties.length === 0 ? (
        <div className="ad-state" role="status">
          No dorm listings match your search and status filter.
        </div>
      ) : !error && data ? (
        <>
          <div className="ap-list" aria-label="Registered dorm properties">
            {data.properties.map((property) => (
              <article className="ap-card" key={property.property_id}>
                <div className="ap-card-top">
                  <div>
                    <h3 className="ap-title">
                      {property.property_name || `Property #${property.property_id}`}
                    </h3>
                    <div className="ap-meta">
                      Owner: {property.owner_username || "Unknown"}
                      {" · "}Property #{property.property_id}
                    </div>
                  </div>
                  <span className={`ap-status ${property.listing_status === "published" ? "published" : ""}`}>
                    {property.listing_status === "published" ? "Published" : (property.listing_status || "Unknown")}
                  </span>
                </div>
                <div className="ap-grid">
                  <div className="ap-detail">
                    <div className="ap-detail-label">Monthly asking rent</div>
                    <div className="ap-detail-value">{peso(property.monthly_rent)}</div>
                  </div>
                  <div className="ap-detail">
                    <div className="ap-detail-label">Total rooms</div>
                    <div className="ap-detail-value">{property.total_rooms ?? "—"}</div>
                  </div>
                  <div className="ap-detail">
                    <div className="ap-detail-label">Available rooms</div>
                    <div className="ap-detail-value">{property.available_rooms ?? "—"}</div>
                  </div>
                  <div className="ap-detail">
                    <div className="ap-detail-label">Assigned rooms</div>
                    <div className="ap-detail-value">{property.assigned_rooms ?? "—"}</div>
                  </div>
                  <div className="ap-detail">
                    <div className="ap-detail-label">Owner account</div>
                    <div className="ap-detail-value">#{property.owner_user_id ?? "—"}</div>
                  </div>
                </div>
                <p className="ap-address">Address: {property.address || "Not specified"}</p>
              </article>
            ))}
          </div>
          <div className="ad-pagination">
            <p className="ad-help">
              {pagination?.matched_listings ?? 0} matching listings · Page {pagination?.page ?? page} of {totalPages || 1}
            </p>
            <div className="ad-pagination-actions">
              <button
                className="ad-button"
                type="button"
                disabled={loading || page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                <ChevronLeft size={16} /> Previous
              </button>
              <button
                className="ad-button"
                type="button"
                disabled={loading || page >= totalPages}
                onClick={() => setPage((current) => current + 1)}
              >
                Next <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </>
      ) : null}

      <p className="ad-note">
        This is a read-only directory. Admins can inspect listing details, but cannot
        modify, publish, unpublish, or delete properties here. Monthly asking rent
        is distinct from a tenant's agreed rent.
      </p>
    </div>
  );
}

// FILE 68 — Uses the two already-working Admin-only directory endpoints.
// If either fails, show an error without hiding or changing Security Monitoring.
function AdminSystemOverview({ onSelectSection }) {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setOverview(null);

    async function getSummary(endpoint) {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: "GET",
        credentials: "include",
        cache: "no-store",
        mode: "cors",
        redirect: "error",
        signal: controller.signal,
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(
          response.status === 401 || response.status === 403
            ? "Admin access could not be verified. Check your login session."
            : `Unable to load overview (HTTP ${response.status}).`
        );
      }
      const data = await response.json();
      if (data?.role !== "admin" || !data.summary) {
        throw new Error("Unexpected dashboard overview response.");
      }
      return data.summary;
    }

    async function load() {
      try {
        const [users, properties] = await Promise.all([
          getSummary("/api/admin/user-directory?page=1&page_size=1"),
          getSummary("/api/admin/property-directory?page=1&page_size=1"),
        ]);
        const values = [
          users.total_renters,
          users.total_property_owners,
          properties.total_listings,
          properties.available_rooms,
        ];
        if (values.some((value) => !Number.isSafeInteger(value) || value < 0)) {
          throw new Error("Overview totals were not valid numbers.");
        }
        if (!controller.signal.aborted) {
          setOverview({
            renters: users.total_renters,
            owners: users.total_property_owners,
            listings: properties.total_listings,
            availableRooms: properties.available_rooms,
          });
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "Unable to load overview.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    load();
    return () => controller.abort();
  }, [refreshKey]);

  const cards = [
    ["Renters", overview?.renters, UserRound],
    ["Property owners", overview?.owners, Users],
    ["Dorm listings", overview?.listings, Building2],
    ["Available rooms", overview?.availableRooms, House],
  ];
  const shortcuts = [
    ["Security Monitoring", "security", ShieldCheck],
    ["Registered Users", "users", Users],
    ["Dorm Listings", "properties", Building2],
  ];

  return (
    <section className="ao-overview" aria-label="Admin system overview">
      <div className="ao-head">
        <div>
          <div className="ao-eyebrow"><ShieldCheck size={15} /> ADMIN OVERVIEW</div>
          <h2>System at a glance</h2>
          <p>Live totals from the existing read-only Admin APIs.</p>
        </div>
        <button
          type="button"
          className="ad-button"
          disabled={loading}
          onClick={() => setRefreshKey((key) => key + 1)}
        >
          <RefreshCw size={16} /> Refresh overview
        </button>
      </div>
      <div className="ao-grid" aria-live="polite">
        {cards.map(([label, value, Icon]) => (
          <div className="ao-metric" key={label}>
            <div className="ao-label"><Icon size={17} /> {label}</div>
            <div className="ao-count">{loading ? "…" : error ? "—" : value ?? "—"}</div>
          </div>
        ))}
      </div>
      {error && <div className="ao-alert" role="alert">{error} The existing Admin sections below are still available.</div>}
      <div className="ao-links" aria-label="Admin quick navigation">
        {shortcuts.map(([label, section, Icon]) => (
          <button
            type="button"
            key={section}
            className="ao-link"
            onClick={() => onSelectSection(section)}
          >
            <Icon size={17} /><span>{label}</span><ChevronRight size={15} />
          </button>
        ))}
      </div>
    </section>
  );
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
  const [hideAccountDetails, setHideAccountDetails] = useState(readHideDetailsSetting);
  const [adminSection, setAdminSection] = useState("security");

  const actionInFlight = useRef(false);
  const userRequestedCheck = useRef(false);

  const onAdminDirectoryAccessLost = useCallback((httpStatus) => {
    setState({ kind: httpStatus === 401 ? "signed-out" : "unavailable" });
    setMessage({
      kind: "error",
      text: "Admin directory access is no longer verified. Protected data has been hidden.",
    });
  }, []);

  // This preference only masks details shown in Settings; it does not
  // change backend authorization or the data available in other pages.
  useEffect(() => {
    try {
      window.localStorage.setItem(
        SETTINGS_HIDE_DETAILS_KEY,
        hideAccountDetails ? "true" : "false"
      );
    } catch {
      // Settings remains usable if browser storage is unavailable.
    }
  }, [hideAccountDetails]);

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
      // File 9: avoid resetting forms after file selection.
      // A native file picker can trigger browser focus events.
      // The existing session deadline timer remains active.
      if (
        !actionInFlight.current &&
        document.visibilityState !== "hidden" &&
        Date.now() >= expiresMs
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
          text: "Refresh response received, but account verification failed.Protected content is hidden.",
        });
      }
    } catch {
      setState({ kind: "unavailable" });
      setMessage({
        kind: "error",
        text: "Session refresh could not be confirmed. Retry verification orcheck FastAPI.",
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

  // File 57: Settings in RoleHome opens the existing verified account
  // security screen. The floating shortcut is no longer rendered.
  // Admins retain their independent monitoring workspace.

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
          onNavigate={(page) => {
            if (page === "settings") {
              navigate(`${location.pathname}?view=account`);
            }
          }}
          onLogout={() => {
            // Open the existing account screen first so that any
            // logout error remains visible.
            navigate(`${location.pathname}?view=account`);
            signOut();
          }}
        />

      </div>
    );
  }

  // FILE 59: Render a polished Settings screen for the verified renter/owner.
  // Existing handlers are reused verbatim. Admin monitoring is unchanged.
  if (ready && account && account.role !== "admin" && accountView) {
    const accountLabel = account.role === "renter" ? "Renter" : "Property Owner";
    const sessionTime = new Date(account.expires_at).toLocaleTimeString("en-PH", {
      hour: "numeric",
      minute: "2-digit",
    });

    return (
      <div className={`${themeClass} ds-screen`}>
        <style>{SETTINGS_STYLES}</style>

        <header className="ds-topbar">
          <div className="ds-brand"><House size={27} /> Dormora</div>
          <div className="ds-top-actions">
            <button
              className="ds-button"
              type="button"
              onClick={() => navigate(location.pathname)}
            >
              <ArrowLeft size={16} /> Back to Dashboard
            </button>
          </div>
        </header>

        <main className="ds-wrap">
          <div className="ds-heading">
            <div>
              <div className="ds-eyebrow">DORMORA / PERSONAL SETTINGS</div>
              <h1>Settings</h1>
              <p className="ds-subtitle">
                Customize your appearance and manage your protected account.
              </p>
            </div>
            <span className="ds-badge"><ShieldCheck size={16} /> Verified session</span>
          </div>

          <div className="ds-grid">
            <section className="ds-card" aria-labelledby="ds-account-title">
              <div className="ds-section-head">
                <div className="ds-section-icon"><UserRound size={22} /></div>
                <div>
                  <h2 id="ds-account-title">Account Information</h2>
                  <p>Your signed-in account, confirmed by FastAPI.</p>
                </div>
              </div>

              <div className="ds-identity">
                <span className="ds-avatar" aria-hidden="true">
                  {hideAccountDetails ? "•" : account.username.charAt(0).toUpperCase()}
                </span>
                <div>
                  <strong>{hideAccountDetails ? "Hidden on this screen" : account.username}</strong>
                  <small>{accountLabel} account</small>
                </div>
              </div>

              <div className="ds-row">
                <div>
                  <p className="ds-row-title">Hide account details</p>
                  <p className="ds-row-sub">Masks your username and session times on this Settings screen.</p>
                </div>
                <button
                  type="button"
                  className="ds-button"
                  aria-pressed={hideAccountDetails}
                  onClick={() => setHideAccountDetails((hidden) => !hidden)}
                >
                  {hideAccountDetails ? <Eye size={16} /> : <EyeOff size={16} />}
                  {hideAccountDetails ? "Show details" : "Hide details"}
                </button>
              </div>
              <p className="ds-help">
                This is an on-screen privacy preference saved in this browser.
                It does not hide information on other pages or change account permissions.
              </p>
            </section>

            <section className="ds-card" aria-labelledby="ds-appearance-title">
              <div className="ds-section-head">
                <div className="ds-section-icon"><Palette size={22} /></div>
                <div>
                  <h2 id="ds-appearance-title">Appearance</h2>
                  <p>Choose the theme you prefer for Dormora.</p>
                </div>
              </div>
              <div className="ds-row">
                <div>
                  <p className="ds-row-title">Color theme</p>
                  <p className="ds-row-sub">Changes are applied immediately and saved by Dormora.</p>
                </div>
                <div className="ds-theme-choices" aria-label="Appearance theme">
                  <button
                    type="button"
                    className="ds-theme-choice"
                    aria-pressed={!darkMode}
                    disabled={typeof onToggleTheme !== "function"}
                    onClick={() => {
                      if (darkMode) onToggleTheme?.();
                    }}
                  >
                    <Sun size={17} /> Light
                  </button>
                  <button
                    type="button"
                    className="ds-theme-choice"
                    aria-pressed={Boolean(darkMode)}
                    disabled={typeof onToggleTheme !== "function"}
                    onClick={() => {
                      if (!darkMode) onToggleTheme?.();
                    }}
                  >
                    <Moon size={17} /> Dark
                  </button>
                </div>
              </div>
            </section>

            <section className="ds-card" aria-labelledby="ds-security-title">
              <div className="ds-section-head">
                <div className="ds-section-icon"><LockKeyhole size={22} /></div>
                <div>
                  <h2 id="ds-security-title">Account &amp; Security</h2>
                  <p>Review your session and use the existing protected actions.</p>
                </div>
              </div>

              <div className="ds-session">
                <div className="ds-detail">
                  <small>Session deadline</small>
                  <strong>{hideAccountDetails ? "Hidden" : sessionTime}</strong>
                </div>
                <div className="ds-detail">
                  <small>Idle time remaining</small>
                  <strong role="timer" aria-live="off">
                    {hideAccountDetails
                      ? "Hidden"
                      : `${Math.floor(remaining / 60)}m ${String(remaining % 60).padStart(2, "0")}s`}
                  </strong>
                </div>
              </div>

              <div className="ds-row">
                <div>
                  <p className="ds-row-title">Login session</p>
                  <p className="ds-row-sub">Checking does not renew your session; Refresh session does.</p>
                </div>
                <div className="ds-actions">
                  <button
                    className="ds-button"
                    type="button"
                    disabled={busy}
                    onClick={checkSession}
                  >
                    <ShieldCheck size={16} /> Check session
                  </button>
                  <button
                    className="ds-button"
                    type="button"
                    disabled={busy}
                    onClick={refreshSession}
                  >
                    <RefreshCw size={16} /> Refresh session
                  </button>
                </div>
              </div>

              <div className="ds-row">
                <div>
                  <p className="ds-row-title">Password</p>
                  <p className="ds-row-sub">Update your password through Dormora's secure form.</p>
                </div>
                <button
                  className="ds-button"
                  type="button"
                  disabled={busy}
                  aria-expanded={passwordChangeOpen}
                  aria-controls="dormora-account-password-panel"
                  onClick={() => setPasswordChangeOpen((open) => !open)}
                >
                  <KeyRound size={16} />
                  {passwordChangeOpen ? "Close password form" : "Change password"}
                </button>
              </div>

              {passwordChangeOpen && (
                <div id="dormora-account-password-panel" style={{ marginTop: 15 }}>
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

              <div className="ds-row">
                <div>
                  <p className="ds-row-title">Sign out</p>
                  <p className="ds-row-sub">End your login session using the CSRF-protected logout endpoint.</p>
                </div>
                <button
                  className="ds-button danger"
                  type="button"
                  disabled={busy}
                  onClick={signOut}
                >
                  <LogOut size={16} /> Sign out
                </button>
              </div>

              {message && (
                <p className={`ds-feedback ${message.kind === "error" ? "error" : ""}`}
                  role={message.kind === "error" ? "alert" : "status"}
                >
                  {message.kind === "error" ? <ShieldCheck size={17} /> : <CheckCircle2 size={17} />}
                  <span>{message.text}</span>
                </p>
              )}
              <p className="ds-help">
                Your session deadline is controlled by FastAPI; appearance and
                display preferences never extend it or change backend security.
              </p>
            </section>
          </div>

          <div className="ds-foot">
            © 2026 Dormora · Secure rental management
          </div>
        </main>
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
                {accountView && account.role !== "admin"
                  ? "Settings"
                  : workspace.title}
              </h1>

              <p style={{ color: "var(--muted)" }}>
                {accountView && account.role !== "admin"
                  ? "Manage your account information, password, and login session."
                  : `Welcome, ${account.username}. ${workspace.summary}`}
              </p>

              {accountView && account.role !== "admin" && (
                <div
                  style={{
                    marginTop: 22,
                    padding: 20,
                    borderRadius: 12,
                    border: "1px solid var(--border)",
                    background: "var(--soft)",
                  }}
                >
                  <h2 style={{ fontSize: 18, margin: "0 0 12px" }}>
                    Account Information
                  </h2>
                  <p style={{ margin: "0 0 8px" }}>
                    Username: <strong>{account.username}</strong>
                  </p>
                  <p style={{ margin: "0 0 18px" }}>
                    Account type: <strong>{account.role === "renter" ? "Renter" : "Property Owner"}</strong>
                  </p>
                  <button
                    type="button"
                    style={ACTION_BUTTON_STYLE}
                    onClick={() => navigate(location.pathname)}
                  >
                    <House size={16} style={{ verticalAlign: "middle" }} />
                    {" "}Back to Dashboard
                  </button>
                </div>
              )}

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
                <>
                  <style>{ADMIN_DIRECTORY_STYLES}</style>
                  <AdminSystemOverview onSelectSection={setAdminSection} />
                  <div className="ad-admin-tabs" role="tablist" aria-label="Admin sections">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={adminSection === "security"}
                      aria-controls="dormora-admin-section"
                      className="ad-admin-tab"
                      onClick={() => setAdminSection("security")}
                    >
                      <ShieldCheck size={17} /> Security Monitoring
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={adminSection === "users"}
                      aria-controls="dormora-admin-section"
                      className="ad-admin-tab"
                      onClick={() => setAdminSection("users")}
                    >
                      <Users size={17} /> User Directory
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={adminSection === "properties"}
                      aria-controls="dormora-admin-section"
                      className="ad-admin-tab"
                      onClick={() => setAdminSection("properties")}
                    >
                      <Building2 size={17} /> Dorm Listings
                    </button>
                  </div>
                  <div id="dormora-admin-section" role="tabpanel">
                    {adminSection === "security" ? (
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
                    ) : adminSection === "users" ? (
                      <AdminUserDirectory onAccessLost={onAdminDirectoryAccessLost} />
                    ) : (
                      <AdminPropertyDirectory onAccessLost={onAdminDirectoryAccessLost} />
                    )}
                  </div>
                </>
              ) : !accountView ? (
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
              ) : null}

              {accountView && account.role !== "admin" && (
                <div style={{ marginTop: 28 }}>
                  <h2 style={{ fontSize: 19, margin: "0 0 8px" }}>
                    Account &amp; Security
                  </h2>
                  <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>
                    Verify or refresh your session, change your password, or sign out securely.
                  </p>
                </div>
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