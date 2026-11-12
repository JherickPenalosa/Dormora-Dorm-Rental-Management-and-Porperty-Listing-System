
/*
 * Dormora Frontend File 113 — extracted administrator monitoring dashboard.
 * CREATE: frontend/src/components/admin/AdminSecurityDashboard.jsx
 *
 * Source: the working File 112 App.jsx. The existing administrator report,
 * 24-hour chart, top-IP ranking, flags and independent event history stay
 * behavior-identical. The backend still enforces administrator authorization.
 *
 * STAGED REFACTOR: App.jsx must remain unchanged until File 114 imports this
 * component and deletes the old inline dashboard implementation.
 */

import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import AdminSecurityEventHistory from "./AdminSecurityEventHistory";

// Keep these values aligned with File 112 until shared configuration is moved.
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

const REPORT_KEYS = Object.freeze([
  "failed_logins",
  "successful_logins",
  "lockout_tier_events",
  "blocked_login_attempts",
  "ip_block_events",
  "active_ip_blocks",
  "limited_requests",
  "currently_locked_accounts",
  "accounts_with_failed_login_counter",
]);

function validAdminReport(report) {
  return Boolean(
    report &&
    report.window_hours === 24 &&
    Number.isFinite(Date.parse(report.generated_at)) &&
    Number.isFinite(Date.parse(report.window_start)) &&
    report.summary &&
    REPORT_KEYS.every((key) => Number.isSafeInteger(report.summary[key]) && report.summary[key] >= 0) &&
    Array.isArray(report.event_counts) &&
    report.event_counts.every((event) =>
      Object.prototype.hasOwnProperty.call(EVENT_LABELS, event?.event_type) &&
      Number.isSafeInteger(event?.count) && event.count >= 0
    ) &&
    Array.isArray(report.recent_events) &&
    report.recent_events.length <= 20 &&
    report.recent_events.every((event) =>
      Object.prototype.hasOwnProperty.call(EVENT_LABELS, event?.event_type) &&
      ["success", "failure", "info", "blocked", "other"].includes(event?.outcome) &&
      Number.isFinite(Date.parse(event?.occurred_at))
    )
  );
}

function displayLocalTime(value) {
  const time = new Date(value);
  return Number.isFinite(time.valueOf())
    ? time.toLocaleString("en-PH", { dateStyle: "medium", timeStyle: "short" })
    : "Unavailable";
}

// Never let optional File 99 charts invalidate File 98's verified core report.
// Optional sections are independently validated and show "Unavailable" rather
// than misleading zeros if the backend reports a warning or unexpected shape.
const OPTIONAL_REPORT_SECTIONS = Object.freeze([
  "failed_logins_hourly", "top_failing_ips", "monitoring_flags",
]);

const MONITOR_FLAG_LABELS = Object.freeze({
  IP_OVER_THRESHOLD: "IP over failure threshold",
  ACCOUNT_TARGETED: "Account targeted from multiple IPs",
  OTP_GUESSING: "Possible OTP guessing",
  OFF_HOURS_LOGIN: "Off-hours login",
});

const MONITOR_FLAG_SEVERITIES = Object.freeze(["HIGH", "MED", "INFO"]);

function safeCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function validHourlySeries(items) {
  return Array.isArray(items) && items.length === 24 && items.every((item) =>
    item && Number.isFinite(Date.parse(item.hour_start)) && safeCount(item.count)
  );
}

function validIpRanking(items) {
  return Array.isArray(items) && items.length <= 5 && items.every((item) =>
    item && typeof item.ip_address === "string" && item.ip_address.length > 0 &&
    item.ip_address.length <= 45 && /^[0-9a-fA-F:.]+$/.test(item.ip_address) &&
    safeCount(item.failed_logins) && typeof item.blocked === "boolean"
  );
}

function validMonitorFlags(items) {
  return Array.isArray(items) && items.length <= 20 && items.every((flag) =>
    flag && Object.prototype.hasOwnProperty.call(MONITOR_FLAG_LABELS, flag.flag_type) &&
    MONITOR_FLAG_SEVERITIES.includes(flag.severity) &&
    typeof flag.target === "string" && flag.target.length <= 100 &&
    typeof flag.description === "string" && flag.description.length <= 255 &&
    safeCount(flag.event_count) && Number.isFinite(Date.parse(flag.detected_at))
  );
}

function hourLabel(value) {
  return new Date(value).toLocaleTimeString("en-PH", {
    hour: "numeric", hour12: true, timeZone: "Asia/Manila",
  });
}

function AdminSecurityDashboard({ onAccessLost }) {
  const [revision, setRevision] = useState(0);
  const [reportState, setReportState] = useState({ kind: "loading" });
  const onAccessLostRef = useRef(onAccessLost);
  onAccessLostRef.current = onAccessLost;

  useEffect(() => {
    const controller = new AbortController();
    // Hide previously fetched admin data while waiting for the next DB check.
    setReportState({ kind: "loading" });

    async function loadSecurityReport() {
      try {
        const response = await fetch(`${API_BASE}/api/auth/admin/security`, {
          method: "GET",
          credentials: "include",
          cache: "no-store",
          mode: "cors",
          redirect: "error",
          signal: controller.signal,
        });

        if (controller.signal.aborted) return;

        if (response.status === 401 || response.status === 403) {
          onAccessLostRef.current(response.status);
          return;
        }

        if (response.status !== 200) {
          setReportState({
            kind: "error",
            message: "Security monitoring is temporarily unavailable.",
          });
          return;
        }

        const report = await response.json();
        if (controller.signal.aborted) return;

        if (!validAdminReport(report)) {
          setReportState({
            kind: "error",
            message: "FastAPI returned an unexpected core monitoring response.",
          });
          return;
        }

        setReportState({ kind: "ready", report });
      } catch (error) {
        if (controller.signal.aborted || error?.name === "AbortError") return;
        setReportState({
          kind: "error",
          message: "Could not connect to the security monitoring API.",
        });
      }
    }

    loadSecurityReport();
    return () => controller.abort();
  }, [revision]);

  // Instructor-required polling; never extends the session expiry. It is
  // intentionally suspended in hidden tabs to avoid unnecessary audit events.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        setRevision((value) => value + 1);
      }
    }, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const panelStyle = {
    padding: 18,
    border: "1px solid var(--border)",
    borderRadius: 14,
    background: "var(--soft)",
  };

  const tableHeadStyle = {
    padding: "12px 14px",
    whiteSpace: "nowrap",
    fontWeight: 700,
    borderBottom: "1px solid var(--border)",
  };

  const tableCellStyle = {
    padding: "12px 14px",
    borderBottom: "1px solid var(--border)",
  };

  const report = reportState.kind === "ready" ? reportState.report : null;

  const headlineMetrics = report ? [
    ["Successful logins", report.summary.successful_logins],
    ["Failed logins", report.summary.failed_logins],
    ["Lockout tier events", report.summary.lockout_tier_events],
    ["IP block events", report.summary.ip_block_events],
  ] : [];

  const additionalMetrics = report ? [
    ["Blocked login attempts", report.summary.blocked_login_attempts],
    ["Rate-limited requests", report.summary.limited_requests],
    ["Currently locked accounts", report.summary.currently_locked_accounts],
    ["Active IP blocks", report.summary.active_ip_blocks],
    ["Accounts with failed counters", report.summary.accounts_with_failed_login_counter],
  ] : [];

  const highestCount = report
    ? Math.max(1, ...report.event_counts.map((item) => item.count)) : 1;

  const backendWarnings = report && Array.isArray(report.report_warnings)
    ? report.report_warnings.filter((item) => OPTIONAL_REPORT_SECTIONS.includes(item))
    : [];

  const optionalUnreliable = (section) => backendWarnings.includes(section);

  const hourlyReady = report && !optionalUnreliable("failed_logins_hourly") &&
    validHourlySeries(report.failed_logins_hourly);

  const topIpsReady = report && !optionalUnreliable("top_failing_ips") &&
    validIpRanking(report.top_failing_ips);

  const flagsReady = report && !optionalUnreliable("monitoring_flags") &&
    report.monitoring_flags_available === true &&
    validMonitorFlags(report.monitoring_flags);

  const flagsMissingTable = report && !optionalUnreliable("monitoring_flags") &&
    report.monitoring_flags_available === false;

  const hourlyMaximum = hourlyReady
    ? Math.max(1, ...report.failed_logins_hourly.map((item) => item.count)) : 1;

  const sectionsUnavailable = report ? [
    !hourlyReady && "Hourly failed-logins chart",
    !topIpsReady && "Top-failing-IP table",
    !flagsReady && !flagsMissingTable && "Monitoring flags",
  ].filter(Boolean) : [];

  return (
    <section style={{ marginTop: 26 }} aria-labelledby="admin-security-title">
      <div style={{
        display: "flex",
        gap: 12,
        alignItems: "start",
        justifyContent: "space-between",
        flexWrap: "wrap",
      }}>
        <div>
          <h2 id="admin-security-title" style={{ margin: "0 0 5px", fontSize: 23 }}>
            Security activity overview
          </h2>
          <p style={{ margin: 0, color: "var(--muted)", fontSize: 13 }}>
            Admin only · Last 24 hours · Auto-refresh every 60 seconds while visible
          </p>
        </div>

        <button
          type="button"
          onClick={() => setRevision((value) => value + 1)}
          disabled={reportState.kind === "loading"}
          style={ACTION_BUTTON_STYLE}
        >
          <RefreshCw size={16} style={{ verticalAlign: "middle" }} /> Refresh report
        </button>
      </div>

      {reportState.kind === "loading" && (
        <p role="status" style={{ marginTop: 20 }}>
          Loading administrator security report…
        </p>
      )}

      {reportState.kind === "error" && (
        <div role="alert" style={{ ...panelStyle, marginTop: 18 }}>
          <p>{reportState.message}</p>
          <button
            type="button"
            onClick={() => setRevision((value) => value + 1)}
            style={ACTION_BUTTON_STYLE}
          >
            Retry report
          </button>
        </div>
      )}

      {report && (
        <>
          <p style={{ fontSize: 12, color: "var(--muted)", margin: "17px 0" }}>
            Generated: {displayLocalTime(report.generated_at)} · Window starts: {displayLocalTime(report.window_start)}
          </p>

          {sectionsUnavailable.length > 0 && (
            <div role="status" style={{
              ...panelStyle,
              marginBottom: 14,
              borderColor: "#b08e56",
            }}>
              <strong>Some additional report sections are unavailable.</strong>
              <p style={{ fontSize: 13, margin: "8px 0 0" }}>
                {sectionsUnavailable.join(", ")}. Core statistics are still available.
                Check File 99's backend log for the unavailable section.
              </p>
            </div>
          )}

          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: 12,
          }}>
            {headlineMetrics.map(([label, value]) => (
              <div key={label} style={panelStyle}>
                <div style={{ color: "var(--muted)", fontSize: 13 }}>{label}</div>
                <strong style={{
                  display: "block",
                  fontSize: 30,
                  marginTop: 7,
                  color: "var(--text)",
                }}>
                  {value.toLocaleString()}
                </strong>
              </div>
            ))}
          </div>

          <h3 style={{ fontSize: 17, margin: "26px 0 12px" }}>
            Current security indicators
          </h3>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            gap: 10,
          }}>
            {additionalMetrics.map(([label, value]) => (
              <div key={label} style={{
                ...panelStyle,
                padding: 14,
                display: "flex",
                gap: 9,
                justifyContent: "space-between",
                alignItems: "center",
              }}>
                <span style={{ color: "var(--muted)", fontSize: 12 }}>{label}</span>
                <strong style={{ fontSize: 19 }}>
                  {value.toLocaleString()}
                </strong>
              </div>
            ))}
          </div>

          <h3 style={{ fontSize: 17, margin: "26px 0 12px" }}>Event breakdown</h3>
          <div style={panelStyle}>
            {report.event_counts.map((event) => (
              <div key={event.event_type} style={{ marginBottom: 12 }}>
                <div style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                  fontSize: 12,
                  marginBottom: 5,
                }}>
                  <span>{EVENT_LABELS[event.event_type]}</span>
                  <strong>{event.count.toLocaleString()}</strong>
                </div>
                <div style={{
                  background: "var(--border)",
                  borderRadius: 30,
                  height: 7,
                  overflow: "hidden",
                }}>
                  <div style={{
                    width: `${(event.count / highestCount) * 100}%`,
                    height: "100%",
                    background: "var(--primary)",
                    borderRadius: 30,
                  }} />
                </div>
              </div>
            ))}
          </div>

          <h3 style={{ fontSize: 17, margin: "27px 0 8px" }}>
            Failed logins per hour
          </h3>
          <p style={{ margin: "0 0 12px", color: "var(--muted)", fontSize: 12 }}>
            24 Philippine-time clock hours. The current hour is partial; counts in this chart
            may differ slightly from the rolling 24-hour summary above.
          </p>

          <div style={{ ...panelStyle, overflowX: "auto" }}>
            {hourlyReady ? (
              <div style={{ minWidth: 650 }} role="group" aria-label="Hourly failed-login chart">
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(24, minmax(18px, 1fr))",
                  gap: 5,
                  alignItems: "end",
                }}>
                  {report.failed_logins_hourly.map((hour, index) => {
                    const height = hour.count > 0
                      ? Math.max(5, (hour.count / hourlyMaximum) * 100)
                      : 2;
                    const label = hourLabel(hour.hour_start);

                    return (
                      <div key={hour.hour_start} style={{ minWidth: 0, textAlign: "center" }}>
                        <span style={{
                          display: "block",
                          fontSize: 10,
                          fontWeight: hour.count > 0 ? 700 : 400,
                          color: "var(--muted)",
                        }}>
                          {hour.count}
                        </span>
                        <div
                          style={{
                            height: 132,
                            display: "flex",
                            alignItems: "end",
                            justifyContent: "center",
                            borderBottom: "1px solid var(--border)",
                          }}
                          title={`${label}: ${hour.count} failed login(s)`}
                          aria-label={`${label}: ${hour.count} failed login(s)`}
                          role="img"
                        >
                          <div style={{
                            width: "75%",
                            height: `${height}%`,
                            minHeight: 2,
                            background: hour.count ? "var(--primary)" : "var(--border)",
                            borderRadius: "4px 4px 0 0",
                          }} />
                        </div>
                        <span style={{
                          display: "block",
                          marginTop: 7,
                          fontSize: 10,
                          color: "var(--muted)",
                          whiteSpace: "nowrap",
                        }}>
                          {index % 3 === 0 || index === 23 ? label : "·"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <p role="status" style={{
                margin: 0,
                fontSize: 13,
                color: "var(--muted)",
              }}>
                Hourly chart unavailable. The other security totals are unaffected.
              </p>
            )}
          </div>

          <h3 style={{ fontSize: 17, margin: "27px 0 8px" }}>
            Top five failing IP addresses
          </h3>
          <p style={{ margin: "0 0 12px", color: "var(--muted)", fontSize: 12 }}>
            Administrator-only IP ranking from failed login events in the last 24 hours.
            Blocked status reflects the active ten-minute IP restriction.
          </p>

          <div style={{ ...panelStyle, padding: 0, overflowX: "auto" }}>
            {topIpsReady ? (
              <table style={{
                width: "100%",
                borderCollapse: "collapse",
                textAlign: "left",
                fontSize: 13,
              }}>
                <thead>
                  <tr>
                    <th scope="col" style={tableHeadStyle}>IP address</th>
                    <th scope="col" style={tableHeadStyle}>Failures</th>
                    <th scope="col" style={tableHeadStyle}>Current status</th>
                  </tr>
                </thead>
                <tbody>
                  {report.top_failing_ips.length
                    ? report.top_failing_ips.map((item) => (
                      <tr key={item.ip_address}>
                        <td style={tableCellStyle}><code>{item.ip_address}</code></td>
                        <td style={tableCellStyle}>{item.failed_logins.toLocaleString()}</td>
                        <td style={tableCellStyle}>
                          {item.blocked ? "Blocked" : "Not blocked"}
                        </td>
                      </tr>
                    ))
                    : (
                      <tr>
                        <td colSpan={3} style={{
                          ...tableCellStyle,
                          color: "var(--muted)",
                        }}>
                          No failed-login IP addresses recorded in the reporting window.
                        </td>
                      </tr>
                    )}
                </tbody>
              </table>
            ) : (
              <p role="status" style={{
                padding: 18,
                margin: 0,
                color: "var(--muted)",
                fontSize: 13,
              }}>
                Top IP ranking unavailable. The core report is still valid.
              </p>
            )}
          </div>

          <h3 style={{ fontSize: 17, margin: "27px 0 8px" }}>
            Monitoring script findings
          </h3>
          <p style={{ margin: "0 0 12px", color: "var(--muted)", fontSize: 12 }}>
            Recent flags generated by <code>python -m app.security_monitor --run</code>.
            The dashboard only reads saved flags; it does not run or modify the monitor.
          </p>

          <div style={{ ...panelStyle, padding: 0, overflowX: "auto" }}>
            {flagsReady ? (
              <table style={{
                width: "100%",
                borderCollapse: "collapse",
                textAlign: "left",
                fontSize: 13,
              }}>
                <thead>
                  <tr>
                    <th scope="col" style={tableHeadStyle}>Severity</th>
                    <th scope="col" style={tableHeadStyle}>Finding</th>
                    <th scope="col" style={tableHeadStyle}>Target</th>
                    <th scope="col" style={tableHeadStyle}>Count</th>
                    <th scope="col" style={tableHeadStyle}>Detected (PHT)</th>
                  </tr>
                </thead>
                <tbody>
                  {report.monitoring_flags.length
                    ? report.monitoring_flags.map((flag, index) => (
                      <tr key={`${flag.flag_type}-${flag.detected_at}-${index}`}>
                        <td style={tableCellStyle}><strong>{flag.severity}</strong></td>
                        <td style={tableCellStyle} title={flag.description}>
                          {MONITOR_FLAG_LABELS[flag.flag_type]}
                          <div style={{ fontSize: 11, color: "var(--muted)" }}>
                            {flag.description}
                          </div>
                        </td>
                        <td style={tableCellStyle}>
                          <code>{flag.target || "Unavailable"}</code>
                        </td>
                        <td style={tableCellStyle}>
                          {flag.event_count.toLocaleString()}
                        </td>
                        <td style={{
                          ...tableCellStyle,
                          whiteSpace: "nowrap",
                        }}>
                          {displayLocalTime(flag.detected_at)}
                        </td>
                      </tr>
                    ))
                    : (
                      <tr>
                        <td colSpan={5} style={{
                          ...tableCellStyle,
                          color: "var(--muted)",
                        }}>
                          No monitoring findings saved in the last 24 hours.
                          This is normal when no patterns match.
                        </td>
                      </tr>
                    )}
                </tbody>
              </table>
            ) : (
              <p role="status" style={{
                padding: 18,
                margin: 0,
                fontSize: 13,
                color: "var(--muted)",
              }}>
                {flagsMissingTable
                  ? "Monitoring flags table is not initialized. Run File 96 with --run on the local backend."
                  : "Monitoring flags are unavailable. Check File 99's report warnings."}
              </p>
            )}
          </div>

          <p style={{
            fontSize: 12,
            color: "var(--muted)",
            marginTop: 18,
          }}>
            The event-history table below queries File 101 separately.
            Access and filters are verified by FastAPI,
            and each request is audited.
          </p>
        </>
      )}

      <AdminSecurityEventHistory onAccessLost={onAccessLost} />
    </section>
  );
}

export default AdminSecurityDashboard;
