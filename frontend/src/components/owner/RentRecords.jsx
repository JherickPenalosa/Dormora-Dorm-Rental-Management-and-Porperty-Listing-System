/**
 * DORMORA — SYSTEM FUNCTIONALITY FILE 46
 * CREATE: frontend/src/components/owner/RentRecords.jsx
 *
 * Owner-only rent ledger, monthly charge creation, payment recording,
 * and individual charge payment history.
 *
 * Backend: File 44 /api/rent-records and File 36 /api/tenancies/owner.
 * Security: session cookies; GET /api/csrf + X-CSRF-Token for POST.
 * No online transactions or automatic monthly billing take place here.
 * File 47 will connect this page to RoleHome.jsx.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, Banknote, Building2, CalendarDays, CheckCircle2,
  ChevronDown, ChevronUp, CircleAlert, ClipboardList, Clock3,
  CreditCard, History, Plus, Receipt, RefreshCw, Search, ShieldCheck,
  Wallet,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const RENT_PATH = "/api/rent-records";
const STATUS_LABELS = {
  pending: "Pending",
  partially_paid: "Partially Paid",
  paid: "Paid",
  overdue: "Overdue",
};
const METHOD_LABELS = {
  cash: "Cash",
  bank_transfer: "Bank transfer",
  e_wallet: "E-wallet",
  other: "Other",
};

const styles = `
.rr-page{color:var(--text);width:100%;min-width:0;font-family:inherit}
.rr-page *{box-sizing:border-box}
.rr-header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin:0 0 22px}
.rr-header h1{margin:0 0 8px;font-size:clamp(25px,3vw,32px);font-weight:850}
.rr-muted,.rr-header p{font-size:13px;line-height:1.65;color:var(--muted);margin:0}
.rr-actions{display:flex;flex-wrap:wrap;align-items:center;gap:9px}
.rr-btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:41px;padding:10px 14px;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);font:inherit;font-size:13px;font-weight:750;cursor:pointer}
.rr-btn.primary{background:var(--primary);color:var(--background);border-color:var(--primary)}
.rr-btn:hover:not(:disabled){filter:brightness(.97)}.rr-btn:disabled{opacity:.5;cursor:not-allowed}
.rr-page button:focus-visible,.rr-page input:focus-visible,.rr-page select:focus-visible,.rr-page textarea:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.rr-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:19px}
.rr-stat{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:17px;min-width:0}
.rr-stat-heading{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}
.rr-stat-heading svg{color:var(--primary)}
.rr-stat strong{display:block;margin-top:11px;font-size:clamp(18px,2.2vw,25px);font-weight:850;overflow-wrap:anywhere}
.rr-panel{border:1px solid var(--border);border-radius:15px;background:var(--card);padding:21px;margin-bottom:18px;min-width:0}
.rr-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:17px}
.rr-panel-head h2{font-size:18px;margin:0;display:flex;align-items:center;gap:9px}
.rr-panel-head h2 svg{color:var(--primary)}
.rr-panel-head p{margin:6px 0 0;color:var(--muted);font-size:12px;line-height:1.6}
.rr-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}
.rr-field{display:grid;gap:7px;min-width:0}
.rr-field.wide{grid-column:1/-1}
.rr-field label{font-size:12px;font-weight:750}
.rr-field input,.rr-field select,.rr-search input,.rr-filter{width:100%;min-width:0;padding:12px;border:1px solid var(--border);border-radius:10px;background:var(--background);color:var(--text);font:inherit;font-size:13px}
.rr-field small{font-size:11px;line-height:1.5;color:var(--muted)}
.rr-field input:disabled,.rr-field select:disabled{opacity:.58}
.rr-form-end{grid-column:1/-1;display:flex;gap:13px;align-items:center;justify-content:space-between;flex-wrap:wrap;padding-top:15px;border-top:1px solid var(--border)}
.rr-note{padding:13px 14px;border:1px solid var(--border);border-radius:11px;background:var(--soft);font-size:12px;line-height:1.65;color:var(--muted)}
.rr-note svg{vertical-align:middle;margin-right:7px;color:var(--primary)}
.rr-notice{display:flex;align-items:flex-start;gap:9px;padding:13px 15px;margin:0 0 17px;border:1px solid var(--border);border-radius:11px;background:var(--soft);font-size:13px;line-height:1.6}
.rr-notice svg{flex-shrink:0;margin-top:2px;color:var(--primary)}
.rr-notice.error{border-style:dashed}
.rr-state{padding:33px 24px;min-height:165px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;text-align:center;border:1px dashed var(--border);border-radius:12px}
.rr-state svg{color:var(--primary)}.rr-state h3{font-size:16px;margin:0}
.rr-state p{margin:0;max-width:560px;color:var(--muted);font-size:12px;line-height:1.7}
.rr-toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:15px}
.rr-search{display:flex;align-items:center;gap:8px;padding:0 12px;flex:1;min-width:210px;background:var(--background);color:var(--muted);border:1px solid var(--border);border-radius:10px}
.rr-search input{padding:12px 0;border:0;outline:0;background:transparent}
.rr-filter{width:auto;max-width:100%}
.rr-list{display:grid;gap:12px}
.rr-entry{padding:17px;background:var(--background);border:1px solid var(--border);border-radius:12px;min-width:0}
.rr-entry-top{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;margin-bottom:13px}
.rr-entry h3{font-size:16px;margin:0 0 6px;overflow-wrap:anywhere}
.rr-entry-sub{color:var(--muted);font-size:12px;line-height:1.6;overflow-wrap:anywhere}
.rr-pill{display:inline-flex;gap:6px;align-items:center;background:var(--soft);color:var(--primary);padding:7px 10px;border-radius:8px;font-size:11px;font-weight:850;white-space:nowrap}
.rr-pill.overdue{color:#b45309}.rr-pill.paid{color:var(--primary)}.rr-pill.pending{color:var(--muted)}
.rr-values{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;border-top:1px solid var(--border);padding-top:13px}
.rr-value-label{color:var(--muted);font-size:11px;margin-bottom:5px}
.rr-value-amount{font-size:13px;font-weight:780;overflow-wrap:anywhere}
.rr-entry-actions{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:14px}
.rr-history{margin-top:14px;border-top:1px solid var(--border);padding-top:14px}
.rr-history-list{display:grid;gap:8px;margin-top:10px}
.rr-history-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:11px 12px;border:1px solid var(--border);border-radius:9px}
.rr-history-row strong{font-size:13px}.rr-history-row p{margin:4px 0 0;font-size:12px;color:var(--muted);line-height:1.55;overflow-wrap:anywhere}
.rr-confirm{grid-column:1/-1;padding:15px;border:1px solid var(--border);background:var(--soft);border-radius:11px}
.rr-confirm strong{font-size:13px}.rr-confirm p{font-size:12px;line-height:1.65;color:var(--muted);margin:8px 0 12px}
@media(max-width:1080px){.rr-summary,.rr-values{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:650px){.rr-summary,.rr-values,.rr-form{grid-template-columns:1fr}.rr-panel{padding:16px}.rr-toolbar{flex-direction:column;align-items:stretch}.rr-search,.rr-filter{width:100%}.rr-header{flex-direction:column}.rr-form-end{align-items:stretch}}
`;

async function requestJSON(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    mode: "cors",
    credentials: "include",
    cache: "no-store",
    redirect: "error",
    ...options,
  });
  let data = null;
  try { data = await response.json(); } catch { /* Never display raw HTML errors. */ }
  return { response, data };
}

function apiError(response, data, fallback) {
  if (response.status === 401) return "Your session expired. Please sign in again.";
  if (response.status === 403) return "Access denied. Check your owner session and CSRF token.";
  if (response.status === 404) return "This tenancy or rent record is unavailable.";
  if (response.status === 409) return typeof data?.detail === "string" ? data.detail : "This record has changed. Refresh before continuing.";
  if (response.status === 422) return "Invalid details. Please review your form.";
  if (response.status === 429) return "Too many requests. Please try again later.";
  if (response.status < 500 && typeof data?.detail === "string") return data.detail;
  return fallback;
}

function toCents(value) {
  const raw = String(value ?? "").trim();
  if (!/^[0-9]{1,10}(?:\.[0-9]{1,2})?$/.test(raw)) return null;
  const [whole, decimal = ""] = raw.split(".");
  const cents = Number(whole) * 100 + Number(decimal.padEnd(2, "0"));
  return Number.isSafeInteger(cents) ? cents : null;
}

function peso(value) {
  const cents = toCents(value);
  if (cents === null) return "—";
  return new Intl.NumberFormat("en-PH", {
    style: "currency", currency: "PHP", minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(cents / 100);
}

function phToday() {
  const pieces = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const get = (type) => pieces.find((piece) => piece.type === type)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function displayDate(value) {
  if (!value) return "—";
  const matched = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!matched) return "—";
  const date = new Date(Number(matched[1]), Number(matched[2]) - 1, Number(matched[3]));
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-PH", {
    month: "short", day: "numeric", year: "numeric",
  }).format(date);
}

function displayMonth(value) {
  const matched = String(value || "").match(/^(\d{4})-(\d{2})/);
  if (!matched) return "Unknown month";
  const date = new Date(Number(matched[1]), Number(matched[2]) - 1, 1);
  return new Intl.DateTimeFormat("en-PH", { month: "long", year: "numeric" }).format(date);
}

function StatusPill({ status: current }) {
  const Icon = current === "paid" ? CheckCircle2 : current === "overdue" ? CircleAlert : Clock3;
  return <span className={`rr-pill ${current || "pending"}`}><Icon size={13} />{STATUS_LABELS[current] || "Pending"}</span>;
}

function Empty({ icon: Icon = ClipboardList, heading, detail, children }) {
  return <div className="rr-state"><Icon size={29}/><h3>{heading}</h3><p>{detail}</p>{children}</div>;
}

export default function RentRecords({ account, onBack }) {
  const isOwner = account?.role === "property_owner";
  const busyRef = useRef(false);
  const [tenancies, setTenancies] = useState([]);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState(null);
  const [revision, setRevision] = useState(0);
  const [uncertain, setUncertain] = useState(false);
  const [verifiedRefresh, setVerifiedRefresh] = useState(false);
  const [savingCharge, setSavingCharge] = useState(false);
  const [savingPayment, setSavingPayment] = useState(false);
  const [tenancyId, setTenancyId] = useState("");
  const [billingMonth, setBillingMonth] = useState(phToday().slice(0, 7));
  const [chargeId, setChargeId] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [paidOn, setPaidOn] = useState(phToday());
  const [note, setNote] = useState("");
  const [confirmPayment, setConfirmPayment] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [openedHistory, setOpenedHistory] = useState(null);
  const [historyState, setHistoryState] = useState({ loading: false, rows: [], error: "" });
  const [historyRevision, setHistoryRevision] = useState(0);

  const activeTenancies = useMemo(
    () => tenancies.filter((item) => item.status === "active"),
    [tenancies]
  );
  const selectedTenancy = activeTenancies.find((item) => String(item.id) === tenancyId) || null;
  const outstanding = useMemo(
    () => records.filter((item) => (toCents(item.balance_due) ?? 0) > 0),
    [records]
  );
  const selectedCharge = outstanding.find((item) => String(item.charge_id) === chargeId) || null;

  useEffect(() => {
    if (!isOwner) {
      setLoading(false);
      setTenancies([]);
      setRecords([]);
      return undefined;
    }
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setLoadError("");
      try {
        const [tenanciesResponse, ledgerResponse] = await Promise.all([
          requestJSON("/api/tenancies/owner", { signal: controller.signal }),
          requestJSON(`${RENT_PATH}/owner`, { signal: controller.signal }),
        ]);
        if (!tenanciesResponse.response.ok) {
          throw new Error(apiError(tenanciesResponse.response, tenanciesResponse.data, "Unable to load tenant assignments."));
        }
        if (!ledgerResponse.response.ok) {
          throw new Error(apiError(ledgerResponse.response, ledgerResponse.data, "Unable to load rent records."));
        }
        if (!Array.isArray(tenanciesResponse.data?.tenancies) || !Array.isArray(ledgerResponse.data?.records)) {
          throw new Error("Unexpected rent data returned by the backend.");
        }
        if (controller.signal.aborted) return;
        const nextTenancies = tenanciesResponse.data.tenancies;
        const nextRecords = ledgerResponse.data.records;
        setTenancies(nextTenancies);
        setRecords(nextRecords);
        const available = nextTenancies.filter((item) => item.status === "active");
        setTenancyId((previous) => {
          if (available.some((item) => String(item.id) === previous)) return previous;
          return available.length ? String(available[0].id) : "";
        });
        setChargeId((previous) => {
          if (nextRecords.some((row) => String(row.charge_id) === previous && (toCents(row.balance_due) ?? 0) > 0)) return previous;
          return "";
        });
        if (uncertain) setVerifiedRefresh(true);
      } catch (error) {
        if (!controller.signal.aborted) setLoadError(error?.message || "Could not reach the Dormora backend.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [isOwner, revision]); // Only explicit refreshes reload the ledger.

  // Keep a newly selected billing month on or after the move-in month.
  useEffect(() => {
    if (!selectedTenancy) return;
    const startMonth = String(selectedTenancy.move_in_date || "").slice(0, 7);
    const defaultMonth = startMonth > phToday().slice(0, 7)
      ? startMonth : phToday().slice(0, 7);
    setBillingMonth((previous) => previous && previous >= startMonth ? previous : defaultMonth);
  }, [selectedTenancy?.id, selectedTenancy?.move_in_date]);

  useEffect(() => {
    if (!isOwner || openedHistory === null) return undefined;
    const controller = new AbortController();
    async function loadHistory() {
      setHistoryState({ loading: true, rows: [], error: "" });
      try {
        const { response, data } = await requestJSON(
          `${RENT_PATH}/charges/${openedHistory}/payments`,
          { signal: controller.signal }
        );
        if (!response.ok) throw new Error(apiError(response, data, "Unable to load payment history."));
        if (!Array.isArray(data?.payments)) throw new Error("Invalid payment history returned.");
        if (!controller.signal.aborted) setHistoryState({ loading: false, rows: data.payments, error: "" });
      } catch (error) {
        if (!controller.signal.aborted) setHistoryState({ loading: false, rows: [], error: error?.message || "Unable to load payments." });
      }
    }
    loadHistory();
    return () => controller.abort();
  }, [isOwner, openedHistory, historyRevision]);

  const visibleRecords = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return records.filter((item) => {
      if (statusFilter !== "all" && item.payment_status !== statusFilter) return false;
      return !needle || [
        item.property_name, item.renter_username, item.room_label,
        item.billing_month, String(item.charge_id),
      ].some((value) => String(value ?? "").toLowerCase().includes(needle));
    });
  }, [records, search, statusFilter]);

  const totals = useMemo(() => {
    return records.reduce((acc, item) => {
      acc.due += toCents(item.amount_due) || 0;
      acc.paid += toCents(item.total_paid) || 0;
      acc.balance += toCents(item.balance_due) || 0;
      if (item.payment_status === "overdue") acc.overdue += 1;
      return acc;
    }, { due: 0, paid: 0, balance: 0, overdue: 0 });
  }, [records]);

  function refresh() { setRevision((n) => n + 1); }

  async function securePost(path, payload, markDispatched) {
    const csrf = await requestJSON("/api/csrf");
    if (!csrf.response.ok || typeof csrf.data?.csrf_token !== "string" || !csrf.data.csrf_token) {
      throw new Error(apiError(csrf.response, csrf.data, "Unable to obtain a signed CSRF token."));
    }
    markDispatched();
    return requestJSON(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf.data.csrf_token },
      body: JSON.stringify(payload),
    });
  }

  async function createCharge(event) {
    event.preventDefault();
    if (!isOwner || busyRef.current || loading || loadError || uncertain || !selectedTenancy) return;
    const month = billingMonth.trim();
    if (!/^\d{4}-\d{2}$/.test(month)) {
      setNotice({ error: true, text: "Choose a valid billing month." }); return;
    }
    if (month < String(selectedTenancy.move_in_date || "").slice(0, 7)) {
      setNotice({ error: true, text: "The billing month cannot be before the renter's move-in month." }); return;
    }
    if (records.some((row) => Number(row.tenancy_id) === selectedTenancy.id && String(row.billing_month).startsWith(month))) {
      setNotice({ error: true, text: "This tenancy already has a rent charge for that month." }); return;
    }
    busyRef.current = true;
    setSavingCharge(true);
    setNotice(null);
    let dispatched = false;
    try {
      const { response, data } = await securePost(`${RENT_PATH}/charges`, {
        tenancy_id: selectedTenancy.id,
        billing_month: month,
      }, () => { dispatched = true; });
      if (!response.ok) {
        setNotice({ error: true, text: apiError(response, data, "Could not create the monthly charge.") });
        if ([404, 409].includes(response.status)) refresh();
        return;
      }
      setNotice({ error: false, text: `Monthly rent charge #${data?.charge?.id ?? ""} created. No payment was recorded.` });
      refresh();
    } catch (error) {
      if (dispatched) {
        setUncertain(true);
        setVerifiedRefresh(false);
        setNotice({ error: true, text: "The connection ended after the charge request was sent. It may have been created. Refresh the ledger and verify the month before doing anything else." });
      } else {
        setNotice({ error: true, text: error?.message || "Could not prepare the secure request." });
      }
    } finally {
      busyRef.current = false;
      setSavingCharge(false);
    }
  }

  async function recordPayment(event) {
    event.preventDefault();
    if (!isOwner || busyRef.current || loading || loadError || uncertain || !selectedCharge) return;
    const cents = toCents(amount);
    const remaining = toCents(selectedCharge.balance_due);
    if (cents === null || cents <= 0 || remaining === null || cents > remaining) {
      setNotice({ error: true, text: `Enter a positive payment amount no greater than the remaining balance (${peso(selectedCharge.balance_due)}).` });
      setConfirmPayment(false);
      return;
    }
    if (paidOn && paidOn > phToday()) {
      setNotice({ error: true, text: "The payment date cannot be in the future." });
      setConfirmPayment(false);
      return;
    }
    if (note.trim().length > 200) {
      setNotice({ error: true, text: "Payment note must not exceed 200 characters." });
      setConfirmPayment(false);
      return;
    }
    if (!confirmPayment) {
      setConfirmPayment(true);
      return;
    }
    busyRef.current = true;
    setSavingPayment(true);
    setNotice(null);
    let dispatched = false;
    try {
      const { response, data } = await securePost(`${RENT_PATH}/payments`, {
        charge_id: selectedCharge.charge_id,
        amount: amount.trim(),
        payment_method: method,
        paid_on: paidOn || null,
        reference_note: note.trim() || null,
      }, () => { dispatched = true; });
      if (!response.ok) {
        setNotice({ error: true, text: apiError(response, data, "Could not record the payment.") });
        setConfirmPayment(false);
        if ([404, 409].includes(response.status)) refresh();
        return;
      }
      setNotice({ error: false, text: `Payment #${data?.payment?.id ?? ""} recorded. This is a manual record of money received, not an online transaction.` });
      setConfirmPayment(false);
      setAmount("");
      setNote("");
      setOpenedHistory(selectedCharge.charge_id);
      setHistoryRevision((n) => n + 1);
      refresh();
    } catch (error) {
      setConfirmPayment(false);
      if (dispatched) {
        setUncertain(true);
        setVerifiedRefresh(false);
        setOpenedHistory(selectedCharge.charge_id);
        setHistoryRevision((n) => n + 1);
        setNotice({ error: true, text: "Connection failed after sending the payment. It may have been recorded. Refresh the rent ledger AND check this charge's Payment History before attempting another payment." });
      } else {
        setNotice({ error: true, text: error?.message || "Could not prepare the secure request." });
      }
    } finally {
      busyRef.current = false;
      setSavingPayment(false);
    }
  }

  if (!isOwner) return <section className="rr-page"><style>{styles}</style>
    <Empty icon={ShieldCheck} heading="Property owner access required" detail="Rent Records is available only to property owner accounts." />
  </section>;

  return <section className="rr-page">
    <style>{styles}</style>
    <header className="rr-header">
      <div><h1>Rent Records</h1><p>Create monthly rent charges and record payments received from tenants.</p></div>
      <div className="rr-actions">
        {typeof onBack === "function" && <button className="rr-btn" type="button" onClick={onBack}><ArrowLeft size={16}/> Home</button>}
        <button className="rr-btn" type="button" disabled={loading || savingCharge || savingPayment} onClick={refresh}>
          <RefreshCw size={16}/> Refresh
        </button>
      </div>
    </header>

    {notice && <div className={`rr-notice ${notice.error ? "error" : ""}`} role={notice.error ? "alert" : "status"}>
      {notice.error ? <CircleAlert size={18}/> : <CheckCircle2 size={18}/>}<span>{notice.text}</span>
    </div>}

    {uncertain && <div className="rr-notice error" role="alert">
      <CircleAlert size={18}/><div>
        <strong>Action needs verification.</strong>
        <p className="rr-muted" style={{marginTop:5}}>Refresh the ledger and inspect the charge or payment history before allowing another write.</p>
        {verifiedRefresh && <button className="rr-btn" type="button" style={{marginTop:10}}
          onClick={() => { setUncertain(false); setVerifiedRefresh(false); }}>
          I verified the records — unlock forms
        </button>}
      </div>
    </div>}

    {loading ? <Empty icon={RefreshCw} heading="Loading rent records" detail="Retrieving tenants, monthly charges, and balances from PostgreSQL." />
      : loadError ? <Empty icon={CircleAlert} heading="Rent records unavailable" detail={loadError}>
        <button className="rr-btn" type="button" onClick={refresh}><RefreshCw size={16}/> Try Again</button>
      </Empty> : <>
        <section className="rr-summary" aria-label="Rent ledger totals">
          {[
            ["Total Charges", records.length, ClipboardList],
            ["Total Paid", peso((totals.paid / 100).toFixed(2)), CheckCircle2],
            ["Outstanding", peso((totals.balance / 100).toFixed(2)), Wallet],
            ["Overdue Charges", totals.overdue, Clock3],
          ].map(([label, value, Icon]) => <div className="rr-stat" key={label}>
            <div className="rr-stat-heading"><Icon size={17}/>{label}</div><strong>{value}</strong>
          </div>)}
        </section>

        <section className="rr-panel" aria-labelledby="rr-create-title">
          <div className="rr-panel-head"><div><h2 id="rr-create-title"><Plus size={20}/> Create Monthly Charge</h2>
            <p>Select an active tenancy and the rent month. Dormora bills the agreed monthly amount without automatic prorating.</p></div></div>
          {!activeTenancies.length ? <Empty icon={Building2} heading="No active tenancies" detail="Assign a renter in Tenant Management before generating rent charges." />
            : <form className="rr-form" onSubmit={createCharge}>
              <div className="rr-field"><label htmlFor="rr-tenancy">Active tenancy *</label>
                <select id="rr-tenancy" value={tenancyId} required disabled={savingCharge || savingPayment || uncertain}
                  onChange={(event) => {
                    const value = event.target.value;
                    const selected = activeTenancies.find((row) => String(row.id) === value);
                    setTenancyId(value);
                    const moveMonth = String(selected?.move_in_date || "").slice(0, 7);
                    setBillingMonth(moveMonth > phToday().slice(0, 7) ? moveMonth : phToday().slice(0, 7));
                  }}>
                  {activeTenancies.map((item) => <option key={item.id} value={String(item.id)}>
                    {item.property_name || `Property #${item.property_id}`} — {item.room_label} — {item.renter_username || `Renter #${item.renter_user_id}`}
                  </option>)}
                </select>
                {selectedTenancy && <small>Agreed rent: {peso(selectedTenancy.monthly_rent)} · Due on day {selectedTenancy.rent_due_day} · Move-in: {displayDate(selectedTenancy.move_in_date)}</small>}
              </div>
              <div className="rr-field"><label htmlFor="rr-billing-month">Billing month *</label>
                <input id="rr-billing-month" type="month" required value={billingMonth}
                  min={String(selectedTenancy?.move_in_date || "").slice(0, 7) || undefined}
                  onChange={(event) => setBillingMonth(event.target.value)}
                  disabled={savingCharge || savingPayment || uncertain}/>
                <small>One rent charge per tenancy per billing month.</small>
              </div>
              <div className="rr-form-end">
                <span className="rr-muted">Charge creation does not collect a payment.</span>
                <button className="rr-btn primary" type="submit" disabled={!selectedTenancy || savingCharge || savingPayment || uncertain}>
                  <Plus size={16}/>{savingCharge ? "Creating..." : "Create Charge"}
                </button>
              </div>
            </form>}
        </section>

        <section className="rr-panel" aria-labelledby="rr-payment-title">
          <div className="rr-panel-head"><div><h2 id="rr-payment-title"><Banknote size={20}/> Record Received Payment</h2>
            <p>Record a payment only after confirming the tenant has actually paid. Partial payments are supported.</p></div></div>
          {!outstanding.length ? <Empty icon={Receipt} heading="No outstanding rent charges" detail="Create a charge first, or all existing rent charges are already fully paid." />
            : <form className="rr-form" onSubmit={recordPayment}>
              <div className="rr-field wide"><label htmlFor="rr-charge">Unpaid rent charge *</label>
                <select id="rr-charge" value={chargeId} required disabled={savingCharge || savingPayment || uncertain}
                  onChange={(event) => {setChargeId(event.target.value);setConfirmPayment(false);setAmount("");}}>
                  <option value="">Select a charge to record payment</option>
                  {outstanding.map((item) => <option value={String(item.charge_id)} key={item.charge_id}>
                    {item.property_name} — {item.room_label} — {item.renter_username} — {displayMonth(item.billing_month)} — Balance {peso(item.balance_due)}
                  </option>)}
                </select>
                {selectedCharge && <small>Charge #{selectedCharge.charge_id} · Due {displayDate(selectedCharge.due_date)} · Outstanding {peso(selectedCharge.balance_due)}</small>}
              </div>
              <div className="rr-field"><label htmlFor="rr-amount">Amount received (₱) *</label>
                <input id="rr-amount" type="text" inputMode="decimal" required maxLength={24} placeholder="e.g. 2000.00"
                  value={amount} disabled={savingCharge || savingPayment || uncertain}
                  onChange={(event) => {setAmount(event.target.value);setConfirmPayment(false);}}/>
                <small>Cannot exceed the outstanding balance.</small>
              </div>
              <div className="rr-field"><label htmlFor="rr-method">Payment method *</label>
                <select id="rr-method" value={method} disabled={savingCharge || savingPayment || uncertain}
                  onChange={(event) => {setMethod(event.target.value);setConfirmPayment(false);}}>
                  {Object.entries(METHOD_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div className="rr-field"><label htmlFor="rr-paid-on">Date received</label>
                <input id="rr-paid-on" type="date" value={paidOn} max={phToday()}
                  disabled={savingCharge || savingPayment || uncertain}
                  onChange={(event) => {setPaidOn(event.target.value);setConfirmPayment(false);}}/>
                <small>Leave blank to record today's date in Philippine time.</small>
              </div>
              <div className="rr-field"><label htmlFor="rr-note">Reference or note (optional)</label>
                <input id="rr-note" value={note} maxLength={200} placeholder="e.g. Cash receipt #15"
                  disabled={savingCharge || savingPayment || uncertain}
                  onChange={(event) => {setNote(event.target.value);setConfirmPayment(false);}}/>
              </div>
              {confirmPayment && selectedCharge && <div className="rr-confirm" role="status">
                <strong>Confirm payment record</strong>
                <p>Confirm that {peso(amount)} was actually received for charge #{selectedCharge.charge_id} ({displayMonth(selectedCharge.billing_month)}) via {METHOD_LABELS[method]}. This creates an append-only payment record and cannot be deleted through this page.</p>
                <div className="rr-actions">
                  <button className="rr-btn" type="button" onClick={() => setConfirmPayment(false)} disabled={savingPayment}>Cancel</button>
                  <button className="rr-btn primary" type="submit" disabled={savingPayment || uncertain}><CheckCircle2 size={16}/>{savingPayment ? "Saving..." : "Confirm Payment Received"}</button>
                </div>
              </div>}
              {!confirmPayment && <div className="rr-form-end">
                <span className="rr-muted">This does not transfer money or process an online payment.</span>
                <button className="rr-btn primary" type="submit" disabled={!selectedCharge || savingCharge || savingPayment || uncertain}>
                  <CreditCard size={16}/> Review Payment
                </button>
              </div>}
            </form>}
        </section>

        <section className="rr-panel" aria-labelledby="rr-ledger-title">
          <div className="rr-panel-head"><div><h2 id="rr-ledger-title"><History size={20}/> Monthly Rent Ledger</h2>
            <p>Pending, partially paid, paid and overdue statuses are calculated using current Philippine time.</p></div></div>
          <div className="rr-toolbar">
            <label className="rr-search"><Search size={17}/><input type="search" value={search}
              onChange={(event) => setSearch(event.target.value)} aria-label="Search rent records"
              placeholder="Search tenant, property, room or billing month"/></label>
            <select className="rr-filter" aria-label="Filter rent status" value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option>
              {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          {visibleRecords.length === 0 ? <Empty icon={ClipboardList} heading="No rent records found"
            detail={records.length === 0 ? "Create your first monthly charge using an active tenancy above." : "No charges match your current search and status filter."} />
            : <div className="rr-list">{visibleRecords.map((item) => {
              const expanded = openedHistory === item.charge_id;
              return <article className="rr-entry" key={item.charge_id}>
                <div className="rr-entry-top">
                  <div><h3>{item.property_name || `Property #${item.property_id}`} · {item.room_label}</h3>
                    <div className="rr-entry-sub">{item.renter_username || `Renter #${item.renter_user_id}`} · {displayMonth(item.billing_month)} · Charge #{item.charge_id}</div></div>
                  <StatusPill status={item.payment_status}/>
                </div>
                <div className="rr-values">
                  {[
                    ["Amount Due", peso(item.amount_due)],
                    ["Total Paid", peso(item.total_paid)],
                    ["Balance", peso(item.balance_due)],
                    ["Due Date", displayDate(item.due_date)],
                  ].map(([label, value]) => <div key={label}><div className="rr-value-label">{label}</div>
                    <div className="rr-value-amount">{value}</div></div>)}
                </div>
                <div className="rr-entry-actions">
                  <button type="button" className="rr-btn" onClick={() => setOpenedHistory(expanded ? null : item.charge_id)}>
                    {expanded ? <ChevronUp size={16}/> : <ChevronDown size={16}/>} {expanded ? "Hide" : "View"} Payment History
                  </button>
                  {(toCents(item.balance_due) ?? 0) > 0 && <button className="rr-btn" type="button"
                    disabled={savingCharge || savingPayment || uncertain} onClick={() => {
                      setChargeId(String(item.charge_id));setAmount("");setConfirmPayment(false);
                      setNotice({error:false,text:`Selected charge #${item.charge_id}. Use the Record Received Payment form above to record a confirmed payment.`});
                    }}><Wallet size={16}/> Record Payment</button>}
                </div>
                {expanded && <div className="rr-history">
                  {historyState.loading ? <p className="rr-muted">Loading payment history...</p>
                    : historyState.error ? <div className="rr-note" role="alert">{historyState.error}<div style={{marginTop:9}}>
                      <button type="button" className="rr-btn" onClick={() => setHistoryRevision((n) => n + 1)}>Retry</button></div></div>
                      : historyState.rows.length === 0 ? <p className="rr-muted">No payments recorded for this charge.</p>
                        : <div className="rr-history-list">{historyState.rows.map((payment) =>
                          <div className="rr-history-row" key={payment.id}>
                            <div><strong>Payment #{payment.id} · {METHOD_LABELS[payment.payment_method] || payment.payment_method}</strong>
                              <p>Received {displayDate(payment.paid_on)} · {payment.reference_note || "No reference note"}</p></div>
                            <strong>{peso(payment.amount)}</strong>
                          </div>)}</div>}
                </div>}
              </article>;
            })}</div>}
          <p className="rr-note" style={{marginTop:16}}><ShieldCheck size={16}/>
            Manual records only. The owner must verify payment outside Dormora before recording it. This page cannot edit or delete saved payment rows. The API currently returns up to 300 recent rent charges.
          </p>
        </section>
      </>}
  </section>;
}
