/**
 * DORMORA — SYSTEM FUNCTIONALITY FILE 32
 *
 * REPLACE: frontend/src/components/owner/OwnerInquiries.jsx
 *
 * Read, reply to, and review rental inquiries received by a property owner.
 * Uses the authenticated File 21 API and Dormora's signed CSRF endpoint.
 * No tenancy, room allocation, or payment changes are performed here.
 *
 * Preserves the File 24 accept/reject, filters, and existing page layout.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Building2,
  CalendarDays,
  Check,
  CheckCircle2,
  Clock3,
  Inbox,
  MapPin,
  MessageSquareText,
  RefreshCw,
  Send,
  MessagesSquare,
  Search,
  ShieldCheck,
  UserRound,
  X,
  XCircle,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const INQUIRIES_PATH = "/api/rental-inquiries";

const styles = `
.oi-page{color:var(--text);font-family:inherit;width:100%;min-width:0}
.oi-page *{box-sizing:border-box}
.oi-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin-bottom:23px;flex-wrap:wrap}
.oi-head h1{font-size:clamp(24px,3vw,31px);font-weight:800;margin:0 0 7px}
.oi-head p{color:var(--muted);font-size:13px;line-height:1.7;margin:0}
.oi-head-actions{display:flex;gap:9px;flex-wrap:wrap}
.oi-btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:10px;padding:10px 14px;min-height:41px;font:inherit;font-size:13px;font-weight:750;cursor:pointer}
.oi-btn:hover:not(:disabled){filter:brightness(.97)}
.oi-btn:disabled{opacity:.52;cursor:not-allowed}
.oi-btn.primary{background:var(--primary);border-color:var(--primary);color:var(--background)}
.oi-btn:focus-visible,.oi-search input:focus-visible,.oi-filter select:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.oi-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:21px}
.oi-summary-item{border:1px solid var(--border);background:var(--card);border-radius:13px;padding:16px}
.oi-summary-item span{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px}
.oi-summary-item svg{color:var(--primary)}
.oi-summary-item strong{display:block;font-size:27px;margin-top:10px;line-height:1.1}
.oi-tools{display:flex;gap:11px;margin-bottom:17px;align-items:center;flex-wrap:wrap}
.oi-search{display:flex;align-items:center;gap:10px;flex:1;min-width:210px;border:1px solid var(--border);border-radius:11px;background:var(--card);padding:0 12px;color:var(--muted)}
.oi-search input{min-width:0;flex:1;border:0;outline:0;padding:12px 0;background:transparent;color:var(--text);font:inherit;font-size:13px}
.oi-filter{display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--border);border-radius:11px;padding:0 11px;color:var(--muted);font-size:13px}
.oi-filter select{background:transparent;color:var(--text);border:0;padding:12px 3px;font:inherit;font-size:13px;outline:none}
.oi-filter option{background:var(--card);color:var(--text)}
.oi-results{color:var(--muted);font-size:12px;margin:0 0 13px}
.oi-list{display:grid;gap:14px}
.oi-card{border:1px solid var(--border);background:var(--card);border-radius:15px;padding:19px;min-width:0}
.oi-card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.oi-card h2{font-size:17px;line-height:1.45;margin:0 0 7px;overflow-wrap:anywhere}
.oi-card-meta{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12px;line-height:1.6}
.oi-badge{display:inline-flex;align-items:center;gap:5px;padding:6px 9px;font-size:11px;font-weight:800;border-radius:7px;background:var(--soft);color:var(--primary);text-transform:capitalize}
.oi-badge.rejected,.oi-badge.withdrawn{background:var(--soft);color:var(--muted)}
.oi-details{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;padding:15px 0;margin-top:12px;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.oi-detail-label{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:11px;margin-bottom:5px}
.oi-detail-value{font-size:13px;font-weight:700;overflow-wrap:anywhere}
.oi-message{padding:14px;background:var(--soft);border-radius:10px;margin-top:13px}
.oi-message h3{font-size:12px;margin:0 0 7px;display:flex;align-items:center;gap:7px}
.oi-message p{color:var(--text);font-size:13px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}
.oi-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:14px}
.oi-footer small{color:var(--muted);font-size:11px;line-height:1.6}
.oi-actions{display:flex;flex-wrap:wrap;gap:9px}
.oi-confirm{margin-top:15px;background:var(--soft);border:1px solid var(--border);border-radius:11px;padding:15px}
.oi-confirm strong{display:block;font-size:14px;margin-bottom:6px}
.oi-confirm p{font-size:12px;line-height:1.65;color:var(--muted);margin:0 0 12px}
.oi-confirm-actions{display:flex;flex-wrap:wrap;gap:9px}
.oi-notice{display:flex;align-items:flex-start;gap:9px;background:var(--soft);border:1px solid var(--border);border-radius:11px;padding:13px 15px;margin-bottom:17px;color:var(--text);font-size:13px;line-height:1.65}
.oi-notice svg{flex-shrink:0;color:var(--primary);margin-top:2px}
.oi-notice.error{color:var(--text)}
.oi-state{background:var(--card);border:1px dashed var(--border);border-radius:14px;min-height:220px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;text-align:center;padding:32px 20px}
.oi-state svg{color:var(--primary)}
.oi-state h3{font-size:17px;margin:0}
.oi-state p{font-size:13px;color:var(--muted);max-width:480px;line-height:1.7;margin:0}
.oi-footnote{font-size:12px;line-height:1.7;color:var(--muted);margin-top:19px}

/* File 32: owner conversation panel (same theme tokens as File 24). */
.oi-thread{margin-top:17px;padding:17px;border-radius:12px;border:1px solid var(--border);background:var(--background);min-width:0}
.oi-thread-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:15px}
.oi-thread-head h3{display:flex;align-items:center;gap:8px;font-size:15px;margin:0}
.oi-thread-head h3 svg{color:var(--primary)}
.oi-thread-note{font-size:12px;line-height:1.6;color:var(--muted);margin:8px 0 14px}
.oi-thread-messages{display:grid;gap:12px;max-height:430px;overflow-y:auto;padding:4px 3px 12px}
.oi-chat-row{display:flex;flex-direction:column;align-items:flex-start;gap:5px;min-width:0}
.oi-chat-row.owner{align-items:flex-end}
.oi-chat-label{font-size:11px;color:var(--muted);display:flex;gap:8px;flex-wrap:wrap}
.oi-chat-bubble{max-width:min(86%,650px);background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:12px;padding:11px 13px;font-size:13px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}
.oi-chat-row.owner .oi-chat-bubble{background:var(--soft);border-color:var(--border)}
.oi-chat-empty{border:1px dashed var(--border);border-radius:10px;padding:20px;text-align:center;color:var(--muted);font-size:13px}
.oi-reply-form{margin-top:12px;padding-top:15px;border-top:1px solid var(--border);display:grid;gap:9px}
.oi-reply-form label{font-size:12px;font-weight:750}
.oi-reply-form textarea{width:100%;min-height:90px;max-height:220px;resize:vertical;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);font:inherit;font-size:13px;line-height:1.6;padding:11px 12px}
.oi-reply-form textarea:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.oi-reply-actions{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.oi-thread-feedback{border-radius:10px;background:var(--soft);border:1px solid var(--border);color:var(--text);font-size:12px;line-height:1.65;padding:12px;margin:10px 0}
.oi-thread-feedback.error{border-style:dashed}
.oi-thread-closed{color:var(--muted);font-size:12px;line-height:1.7;margin:12px 0 0}
@media(max-width:950px){.oi-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){.oi-details{grid-template-columns:1fr}.oi-head-actions{width:100%}.oi-tools{flex-direction:column;align-items:stretch}.oi-search{width:100%}.oi-filter{width:max-content;max-width:100%}.oi-card{padding:15px}}
`;

async function apiJson(path, options = {}) {
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
    // Do not display untrusted HTML or server tracebacks.
  }

  return { response, data };
}

function errorMessage(response, data, fallback) {
  if (response.status === 401) return "Your session has expired. Please sign in again.";
  if (response.status === 403) return "Access was denied. Check your property-owner session or CSRF token.";
  if (response.status === 404) return "This inquiry is no longer available.";
  if (response.status === 409) return "This inquiry has already been reviewed or is no longer pending. Refresh the list.";
  if (response.status === 429) return "Too many requests. Please try again later.";
  if (typeof data?.detail === "string" && response.status < 500) return data.detail;
  return fallback;
}

function formatDate(value) {
  if (!value) return "Not specified";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("en-PH", {
    year: "numeric", month: "short", day: "numeric",
    ...(String(value).includes("T") ? { hour: "numeric", minute: "2-digit" } : {}),
  });
}

function formatMoveInDate(value) {
  if (!value) return "Not specified";
  const parts = String(value).split("-");
  if (parts.length !== 3) return String(value);
  const [year, month, day] = parts.map(Number);
  if (!year || !month || !day) return String(value);
  const date = new Date(year, month - 1, day);
  return date.toLocaleDateString("en-PH", { year: "numeric", month: "short", day: "numeric" });
}

function StatusBadge({ status }) {
  const current = ["pending", "accepted", "rejected", "withdrawn"].includes(status)
    ? status : "unknown";
  const Icon = current === "accepted" ? CheckCircle2
    : current === "rejected" ? XCircle : Clock3;
  return (
    <span className={`oi-badge ${current}`}>
      <Icon size={13} /> {current}
    </span>
  );
}


/**
 * File 32: Private conversation for a single inquiry.
 * Mounted only when its owner explicitly opens it.
 * The server enforces that the account actually owns this property.
 */
function InquiryConversation({ inquiryId }) {
  const [thread, setThread] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [deliveryUncertain, setDeliveryUncertain] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const postingRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    async function loadThread() {
      setLoading(true);
      setLoadError("");
      try {
        const { response, data } = await apiJson(
          `${INQUIRIES_PATH}/${inquiryId}/messages`,
          { method: "GET", signal: controller.signal },
        );
        if (!response.ok) {
          throw new Error(errorMessage(response, data, "Could not load this conversation."));
        }
        if (!data?.inquiry || !Array.isArray(data?.messages)) {
          throw new Error("The server returned an invalid conversation.");
        }
        if (!controller.signal.aborted) {
          setThread(data);
          setDeliveryUncertain(false);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setLoadError(error?.message || "Could not load this conversation.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    loadThread();
    return () => controller.abort();
  }, [inquiryId, reloadKey]);

  function refreshThread() {
    setFeedback(null);
    setReloadKey((value) => value + 1);
  }

  async function sendReply(event) {
    event.preventDefault();
    const cleaned = replyText.trim();
    if (
      postingRef.current || sending || deliveryUncertain ||
      !thread?.inquiry?.can_reply || !cleaned || cleaned.length > 1000
    ) return;

    postingRef.current = true;
    setSending(true);
    setFeedback(null);
    let dispatched = false;
    try {
      const csrf = await apiJson("/api/csrf", { method: "GET" });
      if (
        !csrf.response.ok ||
        typeof csrf.data?.csrf_token !== "string" ||
        !csrf.data.csrf_token
      ) {
        throw new Error(errorMessage(csrf.response, csrf.data, "Unable to obtain a CSRF token."));
      }

      dispatched = true;
      const { response, data } = await apiJson(
        `${INQUIRIES_PATH}/${inquiryId}/messages`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf.data.csrf_token,
          },
          body: JSON.stringify({ message_text: cleaned }),
        },
      );
      if (!response.ok) {
        setFeedback({
          type: "error",
          text: response.status === 409
            ? "This inquiry no longer accepts replies. Refresh its conversation."
            : errorMessage(response, data, "Could not send your reply."),
        });
        if (response.status === 409) setReloadKey((value) => value + 1);
        return;
      }

      setReplyText("");
      setFeedback({ type: "success", text: "Reply saved. The renter can see it in the conversation." });
      if (data?.message && typeof data.message.message_text === "string") {
        setThread((current) => current ? {
          ...current,
          messages: [...current.messages, data.message],
        } : current);
      } else {
        // A successful POST must never be submitted again simply because
        // its response omitted message details. Refresh via a GET instead.
        setReloadKey((value) => value + 1);
      }
    } catch (error) {
      if (dispatched) {
        setDeliveryUncertain(true);
        setFeedback({
          type: "error",
          text: "The connection failed after sending. The reply may already be saved. Refresh the conversation before trying again; do not resend blindly.",
        });
      } else {
        setFeedback({ type: "error", text: error?.message || "Unable to prepare the secure request." });
      }
    } finally {
      postingRef.current = false;
      setSending(false);
    }
  }

  const canReply = Boolean(thread?.inquiry?.can_reply) && !deliveryUncertain;
  const messages = Array.isArray(thread?.messages) ? thread.messages : [];

  return (
    <section className="oi-thread" id={`oi-thread-${inquiryId}`} aria-label={`Conversation for inquiry ${inquiryId}`}>
      <div className="oi-thread-head">
        <h3><MessagesSquare size={19} /> Conversation</h3>
        <button type="button" className="oi-btn"
          onClick={refreshThread} disabled={loading || sending}>
          <RefreshCw size={15} /> Refresh Messages
        </button>
      </div>

      {loading ? (
        <p className="oi-thread-note" role="status">Loading private messages...</p>
      ) : loadError ? (
        <div className="oi-thread-feedback error" role="alert">{loadError}</div>
      ) : (
        <>
          <p className="oi-thread-note">
            Only you and this property's renter can view this conversation.
            {thread?.has_older_replies ? " Showing the latest 200 replies." : ""}
          </p>
          <div className="oi-thread-messages" role="log" aria-label="Inquiry conversation" aria-live="polite">
            {messages.length === 0 ? (
              <div className="oi-chat-empty">No text messages yet. Send a reply to begin.</div>
            ) : messages.map((message, index) => {
              const owner = message.sender_role === "property_owner";
              return (
                <div className={`oi-chat-row ${owner ? "owner" : ""}`}
                  key={message.kind === "initial_inquiry" ? "initial" : `reply-${message.id ?? index}`}>
                  <span className="oi-chat-label">
                    {owner ? "You · Property Owner" : "Renter"}
                    {message.kind === "initial_inquiry" ? " · Original inquiry" : ""}
                    {message.created_at ? ` · ${formatDate(message.created_at)}` : ""}
                  </span>
                  <div className="oi-chat-bubble">{message.message_text}</div>
                </div>
              );
            })}
          </div>

          {thread?.inquiry?.can_reply ? (
            <form className="oi-reply-form" onSubmit={sendReply}>
              <label htmlFor={`oi-reply-${inquiryId}`}>Reply to renter</label>
              <textarea
                id={`oi-reply-${inquiryId}`}
                value={replyText}
                onChange={(event) => setReplyText(event.target.value)}
                maxLength={1000}
                rows={3}
                placeholder="Type your message to the renter..."
                disabled={sending || deliveryUncertain}
              />
              <div className="oi-reply-actions">
                <small className="df-muted">{replyText.length}/1000 characters</small>
                <button className="oi-btn primary" type="submit"
                  disabled={!canReply || sending || !replyText.trim()}>
                  <Send size={15} /> {sending ? "Sending..." : "Send Reply"}
                </button>
              </div>
            </form>
          ) : (
            <p className="oi-thread-closed">
              This inquiry is closed for new replies. The conversation remains visible.
            </p>
          )}
        </>
      )}

      {feedback && (
        <div className={`oi-thread-feedback ${feedback.type === "error" ? "error" : ""}`}
          role={feedback.type === "error" ? "alert" : "status"}>
          {feedback.text}
        </div>
      )}
      {deliveryUncertain && (
        <p className="oi-thread-note">Refresh Messages to confirm whether your reply was saved before trying again.</p>
      )}
    </section>
  );
}

export default function OwnerInquiries({ account, onBack }) {
  const isOwner = account?.role === "property_owner";
  const [inquiries, setInquiries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [refreshKey, setRefreshKey] = useState(0);
  const [confirming, setConfirming] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [openThreadId, setOpenThreadId] = useState(null);

  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

  useEffect(() => {
    if (!isOwner) {
      setInquiries([]);
      setLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      try {
        const { response, data } = await apiJson(`${INQUIRIES_PATH}/owner`, {
          method: "GET", signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(errorMessage(response, data, "Could not load rental inquiries."));
        }
        if (!Array.isArray(data?.inquiries)) {
          throw new Error("The server returned an invalid inquiry list.");
        }
        if (!controller.signal.aborted) setInquiries(data.inquiries);
      } catch (caught) {
        if (!controller.signal.aborted) {
          setError(caught?.message || "Could not connect to the Dormora backend.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [isOwner, refreshKey]);

  const counts = useMemo(() => ({
    total: inquiries.length,
    pending: inquiries.filter((row) => row.status === "pending").length,
    accepted: inquiries.filter((row) => row.status === "accepted").length,
    rejected: inquiries.filter((row) => row.status === "rejected").length,
  }), [inquiries]);

  const visible = useMemo(() => {
    const searchText = query.trim().toLowerCase();
    return inquiries.filter((item) => {
      if (statusFilter !== "all" && item.status !== statusFilter) return false;
      if (!searchText) return true;
      return `${item.property_name || ""} ${item.renter_username || ""}`
        .toLowerCase().includes(searchText);
    });
  }, [inquiries, query, statusFilter]);

  async function submitDecision(inquiryId, decision) {
    if (busyId !== null || !isOwner || !["accepted", "rejected"].includes(decision)) return;
    const target = inquiries.find((item) => item.id === inquiryId);
    if (!target || target.status !== "pending") return;

    setBusyId(inquiryId);
    setNotice(null);
    try {
      // A new signed CSRF cookie/header pair for each state-changing request.
      const csrf = await apiJson("/api/csrf", { method: "GET" });
      if (!csrf.response.ok || typeof csrf.data?.csrf_token !== "string" || !csrf.data.csrf_token) {
        throw new Error(errorMessage(csrf.response, csrf.data, "Could not obtain a CSRF token."));
      }

      const { response, data } = await apiJson(
        `${INQUIRIES_PATH}/${inquiryId}/review`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf.data.csrf_token,
          },
          body: JSON.stringify({ decision }),
        },
      );

      if (!response.ok) {
        setNotice({ type: "error", text: errorMessage(response, data, "Could not review this inquiry.") });
      } else {
        setNotice({
          type: "success",
          text: decision === "accepted"
            ? "Inquiry accepted. This does not assign a room or create a tenancy."
            : "Inquiry rejected successfully.",
        });
      }
    } catch (caught) {
      // The POST may have reached PostgreSQL; never auto-repeat the decision.
      setNotice({
        type: "error",
        text: `${caught?.message || "Connection problem."} The request may have been processed. Review the refreshed status before trying again.`,
      });
    } finally {
      setConfirming(null);
      setBusyId(null);
      refresh();
    }
  }

  if (!isOwner) {
    return (
      <section className="oi-page">
        <style>{styles}</style>
        <div className="oi-state" role="alert">
          <Building2 size={33} />
          <h3>Property Owner Access Required</h3>
          <p>Incoming rental inquiries are available only to registered property owners.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="oi-page">
      <style>{styles}</style>
      <div className="oi-head">
        <div>
          <h1>Rental Inquiries</h1>
          <p>Review requests and reply to renters interested in your properties.</p>
        </div>
        <div className="oi-head-actions">
          {typeof onBack === "function" && (
            <button type="button" className="oi-btn" onClick={onBack}>
              <ArrowLeft size={16} /> Home
            </button>
          )}
          <button type="button" className="oi-btn" onClick={refresh} disabled={loading || busyId !== null}>
            <RefreshCw size={16} /> Refresh
          </button>
        </div>
      </div>

      <div className="oi-summary" aria-label="Inquiry statistics">
        {[
          ["Total Inquiries", counts.total, Inbox],
          ["Pending", counts.pending, Clock3],
          ["Accepted", counts.accepted, CheckCircle2],
          ["Rejected", counts.rejected, XCircle],
        ].map(([label, number, Icon]) => (
          <div className="oi-summary-item" key={label}>
            <span><Icon size={17} /> {label}</span>
            <strong>{number}</strong>
          </div>
        ))}
      </div>

      {notice && (
        <div className={`oi-notice ${notice.type === "error" ? "error" : ""}`}
          role={notice.type === "error" ? "alert" : "status"}>
          <ShieldCheck size={18} /><span>{notice.text}</span>
        </div>
      )}

      <div className="oi-tools">
        <label className="oi-search">
          <Search size={17} />
          <input
            type="search"
            aria-label="Search inquiries by property or renter"
            placeholder="Search by property or renter username"
            value={query}
            maxLength={100}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="oi-filter">
          Status
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            aria-label="Filter inquiries by status"
          >
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
            <option value="withdrawn">Withdrawn</option>
          </select>
        </label>
      </div>

      <p className="oi-results">
        {loading ? "Loading inquiries..." : `${visible.length} ${visible.length === 1 ? "inquiry" : "inquiries"} shown`}
      </p>

      {loading ? (
        <div className="oi-state" role="status">
          <RefreshCw size={32} />
          <h3>Loading Inquiries</h3>
          <p>Retrieving renter requests from Dormora.</p>
        </div>
      ) : error ? (
        <div className="oi-state" role="alert">
          <XCircle size={32} />
          <h3>Unable to Load Inquiries</h3>
          <p>{error}</p>
          <button type="button" className="oi-btn primary" onClick={refresh}>Try Again</button>
        </div>
      ) : visible.length === 0 ? (
        <div className="oi-state">
          <Inbox size={34} />
          <h3>{inquiries.length === 0 ? "No Rental Inquiries Yet" : "No Matching Inquiries"}</h3>
          <p>{inquiries.length === 0
            ? "When renters submit inquiries for your properties, you can review them here."
            : "Try another property name, renter username, or status filter."}</p>
        </div>
      ) : (
        <div className="oi-list">
          {visible.map((item) => {
            const isPending = item.status === "pending";
            const openConfirmation = confirming?.id === item.id ? confirming : null;
            return (
              <article key={item.id} className="oi-card">
                <div className="oi-card-top">
                  <div>
                    <h2>{item.property_name || `Property #${item.property_id}`}</h2>
                    <div className="oi-card-meta">
                      <MapPin size={14} /> Property ID #{item.property_id} · Inquiry #{item.id}
                    </div>
                  </div>
                  <StatusBadge status={item.status} />
                </div>

                <div className="oi-details">
                  <div>
                    <div className="oi-detail-label"><UserRound size={14} /> Renter</div>
                    <div className="oi-detail-value">{item.renter_username || "Unknown renter"}</div>
                  </div>
                  <div>
                    <div className="oi-detail-label"><CalendarDays size={14} /> Preferred move-in</div>
                    <div className="oi-detail-value">{formatMoveInDate(item.preferred_move_in_date)}</div>
                  </div>
                  <div>
                    <div className="oi-detail-label"><Clock3 size={14} /> Received</div>
                    <div className="oi-detail-value">{formatDate(item.created_at)}</div>
                  </div>
                </div>

                <div className="oi-message">
                  <h3><MessageSquareText size={15} /> Renter's message</h3>
                  <p>{item.message || "No message was provided."}</p>
                </div>

                <div className="oi-footer">
                  <small>
                    {item.reviewed_at
                      ? `Reviewed: ${formatDate(item.reviewed_at)}`
                      : "Reviewing an inquiry does not assign a room or create rent records."}
                  </small>
                  <div className="oi-actions">
                    <button type="button" className="oi-btn"
                      aria-expanded={openThreadId === item.id}
                      aria-controls={`oi-thread-${item.id}`}
                      onClick={() => setOpenThreadId((current) => current === item.id ? null : item.id)}>
                      <MessagesSquare size={16} />
                      {openThreadId === item.id ? "Hide Conversation" : "View Conversation"}
                    </button>
                    {isPending && (
                      <>
                        <button type="button" className="oi-btn"
                          disabled={busyId !== null}
                          onClick={() => setConfirming({ id: item.id, decision: "rejected" })}>
                          <X size={16} /> Reject
                        </button>
                        <button type="button" className="oi-btn primary"
                          disabled={busyId !== null}
                          onClick={() => setConfirming({ id: item.id, decision: "accepted" })}>
                          <Check size={16} /> Accept
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {openConfirmation && isPending && (
                  <div className="oi-confirm" role="group"
                    aria-label={`Confirm ${openConfirmation.decision} inquiry ${item.id}`}>
                    <strong>
                      {openConfirmation.decision === "accepted" ? "Accept this inquiry?" : "Reject this inquiry?"}
                    </strong>
                    <p>
                      {openConfirmation.decision === "accepted"
                        ? "The renter will see an accepted status. This will not reserve a room or create a tenancy."
                        : "The renter will see a rejected status. This inquiry cannot be reviewed again."}
                    </p>
                    <div className="oi-confirm-actions">
                      <button type="button" className="oi-btn"
                        disabled={busyId !== null} onClick={() => setConfirming(null)}>
                        Cancel
                      </button>
                      <button type="button" className="oi-btn primary"
                        disabled={busyId !== null}
                        onClick={() => submitDecision(item.id, openConfirmation.decision)}>
                        {busyId === item.id ? "Saving..." : `Confirm ${openConfirmation.decision === "accepted" ? "Acceptance" : "Rejection"}`}
                      </button>
                    </div>
                  </div>
                )}

                {openThreadId === item.id && (
                  <InquiryConversation key={`${item.id}-${refreshKey}`} inquiryId={item.id} />
                )}
              </article>
            );
          })}
        </div>
      )}

      <p className="oi-footnote">
        Rental inquiries are expressions of interest only. Accepted inquiries will require
        separate tenant assignment and rent-tracking steps.
      </p>
    </section>
  );
}
