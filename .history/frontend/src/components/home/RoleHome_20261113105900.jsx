
/**
 * DORMORA — SYSTEM FUNCTIONALITY, FILE 54
 * REPLACE: frontend/src/components/home/RoleHome.jsx
 *
 * Adds real PostgreSQL-backed Home statistics using GET /api/dashboard/summary.
 * Preserves all File 50 renter/owner pages, navigation, theme and logout.
 * Read-only: no database mutations or additional dependencies.
 */
import { useEffect, useState } from "react";
import {
  Bell, Building2, CalendarDays, ChevronRight, CreditCard, DoorOpen,
  History, House, Inbox, LogOut, Menu, Moon, Search, Settings, Sun, Users,
  Wallet, X, RefreshCw, AlertCircle, ShieldCheck,
} from "lucide-react";
import MyProperties from "../owner/MyProperties";
import OwnerInquiries from "../owner/OwnerInquiries";
import TenantManagement from "../owner/TenantManagement";
import RentRecords from "../owner/RentRecords";
import DormDiscovery from "../renter/DormDiscovery";
import MyInquiries from "../renter/MyInquiries";
import MyRental from "../renter/MyRental";
import RentPayments from "../renter/RentPayments";
import PaymentHistory from "../renter/PaymentHistory";

const PAGES = {
  renter: [
    ["home", "Home", House],
    ["discover", "Discover Dorms", Search],
    ["my-inquiries", "My Inquiries", Inbox],
    ["my-rental", "My Rental", DoorOpen],
    ["rent-payments", "Rent Payments", Wallet],
    ["payment-history", "Payment History", History],
  ],
  property_owner: [
    ["home", "Home", House],
    ["my-properties", "My Properties", Building2],
    ["inquiries", "Rental Inquiries", Inbox],
    ["tenants", "Tenants", Users],
    ["rent-records", "Rent Records", CreditCard],
  ],
};

const HOME = {
  renter: {
    role: "Renter",
    intro: "Find a dorm and keep your rental information organized.",
    stats: [
      ["Current Dorm", Building2],
      ["Monthly Rent", Wallet],
      ["Next Unpaid Due", CalendarDays],
      ["Payment Status", CreditCard],
    ],
    panel: "My Rental",
    empty: "Your rental information will appear here when you have a room.",
    actions: [
      ["discover", "Browse Dorms", Search],
      ["my-inquiries", "My Inquiries", Inbox],
      ["rent-payments", "Rent Payments", Wallet],
      ["payment-history", "Payment History", History],
    ],
  },
  property_owner: {
    role: "Property Owner",
    intro: "Your properties, rooms and rent records in one place.",
    stats: [
      ["Total Listings", Building2],
      ["Available Rooms", DoorOpen],
      ["Assigned Rooms", Users],
      ["Rent Charges", CreditCard],
    ],
    panel: "My Properties",
    empty: "Your property portfolio will appear here after you create a listing.",
    actions: [
      ["my-properties", "Manage Properties", Building2],
      ["inquiries", "Rental Inquiries", Inbox],
      ["tenants", "Manage Tenants", Users],
      ["rent-records", "Rent Records", CreditCard],
    ],
  },
};

const DASHBOARD_API = "http://localhost:8000/api/dashboard/summary";

const pesoFormatter = new Intl.NumberFormat("en-PH", {
  style: "currency",
  currency: "PHP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function peso(value) {
  if (value === null || value === undefined || value === "") return "—";
  const amount = Number(value);
  return Number.isFinite(amount) && amount >= 0
    ? pesoFormatter.format(amount)
    : "—";
}

function calendarDate(iso) {
  const matched = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!matched) return "—";
  const year = Number(matched[1]);
  const month = Number(matched[2]);
  const day = Number(matched[3]);
  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return "—";
  }
  return new Intl.DateTimeFormat("en-PH", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function ordinal(value) {
  if (!Number.isInteger(value) || value < 1 || value > 31) return "—";
  const suffix = value % 100 >= 11 && value % 100 <= 13
    ? "th"
    : ({ 1: "st", 2: "nd", 3: "rd" }[value % 10] || "th");
  return `${value}${suffix}`;
}

function paymentStatus(value) {
  const names = {
    paid: "Paid",
    pending: "Pending",
    partially_paid: "Partially Paid",
    overdue: "Overdue",
    no_records: "No charges yet",
  };
  return names[value] || "Unavailable";
}

function summaryStats(role, summary, loading) {
  if (!summary) {
    const waiting = loading ? "Loading…" : "Unavailable";
    return Array(4).fill(waiting);
  }

  if (role === "property_owner") {
    return [
      String(summary.total_listings ?? 0),
      String(summary.available_rooms ?? 0),
      String(summary.assigned_rooms ?? 0),
      String(summary.rent_charge_count ?? 0),
    ];
  }

  return [
    summary.current_property_name || "Not assigned",
    peso(summary.monthly_rent),
    summary.next_due_date
      ? calendarDate(summary.next_due_date)
      : summary.payment_status === "no_records"
        ? "No charge yet"
        : "None outstanding",
    paymentStatus(summary.payment_status),
  ];
}

async function requestDashboardSummary(signal) {
  const response = await fetch(DASHBOARD_API, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    mode: "cors",
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error(
        "Your login session has expired. Please sign in again."
      );
    }

    if (response.status === 403) {
      throw new Error(
        "Your account is not authorized to view this dashboard."
      );
    }

    throw new Error(
      `Could not load dashboard data (HTTP ${response.status}).`
    );
  }

  const payload = await response.json();

  if (
    !payload ||
    typeof payload.summary !== "object" ||
    payload.summary === null
  ) {
    throw new Error(
      "The dashboard API returned an unexpected response."
    );
  }

  return payload.summary;
}

const styles = `
.df-home{min-height:100vh;display:flex;background:var(--background);color:var(--text);font-family:Inter,"Segoe UI",sans-serif}
.df-home *{box-sizing:border-box}.df-home button{font:inherit}
.df-side{width:245px;flex:0 0 245px;height:100vh;position:sticky;top:0;display:flex;flex-direction:column;background:var(--card);border-right:1px solid var(--border);padding:27px 14px 20px;z-index:5}
.df-logo{display:flex;gap:12px;align-items:center;font-size:22px;font-weight:850;padding:0 12px 32px}.df-logo svg{color:var(--primary)}
.df-menu{display:grid;gap:5px}.df-nav{display:flex;align-items:center;gap:13px;width:100%;padding:12px 14px;border:0;border-radius:10px;background:transparent;color:var(--muted);text-align:left;font-weight:600;font-size:13px;cursor:pointer}
.df-nav.active{background:var(--soft);color:var(--primary);font-weight:800}.df-nav:hover:not(:disabled){background:var(--soft)}.df-nav:disabled:not(.active){opacity:.55;cursor:not-allowed}
.df-side-bottom{margin-top:auto;border-top:1px solid var(--border);padding-top:12px}
.df-body{min-width:0;flex:1}.df-top{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:78px;padding:15px 30px;background:var(--card);border-bottom:1px solid var(--border)}
.df-top h2{margin:0;font-size:17px}.df-top small,.df-muted{color:var(--muted);font-size:12px}.df-tools{display:flex;align-items:center;gap:12px}
.df-icon{width:39px;height:39px;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);display:grid;place-items:center;cursor:pointer}.df-icon:disabled{opacity:.45;cursor:not-allowed}
.df-user{display:flex;align-items:center;gap:9px;border-left:1px solid var(--border);padding-left:14px}.df-avatar{display:grid;place-items:center;width:37px;height:37px;border-radius:50%;background:var(--soft);color:var(--primary);font-weight:850}.df-user strong{font-size:12px}
.df-content{max-width:1300px;margin:auto;padding:28px 30px 45px}.df-hero{border:1px solid var(--border);border-radius:17px;background:linear-gradient(110deg,var(--hero),var(--card));padding:27px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.df-hero h1{font-size:clamp(22px,3vw,31px);margin:0 0 9px}.df-hero p{color:var(--muted);font-size:13px;margin:0;line-height:1.6}
.df-button{display:inline-flex;align-items:center;justify-content:center;gap:9px;border:1px solid var(--border);padding:12px 15px;border-radius:10px;cursor:pointer;font-weight:750;font-size:13px;background:var(--card);color:var(--text)}
.df-button.primary{background:var(--primary);color:var(--background);border-color:var(--primary)}.df-button:disabled{opacity:.5;cursor:not-allowed}
.df-heading{font-size:17px;margin:28px 0 15px}.df-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.df-card{background:var(--card);border:1px solid var(--border);border-radius:15px;padding:20px;min-width:0}
.df-stat-top{display:flex;align-items:center;justify-content:space-between;gap:10px}.df-stat-top svg{color:var(--primary)}.df-value{font-size:21px;font-weight:850;margin:15px 0 0;overflow-wrap:anywhere}
.df-panels{display:grid;grid-template-columns:1.6fr 1fr;gap:15px;margin-top:15px}.df-card h3{margin:0;font-size:16px}.df-empty{display:grid;place-content:center;text-align:center;min-height:210px;padding:22px;margin-top:16px;background:var(--soft);border:1px dashed var(--border);border-radius:12px;color:var(--muted);font-size:13px;line-height:1.7}
.df-actions{display:grid;gap:10px;margin-top:21px}.df-actions button{justify-content:space-between;width:100%}.df-footnote{padding-top:17px;margin-top:20px;border-top:1px solid var(--border);line-height:1.6}
.df-dashboard-actions{display:flex;align-items:center;gap:10px;justify-content:space-between;flex-wrap:wrap}
.df-inline{display:flex;align-items:center;gap:8px}
.df-reload{padding:8px 12px;min-height:35px;font-size:12px}
.df-notice{display:flex;align-items:flex-start;gap:10px;margin:16px 0 0;padding:12px 14px;border:1px solid var(--border);border-radius:11px;background:var(--soft);font-size:12px;line-height:1.6;color:var(--muted)}
.df-notice svg{flex-shrink:0}
.df-notice.error{color:var(--text)}
.df-summary{display:grid;gap:11px;margin-top:18px}
.df-summary-row{display:flex;align-items:flex-start;justify-content:space-between;gap:13px;border-bottom:1px solid var(--border);padding:0 0 10px;font-size:12px}
.df-summary-row:last-child{border-bottom:0;padding-bottom:0}
.df-summary-row span{color:var(--muted)}.df-summary-row strong{text-align:right;max-width:63%;overflow-wrap:anywhere}
.df-summary-note{margin:16px 0 0;font-size:11px;line-height:1.6;color:var(--muted)}
.df-mobile-menu,.df-overlay{display:none}.df-home button:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
@media(max-width:1100px){.df-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:800px){.df-side{position:fixed;left:0;transform:translateX(-100%);transition:transform .2s}.df-side.open{transform:translateX(0)}.df-overlay.open{display:block;position:fixed;inset:0;z-index:4;border:0;background:#0006}.df-mobile-menu{display:grid}.df-panels{grid-template-columns:1fr}}
@media(max-width:550px){.df-top{padding:13px 16px}.df-content{padding:18px 16px}.df-hero{align-items:stretch;flex-direction:column}.df-user .df-user-name{display:none}.df-card{padding:15px}.df-stats{gap:9px}}
`;

export default function RoleHome({
  account,
  darkMode = false,
  onToggleTheme,
  onNavigate,
  onLogout,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activePage, setActivePage] = useState("home");
  const [summary, setSummary] = useState(null);
  const [loadedFor, setLoadedFor] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const role = account?.role;
  const info = HOME[role];
  const accountKey = String(
    account?.user_id ?? account?.id ?? account?.username ?? ""
  );
  const scopeKey = `${role || ""}:${accountKey}`;
  const name =
    typeof account?.username === "string" && account.username.trim()
      ? account.username.trim()
      : "User";

  useEffect(() => {
    setActivePage("home");
    setMenuOpen(false);
  }, [role]);

  useEffect(() => {
    if (!HOME[role] || activePage !== "home") return undefined;

    const controller = new AbortController();
    setSummaryLoading(true);
    setSummaryError("");
    setSummary(null);
    setLoadedFor("");

    async function load() {
      try {
        const data = await requestDashboardSummary(controller.signal);

        if (data.role !== role) {
          throw new Error(
            "The dashboard response does not match the current account role."
          );
        }

        if (!controller.signal.aborted) {
          setSummary(data);
          setLoadedFor(scopeKey);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setSummaryError(
            error instanceof Error
              ? error.message
              : "Unable to load dashboard data."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setSummaryLoading(false);
        }
      }
    }

    load();

    return () => controller.abort();
  }, [role, scopeKey, activePage, refreshKey]);

  if (!info) {
    return (
      <div role="status">
        This Home page is for renters and property owners.
      </div>
    );
  }

  function isLocalPage(page) {
    return page === "home" ||
      (role === "property_owner" &&
        (page === "my-properties" ||
          page === "inquiries" ||
          page === "tenants" ||
          page === "rent-records")) ||
      (role === "renter" &&
        (page === "discover" ||
          page === "my-inquiries" ||
          page === "my-rental" ||
          page === "rent-payments" ||
          page === "payment-history"));
  }

  function canNavigate(page) {
    return isLocalPage(page) || typeof onNavigate === "function";
  }

  function go(page) {
    if (!canNavigate(page)) return;

    setMenuOpen(false);

    if (isLocalPage(page)) {
      setActivePage(page);
    } else {
      onNavigate(page);
    }
  }

  const pageTitle =
    PAGES[role].find(([page]) => page === activePage)?.[1] || "Home";

  const currentSummary = loadedFor === scopeKey ? summary : null;
  const stats = summaryStats(role, currentSummary, summaryLoading);

  return (
    <div className={`dormora ${darkMode ? "dark-mode" : ""} df-home`}>
      <style>{styles}</style>

      <button
        type="button"
        className={`df-overlay ${menuOpen ? "open" : ""}`}
        aria-label="Close navigation"
        onClick={() => setMenuOpen(false)}
      />

      <aside
        className={`df-side ${menuOpen ? "open" : ""}`}
        aria-label="Dashboard navigation"
      >
        <div className="df-logo">
          <Building2 size={28} /> Dormora
        </div>

        <nav className="df-menu" aria-label={`${info.role} pages`}>
          {PAGES[role].map(([page, label, Icon]) => (
            <button
              key={page}
              type="button"
              className={`df-nav ${page === activePage ? "active" : ""}`}
              aria-current={page === activePage ? "page" : undefined}
              disabled={!canNavigate(page)}
              onClick={() => go(page)}
            >
              <Icon size={18} /> {label}
            </button>
          ))}
        </nav>

        <div className="df-side-bottom">
          <button
            type="button"
            className="df-nav"
            disabled={typeof onNavigate !== "function"}
            onClick={() => go("settings")}
          >
            <Settings size={18} /> Settings
          </button>

          <button
            type="button"
            className="df-nav"
            disabled={typeof onLogout !== "function"}
            onClick={onLogout}
          >
            <LogOut size={18} /> Log Out
          </button>
        </div>
      </aside>

      <div className="df-body">
        <header className="df-top">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              className="df-icon df-mobile-menu"
              type="button"
              aria-label="Toggle navigation"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
            >
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>

            <div>
              <h2>{pageTitle}</h2>
              <small>My Dormora workspace</small>
            </div>
          </div>

          <div className="df-tools">
            <button
              className="df-icon"
              type="button"
              disabled
              aria-label="Notifications coming soon"
            >
              <Bell size={18} />
            </button>

            <button
              className="df-icon"
              type="button"
              disabled={typeof onToggleTheme !== "function"}
              aria-label={darkMode ? "Light mode" : "Dark mode"}
              onClick={onToggleTheme}
            >
              {darkMode ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <div className="df-user">
              <span className="df-avatar" aria-hidden="true">
                {name[0].toUpperCase()}
              </span>
              <div className="df-user-name">
                <strong>{name}</strong>
                <div className="df-muted">{info.role}</div>
              </div>
            </div>
          </div>
        </header>

        <main className="df-content">
          {role === "property_owner" && activePage === "my-properties" ? (
            <MyProperties
              account={account}
              onBack={() => go("home")}
            />
          ) : role === "property_owner" && activePage === "inquiries" ? (
            <OwnerInquiries
              account={account}
              onBack={() => go("home")}
            />
          ) : role === "property_owner" && activePage === "tenants" ? (
            <TenantManagement
              account={account}
              onBack={() => go("home")}
            />
          ) : role === "property_owner" && activePage === "rent-records" ? (
            <RentRecords
              account={account}
              onBack={() => go("home")}
            />
          ) : role === "renter" && activePage === "discover" ? (
            <DormDiscovery
              account={account}
              onBack={() => go("home")}
            />
          ) : role === "renter" && activePage === "my-inquiries" ? (
            <MyInquiries
              account={account}
              onBack={() => go("home")}
            />
          ) : role === "renter" && activePage === "my-rental" ? (
            <MyRental
              account={account}
              onBack={() => go("home")}
            />
          ) : role === "renter" && activePage === "rent-payments" ? (
            <RentPayments
              account={account}
              onBack={() => go("home")}
            />
          ) : role === "renter" && activePage === "payment-history" ? (
            <PaymentHistory
              account={account}
              onBack={() => go("home")}
            />
          ) : (
            <>
              <section className="df-hero">
                <div>
                  <h1>Welcome home, {name}!</h1>
                  <p>{info.intro}</p>
                </div>

                <button
                  className="df-button primary"
                  type="button"
                  disabled={!canNavigate(info.actions[0][0])}
                  onClick={() => go(info.actions[0][0])}
                >
                  {info.actions[0][1]}
                  <ChevronRight size={17} />
                </button>
              </section>

              <div className="df-dashboard-actions">
                <h2 className="df-heading">Overview</h2>
                <button
                  type="button"
                  className="df-button df-reload"
                  disabled={summaryLoading}
                  onClick={() => setRefreshKey((key) => key + 1)}
                >
                  <RefreshCw size={15} /> Refresh data
                </button>
              </div>

              {summaryError && (
                <div className="df-notice error" role="alert">
                  <AlertCircle size={18} />
                  <span>
                    {summaryError} Existing rental pages remain available.
                    Use Refresh data to retry.
                  </span>
                </div>
              )}

              <section className="df-stats" aria-label="Account overview">
                {info.stats.map(([label, Icon], index) => (
                  <div className="df-card" key={label}>
                    <div className="df-stat-top">
                      <span className="df-muted">{label}</span>
                      <Icon size={20} />
                    </div>
                    <p className="df-value" aria-live="polite">
                      {stats[index]}
                    </p>
                  </div>
                ))}
              </section>

              <section className="df-panels" aria-label="Home panels">
                <div className="df-card">
                  <h3>{info.panel}</h3>
                  <p className="df-muted">
                    {role === "renter"
                      ? "Your current room and rent details"
                      : "Your rental portfolio at a glance"}
                  </p>

                  {!currentSummary ? (
                    <div className="df-empty">
                      {summaryLoading
                        ? "Loading your latest records…"
                        : summaryError
                          ? "Summary unavailable. Refresh to try again."
                          : info.empty}
                    </div>
                  ) : role === "renter" && !currentSummary.tenancy_id ? (
                    <div className="df-empty">
                      No active room assigned yet. Browse dorms or review
                      your rental inquiries.
                    </div>
                  ) : role === "renter" ? (
                    <div className="df-summary">
                      <div className="df-summary-row">
                        <span>Property</span>
                        <strong>
                          {currentSummary.current_property_name || "—"}
                        </strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Assigned room</span>
                        <strong>
                          {currentSummary.current_room_label || "—"}
                        </strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Monthly rent</span>
                        <strong>{peso(currentSummary.monthly_rent)}</strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Rent due day</span>
                        <strong>
                          {currentSummary.rent_due_day
                            ? `${ordinal(currentSummary.rent_due_day)} of each month`
                            : "—"}
                        </strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Move-in date</span>
                        <strong>
                          {calendarDate(currentSummary.move_in_date)}
                        </strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Outstanding balance</span>
                        <strong>
                          {peso(currentSummary.outstanding_balance)}
                        </strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Payment status</span>
                        <strong>
                          {paymentStatus(currentSummary.payment_status)}
                        </strong>
                      </div>

                      <button
                        className="df-button"
                        type="button"
                        onClick={() => go("my-rental")}
                      >
                        View My Rental <ChevronRight size={16} />
                      </button>
                    </div>
                  ) : (
                    <div className="df-summary">
                      <div className="df-summary-row">
                        <span>Total rooms</span>
                        <strong>{currentSummary.total_rooms ?? 0}</strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Assigned rooms</span>
                        <strong>{currentSummary.assigned_rooms ?? 0}</strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Active tenants</span>
                        <strong>{currentSummary.active_tenants ?? 0}</strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Rent charges</span>
                        <strong>{currentSummary.rent_charge_count ?? 0}</strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Outstanding rent</span>
                        <strong>
                          {peso(currentSummary.outstanding_balance)}
                        </strong>
                      </div>

                      <div className="df-summary-row">
                        <span>Overdue charges</span>
                        <strong>
                          {currentSummary.overdue_charge_count ?? 0}
                        </strong>
                      </div>

                      <p className="df-summary-note">
                        Assigned rooms include reserved allocations and
                        are not a measure of physical occupancy.
                      </p>

                      <button
                        className="df-button"
                        type="button"
                        onClick={() => go("rent-records")}
                      >
                        View Rent Records <ChevronRight size={16} />
                      </button>
                    </div>
                  )}
                </div>

                <div className="df-card">
                  <h3>Quick Actions</h3>
                  <p className="df-muted">Go to your main features</p>

                  <div className="df-actions">
                    {info.actions.map(([page, label, Icon], index) => (
                      <button
                        key={page}
                        type="button"
                        className={`df-button ${index === 0 ? "primary" : ""}`}
                        disabled={!canNavigate(page)}
                        onClick={() => go(page)}
                      >
                        <span
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 9,
                          }}
                        >
                          <Icon size={18} /> {label}
                        </span>
                        <ChevronRight size={16} />
                      </button>
                    ))}
                  </div>

                  <p className="df-muted df-footnote">
                    <span className="df-inline">
                      <ShieldCheck size={14} />
                      Your dashboard is read-only and restricted to your account.
                    </span>
                    {currentSummary
                      ? " Figures refresh when you return Home or press Refresh data."
                      : ""}
                  </p>
                </div>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
