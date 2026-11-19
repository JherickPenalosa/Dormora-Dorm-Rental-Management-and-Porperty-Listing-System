
/*
 * DORMORA — SYSTEM FUNCTIONALITY FILE 13
 * REPLACE: frontend/src/components/owner/MyProperties.jsx
 *
 * Adds Edit and Publish controls to the working property listing page.
 * Retains photo upload (3–8 images), owner listings, summaries, search,
 * and high-contrast photo overlays for light/dark themes.
 * Uses File 12's POST /{property_id}/edit and /{property_id}/publish endpoints.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft, Building2, Camera, CheckCircle2, DoorOpen,
  ImagePlus, MapPin, Pencil, Plus, Search, Send, Trash2, X,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const OWNER_URL = `${API_BASE}/api/owner/properties`;
const MAX_PHOTOS = 8;
const MAX_PHOTO_SIZE = 5 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

const EMPTY_FORM = {
  name: "",
  address: "",
  description: "",
  monthly_rent: "",
  total_rooms: "",
  available_rooms: "",
};

const styles = `
.mp-page{width:100%;color:var(--text)}.mp-page *{box-sizing:border-box}
.mp-header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:22px}
.mp-heading h1{font-size:clamp(24px,3vw,31px);margin:0 0 6px}.mp-heading p{font-size:14px;color:var(--muted);margin:0;line-height:1.6}
.mp-header-actions,.mp-form-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.mp-button{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:11px 15px;min-height:42px;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);font:inherit;font-size:13px;font-weight:700;cursor:pointer}
.mp-button.primary{background:var(--primary);color:var(--background);border-color:var(--primary)}
.mp-button:disabled{opacity:.5;cursor:not-allowed}.mp-button:focus-visible,.mp-field:focus-visible,.mp-upload:focus-within{outline:3px solid var(--primary);outline-offset:2px}
.mp-overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:22px}
.mp-stat{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:19px}
.mp-stat-heading{display:flex;justify-content:space-between;align-items:center;color:var(--muted);font-size:12px;gap:8px}.mp-stat-heading svg{color:var(--primary)}.mp-stat-value{margin:9px 0 0;font-weight:800;font-size:27px}
.mp-toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:20px 0 15px}.mp-toolbar h2{margin:0;font-size:18px}
.mp-search{display:flex;align-items:center;gap:9px;padding:0 12px;background:var(--card);border:1px solid var(--border);border-radius:10px;min-width:225px}.mp-search svg{color:var(--muted)}
.mp-search input{width:100%;padding:12px 0;border:0;outline:none;background:transparent;color:var(--text);font:inherit;font-size:13px}
.mp-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}
.mp-property{background:var(--card);border:1px solid var(--border);border-radius:15px;overflow:hidden;min-width:0}
.mp-property-cover{position:relative;height:290px;background:#17332d;overflow:hidden}
.mp-property-image{position:absolute;inset:0;width:100%;height:100%;display:grid;place-items:center;color:#d8f0e9}
.mp-property-image img{width:100%;height:100%;object-fit:cover;display:block}
.mp-property-cover::after{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,rgba(5,20,17,.04) 24%,rgba(5,20,17,.35) 56%,rgba(5,20,17,.94) 100%);pointer-events:none}
.mp-property-details{position:absolute;left:0;right:0;bottom:0;z-index:1;padding:22px;color:#fff}
.mp-property-details h3{font-size:18px;margin:0 0 8px;color:#fff;text-shadow:0 1px 3px #0008}
.mp-property-address{display:flex;align-items:center;gap:6px;font-size:12px;color:#e8f3ef}
.mp-property-meta{display:flex;flex-wrap:wrap;gap:13px;margin-top:14px;font-size:13px;color:#fff}
.mp-property-meta strong{color:#7af0cd}
.mp-property-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 15px;flex-wrap:wrap}
.mp-card-buttons{display:flex;gap:8px;flex-wrap:wrap}
.mp-card-buttons .mp-button{padding:8px 12px;min-height:36px;font-size:12px}
.mp-status{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:99px;padding:6px 11px;background:var(--soft);color:var(--muted);font-size:12px;font-weight:700;text-transform:capitalize}
.mp-status.published{color:var(--primary)}
.mp-empty{background:var(--card);border:1px dashed var(--border);border-radius:15px;text-align:center;padding:46px 24px;color:var(--muted)}
.mp-empty svg{color:var(--primary)}.mp-empty h3{color:var(--text);margin:12px 0 8px}.mp-empty p{max-width:450px;margin:0 auto;line-height:1.7;font-size:13px}
.mp-notice{background:var(--soft);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:13px 15px;margin:15px 0;font-size:13px;line-height:1.6}.mp-notice.error{border-color:#c96565}
.mp-form{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:23px;margin:0 0 24px}
.mp-form-header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px}.mp-form-header h2{margin:0;font-size:19px}
.mp-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.mp-label{display:grid;gap:8px;font-size:13px;font-weight:700}.mp-label.wide{grid-column:1/-1}
.mp-field{width:100%;min-width:0;padding:12px;border-radius:10px;border:1px solid var(--border);background:var(--background);color:var(--text);font:inherit;font-size:13px}
textarea.mp-field{min-height:95px;resize:vertical}
.mp-photos{background:var(--soft);border:1px dashed var(--border);border-radius:12px;padding:16px;margin-top:19px}
.mp-photos h3{margin:0 0 7px;font-size:14px}.mp-photos p{margin:0 0 12px;font-size:12px;color:var(--muted);line-height:1.6}
.mp-upload{display:inline-flex;align-items:center;gap:8px;cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:9px;padding:10px 13px;font-size:13px;font-weight:700}
.mp-upload input{display:none}.mp-photo-count{margin-left:10px;font-size:12px;color:var(--muted)}
.mp-preview-list{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}.mp-preview{position:relative;width:105px;height:85px;border:1px solid var(--border);border-radius:9px;overflow:hidden}.mp-preview img{width:100%;height:100%;object-fit:cover}
.mp-preview button{position:absolute;right:4px;top:4px;border:0;background:#152522;color:#fff;border-radius:50%;width:25px;height:25px;cursor:pointer;display:grid;place-items:center}
.mp-form-actions{justify-content:flex-end;margin-top:22px}
@media(max-width:760px){.mp-header{flex-direction:column}.mp-overview{grid-template-columns:repeat(2,minmax(0,1fr))}.mp-list,.mp-fields{grid-template-columns:1fr}.mp-toolbar{align-items:stretch;flex-direction:column}.mp-search{min-width:0}}
@media(max-width:480px){.mp-overview{grid-template-columns:1fr}.mp-form{padding:16px}.mp-property-cover{height:260px}}
`;

function formatPeso(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return "—";
  return new Intl.NumberFormat("en-PH", {
    style: "currency", currency: "PHP", maximumFractionDigits: 0,
  }).format(amount);
}

function validateProperty(form, photos, isEditing) {
  if (!form.name.trim()) return "Enter the dorm or property name.";
  if (!form.address.trim()) return "Enter the complete property address.";
  if (!form.description.trim()) return "Enter a property description.";
  const rent = Number(form.monthly_rent);
  const total = Number(form.total_rooms);
  const available = Number(form.available_rooms);
  if (!Number.isFinite(rent) || rent <= 0) return "Monthly rent must be greater than zero.";
  if (!Number.isInteger(total) || total < 1) return "Total rooms must be at least one.";
  if (!Number.isInteger(available) || available < 0 || available > total) {
    return "Available rooms must be between zero and total rooms.";
  }
  if (!isEditing && photos.length < 3) return "Upload at least three property photos.";
  return "";
}

async function getCsrfToken() {
  const response = await fetch(`${API_BASE}/api/csrf`, {
    credentials: "include", cache: "no-store", mode: "cors", redirect: "error",
  });
  if (!response.ok) throw new Error("Could not retrieve the form security token.");
  const body = await response.json();
  if (typeof body?.csrf_token !== "string" || !body.csrf_token) {
    throw new Error("The form security token is missing.");
  }
  return body.csrf_token;
}

async function failureMessage(response, fallback) {
  if (response.status === 401) return "Your session has expired. Sign in again.";
  if (response.status === 403) return "Your account is not permitted to perform this action.";
  if (response.status === 404 || response.status === 405) return "This property action is not connected to FastAPI yet.";
  try {
    const data = await response.json();
    if (typeof data?.detail === "string" && data.detail.length <= 250) return data.detail;
  } catch { /* Use the fallback. */ }
  return fallback;
}

export default function MyProperties({ account, onBack }) {
  const isOwner = account?.role === "property_owner";
  const formRef = useRef(null);
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [photos, setPhotos] = useState([]);
  const [previewUrls, setPreviewUrls] = useState([]);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [publishingId, setPublishingId] = useState(null);
  const [search, setSearch] = useState("");
  const isEditing = editingId !== null;

  const loadProperties = useCallback(async (signal) => {
    setLoading(true);
    setLoadError("");
    try {
      const response = await fetch(OWNER_URL, {
        credentials: "include", cache: "no-store", mode: "cors",
        redirect: "error", signal,
      });
      if (!response.ok) {
        throw new Error(await failureMessage(response, "Could not load properties from FastAPI."));
      }
      const body = await response.json();
      const rows = Array.isArray(body) ? body : body?.properties;
      if (!Array.isArray(rows)) throw new Error("The property response format is not recognized.");
      if (!signal?.aborted) setProperties(rows);
    } catch (error) {
      if (!signal?.aborted && error?.name !== "AbortError") {
        setLoadError(error?.message || "Unable to connect to the property service.");
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isOwner) return undefined;
    const controller = new AbortController();
    loadProperties(controller.signal);
    return () => controller.abort();
  }, [isOwner, loadProperties]);

  useEffect(() => {
    const urls = photos.map((file) => URL.createObjectURL(file));
    setPreviewUrls(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [photos]);

  function updateField(key, value) {
    setForm((previous) => ({ ...previous, [key]: value }));
    setFormError("");
  }

  function showForm() {
    window.requestAnimationFrame(() => {
      formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function startNew() {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setPhotos([]);
    setFormError("");
    setNotice("");
    setFormOpen(true);
    showForm();
  }

  function startEdit(property) {
    if (property.status === "archived") return;
    setEditingId(property.id);
    setForm({
      name: String(property.name ?? ""),
      address: String(property.address ?? ""),
      description: String(property.description ?? ""),
      monthly_rent: String(property.monthly_rent ?? ""),
      total_rooms: String(property.total_rooms ?? ""),
      available_rooms: String(property.available_rooms ?? ""),
    });
    setPhotos([]);
    setFormError("");
    setNotice("");
    setFormOpen(true);
    showForm();
  }

  function closeForm() {
    if (saving) return;
    setFormOpen(false);
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setPhotos([]);
    setFormError("");
  }

  function addPhotos(event) {
    const selected = Array.from(event.target.files || []);
    event.target.value = "";
    const combined = [...photos, ...selected];
    if (combined.length > MAX_PHOTOS) {
      setFormError(`You can upload a maximum of ${MAX_PHOTOS} photos.`);
      return;
    }
    if (selected.some((file) => !PHOTO_TYPES.includes(file.type) || file.size > MAX_PHOTO_SIZE)) {
      setFormError("Use JPG, PNG or WebP images, maximum 5 MB each.");
      return;
    }
    setPhotos(combined);
    setFormError("");
  }

  async function submitListing(event) {
    event.preventDefault();
    if (saving || publishingId !== null || !isOwner) return;
    const error = validateProperty(form, photos, isEditing);
    if (error) { setFormError(error); return; }
    setSaving(true);
    setFormError("");
    setNotice("");
    let requestSent = false;
    try {
      const csrf = await getCsrfToken();
      const payload = new FormData();
      Object.entries(form).forEach(([key, value]) => payload.append(key, String(value).trim()));
      if (!isEditing) photos.forEach((photo) => payload.append("photos", photo));
      const url = isEditing ? `${OWNER_URL}/${editingId}/edit` : OWNER_URL;
      requestSent = true;
      const response = await fetch(url, {
        method: "POST", credentials: "include", mode: "cors", redirect: "error",
        headers: { "X-CSRF-Token": csrf }, body: payload,
      });
      if (!response.ok) {
        requestSent = false;
        throw new Error(await failureMessage(response, "The server rejected this property change."));
      }
      closeFormAfterSave();
      setNotice(isEditing ? "Property details updated successfully." : "Property saved successfully by the server as a draft.");
      await loadProperties();
    } catch (caught) {
      setFormError(requestSent
        ? "The connection was interrupted. Check the property list before submitting again."
        : caught?.message || "Unable to save the property.");
    } finally {
      setSaving(false);
    }
  }

  function closeFormAfterSave() {
    setFormOpen(false);
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setPhotos([]);
  }

  async function publishProperty(property) {
    if (saving || publishingId !== null || !isOwner || property.status !== "draft") return;
    if (!window.confirm(`Publish "${property.name}"? It will be ready for renters to discover once the renter page is connected.`)) return;
    setPublishingId(property.id);
    setNotice("");
    let requestSent = false;
    try {
      const csrf = await getCsrfToken();
      requestSent = true;
      const response = await fetch(`${OWNER_URL}/${property.id}/publish`, {
        method: "POST", credentials: "include", mode: "cors", redirect: "error",
        headers: { "X-CSRF-Token": csrf },
      });
      if (!response.ok) {
        requestSent = false;
        throw new Error(await failureMessage(response, "Could not publish the property."));
      }
      setNotice(`"${property.name}" is now published.`);
      await loadProperties();
    } catch (caught) {
      setNotice(requestSent
        ? "The connection was interrupted. Refresh the listings to check whether publishing succeeded."
        : caught?.message || "Unable to publish the property.");
    } finally {
      setPublishingId(null);
    }
  }

  const filtered = properties.filter((property) => {
    const query = search.trim().toLowerCase();
    return String(property.name ?? "").toLowerCase().includes(query) ||
      String(property.address ?? "").toLowerCase().includes(query);
  });
  const totalRooms = properties.every((p) => Number.isFinite(Number(p.total_rooms)))
    ? properties.reduce((sum, p) => sum + Number(p.total_rooms), 0) : "—";
  const availableRooms = properties.every((p) => Number.isFinite(Number(p.available_rooms)))
    ? properties.reduce((sum, p) => sum + Number(p.available_rooms), 0) : "—";

  if (!isOwner) return <section role="alert">This page is for property-owner accounts only.</section>;

  return (
    <section className="mp-page">
      <style>{styles}</style>
      <div className="mp-header">
        <div className="mp-heading">
          <h1>My Properties</h1>
          <p>Manage your dorm listings, room availability, and rental information.</p>
        </div>
        <div className="mp-header-actions">
          {onBack && <button type="button" className="mp-button" onClick={onBack}>
            <ArrowLeft size={17} /> Home
          </button>}
          <button type="button" className="mp-button primary"
            disabled={formOpen || saving || publishingId !== null} onClick={startNew}>
            <Plus size={17} /> Add Property
          </button>
        </div>
      </div>

      <div className="mp-overview">
        {[
          ["My Listings", loading || loadError ? "—" : properties.length, Building2],
          ["Total Rooms", loading || loadError ? "—" : totalRooms, DoorOpen],
          ["Available Rooms", loading || loadError ? "—" : availableRooms, CheckCircle2],
        ].map(([label, value, Icon]) => (
          <div className="mp-stat" key={label}>
            <div className="mp-stat-heading"><span>{label}</span><Icon size={19} /></div>
            <p className="mp-stat-value">{value}</p>
          </div>
        ))}
      </div>

      {notice && <div className="mp-notice" role="status">{notice}</div>}

      {formOpen && (
        <form ref={formRef} className="mp-form" onSubmit={submitListing}>
          <div className="mp-form-header">
            <h2>{isEditing ? "Edit Property" : "New Property Listing"}</h2>
            <button type="button" className="mp-button" aria-label="Close form"
              disabled={saving} onClick={closeForm}><X size={18} /></button>
          </div>
          <div className="mp-fields">
            <label className="mp-label wide">Dorm / Property Name
              <input className="mp-field" required maxLength={120}
                placeholder="e.g. Greenview Dormitory" value={form.name}
                onChange={(e) => updateField("name", e.target.value)} />
            </label>
            <label className="mp-label wide">Complete Address
              <input className="mp-field" required maxLength={250}
                placeholder="Street, barangay, city" value={form.address}
                onChange={(e) => updateField("address", e.target.value)} />
            </label>
            <label className="mp-label">Monthly Rent (PHP)
              <input className="mp-field" type="number" min="1" step="0.01" required
                placeholder="3500" value={form.monthly_rent}
                onChange={(e) => updateField("monthly_rent", e.target.value)} />
            </label>
            <label className="mp-label">Total Rooms
              <input className="mp-field" type="number" min="1" step="1" required
                placeholder="10" value={form.total_rooms}
                onChange={(e) => updateField("total_rooms", e.target.value)} />
            </label>
            <label className="mp-label">Available Rooms
              <input className="mp-field" type="number" min="0" step="1" required
                placeholder="8" value={form.available_rooms}
                onChange={(e) => updateField("available_rooms", e.target.value)} />
            </label>
            <label className="mp-label wide">Property Description
              <textarea className="mp-field" required maxLength={1500}
                placeholder="Describe rooms, facilities, and property rules."
                value={form.description}
                onChange={(e) => updateField("description", e.target.value)} />
            </label>
          </div>
          {isEditing ? (
            <div className="mp-notice">Existing photos will stay unchanged when you update the property details.</div>
          ) : (
            <div className="mp-photos">
              <h3><Camera size={16} style={{ verticalAlign: "middle" }} /> Property Photos</h3>
              <p>Upload at least three images of your dorm. Maximum eight images, 5 MB each.</p>
              <label className="mp-upload"><ImagePlus size={17} /> Choose Photos
                <input type="file" accept="image/jpeg,image/png,image/webp"
                  multiple disabled={saving} onChange={addPhotos} />
              </label>
              <span className="mp-photo-count">{photos.length} / {MAX_PHOTOS} selected</span>
              <div className="mp-preview-list">
                {previewUrls.map((url, index) => (
                  <div className="mp-preview" key={url}>
                    <img src={url} alt={`Property photo ${index + 1}`} />
                    <button type="button" disabled={saving}
                      aria-label={`Remove photo ${index + 1}`}
                      onClick={() => setPhotos((old) => old.filter((_, i) => i !== index))}>
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          {formError && <div className="mp-notice error" role="alert">{formError}</div>}
          <div className="mp-form-actions">
            <button type="button" className="mp-button" disabled={saving} onClick={closeForm}>Cancel</button>
            <button type="submit" className="mp-button primary" disabled={saving || publishingId !== null}>
              {saving ? "Saving…" : isEditing ? "Save Changes" : "Save Property"}
            </button>
          </div>
        </form>
      )}

      <div className="mp-toolbar">
        <h2>Property Listings</h2>
        <label className="mp-search"><Search size={16} />
          <input type="search" placeholder="Search properties"
            aria-label="Search properties" value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </label>
      </div>

      {loading ? (
        <div className="mp-empty" role="status">Loading your properties…</div>
      ) : loadError ? (
        <div className="mp-empty" role="status">
          <Building2 size={33} /><h3>Listings Not Available</h3><p>{loadError}</p>
          <button type="button" className="mp-button" style={{ marginTop: 16 }}
            onClick={() => loadProperties()}>Try Again</button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="mp-empty"><Building2 size={33} />
          <h3>{search ? "No Matching Properties" : "No Properties Yet"}</h3>
          <p>{search ? "Try another name or address." : "Click Add Property to create your first dorm listing."}</p>
        </div>
      ) : (
        <div className="mp-list">
          {filtered.map((property) => {
            const photo = property.cover_photo_url || property.photo_urls?.[0];
            const isPublishing = publishingId === property.id;
            const published = property.status === "published";
            return (
              <article className="mp-property" key={property.id}>
                <div className="mp-property-cover">
                  <div className="mp-property-image">
                    {photo && /^https?:\/\//.test(photo)
                      ? <img src={photo} alt={`${property.name} property`} />
                      : <Building2 size={44} />}
                  </div>
                  <div className="mp-property-details">
                    <h3>{property.name}</h3>
                    <div className="mp-property-address"><MapPin size={15} />{property.address}</div>
                    <div className="mp-property-meta">
                      <span><strong>{formatPeso(property.monthly_rent)}</strong> / month</span>
                      <span>{property.available_rooms ?? "—"} rooms available</span>
                    </div>
                  </div>
                </div>
                <div className="mp-property-footer">
                  <span className={`mp-status ${published ? "published" : ""}`}>
                    {property.status || "draft"}
                  </span>
                  <div className="mp-card-buttons">
                    <button type="button" className="mp-button"
                      disabled={saving || publishingId !== null || property.status === "archived"}
                      onClick={() => startEdit(property)}>
                      <Pencil size={15} /> Edit
                    </button>
                    {!published && property.status !== "archived" && (
                      <button type="button" className="mp-button primary"
                        disabled={saving || publishingId !== null}
                        onClick={() => publishProperty(property)}>
                        <Send size={15} /> {isPublishing ? "Publishing…" : "Publish"}
                      </button>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
