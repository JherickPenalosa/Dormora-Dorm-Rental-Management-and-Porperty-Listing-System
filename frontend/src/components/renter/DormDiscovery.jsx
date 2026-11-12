/**
 * DORMORA — SYSTEM FUNCTIONALITY FILE 23
 * REPLACE: frontend/src/components/renter/DormDiscovery.jsx
 *
 * Published property discovery + authenticated rental inquiry form.
 * Existing authentication and CSRF protections are enforced by FastAPI.
 * This form never reserves a room, assigns a tenant, or takes payment.
 */
import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft, ArrowRight, Building2, CalendarDays, CheckCircle2,
  DoorOpen, ImageIcon, Info, MapPin, RefreshCw, Search, Send,
  ShieldCheck, SlidersHorizontal, X,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const DISCOVERY_PATH = "/api/renter/discovery";
const INQUIRY_PATH = "/api/rental-inquiries";

const styles = `
.dd-page{width:100%;min-width:0;color:var(--text);font-family:inherit}
.dd-page *{box-sizing:border-box}
.dd-header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:22px}
.dd-header h1{font-size:clamp(25px,3vw,32px);margin:0 0 8px;font-weight:800}
.dd-header p{color:var(--muted);margin:0;font-size:14px;line-height:1.7}
.dd-button{display:inline-flex;align-items:center;justify-content:center;gap:9px;min-height:42px;padding:11px 15px;border:1px solid var(--border);border-radius:11px;background:var(--card);color:var(--text);font:inherit;font-size:13px;font-weight:700;cursor:pointer}
.dd-button:hover:not(:disabled){filter:brightness(.96)}
.dd-button:disabled{opacity:.55;cursor:not-allowed}
.dd-button.primary{background:var(--primary);border-color:var(--primary);color:#fff}
.dd-page button:focus-visible,.dd-page input:focus-visible,.dd-page select:focus-visible,.dd-page textarea:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.dd-intro{background:var(--card);border:1px solid var(--border);border-radius:17px;padding:24px;margin-bottom:20px}
.dd-intro-top{display:flex;gap:12px;align-items:center;margin-bottom:13px}
.dd-intro-icon{display:grid;place-items:center;width:42px;height:42px;flex-shrink:0;border-radius:12px;background:var(--soft);color:var(--primary)}
.dd-intro h2{margin:0;font-size:19px;font-weight:800}
.dd-intro p{color:var(--muted);font-size:13px;line-height:1.7;margin:0;max-width:800px}
.dd-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:20px 0 14px}
.dd-search{flex:1;min-width:210px;display:flex;align-items:center;gap:10px;border:1px solid var(--border);border-radius:11px;background:var(--card);padding:0 13px;color:var(--muted)}
.dd-search input{border:0;outline:0;flex:1;min-width:0;padding:13px 0;background:transparent;color:var(--text);font:inherit;font-size:13px}
.dd-search button{display:grid;place-items:center;border:0;background:transparent;color:var(--muted);cursor:pointer;padding:4px}
.dd-select-wrap{display:flex;align-items:center;gap:9px;background:var(--card);border:1px solid var(--border);border-radius:11px;padding:0 12px}
.dd-select-wrap svg{color:var(--primary)}
.dd-select{border:0;outline:0;background:transparent;color:var(--text);font:inherit;font-size:13px;padding:12px 4px;cursor:pointer}
.dd-select option{color:var(--text);background:var(--card)}
.dd-filter-row{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:17px}
.dd-filter-row p{color:var(--muted);font-size:13px;margin:0}
.dd-filter{display:flex;align-items:center;gap:9px;font-size:13px;color:var(--text);cursor:pointer}
.dd-filter input{width:16px;height:16px;accent-color:var(--primary)}
.dd-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:17px}
.dd-card{overflow:hidden;min-width:0;background:var(--card);border:1px solid var(--border);border-radius:16px;display:flex;flex-direction:column}
.dd-card-photo{position:relative;height:235px;background:var(--soft)}
.dd-photo{display:block;width:100%;height:100%;object-fit:cover}
.dd-photo-fallback{width:100%;height:100%;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:9px;background:var(--soft);color:var(--muted);font-size:12px}
.dd-card-badge{position:absolute;top:13px;left:13px;display:inline-flex;align-items:center;gap:6px;padding:7px 10px;border-radius:8px;font-size:11px;font-weight:800;background:rgba(9,33,27,.86);color:#b8ffe2}
.dd-card-badge.full{color:#fff;background:rgba(38,45,43,.86)}
.dd-card-content{padding:18px;flex:1;display:flex;flex-direction:column}
.dd-card-content h3{font-size:18px;margin:0 0 9px;line-height:1.4}
.dd-address{display:flex;align-items:flex-start;gap:7px;color:var(--muted);font-size:12px;line-height:1.6}
.dd-address svg{flex-shrink:0;margin-top:2px}
.dd-description{color:var(--muted);font-size:13px;line-height:1.7;margin:15px 0;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;line-clamp:3;overflow:hidden}
.dd-card-bottom{margin-top:auto;padding-top:15px;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:12px}
.dd-price{display:flex;flex-direction:column;gap:4px}
.dd-price strong{font-size:20px;color:var(--primary)}
.dd-price span{color:var(--muted);font-size:11px}
.dd-state{padding:48px 24px;background:var(--card);border:1px dashed var(--border);border-radius:16px;text-align:center;display:flex;align-items:center;flex-direction:column;gap:12px}
.dd-state svg{color:var(--primary)}
.dd-state h3{margin:0;font-size:18px}
.dd-state p{max-width:500px;font-size:13px;line-height:1.7;color:var(--muted);margin:0}
.dd-detail{background:var(--card);border:1px solid var(--border);border-radius:17px;overflow:hidden}
.dd-detail-gallery{padding:16px}
.dd-detail-main-photo{width:100%;height:clamp(240px,42vw,430px);border-radius:12px;overflow:hidden;background:var(--soft)}
.dd-gallery-thumbs{display:flex;flex-wrap:wrap;gap:9px;margin-top:12px}
.dd-photo-thumb{width:83px;height:65px;border:2px solid var(--border);background:var(--soft);border-radius:9px;padding:0;overflow:hidden;cursor:pointer}
.dd-photo-thumb.active{border-color:var(--primary)}
.dd-detail-body{padding:6px 24px 25px}
.dd-detail-heading{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:19px}
.dd-detail-heading h2{font-size:25px;margin:0 0 10px}
.dd-detail-rent{color:var(--primary);font-size:24px;font-weight:800;white-space:nowrap}
.dd-detail-rent span{display:block;color:var(--muted);font-size:12px;font-weight:500;text-align:right}
.dd-detail-stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:20px}
.dd-detail-stat{background:var(--soft);border-radius:12px;padding:15px;display:flex;align-items:center;gap:12px}
.dd-detail-stat svg{color:var(--primary);flex-shrink:0}
.dd-detail-stat strong{display:block;font-size:19px}
.dd-detail-stat span{font-size:12px;color:var(--muted)}
.dd-detail-body h3{margin:20px 0 9px;font-size:17px}
.dd-full-description{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--muted);font-size:14px;line-height:1.8}
.dd-info{margin-top:22px;background:var(--soft);border:1px solid var(--border);border-radius:12px;padding:14px;font-size:12px;color:var(--muted);line-height:1.7}
.dd-inquiry{margin-top:24px;padding:22px;border:1px solid var(--border);border-radius:15px;background:var(--background)}
.dd-inquiry-heading{display:flex;align-items:center;gap:11px;margin-bottom:7px}
.dd-inquiry-heading svg{color:var(--primary)}
.dd-inquiry-heading h3{font-size:18px;margin:0}
.dd-inquiry-subtitle{margin:0 0 18px;color:var(--muted);font-size:13px;line-height:1.7}
.dd-form{display:grid;gap:16px}
.dd-field{display:grid;gap:7px;font-size:13px;font-weight:700}
.dd-field span{color:var(--text)}
.dd-field input,.dd-field textarea{display:block;width:100%;min-width:0;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);padding:12px 13px;font:inherit;font-size:13px;line-height:1.6}
.dd-field textarea{min-height:120px;resize:vertical}
.dd-field small{color:var(--muted);font-size:12px;font-weight:400;line-height:1.5}
.dd-form-footer{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
.dd-form-footer p{margin:0;color:var(--muted);font-size:12px;line-height:1.6;max-width:430px}
.dd-notice{border:1px solid var(--border);border-radius:11px;background:var(--soft);padding:13px 15px;font-size:13px;line-height:1.6;margin:12px 0;display:flex;align-items:flex-start;gap:10px;color:var(--text)}
.dd-notice svg{flex-shrink:0;color:var(--primary);margin-top:2px}
.dd-notice.error{border-color:#cf6a65;background:var(--card)}
.dd-notice.error svg{color:#cf6a65}
.dd-notice strong{display:block;margin-bottom:2px}
.dd-notice p{margin:0;color:var(--muted)}
.dd-tools-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
@media(max-width:900px){.dd-grid{grid-template-columns:1fr}}
@media(max-width:650px){.dd-header{flex-direction:column}.dd-toolbar{flex-direction:column;align-items:stretch}.dd-search{width:100%}.dd-detail-heading{flex-direction:column}.dd-detail-rent span{text-align:left}.dd-detail-body{padding:4px 16px 20px}.dd-detail-stats{grid-template-columns:1fr}.dd-card-bottom{flex-wrap:wrap}.dd-inquiry{padding:15px}}
`;

function formatPeso(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return "—";
  return new Intl.NumberFormat("en-PH", {
    style: "currency", currency: "PHP",
    minimumFractionDigits: 0, maximumFractionDigits: 2,
  }).format(number);
}

function todayInManila() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Manila", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

async function apiJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    mode: "cors",
    credentials: "include",
    cache: "no-store",
    redirect: "error",
    headers: { Accept: "application/json", ...options.headers },
    ...options,
  });
  let data = null;
  try { data = await response.json(); } catch { /* Non-JSON response. */ }
  return { response, data };
}

function errorMessage(response, data, fallback) {
  if (response.status === 401) return "Your session expired. Please sign in again.";
  if (response.status === 403) return "This action is not permitted. Check your account or refresh the page.";
  if (response.status === 404) return "This property or endpoint is no longer available.";
  if (response.status === 409) return "You already have a pending inquiry for this property.";
  if (typeof data?.detail === "string" && data.detail) return data.detail;
  if (response.status === 422) return "Please check the inquiry fields and try again.";
  return fallback;
}

async function findPendingInquiry(propertyId, signal) {
  const { response, data } = await apiJson(`${INQUIRY_PATH}/mine`, { signal });
  if (!response.ok) {
    throw new Error(errorMessage(response, data, "Unable to check your existing inquiries."));
  }
  if (!Array.isArray(data?.inquiries)) {
    throw new Error("Unexpected inquiry list returned by the server.");
  }
  return data.inquiries.find(
    (inquiry) => Number(inquiry.property_id) === Number(propertyId) && inquiry.status === "pending"
  ) || null;
}

function PropertyImage({ src, alt }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  if (!src || failed) {
    return <div className="dd-photo-fallback"><ImageIcon size={36} /><span>No photo available</span></div>;
  }
  return (
    <img className="dd-photo" src={src} alt={alt} loading="lazy"
      referrerPolicy="no-referrer" onError={() => setFailed(true)} />
  );
}

function AvailabilityBadge({ available }) {
  const count = Math.max(0, Number(available) || 0);
  const hasRooms = count > 0;
  return (
    <span className={`dd-card-badge ${hasRooms ? "" : "full"}`}>
      {hasRooms ? <CheckCircle2 size={13} /> : <DoorOpen size={13} />}
      {hasRooms ? `${count} ${count === 1 ? "room" : "rooms"} available` : "No available rooms"}
    </span>
  );
}

function PropertyCard({ property, onView }) {
  return (
    <article className="dd-card">
      <div className="dd-card-photo">
        <PropertyImage src={property.cover_photo_url} alt={`${property.name} property photo`} />
        <AvailabilityBadge available={property.available_rooms} />
      </div>
      <div className="dd-card-content">
        <h3>{property.name}</h3>
        <div className="dd-address"><MapPin size={15} /><span>{property.address}</span></div>
        <p className="dd-description">{property.description || "No description provided."}</p>
        <div className="dd-card-bottom">
          <div className="dd-price"><strong>{formatPeso(property.monthly_rent)}</strong><span>Per month</span></div>
          <button className="dd-button primary" type="button" onClick={() => onView(property.id)}>
            View Details <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </article>
  );
}

function InquiryForm({ property }) {
  const [message, setMessage] = useState("");
  const [preferredDate, setPreferredDate] = useState("");
  const [pendingInquiry, setPendingInquiry] = useState(null);
  const [checking, setChecking] = useState(true);
  const [lookupError, setLookupError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [recheck, setRecheck] = useState(0);
  const hasRooms = Number(property.available_rooms) > 0;
  const earliestDate = todayInManila();

  useEffect(() => {
    const controller = new AbortController();
    setChecking(true);
    setLookupError("");
    (async () => {
      try {
        const existing = await findPendingInquiry(property.id, controller.signal);
        if (!controller.signal.aborted) {
          setPendingInquiry(existing);
          if (existing) setFeedback(null);
        }
      } catch (error) {
        if (!controller.signal.aborted) setLookupError(error.message || "Could not verify inquiry status.");
      } finally {
        if (!controller.signal.aborted) setChecking(false);
      }
    })();
    return () => controller.abort();
  }, [property.id, recheck]);

  async function submitInquiry(event) {
    event.preventDefault();
    if (submitting || checking || pendingInquiry || !hasRooms) return;

    const cleanMessage = message.trim();
    if (cleanMessage.length > 1000) {
      setFeedback({ type: "error", text: "Message must be 1000 characters or fewer." });
      return;
    }
    if (preferredDate && preferredDate < earliestDate) {
      setFeedback({ type: "error", text: "Choose a future move-in date." });
      return;
    }

    setSubmitting(true);
    setFeedback(null);
    let postStarted = false;

    try {
      // Same signed-cookie + X-CSRF-Token flow as Dormora's login forms.
      const csrf = await apiJson("/api/csrf");
      if (!csrf.response.ok || typeof csrf.data?.csrf_token !== "string" || !csrf.data.csrf_token) {
        throw new Error(errorMessage(csrf.response, csrf.data, "Could not obtain a CSRF token. Refresh and try again."));
      }

      postStarted = true;
      const { response, data } = await apiJson(INQUIRY_PATH, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf.data.csrf_token,
        },
        body: JSON.stringify({
          property_id: property.id,
          message: cleanMessage || null,
          preferred_move_in_date: preferredDate || null,
        }),
      });

      if (response.status === 201) {
        setPendingInquiry({ id: data?.id ?? null, property_id: property.id, status: "pending" });
        setFeedback({ type: "success", text: "Your rental inquiry was submitted and is awaiting the property owner's review." });
        return;
      }

      if (response.status === 409) {
        // Database uniqueness prevents a second pending request.
        try {
          const existing = await findPendingInquiry(property.id);
          if (existing) setPendingInquiry(existing);
        } catch { /* Keep the server response; never retry automatically. */ }
        setFeedback({ type: "info", text: errorMessage(response, data, "You already have a pending inquiry.") });
        return;
      }

      // A received HTTP response is a definite rejection, not an unknown outcome.
      setFeedback({
        type: "error",
        text: errorMessage(response, data, "The inquiry could not be submitted."),
      });
    } catch (error) {
      if (postStarted) {
        // A connection failure after POST may have occurred after a DB commit.
        // Check the server before allowing another attempt.
        try {
          const existing = await findPendingInquiry(property.id);
          if (existing) {
            setPendingInquiry(existing);
            setFeedback({ type: "info", text: "A pending inquiry was found. Please review your inquiries before taking further action." });
          } else {
            setFeedback({ type: "uncertain", text: "The connection was interrupted, so submission could not be confirmed. Check your inquiry status before trying again." });
          }
        } catch {
          setFeedback({ type: "uncertain", text: "Submission status is unknown. Do not submit again until you have checked your existing inquiries." });
        }
      } else {
        setFeedback({ type: "error", text: error.message || "Could not connect to Dormora." });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="dd-inquiry" aria-labelledby="dd-inquiry-title">
      <div className="dd-inquiry-heading"><Send size={21} /><h3 id="dd-inquiry-title">Send a Rental Inquiry</h3></div>
      <p className="dd-inquiry-subtitle">
        Ask the property owner about renting a room. Sending an inquiry does not reserve a room or create a payment.
      </p>

      {checking && (
        <div className="dd-notice" role="status"><RefreshCw size={17} /><span>Checking your existing inquiries...</span></div>
      )}
      {!checking && pendingInquiry && (
        <div className="dd-notice" role="status">
          <CheckCircle2 size={18} />
          <div><strong>Inquiry pending</strong><p>You already have a pending inquiry for this property. The owner can review it. You cannot send another pending inquiry.</p></div>
        </div>
      )}
      {!checking && lookupError && !pendingInquiry && (
        <div className="dd-notice" role="alert">
          <Info size={18} /><div><strong>Inquiry status unavailable</strong><p>{lookupError}</p></div>
        </div>
      )}
      {!hasRooms && !pendingInquiry && (
        <div className="dd-notice"><Info size={18} /><span>This property currently has no available rooms, so new inquiries are disabled.</span></div>
      )}

      {feedback && (
        <div className={`dd-notice ${feedback.type === "error" ? "error" : ""}`} role="status">
          {feedback.type === "success" ? <CheckCircle2 size={18} /> : <Info size={18} />}
          <span>{feedback.text}</span>
        </div>
      )}

      {!pendingInquiry && hasRooms && (
        <form className="dd-form" onSubmit={submitInquiry}>
          <label className="dd-field">
            <span>Message to the owner (optional)</span>
            <textarea value={message} onChange={(event) => setMessage(event.target.value)}
              maxLength={1000} disabled={submitting || checking || feedback?.type === "uncertain"}
              placeholder="Hello! I'm interested in this property. May I ask about the available rooms?" />
            <small>{message.length}/1000 characters. Please do not include passwords or sensitive account information.</small>
          </label>
          <label className="dd-field">
            <span>Preferred move-in date (optional)</span>
            <input type="date" min={earliestDate} value={preferredDate}
              disabled={submitting || checking || feedback?.type === "uncertain"}
              onChange={(event) => setPreferredDate(event.target.value)} />
          </label>
          <div className="dd-form-footer">
            <p>Only the owner of this property can review your inquiry. An accepted inquiry is not yet a room assignment.</p>
            <div className="dd-tools-row">
              {(lookupError || feedback?.type === "uncertain") && (
                <button className="dd-button" type="button" disabled={checking || submitting}
                  onClick={() => setRecheck((value) => value + 1)}>
                  <RefreshCw size={16} /> Check Status
                </button>
              )}
              <button className="dd-button primary" type="submit"
                disabled={checking || submitting || feedback?.type === "uncertain"}>
                {submitting ? <RefreshCw size={16} /> : <Send size={16} />}
                {submitting ? "Submitting..." : "Send Inquiry"}
              </button>
            </div>
          </div>
        </form>
      )}
    </section>
  );
}

function DiscoveryDetail({ property, onBack }) {
  const [photoIndex, setPhotoIndex] = useState(0);
  const images = Array.isArray(property.photo_urls) ? property.photo_urls : [];
  const activeImage = images[photoIndex] || images[0] || "";

  return (
    <>
      <div className="dd-header">
        <div><h1>Property Details</h1><p>View rooms, photos, and send an inquiry to the owner.</p></div>
        <button className="dd-button" type="button" onClick={onBack}><ArrowLeft size={17} /> Back to Results</button>
      </div>
      <article className="dd-detail">
        <div className="dd-detail-gallery">
          <div className="dd-detail-main-photo">
            <PropertyImage src={activeImage} alt={`${property.name} photo ${photoIndex + 1}`} />
          </div>
          {images.length > 1 && (
            <div className="dd-gallery-thumbs">
              {images.map((url, index) => (
                <button key={`${url}-${index}`} className={`dd-photo-thumb ${photoIndex === index ? "active" : ""}`}
                  type="button" aria-label={`View property photo ${index + 1}`}
                  aria-pressed={photoIndex === index} onClick={() => setPhotoIndex(index)}>
                  <PropertyImage src={url} alt={`Thumbnail ${index + 1}`} />
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="dd-detail-body">
          <div className="dd-detail-heading">
            <div><h2>{property.name}</h2><div className="dd-address"><MapPin size={16} /><span>{property.address}</span></div></div>
            <div className="dd-detail-rent">{formatPeso(property.monthly_rent)}<span>per month</span></div>
          </div>
          <div className="dd-detail-stats">
            <div className="dd-detail-stat"><Building2 size={23} /><div><strong>{property.total_rooms ?? "—"}</strong><span>Total Rooms</span></div></div>
            <div className="dd-detail-stat"><DoorOpen size={23} /><div><strong>{property.available_rooms ?? "—"}</strong><span>Available Rooms</span></div></div>
          </div>
          <h3>About This Property</h3>
          <p className="dd-full-description">{property.description || "No property description available."}</p>
          <div className="dd-info"><ShieldCheck size={15} style={{ verticalAlign: "middle", marginRight: 7 }} />
            Published Dormora property. Viewing a listing or sending an inquiry never charges you or reserves a room.
          </div>
          <InquiryForm key={property.id} property={property} />
        </div>
      </article>
    </>
  );
}

export default function DormDiscovery({ account, onBack }) {
  const isRenter = account?.role === "renter";
  const [search, setSearch] = useState("");
  const [sortOrder, setSortOrder] = useState("newest");
  const [availableOnly, setAvailableOnly] = useState(false);
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadCount, setReloadCount] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedProperty, setSelectedProperty] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    if (!isRenter) { setLoading(false); return undefined; }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ search: search.trim(), limit: "50" });
        const { response, data } = await apiJson(`${DISCOVERY_PATH}?${params.toString()}`, { signal: controller.signal });
        if (!response.ok) throw new Error(errorMessage(response, data, "Unable to load dorm listings."));
        if (!Array.isArray(data?.properties)) throw new Error("Unexpected property list from the server.");
        if (!controller.signal.aborted) setProperties(data.properties);
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught.message || "Could not connect to Dormora.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, search.trim() ? 350 : 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [isRenter, search, reloadCount]);

  useEffect(() => {
    if (!isRenter || selectedId === null) return undefined;
    const controller = new AbortController();
    setDetailLoading(true);
    setDetailError("");
    setSelectedProperty(null);
    (async () => {
      try {
        const { response, data } = await apiJson(`${DISCOVERY_PATH}/${selectedId}`, { signal: controller.signal });
        if (!response.ok) throw new Error(errorMessage(response, data, "Unable to load property details."));
        if (!data?.property || typeof data.property !== "object") throw new Error("Unexpected property details returned by the server.");
        if (!controller.signal.aborted) setSelectedProperty(data.property);
      } catch (caught) {
        if (!controller.signal.aborted) setDetailError(caught.message || "Unable to load property details.");
      } finally {
        if (!controller.signal.aborted) setDetailLoading(false);
      }
    })();
    return () => controller.abort();
  }, [isRenter, selectedId]);

  const visibleProperties = useMemo(() => {
    const results = properties.filter((property) => !availableOnly || Number(property.available_rooms) > 0);
    if (sortOrder === "price-low") results.sort((a, b) => Number(a.monthly_rent) - Number(b.monthly_rent));
    else if (sortOrder === "price-high") results.sort((a, b) => Number(b.monthly_rent) - Number(a.monthly_rent));
    else if (sortOrder === "rooms") results.sort((a, b) => Number(b.available_rooms) - Number(a.available_rooms));
    return results;
  }, [properties, availableOnly, sortOrder]);

  function returnToResults() { setSelectedId(null); setSelectedProperty(null); setDetailError(""); }

  if (!isRenter) {
    return <section className="dd-page"><style>{styles}</style><div className="dd-state" role="alert">
      <Building2 size={36} /><h3>Renter Access Required</h3><p>This page is available to registered renter accounts.</p>
    </div></section>;
  }

  if (selectedId !== null) {
    return <section className="dd-page"><style>{styles}</style>
      {detailLoading ? (
        <div className="dd-state" role="status"><RefreshCw size={33} /><h3>Loading Property Details</h3><p>Retrieving the latest information from Dormora.</p></div>
      ) : detailError ? (
        <div className="dd-state" role="alert"><Building2 size={33} /><h3>Property Unavailable</h3><p>{detailError}</p>
          <button className="dd-button" type="button" onClick={returnToResults}><ArrowLeft size={16} /> Back to Results</button></div>
      ) : selectedProperty ? (
        <DiscoveryDetail key={selectedProperty.id} property={selectedProperty} onBack={returnToResults} />
      ) : null}
    </section>;
  }

  return (
    <section className="dd-page"><style>{styles}</style>
      <div className="dd-header">
        <div><h1>Discover Dorms</h1><p>Find a rental property that matches your location, budget, and room availability.</p></div>
        <div className="dd-tools-row">
          {onBack && <button className="dd-button" type="button" onClick={onBack}><ArrowLeft size={17} /> Home</button>}
          <button className="dd-button" type="button" onClick={() => setReloadCount((value) => value + 1)} disabled={loading}><RefreshCw size={16} /> Refresh</button>
        </div>
      </div>
      <div className="dd-intro">
        <div className="dd-intro-top"><div className="dd-intro-icon"><Building2 size={24} /></div><h2>Find Your Next Place</h2></div>
        <p>Explore dormitories, apartments, boarding houses, and rental rooms published by registered Dormora property owners. View photos, compare prices, and send a rental inquiry.</p>
      </div>
      <div className="dd-toolbar">
        <label className="dd-search"><Search size={18} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)}
          placeholder="Search by property name or location" aria-label="Search dorm properties" maxLength={100} />
          {search && <button type="button" aria-label="Clear search" onClick={() => setSearch("")}><X size={16} /></button>}</label>
        <label className="dd-select-wrap"><SlidersHorizontal size={17} />
          <select className="dd-select" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)} aria-label="Sort properties">
            <option value="newest">Newest Listings</option><option value="price-low">Lowest Price</option>
            <option value="price-high">Highest Price</option><option value="rooms">Most Available Rooms</option>
          </select>
        </label>
      </div>
      <div className="dd-filter-row">
        <p>{loading ? "Loading published listings..." : error ? "Listings unavailable" : `${visibleProperties.length} ${visibleProperties.length === 1 ? "property" : "properties"} found`}</p>
        <label className="dd-filter"><input type="checkbox" checked={availableOnly} onChange={(event) => setAvailableOnly(event.target.checked)} /> Show available rooms only</label>
      </div>
      {loading ? (
        <div className="dd-state" role="status"><RefreshCw size={34} /><h3>Searching Dormora Properties</h3><p>Retrieving published listings from the server.</p></div>
      ) : error ? (
        <div className="dd-state" role="alert"><Building2 size={36} /><h3>Unable to Load Dorms</h3><p>{error}</p>
          <button className="dd-button primary" type="button" onClick={() => setReloadCount((value) => value + 1)}><RefreshCw size={16} /> Try Again</button></div>
      ) : visibleProperties.length === 0 ? (
        <div className="dd-state"><Search size={36} /><h3>No Matching Properties</h3>
          <p>{search.trim() || availableOnly ? "No published properties match your search or filters." : "No properties have been published yet. Check back when owners publish their listings."}</p>
          {(search || availableOnly) && <button className="dd-button" type="button" onClick={() => { setSearch(""); setAvailableOnly(false); }}>Clear Filters</button>}</div>
      ) : (
        <div className="dd-grid">{visibleProperties.map((property) => <PropertyCard key={property.id} property={property} onView={setSelectedId} />)}</div>
      )}
    </section>
  );
}
