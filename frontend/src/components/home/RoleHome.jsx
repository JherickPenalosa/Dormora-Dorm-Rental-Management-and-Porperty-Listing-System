/**
 * DORMORA — SYSTEM FUNCTIONALITY, FILE 58
 * REPLACE: frontend/src/components/home/RoleHome.jsx
 *
 * Adds a working renter/owner notification bell using existing authenticated
 * inquiry, private conversation, and rent APIs. Read flags are local to this
 * browser/account, not persisted in PostgreSQL or delivered as push alerts.
 * Preserves File 54 dashboard statistics, all role pages, theme and logout.
 */
import { useEffect, useRef, useState } from "react";
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
const NOTIFY_BASE = "http://localhost:8000";
const MAX_CONVERSATIONS_TO_CHECK = 8;
const MAX_DISPLAY_NOTICES = 40;


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
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return "—";
  }
  return new Intl.DateTimeFormat("en-PH", {
    month: "short", day: "numeric", year: "numeric",
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
      : summary.payment_status === "no_records" ? "No charge yet" : "None outstanding",
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
      throw new Error("Your login session has expired. Please sign in again.");
    }
    if (response.status === 403) {
      throw new Error("Your account is not authorized to view this dashboard.");
    }
    throw new Error(`Could not load dashboard data (HTTP ${response.status}).`);
  }
  const payload = await response.json();
  if (!payload || typeof payload.summary !== "object" || payload.summary === null) {
    throw new Error("The dashboard API returned an unexpected response.");
  }
  return payload.summary;
}


// A read-only, on-demand notice feed assembled from existing authorized APIs.
// It is not a push service or a complete historical event log.
async function notificationJson(path, signal) {
  const response = await fetch(`${NOTIFY_BASE}${path}`, {
    method: "GET",
    credentials: "include",
    mode: "cors",
    cache: "no-store",
    redirect: "error",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error("Your session expired. Sign in again.");
    if (response.status === 403) throw new Error("Notification access denied for this account.");
    throw new Error(`Notification source returned HTTP ${response.status}.`);
  }
  return response.json();
}

function notificationMonth(value) {
  const matched = /^(\d{4})-(\d{2})/.exec(String(value ?? ""));
  if (!matched) return "this month";
  const y = Number(matched[1]);
  const m = Number(matched[2]);
  if (m < 1 || m > 12) return "this month";
  return new Intl.DateTimeFormat("en-PH", { month: "long", year: "numeric" }).format(new Date(y, m - 1, 1));
}

function notificationTimestamp(value) {
  const result = Date.parse(String(value ?? ""));
  return Number.isFinite(result) ? result : 0;
}

function philippinesTodayUtc() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const read = (type) => Number(parts.find((part) => part.type === type)?.value);
  return Date.UTC(read("year"), read("month") - 1, read("day"));
}

function daysUntilDue(value) {
  const matched = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value ?? ""));
  if (!matched) return null;
  const due = Date.UTC(Number(matched[1]), Number(matched[2]) - 1, Number(matched[3]));
  if (!Number.isFinite(due)) return null;
  return Math.round((due - philippinesTodayUtc()) / 86400000);
}

function notificationScopeKey(account) {
  // Only opaque notification IDs are stored, never message text, rent amounts,
  // session IDs, OTPs, passwords, or authentication tokens.
  return `dormora:notification-read:v1:${account?.role || ""}:${encodeURIComponent(account?.username || "")}`;
}

function readLocalNoticeIds(scope) {
  try {
    const value = JSON.parse(window.localStorage.getItem(scope) || "[]");
    return Array.isArray(value) ? value.filter((id) => typeof id === "string").slice(-500) : [];
  } catch {
    return [];
  }
}

async function loadNotificationFeed(role, signal) {
  const inquiryRoute = role === "property_owner" ? "owner" : "mine";
  const rentRoute = role === "property_owner" ? "owner" : "mine";
  const settled = await Promise.allSettled([
    notificationJson(`/api/rental-inquiries/${inquiryRoute}`, signal),
    notificationJson(`/api/rent-records/${rentRoute}`, signal),
  ]);
  if (signal.aborted) return { items: [], warnings: [] };

  const notices = [];
  const warnings = [];
  const [inquiryResult, rentResult] = settled;
  let inquiries = [];
  let charges = [];

  if (inquiryResult.status === "fulfilled" && Array.isArray(inquiryResult.value?.inquiries)) {
    inquiries = inquiryResult.value.inquiries;
  } else {
    warnings.push("Inquiries could not be checked.");
  }
  if (rentResult.status === "fulfilled" && Array.isArray(rentResult.value?.records)) {
    charges = rentResult.value.records;
  } else {
    warnings.push("Rent records could not be checked.");
  }

  for (const inquiry of inquiries) {
    if (!Number.isInteger(inquiry.id) || inquiry.id <= 0) continue;
    const property = inquiry.property_name || `Property #${inquiry.property_id}`;
    const when = notificationTimestamp(inquiry.reviewed_at || inquiry.created_at);

    if (role === "property_owner" && inquiry.status === "pending") {
      notices.push({
        id: `owner-inquiry:${inquiry.id}`, kind: "inquiry", when,
        title: "Rental inquiry awaiting review",
        body: `${inquiry.renter_username || "A renter"} asked about ${property}.`,
        page: "inquiries",
      });
    } else if (role === "renter" && ["accepted", "rejected"].includes(inquiry.status)) {
      notices.push({
        id: `renter-inquiry:${inquiry.id}:${inquiry.status}`, kind: "inquiry", when,
        title: inquiry.status === "accepted" ? "Your rental inquiry was accepted" : "Rental inquiry was declined",
        body: `${property} · View the inquiry for details.`,
        page: "my-inquiries",
      });
    }
  }

  // Check just the most recent eight conversations to avoid unbounded API calls.
  const recent = [...inquiries]
    .filter((item) => Number.isInteger(item.id) && item.id > 0)
    .sort((a, b) => notificationTimestamp(b.created_at) - notificationTimestamp(a.created_at))
    .slice(0, MAX_CONVERSATIONS_TO_CHECK);
  const conversations = await Promise.allSettled(recent.map((item) =>
    notificationJson(`/api/rental-inquiries/${item.id}/messages`, signal)
  ));
  if (signal.aborted) return { items: [], warnings: [] };
  conversations.forEach((result, index) => {
    if (result.status !== "fulfilled" || !Array.isArray(result.value?.messages)) {
      warnings.push(`Conversation #${recent[index].id} could not be checked.`);
      return;
    }
    const incoming = result.value.messages
      .filter((message) => message.kind === "reply" && message.sender_role !== role && Number.isInteger(message.id))
      .sort((a, b) => notificationTimestamp(b.created_at) - notificationTimestamp(a.created_at));
    const latest = incoming[0];
    if (!latest) return;
    notices.push({
      id: `reply:${recent[index].id}:${latest.id}`, kind: "message",
      when: notificationTimestamp(latest.created_at),
      title: role === "renter" ? "Property owner replied to your inquiry" : "Renter replied to an inquiry",
      body: `${recent[index].property_name || `Inquiry #${recent[index].id}`} · Open the conversation to read the reply.`,
      page: role === "renter" ? "my-inquiries" : "inquiries",
    });
  });

  for (const charge of charges) {
    if (!Number.isInteger(charge.charge_id) || charge.charge_id <= 0) continue;
    const balance = Number(charge.balance_due);
    const totalPaid = Number(charge.total_paid);
    const month = notificationMonth(charge.billing_month);
    const room = charge.room_label || "assigned room";
    const days = daysUntilDue(charge.due_date);
    const page = role === "renter" ? "rent-payments" : "rent-records";

    if (Number.isFinite(balance) && balance > 0 && days !== null && days <= 7) {
      const overdue = days < 0 || charge.payment_status === "overdue";
      notices.push({
        id: `rent-due:${charge.charge_id}:${overdue ? "overdue" : "upcoming"}`, kind: "rent",
        when: Date.now(),
        title: overdue ? "Outstanding rent is overdue" : "Upcoming rent balance",
        body: `${charge.property_name || "Rental"} · ${room} · ${month}. ${peso(charge.balance_due)} outstanding, due ${calendarDate(charge.due_date)}.`,
        page,
      });
    }

    if (role === "renter" && Number.isFinite(totalPaid) && totalPaid > 0) {
      notices.push({
        id: `rent-payment:${charge.charge_id}:${String(charge.total_paid)}`, kind: "payment",
        when: notificationTimestamp(charge.created_at),
        title: balance <= 0 ? "Monthly rent recorded as fully paid" : "Rent payment recorded by owner",
        body: `${month} · ${peso(charge.total_paid)} recorded as paid. ${peso(charge.balance_due)} remaining.`,
        page: "payment-history",
      });
    }
  }

  notices.sort((a, b) => b.when - a.when || a.id.localeCompare(b.id));
  return { items: notices.slice(0, MAX_DISPLAY_NOTICES), warnings };
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

/* File 58: Notifications dropdown lives inside the dashboard header. */
.df-notification-wrap{position:relative;display:flex;align-items:center}
.df-notification-trigger{position:relative}
.df-notification-count{position:absolute;right:-6px;top:-7px;min-width:18px;height:18px;padding:0 4px;border-radius:99px;background:#b91c1c;color:white;display:grid;place-items:center;font-size:10px;font-weight:800;pointer-events:none}
.df-notification-panel{position:absolute;right:0;top:calc(100% + 12px);width:min(385px,calc(100vw - 28px));z-index:40;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:15px;box-shadow:0 12px 30px #0002;overflow:hidden}
.df-notification-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:15px 16px;border-bottom:1px solid var(--border)}
.df-notification-head strong{font-size:15px}.df-notification-head small{font-size:11px;color:var(--muted)}
.df-notification-tools{display:flex;gap:5px}
.df-notification-mini{border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:8px;padding:6px 9px;cursor:pointer;font-size:11px;font-weight:700}
.df-notification-mini:disabled{opacity:.45;cursor:not-allowed}
.df-notification-list{max-height:min(55vh,470px);overflow:auto;overscroll-behavior:contain}
.df-notification-item{border:0;border-bottom:1px solid var(--border);background:transparent;color:var(--text);display:block;text-align:left;width:100%;padding:13px 16px;cursor:pointer}
.df-notification-item:hover{background:var(--soft)}.df-notification-item.unread{background:var(--soft)}
.df-notification-item-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;font-size:12px;font-weight:800}
.df-notification-dot{height:8px;width:8px;background:var(--primary);border-radius:50%;flex-shrink:0;margin-top:4px}
.df-notification-item p{font-size:11px;line-height:1.6;color:var(--muted);margin:5px 0 0}
.df-notification-empty{padding:25px 17px;font-size:12px;color:var(--muted);line-height:1.7;text-align:center}
.df-notification-foot{padding:10px 16px;border-top:1px solid var(--border);font-size:10px;line-height:1.5;color:var(--muted)}
.df-notification-alert{padding:9px 16px;background:var(--soft);font-size:11px;line-height:1.5;color:var(--muted)}
@media print{.df-notification-wrap{display:none!important}}
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
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [noticeItems, setNoticeItems] = useState([]);
  const [noticeScope, setNoticeScope] = useState("");
  const [noticeLoading, setNoticeLoading] = useState(false);
  const [noticeWarnings, setNoticeWarnings] = useState([]);
  const [noticeRefresh, setNoticeRefresh] = useState(0);
  const [readIds, setReadIds] = useState([]);
  const [readScope, setReadScope] = useState("");
  const noticeWrapRef = useRef(null);

  const role = account?.role;
  const info = HOME[role];
  const accountKey = String(account?.user_id ?? account?.id ?? account?.username ?? "");
  const scopeKey = `${role || ""}:${accountKey}`;
  const name = typeof account?.username === "string" && account.username.trim()
    ? account.username.trim()
    : "User";

  useEffect(() => {
    setActivePage("home");
    setMenuOpen(false);
  }, [role]);
  // Account-scoped read state. Local-only preference, not an authorization check.
  useEffect(() => {
    setNoticeOpen(false);
    setReadScope(scopeKey);
    setReadIds(readLocalNoticeIds(notificationScopeKey(account)));
    setNoticeItems([]);
    setNoticeScope("");
    setNoticeWarnings([]);
  }, [scopeKey]);

  useEffect(() => {
    if (readScope !== scopeKey) return;
    try {
      window.localStorage.setItem(notificationScopeKey(account), JSON.stringify(readIds.slice(-500)));
    } catch {
      // The bell still works if private browsing blocks local storage.
    }
  }, [readIds, readScope, scopeKey]);

  useEffect(() => {
    if (!HOME[role]) return undefined;
    const controller = new AbortController();
    setNoticeLoading(true);
    setNoticeWarnings([]);

    loadNotificationFeed(role, controller.signal)
      .then(({ items, warnings }) => {
        if (controller.signal.aborted) return;
        setNoticeItems(items);
        setNoticeWarnings(warnings);
        setNoticeScope(scopeKey);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setNoticeWarnings(["Notifications are temporarily unavailable. Refresh to retry."]);
        setNoticeItems([]);
        setNoticeScope(scopeKey);
      })
      .finally(() => {
        if (!controller.signal.aborted) setNoticeLoading(false);
      });

    return () => controller.abort();
  }, [role, scopeKey, noticeRefresh]);

  useEffect(() => {
    if (!noticeOpen) return undefined;
    const onPointerDown = (event) => {
      if (!noticeWrapRef.current?.contains(event.target)) setNoticeOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setNoticeOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [noticeOpen]);


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
          throw new Error("The dashboard response does not match the current account role.");
        }
        if (!controller.signal.aborted) {
          setSummary(data);
          setLoadedFor(scopeKey);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setSummaryError(error instanceof Error ? error.message : "Unable to load dashboard data.");
        }
      } finally {
        if (!controller.signal.aborted) setSummaryLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [role, scopeKey, activePage, refreshKey]);

  if (!info) {
    return <div role="status">This Home page is for renters and property owners.</div>;
  }

  function isLocalPage(page) {
    return page === "home" ||
      (role === "property_owner" && (page === "my-properties" || page === "inquiries" || page === "tenants" || page === "rent-records")) ||
      (role === "renter" && (page === "discover" || page === "my-inquiries" || page === "my-rental" || page === "rent-payments" || page === "payment-history"));
  }

  function canNavigate(page) {
    return isLocalPage(page) || typeof onNavigate === "function";
  }

  function go(page) {
    if (!canNavigate(page)) return;
    setMenuOpen(false);
    setNoticeOpen(false);
    if (isLocalPage(page)) {
      setActivePage(page);
      if (page === "home") setNoticeRefresh((value) => value + 1);
    } else {
      onNavigate(page);
    }
  }

  const visibleNotices = noticeScope === scopeKey ? noticeItems : [];
  const validReadIds = readScope === scopeKey ? readIds : [];
  const readSet = new Set(validReadIds);
  const unreadCount = visibleNotices.filter((item) => !readSet.has(item.id)).length;

  function markNoticesRead(ids) {
    if (!ids.length) return;
    setReadIds((current) => Array.from(new Set([...current, ...ids])).slice(-500));
  }

  function openNotification(item) {
    markNoticesRead([item.id]);
    setNoticeOpen(false);
    go(item.page);
  }

  const pageTitle = PAGES[role].find(([page]) => page === activePage)?.[1] || "Home";
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
      <aside className={`df-side ${menuOpen ? "open" : ""}`} aria-label="Dashboard navigation">
        <div className="df-logo"><House size={29} strokeWidth={2.5} /> Dormora</div>
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
            <div><h2>{pageTitle}</h2><small>My Dormora workspace</small></div>
          </div>
          <div className="df-tools">
            <div className="df-notification-wrap" ref={noticeWrapRef}>
              <button
                className="df-icon df-notification-trigger"
                type="button"
                aria-label={`Notifications${unreadCount ? ` (${unreadCount} unread)` : ""}`}
                aria-expanded={noticeOpen}
                aria-controls="dormora-notifications-panel"
                onClick={() => {
                  setNoticeOpen((opened) => !opened);
                  if (!noticeOpen) setNoticeRefresh((value) => value + 1);
                }}
              >
                <Bell size={18} />
                {unreadCount > 0 && <span className="df-notification-count">{unreadCount > 99 ? "99+" : unreadCount}</span>}
              </button>

              {noticeOpen && (
                <div className="df-notification-panel" id="dormora-notifications-panel" role="region" aria-label="Notifications">
                  <div className="df-notification-head">
                    <div>
                      <strong>Notifications</strong>
                      <div><small>{unreadCount} unread · {visibleNotices.length} updates</small></div>
                    </div>
                    <div className="df-notification-tools">
                      <button
                        type="button"
                        className="df-notification-mini"
                        disabled={noticeLoading}
                        title="Refresh notifications"
                        onClick={() => setNoticeRefresh((value) => value + 1)}
                      >
                        <RefreshCw size={13} />
                      </button>
                      <button
                        type="button"
                        className="df-notification-mini"
                        disabled={unreadCount === 0}
                        onClick={() => markNoticesRead(visibleNotices.map((item) => item.id))}
                      >
                        Mark all read
                      </button>
                    </div>
                  </div>
                  {noticeWarnings.length > 0 && (
                    <div className="df-notification-alert" role="status">{noticeWarnings[0]}{noticeWarnings.length > 1 ? " Some updates may be missing." : ""}</div>
                  )}
                  <div className="df-notification-list">
                    {noticeLoading && visibleNotices.length === 0 ? (
                      <div className="df-notification-empty">Checking your rental updates…</div>
                    ) : visibleNotices.length === 0 ? (
                      <div className="df-notification-empty">No updates available right now. Use Refresh to check again.</div>
                    ) : visibleNotices.map((item) => (
                      <button
                        key={item.id}
                        className={`df-notification-item ${!readSet.has(item.id) ? "unread" : ""}`}
                        type="button"
                        onClick={() => openNotification(item)}
                      >
                        <span className="df-notification-item-head">
                          <span>{item.title}</span>
                          {!readSet.has(item.id) && <span className="df-notification-dot" aria-label="Unread" />}
                        </span>
                        <p>{item.body}</p>
                      </button>
                    ))}
                  </div>
                  <div className="df-notification-foot">
                    From your existing inquiry and rent records, plus replies in up to 8 recent conversations. Updates are checked when the bell opens or you refresh, not pushed live. Read status is saved only in this browser.
                  </div>
                </div>
              )}
            </div>
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
              <span className="df-avatar" aria-hidden="true">{name[0].toUpperCase()}</span>
              <div className="df-user-name">
                <strong>{name}</strong>
                <div className="df-muted">{info.role}</div>
              </div>
            </div>
          </div>
        </header>

        <main className="df-content">
          {role === "property_owner" && activePage === "my-properties" ? (
            <MyProperties account={account} onBack={() => go("home")} />
          ) : role === "property_owner" && activePage === "inquiries" ? (
            <OwnerInquiries account={account} onBack={() => go("home")} />
          ) : role === "property_owner" && activePage === "tenants" ? (
            <TenantManagement account={account} onBack={() => go("home")} />
          ) : role === "property_owner" && activePage === "rent-records" ? (
            <RentRecords account={account} onBack={() => go("home")} />
          ) : role === "renter" && activePage === "discover" ? (
            <DormDiscovery account={account} onBack={() => go("home")} />
          ) : role === "renter" && activePage === "my-inquiries" ? (
            <MyInquiries account={account} onBack={() => go("home")} />
          ) : role === "renter" && activePage === "my-rental" ? (
            <MyRental account={account} onBack={() => go("home")} />
          ) : role === "renter" && activePage === "rent-payments" ? (
            <RentPayments account={account} onBack={() => go("home")} />
          ) : role === "renter" && activePage === "payment-history" ? (
            <PaymentHistory account={account} onBack={() => go("home")} />
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
                  {info.actions[0][1]} <ChevronRight size={17} />
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
                  <span>{summaryError} Existing rental pages remain available. Use Refresh data to retry.</span>
                </div>
              )}
              <section className="df-stats" aria-label="Account overview">
                {info.stats.map(([label, Icon], index) => (
                  <div className="df-card" key={label}>
                    <div className="df-stat-top">
                      <span className="df-muted">{label}</span><Icon size={20} />
                    </div>
                    <p className="df-value" aria-live="polite">{stats[index]}</p>
                  </div>
                ))}
              </section>

              <section className="df-panels" aria-label="Home panels">
                <div className="df-card">
                  <h3>{info.panel}</h3>
                  <p className="df-muted">
                    {role === "renter" ? "Your current room and rent details" : "Your rental portfolio at a glance"}
                  </p>
                  {!currentSummary ? (
                    <div className="df-empty">
                      {summaryLoading ? "Loading your latest records…" : summaryError ? "Summary unavailable. Refresh to try again." : info.empty}
                    </div>
                  ) : role === "renter" && !currentSummary.tenancy_id ? (
                    <div className="df-empty">
                      No active room assigned yet. Browse dorms or review your rental inquiries.
                    </div>
                  ) : role === "renter" ? (
                    <div className="df-summary">
                      <div className="df-summary-row"><span>Property</span><strong>{currentSummary.current_property_name || "—"}</strong></div>
                      <div className="df-summary-row"><span>Assigned room</span><strong>{currentSummary.current_room_label || "—"}</strong></div>
                      <div className="df-summary-row"><span>Monthly rent</span><strong>{peso(currentSummary.monthly_rent)}</strong></div>
                      <div className="df-summary-row"><span>Rent due day</span><strong>{currentSummary.rent_due_day ? `${ordinal(currentSummary.rent_due_day)} of each month` : "—"}</strong></div>
                      <div className="df-summary-row"><span>Move-in date</span><strong>{calendarDate(currentSummary.move_in_date)}</strong></div>
                      <div className="df-summary-row"><span>Outstanding balance</span><strong>{peso(currentSummary.outstanding_balance)}</strong></div>
                      <div className="df-summary-row"><span>Payment status</span><strong>{paymentStatus(currentSummary.payment_status)}</strong></div>
                      <button className="df-button" type="button" onClick={() => go("my-rental")}>View My Rental <ChevronRight size={16} /></button>
                    </div>
                  ) : (
                    <div className="df-summary">
                      <div className="df-summary-row"><span>Total rooms</span><strong>{currentSummary.total_rooms ?? 0}</strong></div>
                      <div className="df-summary-row"><span>Assigned rooms</span><strong>{currentSummary.assigned_rooms ?? 0}</strong></div>
                      <div className="df-summary-row"><span>Active tenants</span><strong>{currentSummary.active_tenants ?? 0}</strong></div>
                      <div className="df-summary-row"><span>Rent charges</span><strong>{currentSummary.rent_charge_count ?? 0}</strong></div>
                      <div className="df-summary-row"><span>Outstanding rent</span><strong>{peso(currentSummary.outstanding_balance)}</strong></div>
                      <div className="df-summary-row"><span>Overdue charges</span><strong>{currentSummary.overdue_charge_count ?? 0}</strong></div>
                      <p className="df-summary-note">Assigned rooms include reserved allocations and are not a measure of physical occupancy.</p>
                      <button className="df-button" type="button" onClick={() => go("rent-records")}>View Rent Records <ChevronRight size={16} /></button>
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
                        <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
                          <Icon size={18} /> {label}
                        </span>
                        <ChevronRight size={16} />
                      </button>
                    ))}
                  </div>
                  <p className="df-muted df-footnote">
                    <span className="df-inline"><ShieldCheck size={14} /> Your dashboard is read-only and restricted to your account.</span>
                    {currentSummary ? " Figures refresh when you return Home or press Refresh data." : ""}
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
