/**
 * DORMORA — SYSTEM FUNCTIONALITY FILE 38
 * CREATE: frontend/src/components/owner/TenantManagement.jsx
 *
 * Owner-only UI for assigning an accepted inquiry to a room, viewing
 * existing tenancies, and ending a tenancy. This is not a payment module.
 *
 * Backend: File 36 /api/tenancies and File 21 /api/rental-inquiries/owner.
 * Security: credentials=include, GET /api/csrf + X-CSRF-Token on POST.
 * The backend, not this component, verifies ownership and room availability.
 * File 39 will connect this page to the owner sidebar.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, Building2, CalendarDays, CheckCircle2, CircleAlert,
  ClipboardList, DoorOpen, KeyRound, RefreshCw, Search, Users,
  Wallet, XCircle,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const TENANCIES_PATH = "/api/tenancies";
const INQUIRIES_PATH = "/api/rental-inquiries/owner";

const styles = `
.tm-page{color:var(--text);width:100%;min-width:0;font-family:inherit}
.tm-page *{box-sizing:border-box}
.tm-header{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:22px}
.tm-header h1{margin:0 0 8px;font-size:clamp(24px,3vw,31px);font-weight:800}
.tm-header p,.tm-muted{color:var(--muted);font-size:13px;line-height:1.7;margin:0}
.tm-actions,.tm-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.tm-btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:41px;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);font:inherit;font-size:13px;font-weight:700;padding:10px 14px;cursor:pointer}
.tm-btn.primary{background:var(--primary);border-color:var(--primary);color:var(--background)}
.tm-btn:disabled{opacity:.52;cursor:not-allowed}
.tm-btn:hover:not(:disabled){filter:brightness(.97)}
.tm-page button:focus-visible,.tm-page input:focus-visible,.tm-page select:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.tm-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 20px}
.tm-stat{border:1px solid var(--border);background:var(--card);border-radius:14px;padding:17px;min-width:0}
.tm-stat-label{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px}
.tm-stat-label svg{color:var(--primary)}
.tm-stat strong{display:block;font-size:27px;font-weight:800;margin-top:10px}
.tm-card{background:var(--card);border:1px solid var(--border);border-radius:15px;padding:22px;margin-bottom:18px;min-width:0}
.tm-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.tm-section-head h2{display:flex;align-items:center;gap:9px;margin:0;font-size:18px}
.tm-section-head h2 svg{color:var(--primary)}
.tm-section-head p{color:var(--muted);font-size:12px;line-height:1.7;margin:5px 0 0}
.tm-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.tm-field{display:grid;gap:7px;min-width:0}
.tm-field.wide{grid-column:1/-1}
.tm-field label{font-size:12px;font-weight:750}
.tm-field input,.tm-field select,.tm-search input,.tm-filter{width:100%;background:var(--background);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:12px;font:inherit;font-size:13px;min-width:0}
.tm-field input:disabled,.tm-field select:disabled{opacity:.58}
.tm-field small{font-size:11px;color:var(--muted);line-height:1.5}
.tm-form-footer{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;border-top:1px solid var(--border);padding-top:15px}
.tm-note{background:var(--soft);border:1px solid var(--border);padding:12px 14px;border-radius:11px;color:var(--muted);font-size:12px;line-height:1.7}
.tm-message{display:flex;align-items:flex-start;gap:9px;padding:13px 15px;background:var(--soft);border:1px solid var(--border);border-radius:11px;margin:0 0 16px;color:var(--text);font-size:13px;line-height:1.6}
.tm-message svg{flex-shrink:0;margin-top:2px;color:var(--primary)}
.tm-message.error{border-style:dashed}
.tm-toolbar{margin-bottom:16px}
.tm-search{flex:1;min-width:210px;display:flex;align-items:center;gap:9px;color:var(--muted);border:1px solid var(--border);background:var(--background);padding:0 12px;border-radius:10px}
.tm-search input{border:0;outline:0;padding:12px 0;background:transparent}
.tm-search svg{flex-shrink:0}
.tm-filter{width:auto;max-width:100%}
.tm-list{display:grid;gap:12px}
.tm-entry{border:1px solid var(--border);border-radius:12px;padding:17px;background:var(--background)}
.tm-entry-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:13px}
.tm-entry h3{margin:0 0 5px;font-size:16px;overflow-wrap:anywhere}
.tm-entry-sub{color:var(--muted);font-size:12px;line-height:1.6}
.tm-status{display:inline-flex;align-items:center;gap:6px;background:var(--soft);color:var(--primary);border-radius:8px;padding:7px 10px;font-size:11px;font-weight:800;text-transform:capitalize}
.tm-status.ended{color:var(--muted)}
.tm-details{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;padding-top:12px;border-top:1px solid var(--border)}
.tm-detail-label{color:var(--muted);font-size:11px;margin:0 0 5px}
.tm-detail-value{font-size:13px;font-weight:750;overflow-wrap:anywhere}
.tm-entry-footer{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-top:15px}
.tm-confirm{background:var(--soft);border:1px solid var(--border);border-radius:11px;padding:15px;margin-top:14px}
.tm-confirm strong{font-size:14px}
.tm-confirm p{font-size:12px;line-height:1.7;color:var(--muted);margin:8px 0 13px}
.tm-empty{border:1px dashed var(--border);border-radius:12px;min-height:170px;padding:25px;text-align:center;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px}
.tm-empty svg{color:var(--primary)}
.tm-empty h3{margin:0;font-size:16px}.tm-empty p{font-size:12px;color:var(--muted);line-height:1.7;margin:0;max-width:520px}
@media(max-width:1000px){.tm-summary,.tm-details{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.tm-summary,.tm-form,.tm-details{grid-template-columns:1fr}.tm-card{padding:16px}.tm-header{flex-direction:column}.tm-form-footer{align-items:stretch}.tm-toolbar{align-items:stretch;flex-direction:column}.tm-search,.tm-filter{width:100%}}
`;

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    mode: "cors",
    credentials: "include",
    cache: "no-store",
    redirect: "error",
    ...options,
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    // Do not display raw HTML or server error traces.
  }
  return { response, data };
}

function messageFor(response, data, fallback) {
  if (response.status === 401) return "Your session has expired. Sign in again.";
  if (response.status === 403) return "Access denied. Check your owner session and CSRF token.";
  if (response.status === 404) return "This inquiry or tenancy is no longer available.";
  if (response.status === 409) return typeof data?.detail === "string"
    ? data.detail : "The rental state changed. Refresh before continuing.";
  if (response.status === 429) return "Too many requests. Please try again later.";
  if (response.status === 422) return "Invalid rental details. Review the form fields.";
  if (response.status < 500 && typeof data?.detail === "string") return data.detail;
  return fallback;
}

function peso(value) {
  const number = Number(value);
  return Number.isFinite(number)
    ? new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(number)
    : "—";
}

function localDate(value) {
  if (!value) return "Not specified";
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return String(value);
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return date.toLocaleDateString("en-PH", { year: "numeric", month: "short", day: "numeric" });
}

function phToday() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const get = (type) => parts.find((part) => part.type === type)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

const emptyForm = {
  inquiryId: "",
  roomLabel: "",
  moveInDate: "",
  monthlyRent: "",
  rentDueDay: "1",
};

export default function TenantManagement({ account, onBack }) {
  const isOwner = account?.role === "property_owner";
  const [tenancies, setTenancies] = useState([]);
  const [inquiries, setInquiries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState(null);
  const [refreshNumber, setRefreshNumber] = useState(0);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [endingId, setEndingId] = useState(null);
  const [confirmEndId, setConfirmEndId] = useState(null);
  const [uncertain, setUncertain] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const requestBusy = useRef(false);

  const refresh = useCallback(() => setRefreshNumber((n) => n + 1), []);

  useEffect(() => {
    if (!isOwner) {
      setLoading(false);
      setTenancies([]);
      setInquiries([]);
      return undefined;
    }
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setLoadError("");
      try {
        const [rentals, requests] = await Promise.all([
          requestJson(`${TENANCIES_PATH}/owner`, { signal: controller.signal }),
          requestJson(INQUIRIES_PATH, { signal: controller.signal }),
        ]);
        if (!rentals.response.ok) {
          throw new Error(messageFor(rentals.response, rentals.data, "Unable to load tenants."));
        }
        if (!requests.response.ok) {
          throw new Error(messageFor(requests.response, requests.data, "Unable to load accepted inquiries."));
        }
        if (!Array.isArray(rentals.data?.tenancies) || !Array.isArray(requests.data?.inquiries)) {
          throw new Error("The backend returned an invalid tenant or inquiry list.");
        }
        if (!controller.signal.aborted) {
          setTenancies(rentals.data.tenancies);
          setInquiries(requests.data.inquiries);
          setUncertain(false);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setLoadError(error?.message || "Could not contact the Dormora backend.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [isOwner, refreshNumber]);

  const acceptedReady = useMemo(() => {
    const usedInquiries = new Set(tenancies.map((item) => Number(item.inquiry_id)));
    const occupiedRenters = new Set(tenancies
      .filter((item) => item.status === "active")
      .map((item) => Number(item.renter_user_id)));
    return inquiries.filter((item) =>
      item.status === "accepted" &&
      !usedInquiries.has(Number(item.id)) &&
      !occupiedRenters.has(Number(item.renter_user_id))
    );
  }, [inquiries, tenancies]);

  const selectedInquiry = acceptedReady.find((item) => String(item.id) === form.inquiryId);
  const active = tenancies.filter((item) => item.status === "active").length;
  const ended = tenancies.filter((item) => item.status === "ended").length;
  const visible = useMemo(() => {
    const text = search.trim().toLowerCase();
    return tenancies.filter((item) => {
      if (statusFilter !== "all" && item.status !== statusFilter) return false;
      return !text || `${item.property_name || ""} ${item.renter_username || ""} ${item.room_label || ""}`
        .toLowerCase().includes(text);
    });
  }, [tenancies, search, statusFilter]);

  function change(field, value) {
    setForm((old) => ({ ...old, [field]: value }));
    if (notice?.type === "error") setNotice(null);
  }

  async function assign(event) {
    event.preventDefault();
    if (!isOwner || requestBusy.current || saving || uncertain || loading || loadError || !selectedInquiry) return;
    const label = form.roomLabel.trim().replace(/\s+/g, " ");
    const dueDay = Number(form.rentDueDay);
    if (!label || label.length > 60 || !form.moveInDate || !Number.isInteger(dueDay) || dueDay < 1 || dueDay > 28) {
      setNotice({ type: "error", text: "Choose an accepted inquiry and enter a valid room, move-in date, and rent due day." });
      return;
    }
    const rent = form.monthlyRent.trim();
    if (rent && (!/^\d+(\.\d{1,2})?$/.test(rent) || Number(rent) <= 0 || Number(rent) > 9999999999.99)) {
      setNotice({ type: "error", text: "Enter a valid positive monthly rent (up to two decimal places), or leave it blank to use the listing price." });
      return;
    }
    if (tenancies.some((item) => item.status === "active" &&
      Number(item.property_id) === Number(selectedInquiry.property_id) &&
      String(item.room_label).trim().toLowerCase() === label.toLowerCase())) {
      setNotice({ type: "error", text: "That room is already assigned in this property." });
      return;
    }

    requestBusy.current = true;
    setSaving(true);
    setNotice(null);
    let dispatched = false;
    try {
      // Fetch the signed token first. Sending the POST may create a tenancy.
      const csrf = await requestJson("/api/csrf", { method: "GET" });
      if (!csrf.response.ok || typeof csrf.data?.csrf_token !== "string" || !csrf.data.csrf_token) {
        throw new Error(messageFor(csrf.response, csrf.data, "Unable to obtain CSRF protection."));
      }
      dispatched = true;
      const { response, data } = await requestJson(`${TENANCIES_PATH}/assign`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf.data.csrf_token },
        body: JSON.stringify({
          inquiry_id: Number(form.inquiryId),
          room_label: label,
          move_in_date: form.moveInDate,
          agreed_monthly_rent: rent || null,
          rent_due_day: dueDay,
        }),
      });
      if (!response.ok) {
        setNotice({ type: "error", text: messageFor(response, data, "Could not assign the tenant.") });
        if ([404, 409].includes(response.status)) refresh();
        return;
      }
      setForm({ ...emptyForm });
      setNotice({ type: "success", text: `Room assigned successfully${data?.tenancy?.room_label ? `: ${data.tenancy.room_label}` : ""}. The property availability was updated.` });
      refresh();
    } catch (error) {
      if (dispatched) {
        setUncertain(true);
        setNotice({ type: "error", text: "Connection interrupted after assignment was sent. It may have succeeded. Refresh the tenant list before attempting it again." });
      } else {
        setNotice({ type: "error", text: error?.message || "Could not prepare the secure request." });
      }
    } finally {
      requestBusy.current = false;
      setSaving(false);
    }
  }

  async function finishTenancy(item) {
    if (!isOwner || requestBusy.current || uncertain || loading || loadError || item.status !== "active") return;
    if (item.move_in_date > phToday()) {
      setNotice({ type: "error", text: "This tenancy starts in the future. The current backend does not support ending it before its move-in date." });
      return;
    }
    requestBusy.current = true;
    setEndingId(item.id);
    setNotice(null);
    let dispatched = false;
    try {
      const csrf = await requestJson("/api/csrf", { method: "GET" });
      if (!csrf.response.ok || typeof csrf.data?.csrf_token !== "string" || !csrf.data.csrf_token) {
        throw new Error(messageFor(csrf.response, csrf.data, "Unable to obtain CSRF protection."));
      }
      dispatched = true;
      const { response, data } = await requestJson(`${TENANCIES_PATH}/${item.id}/end`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf.data.csrf_token },
        body: JSON.stringify({}),
      });
      if (!response.ok) {
        setNotice({ type: "error", text: messageFor(response, data, "Could not end this tenancy.") });
        if ([404, 409].includes(response.status)) refresh();
        return;
      }
      setConfirmEndId(null);
      setNotice({ type: "success", text: "Tenancy ended successfully. One room has been returned to the property's available-room count." });
      refresh();
    } catch (error) {
      if (dispatched) {
        setUncertain(true);
        setNotice({ type: "error", text: "Connection interrupted after the end request was sent. Refresh and confirm the tenancy status before trying again." });
      } else {
        setNotice({ type: "error", text: error?.message || "Could not prepare the secure request." });
      }
    } finally {
      requestBusy.current = false;
      setEndingId(null);
    }
  }

  if (!isOwner) {
    return <section className="tm-page"><style>{styles}</style>
      <div className="tm-empty" role="alert"><XCircle size={30} /><h3>Owner Access Required</h3>
        <p>Tenant Management is available only to property owner accounts.</p></div>
    </section>;
  }

  return <section className="tm-page">
    <style>{styles}</style>
    <header className="tm-header">
      <div><h1>Tenant Management</h1><p>Assign accepted renters to rooms and manage rental occupancy.</p></div>
      <div className="tm-actions">
        {onBack && <button className="tm-btn" type="button" onClick={onBack}><ArrowLeft size={16} /> Home</button>}
        <button className="tm-btn" type="button" onClick={refresh} disabled={loading || saving || endingId !== null}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>
    </header>

    {notice && <div className={`tm-message ${notice.type === "error" ? "error" : ""}`}
      role={notice.type === "error" ? "alert" : "status"}>
      {notice.type === "error" ? <CircleAlert size={18} /> : <CheckCircle2 size={18} />}{notice.text}
    </div>}
    {uncertain && <p className="tm-note" role="alert">Do not repeat the last action yet. Press Refresh to check whether the database saved it.</p>}

    {loading ? <div className="tm-empty" role="status"><RefreshCw size={28} /><h3>Loading tenant records</h3><p>Checking your tenancies and accepted inquiries.</p></div>
      : loadError ? <div className="tm-empty" role="alert"><CircleAlert size={28} /><h3>Unable to load Tenant Management</h3><p>{loadError}</p><button className="tm-btn" type="button" onClick={refresh}><RefreshCw size={16} /> Try Again</button></div>
        : <>
          <div className="tm-summary" aria-label="Tenant management overview">
            {[
              ["Total Tenancies", tenancies.length, ClipboardList],
              ["Active Tenants", active, Users],
              ["Ended Tenancies", ended, DoorOpen],
              ["Ready to Assign", acceptedReady.length, KeyRound],
            ].map(([label, count, Icon]) => <div className="tm-stat" key={label}>
              <div className="tm-stat-label"><Icon size={18}/>{label}</div><strong>{count}</strong>
            </div>)}
          </div>

          <article className="tm-card">
            <div className="tm-section-head">
              <div><h2><KeyRound size={20}/> Assign a Tenant</h2>
                <p>Select an accepted inquiry and record the agreed room and rental terms.</p></div>
            </div>
            {acceptedReady.length === 0 ? <div className="tm-empty">
              <Building2 size={28}/><h3>No inquiries ready for assignment</h3>
              <p>Accept an inquiry first in Rental Inquiries. Already assigned inquiries are excluded automatically.</p>
            </div> : <form className="tm-form" onSubmit={assign}>
              <div className="tm-field wide"><label htmlFor="tm-inquiry">Accepted rental inquiry *</label>
                <select id="tm-inquiry" value={form.inquiryId} onChange={(event) => change("inquiryId", event.target.value)} required disabled={saving || uncertain}>
                  <option value="">Select an accepted inquiry</option>
                  {acceptedReady.map((item) => <option key={item.id} value={String(item.id)}>
                    {item.property_name || `Property #${item.property_id}`} — {item.renter_username || `Renter #${item.renter_user_id}`} (Inquiry #{item.id})
                  </option>)}
                </select>
                {selectedInquiry && <small>Property #{selectedInquiry.property_id} · Renter #{selectedInquiry.renter_user_id}</small>}
              </div>
              <div className="tm-field"><label htmlFor="tm-room">Room or unit label *</label>
                <input id="tm-room" type="text" value={form.roomLabel} onChange={(event) => change("roomLabel", event.target.value)}
                  placeholder="e.g. Room 101" maxLength={60} required disabled={saving || uncertain}/>
                <small>Use a unique label for this property.</small>
              </div>
              <div className="tm-field"><label htmlFor="tm-date">Agreed move-in date *</label>
                <input id="tm-date" type="date" value={form.moveInDate} onChange={(event) => change("moveInDate", event.target.value)}
                  required disabled={saving || uncertain}/>
                <small>A future move-in still reserves the room immediately.</small>
              </div>
              <div className="tm-field"><label htmlFor="tm-rent">Agreed monthly rent (₱)</label>
                <input id="tm-rent" type="text" inputMode="decimal" value={form.monthlyRent} onChange={(event) => change("monthlyRent", event.target.value)}
                  placeholder="Leave empty to use listing price" maxLength={24} disabled={saving || uncertain}/>
                <small>Example: 5000.00. If blank, the backend uses the current property price.</small>
              </div>
              <div className="tm-field"><label htmlFor="tm-due">Monthly rent due day *</label>
                <select id="tm-due" value={form.rentDueDay} onChange={(event) => change("rentDueDay", event.target.value)} disabled={saving || uncertain}>
                  {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => <option key={day} value={day}>{day}</option>)}
                </select>
                <small>Days 1–28 are available to avoid shorter-month date issues.</small>
              </div>
              <div className="tm-form-footer">
                <span className="tm-muted">Only assign a room after the renter and owner agree on the rental terms.</span>
                <button className="tm-btn primary" type="submit" disabled={!selectedInquiry || saving || uncertain || requestBusy.current}>
                  <KeyRound size={16}/>{saving ? "Assigning..." : "Assign Tenant"}
                </button>
              </div>
            </form>}
          </article>

          <article className="tm-card">
            <div className="tm-section-head"><div><h2><Users size={20}/> Tenant Records</h2>
              <p>Review active assignments and previous rental records.</p></div></div>
            <div className="tm-toolbar">
              <label className="tm-search"><Search size={17}/><input aria-label="Search tenant records" type="search" value={search}
                onChange={(event) => setSearch(event.target.value)} placeholder="Search tenant, property, or room" /></label>
              <select className="tm-filter" aria-label="Filter tenancy status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">All records</option><option value="active">Active</option><option value="ended">Ended</option>
              </select>
            </div>
            {visible.length === 0 ? <div className="tm-empty"><ClipboardList size={28}/><h3>No tenancy records found</h3>
              <p>{tenancies.length === 0 ? "Assign an accepted inquiry to create the first tenancy." : "Try another search or status filter."}</p></div>
              : <div className="tm-list">{visible.map((item) => {
                const future = Boolean(item.move_in_date) && item.move_in_date > phToday();
                const confirming = confirmEndId === item.id;
                return <section className="tm-entry" key={item.id}>
                  <div className="tm-entry-head">
                    <div><h3>{item.renter_username || `Renter #${item.renter_user_id}`}</h3>
                      <div className="tm-entry-sub">{item.property_name || `Property #${item.property_id}`} · {item.room_label} · Tenancy #{item.id}</div></div>
                    <span className={`tm-status ${item.status === "ended" ? "ended" : ""}`}>
                      {item.status === "ended" ? <XCircle size={13}/> : <CheckCircle2 size={13}/>} {item.status}
                    </span>
                  </div>
                  <div className="tm-details">
                    <div><p className="tm-detail-label">Monthly rent</p><div className="tm-detail-value">{peso(item.monthly_rent)}</div></div>
                    <div><p className="tm-detail-label">Rent due</p><div className="tm-detail-value">Day {item.rent_due_day}</div></div>
                    <div><p className="tm-detail-label">Move-in</p><div className="tm-detail-value">{localDate(item.move_in_date)}</div></div>
                    <div><p className="tm-detail-label">Move-out</p><div className="tm-detail-value">{localDate(item.move_out_date)}</div></div>
                  </div>
                  <div className="tm-entry-footer">
                    <span className="tm-muted">Inquiry #{item.inquiry_id}{future && item.status === "active" ? " · Move-in is scheduled for the future" : ""}</span>
                    {item.status === "active" && <button className="tm-btn" type="button" disabled={saving || endingId !== null || uncertain || future}
                      title={future ? "This tenancy cannot end before its move-in date." : "End this tenancy"}
                      onClick={() => setConfirmEndId(confirming ? null : item.id)}><CalendarDays size={15}/> End Tenancy</button>}
                  </div>
                  {confirming && item.status === "active" && <div className="tm-confirm">
                    <strong>End the rental for {item.renter_username || `Renter #${item.renter_user_id}`}?</strong>
                    <p>This marks the tenancy ended today and releases one room. It does not delete rental history. This action cannot be undone here.</p>
                    <div className="tm-actions">
                      <button className="tm-btn" type="button" disabled={endingId !== null} onClick={() => setConfirmEndId(null)}>Cancel</button>
                      <button className="tm-btn primary" type="button" disabled={endingId !== null || uncertain}
                        onClick={() => finishTenancy(item)}><CheckCircle2 size={15}/>{endingId === item.id ? "Ending..." : "Confirm End Tenancy"}</button>
                    </div>
                  </div>}
                </section>;
              })}</div>}
          </article>
          <p className="tm-note"><Wallet size={15} style={{ verticalAlign: "middle", marginRight: 7 }}/>
            Tenant assignment records the agreed rent but does not create invoices or payment records. Rent tracking is a separate upcoming feature.</p>
        </>}
  </section>;
}
