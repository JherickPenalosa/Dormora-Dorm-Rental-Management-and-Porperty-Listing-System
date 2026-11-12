/*
 * Dormora Frontend File 111 — extract the existing admin security event history.
 * CREATE: frontend/src/components/admin/AdminSecurityEventHistory.jsx
 *
 * Copied from the current, user-supplied App.jsx (File 106).
 * This file is a staged component: leave App.jsx unchanged until File 112.
 * The backend controls authentication, authorization, filtering and audit writes.
 * No report data is stored in localStorage or rendered as raw HTML.
 */

import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

// Keep these values identical to the current App.jsx until its shared
// configuration is moved to one place in a later refactor.
const API_BASE = "http://localhost:8000";
const ACTION_BUTTON_STYLE = {
  padding: "12px 18px",
  borderRadius: 10,
  border: "1px solid var(--border)",
  background: "var(--soft)",
  color: "var(--text)",
  cursor: "pointer",
};

// File 99 returns allowlisted event names and aggregated data; only the
// admin-specific top-IP ranking includes IP addresses. Never store or log it.
const EVENT_LABELS = Object.freeze({
  LOGIN_REQUEST: "Login requests",
  LOGIN_REQUEST_LIMITED: "Rate-limited requests",
  LOGIN_FAILED: "Failed logins",
  LOGIN_LOCKED: "Blocked login attempts",
  LOCKOUT_TIER_1: "Lockout tier 1",
  LOCKOUT_TIER_2: "Lockout tier 2",
  LOCKOUT_TIER_3: "Lockout tier 3",
  IP_BLOCKED: "IP block events",
  LOGIN_PASSWORD_VERIFIED: "Passwords verified",
  LOGIN_SUCCESS: "Successful logins",
  LOGIN_NOT_ELIGIBLE: "Ineligible account attempts",
  OTP_SENT: "OTP emails accepted",
  OTP_FAILED: "OTP delivery failures",
  LOGOUT: "Logouts",
  ADMIN_VIEWED_DASHBOARD: "Admin dashboard views",
  ADMIN_ACCESS_DENIED: "Denied admin access",
});

// File 101 exposes a separate, authorized event-history endpoint. Keep this
// independent from the overview: an invalid history filter or unavailable
// history query must never erase File 100's working statistics or graphs.
const EMPTY_HISTORY_FILTERS = Object.freeze({
  event_type: "", username: "", ip_address: "", start_at: "", end_at: "",
});
const HISTORY_EVENT_PATTERN = /^[A-Z][A-Z0-9_]{0,79}$/;
const HISTORY_EVENT_OPTIONS = Object.freeze([
  ...Object.keys(EVENT_LABELS),
  "REGISTERED", "ACCOUNT_VERIFIED", "RESET_REQUESTED", "PASSWORD_CHANGED",
  "ALERT_EMAIL_SENT", "CAPTCHA_FAILED", "CSRF_REJECTED", "ADMIN_PROVISIONED",
]);
const HISTORY_OUTCOMES = Object.freeze(["success", "failure", "info", "blocked", "other"]);
const HISTORY_INPUT_STYLE = {
  width: "100%", minWidth: 0, boxSizing: "border-box", borderRadius: 9,
  padding: "10px 11px", border: "1px solid var(--border)",
  background: "var(--card)", color: "var(--text)", font: "inherit", fontSize: 13,
};

function displayPhilippineTime(value) {
  const time = new Date(value);
  return Number.isFinite(time.valueOf())
    ? time.toLocaleString("en-PH", {
      timeZone: "Asia/Manila", dateStyle: "medium", timeStyle: "short",
    })
    : "Unavailable";
}

function validSecurityHistory(body) {
  return Boolean(
    body &&
    Number.isFinite(Date.parse(body.generated_at)) &&
    Number.isFinite(Date.parse(body.window_start)) &&
    Number.isFinite(Date.parse(body.window_end)) &&
    body.limit === 50 &&
    typeof body.has_more === "boolean" &&
    Array.isArray(body.events) &&
    body.events.length <= 50 &&
    body.events.every((item) =>
      item &&
      typeof item.event_type === "string" &&
      HISTORY_EVENT_PATTERN.test(item.event_type) &&
      HISTORY_OUTCOMES.includes(item.outcome) &&
      Number.isFinite(Date.parse(item.occurred_at)) &&
      (item.username === null || (
        typeof item.username === "string" && item.username.length <= 100
      )) &&
      (item.ip_address === null || (
        typeof item.ip_address === "string" &&
        item.ip_address.length <= 45 && /^[0-9a-fA-F:.]+$/.test(item.ip_address)
      )) &&
      (item.user_agent === null || (
        typeof item.user_agent === "string" && item.user_agent.length <= 255
      ))
    )
  );
}

function historyDateToApi(value) {
  // datetime-local is intentionally interpreted in Philippine time, not the
  // browser's timezone; File 101 requires explicit timezone offsets.
  if (!value) return null;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  const datetime = `${value}:00+08:00`;
  if (!Number.isFinite(Date.parse(datetime))) return null;
  return datetime;
}

function validateHistoryFilters(filters) {
  const event = filters.event_type.trim();
  const username = filters.username.trim();
  const ip = filters.ip_address.trim();
  if (event && !HISTORY_EVENT_PATTERN.test(event)) {
    return "Event type must contain uppercase letters, digits or underscores (for example, LOGIN_FAILED).";
  }
  if (username.length > 100) return "Username search must be at most 100 characters.";
  if (ip && (ip.length > 64 || !/^[0-9a-fA-F:.]+$/.test(ip))) {
    return "Enter a complete IPv4 or IPv6 address, not a partial IP or a wildcard.";
  }
  const start = filters.start_at ? historyDateToApi(filters.start_at) : null;
  const end = filters.end_at ? historyDateToApi(filters.end_at) : null;
  if (filters.start_at && !start) return "Invalid start date/time. Use Philippine time.";
  if (filters.end_at && !end) return "Invalid end date/time. Use Philippine time.";
  const now = Date.now();
  const oldest = now - 30 * 24 * 60 * 60 * 1000;
  const startMs = start ? Date.parse(start) : null;
  const endMs = end ? Date.parse(end) : now;
  const effectiveStartMs = startMs ?? endMs - 24 * 60 * 60 * 1000;
  if (effectiveStartMs >= endMs || effectiveStartMs < oldest ||
      endMs > now + 60 * 1000 || endMs - effectiveStartMs > 30 * 24 * 60 * 60 * 1000) {
    return "Choose a valid time range within the last 30 days (start must precede end).";
  }
  return "";
}

function AdminSecurityEventHistory({ onAccessLost }) {
  const [draftFilters, setDraftFilters] = useState({ ...EMPTY_HISTORY_FILTERS });
  const [appliedFilters, setAppliedFilters] = useState({ ...EMPTY_HISTORY_FILTERS });
  const [historyRevision, setHistoryRevision] = useState(0);
  const [filterError, setFilterError] = useState("");
  const [historyState, setHistoryState] = useState({ kind: "loading" });
  const onAccessLostRef = useRef(onAccessLost);
  onAccessLostRef.current = onAccessLost;

  useEffect(() => {
    const controller = new AbortController();
    setHistoryState({ kind: "loading" }); // Hide stale admin-only history.

    async function loadHistory() {
      const query = new URLSearchParams();
      for (const key of ["event_type", "username", "ip_address"]) {
        const value = appliedFilters[key].trim();
        if (value) query.set(key, value);
      }
      for (const key of ["start_at", "end_at"]) {
        const value = historyDateToApi(appliedFilters[key]);
        if (value) query.set(key, value);
      }
      const suffix = query.toString();
      const url = `${API_BASE}/api/auth/admin/security/events${suffix ? `?${suffix}` : ""}`;
      try {
        const response = await fetch(url, {
          method: "GET", credentials: "include", cache: "no-store",
          mode: "cors", redirect: "error", signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        if (response.status === 401 || response.status === 403) {
          onAccessLostRef.current(response.status);
          return;
        }
        if (response.status === 422) {
          setHistoryState({
            kind: "error",
            message: "The server rejected these filters. Check the date range, event type or IP address.",
          });
          return;
        }
        if (response.status !== 200) {
          setHistoryState({
            kind: "error", message: "Security event history is temporarily unavailable.",
          });
          return;
        }
        const history = await response.json();
        if (controller.signal.aborted) return;
        if (!validSecurityHistory(history)) {
          setHistoryState({
            kind: "error", message: "FastAPI returned an unexpected security history response.",
          });
          return;
        }
        setHistoryState({ kind: "ready", history });
      } catch (error) {
        if (controller.signal.aborted || error?.name === "AbortError") return;
        setHistoryState({
          kind: "error", message: "Could not connect to the event history endpoint.",
        });
      }
    }

    loadHistory();
    return () => controller.abort();
  }, [appliedFilters, historyRevision]);

  function updateDraft(key, value) {
    setDraftFilters((current) => ({ ...current, [key]: value }));
    if (filterError) setFilterError("");
  }

  function applyHistoryFilters(event) {
    event.preventDefault();
    const error = validateHistoryFilters(draftFilters);
    if (error) {
      setFilterError(error);
      return;
    }
    setFilterError("");
    setAppliedFilters({
      event_type: draftFilters.event_type.trim(),
      username: draftFilters.username.trim(),
      ip_address: draftFilters.ip_address.trim(),
      start_at: draftFilters.start_at,
      end_at: draftFilters.end_at,
    });
    setHistoryRevision((revision) => revision + 1);
  }

  function clearHistoryFilters() {
    setDraftFilters({ ...EMPTY_HISTORY_FILTERS });
    setAppliedFilters({ ...EMPTY_HISTORY_FILTERS });
    setFilterError("");
    setHistoryRevision((revision) => revision + 1);
  }

  const panel = {
    border: "1px solid var(--border)", borderRadius: 14,
    background: "var(--soft)", overflow: "hidden",
  };
  const th = {
    textAlign: "left", fontWeight: 700, whiteSpace: "nowrap",
    padding: "12px 14px", borderBottom: "1px solid var(--border)",
  };
  const td = {
    padding: "12px 14px", verticalAlign: "top",
    borderBottom: "1px solid var(--border)", overflowWrap: "anywhere",
  };
  const history = historyState.kind === "ready" ? historyState.history : null;
  const filterLabels = [
    appliedFilters.event_type && `Event: ${appliedFilters.event_type}`,
    appliedFilters.username && `Username contains: ${appliedFilters.username}`,
    appliedFilters.ip_address && `IP: ${appliedFilters.ip_address}`,
    appliedFilters.start_at && `From: ${appliedFilters.start_at} PHT`,
    appliedFilters.end_at && `To: ${appliedFilters.end_at} PHT`,
  ].filter(Boolean);

  return (
    <section aria-labelledby="admin-history-title" style={{ marginTop: 32 }}>
      <h3 id="admin-history-title" style={{ fontSize: 20, margin: "0 0 8px" }}>
        Filterable security event history
      </h3>
      <p style={{ margin: "0 0 15px", color: "var(--muted)", fontSize: 12 }}>
        Latest 50 matching audit events · Default window: rolling 24 hours ·
        Date/time inputs use Philippine time (UTC+08:00). Server filters are read-only.
      </p>

      <form onSubmit={applyHistoryFilters} style={{ ...panel, padding: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
          <label style={{ display: "block", fontSize: 12, fontWeight: 650 }}>
            Event type
            <input type="text" list="dormora-audit-event-types" name="event_type"
              autoComplete="off" maxLength={80} placeholder="All events"
              value={draftFilters.event_type}
              onChange={(event) => updateDraft("event_type", event.target.value)}
              style={{ ...HISTORY_INPUT_STYLE, marginTop: 6 }} />
            <datalist id="dormora-audit-event-types">
              {HISTORY_EVENT_OPTIONS.map((type) => <option key={type} value={type} />)}
            </datalist>
          </label>
          <label style={{ display: "block", fontSize: 12, fontWeight: 650 }}>
            Username contains
            <input type="text" name="username" autoComplete="off"
              maxLength={100} placeholder="All usernames"
              value={draftFilters.username}
              onChange={(event) => updateDraft("username", event.target.value)}
              style={{ ...HISTORY_INPUT_STYLE, marginTop: 6 }} />
          </label>
          <label style={{ display: "block", fontSize: 12, fontWeight: 650 }}>
            Exact IP address
            <input type="text" name="ip_address" autoComplete="off"
              maxLength={64} placeholder="All IP addresses"
              value={draftFilters.ip_address}
              onChange={(event) => updateDraft("ip_address", event.target.value)}
              style={{ ...HISTORY_INPUT_STYLE, marginTop: 6 }} />
          </label>
          <label style={{ display: "block", fontSize: 12, fontWeight: 650 }}>
            Start (PHT)
            <input type="datetime-local" name="start_at" step="60"
              value={draftFilters.start_at}
              onChange={(event) => updateDraft("start_at", event.target.value)}
              style={{ ...HISTORY_INPUT_STYLE, marginTop: 6 }} />
          </label>
          <label style={{ display: "block", fontSize: 12, fontWeight: 650 }}>
            End (PHT)
            <input type="datetime-local" name="end_at" step="60"
              value={draftFilters.end_at}
              onChange={(event) => updateDraft("end_at", event.target.value)}
              style={{ ...HISTORY_INPUT_STYLE, marginTop: 6 }} />
          </label>
        </div>
        {filterError && <p role="alert" style={{ color: "#d35f5f", fontSize: 12, margin: "13px 0 0" }}>
          {filterError} The displayed results, if any, still use the last applied filters.
        </p>}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 14 }}>
          <button type="submit" style={ACTION_BUTTON_STYLE}>Apply filters</button>
          <button type="button" onClick={clearHistoryFilters}
            style={ACTION_BUTTON_STYLE}>Clear filters</button>
          <button type="button" onClick={() => setHistoryRevision((revision) => revision + 1)}
            disabled={historyState.kind === "loading"} style={ACTION_BUTTON_STYLE}>
            <RefreshCw size={15} style={{ verticalAlign: "middle" }} /> Refresh history
          </button>
        </div>
      </form>

      {filterLabels.length > 0 && <p style={{ margin: "12px 0", fontSize: 12, color: "var(--muted)", overflowWrap: "anywhere" }}>
        Applied: {filterLabels.join(" · ")}
      </p>}
      {historyState.kind === "loading" && (
        <p role="status" style={{ marginTop: 15 }}>Loading filtered security events…</p>
      )}
      {historyState.kind === "error" && (
        <div role="alert" style={{ ...panel, padding: 16, marginTop: 14 }}>
          <p style={{ marginTop: 0 }}>{historyState.message}</p>
          <button type="button" style={ACTION_BUTTON_STYLE}
            onClick={() => setHistoryRevision((revision) => revision + 1)}>
            Retry event history
          </button>
        </div>
      )}
      {history && <>
        <p role="status" style={{ fontSize: 12, color: "var(--muted)", margin: "13px 0" }}>
          Showing {history.events.length} event(s)
          {history.has_more ? " · More matches exist; narrow your filters" : ""}.
          {" "}Window: {displayPhilippineTime(history.window_start)} to {displayPhilippineTime(history.window_end)} PHT.
        </p>
        <div style={{ ...panel, overflowX: "auto" }}>
          <table style={{ width: "100%", minWidth: 780, borderCollapse: "collapse", textAlign: "left", fontSize: 12 }}>
            <thead><tr>
              <th scope="col" style={th}>Event</th>
              <th scope="col" style={th}>Outcome</th>
              <th scope="col" style={th}>Username</th>
              <th scope="col" style={th}>IP address</th>
              <th scope="col" style={th}>Browser/device</th>
              <th scope="col" style={th}>Occurred (PHT)</th>
            </tr></thead>
            <tbody>
              {history.events.length === 0 ? (
                <tr><td colSpan={6} style={{ ...td, color: "var(--muted)" }}>
                  No security events matched the selected filters.
                </td></tr>
              ) : history.events.map((event, index) => (
                <tr key={`${event.occurred_at}-${event.event_type}-${index}`}>
                  <td style={td}>{EVENT_LABELS[event.event_type] || event.event_type}</td>
                  <td style={{ ...td, textTransform: "capitalize" }}>{event.outcome}</td>
                  <td style={td}>{event.username || "—"}</td>
                  <td style={td}><code>{event.ip_address || "—"}</code></td>
                  <td style={{ ...td, maxWidth: 190 }} title={event.user_agent || ""}>
                    {event.user_agent || "—"}
                  </td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>
                    {displayPhilippineTime(event.occurred_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 10 }}>
          Audit values are rendered as plain text. Nothing can be edited or deleted here.
          History refreshes when you apply filters or select Refresh history;
          the overall dashboard summary auto-refreshes every 60 seconds while visible.
        </p>
      </>}
    </section>
  );
}

export default AdminSecurityEventHistory;
