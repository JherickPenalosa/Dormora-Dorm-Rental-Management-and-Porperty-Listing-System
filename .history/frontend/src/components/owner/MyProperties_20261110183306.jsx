
/*
 * DORMORA — SYSTEM FUNCTIONALITY FILE 3
 * CREATE: frontend/src/components/owner/MyProperties.jsx
 *
 * Property Owner — My Properties
 * Uses Dormora's existing light/dark theme variables.
 *
 * Backend property endpoints will be connected in subsequent files.
 * This page never treats unsaved data as a saved PostgreSQL record.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  Building2,
  Camera,
  CheckCircle2,
  DoorOpen,
  ImagePlus,
  MapPin,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const OWNER_URL = `${API_BASE}/api/owner/properties`;

const MAX_PHOTOS = 8;
const MAX_PHOTO_SIZE = 5 * 1024 * 1024;
const PHOTO_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
];

const EMPTY_FORM = {
  name: "",
  address: "",
  description: "",
  monthly_rent: "",
  total_rooms: "",
  available_rooms: "",
};

const styles = `
.mp-page {
  width: 100%;
  color: var(--text);
}

.mp-page * {
  box-sizing: border-box;
}

.mp-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 22px;
}

.mp-heading h1 {
  font-size: clamp(24px, 3vw, 31px);
  margin: 0 0 6px;
}

.mp-heading p {
  font-size: 14px;
  color: var(--muted);
  margin: 0;
  line-height: 1.6;
}

.mp-header-actions,
.mp-form-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.mp-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 15px;
  min-height: 42px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card);
  color: var(--text);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.mp-button.primary {
  background: var(--primary);
  color: var(--background);
  border-color: var(--primary);
}

.mp-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.mp-button:focus-visible,
.mp-field:focus-visible {
  outline: 3px solid var(--primary);
  outline-offset: 2px;
}

.mp-overview {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 22px;
}

.mp-stat {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 19px;
}

.mp-stat-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted);
  font-size: 12px;
  gap: 8px;
}

.mp-stat-heading svg {
  color: var(--primary);
}

.mp-stat-value {
  margin: 9px 0 0;
  font-weight: 800;
  font-size: 27px;
}

.mp-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin: 20px 0 15px;
}

.mp-toolbar h2 {
  margin: 0;
  font-size: 18px;
}

.mp-search {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 12px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  min-width: 225px;
}

.mp-search svg {
  color: var(--muted);
}

.mp-search input {
  width: 100%;
  padding: 12px 0;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.mp-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 15px;
}

.mp-property {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 15px;
  overflow: hidden;
}

.mp-property-image {
  background: var(--soft);
  height: 155px;
  display: grid;
  place-items: center;
  color: var(--primary);
}

.mp-property-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.mp-property-details {
  padding: 18px;
}

.mp-property-details h3 {
  font-size: 17px;
  margin: 0 0 8px;
}

.mp-property-address {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  color: var(--muted);
}

.mp-property-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 13px;
  margin-top: 16px;
  font-size: 13px;
}

.mp-property-meta strong {
  color: var(--primary);
}

.mp-empty {
  background: var(--card);
  border: 1px dashed var(--border);
  border-radius: 15px;
  text-align: center;
  padding: 46px 24px;
  color: var(--muted);
}

.mp-empty svg {
  color: var(--primary);
}

.mp-empty h3 {
  color: var(--text);
  margin: 12px 0 8px;
}

.mp-empty p {
  max-width: 450px;
  margin: 0 auto;
  line-height: 1.7;
  font-size: 13px;
}

.mp-notice {
  background: var(--soft);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 13px 15px;
  margin: 15px 0;
  font-size: 13px;
  line-height: 1.6;
}

.mp-notice.error {
  border-color: #c96565;
}

.mp-form {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 23px;
  margin: 0 0 24px;
}

.mp-form-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 20px;
}

.mp-form-header h2 {
  margin: 0;
  font-size: 19px;
}

.mp-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.mp-label {
  display: grid;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
}

.mp-label.wide {
  grid-column: 1 / -1;
}

.mp-field {
  width: 100%;
  min-width: 0;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--background);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

textarea.mp-field {
  min-height: 95px;
  resize: vertical;
}

.mp-photos {
  background: var(--soft);
  border: 1px dashed var(--border);
  border-radius: 12px;
  padding: 16px;
  margin-top: 19px;
}

.mp-photos h3 {
  margin: 0 0 7px;
  font-size: 14px;
}

.mp-photos p {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.6;
}

.mp-upload {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  border-radius: 9px;
  padding: 10px 13px;
  font-size: 13px;
  font-weight: 700;
}

.mp-upload input {
  display: none;
}

.mp-photo-count {
  margin-left: 10px;
  font-size: 12px;
  color: var(--muted);
}

.mp-preview-list {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.mp-preview {
  position: relative;
  width: 105px;
  height: 85px;
  border: 1px solid var(--border);
  border-radius: 9px;
  overflow: hidden;
}

.mp-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.mp-preview button {
  position: absolute;
  right: 4px;
  top: 4px;
  border: 0;
  background: #152522;
  color: white;
  border-radius: 50%;
  width: 25px;
  height: 25px;
  cursor: pointer;
  display: grid;
  place-items: center;
}

.mp-form-actions {
  justify-content: flex-end;
  margin-top: 22px;
}

@media (max-width: 760px) {
  .mp-header {
    flex-direction: column;
  }

  .mp-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mp-list,
  .mp-fields {
    grid-template-columns: 1fr;
  }

  .mp-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .mp-search {
    min-width: 0;
  }
}

@media (max-width: 480px) {
  .mp-overview {
    grid-template-columns: 1fr;
  }

  .mp-form {
    padding: 16px;
  }
}
`;

function formatPeso(value) {
  const amount = Number(value);

  if (!Number.isFinite(amount) || amount < 0) {
    return "—";
  }

  return new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    maximumFractionDigits: 0,
  }).format(amount);
}

function validateProperty(form, photos) {
  if (!form.name.trim()) {
    return "Enter the dorm or property name.";
  }

  if (!form.address.trim()) {
    return "Enter the complete property address.";
  }

  if (!form.description.trim()) {
    return "Enter a property description.";
  }

  const rent = Number(form.monthly_rent);
  const total = Number(form.total_rooms);
  const available = Number(form.available_rooms);

  if (!Number.isFinite(rent) || rent <= 0) {
    return "Monthly rent must be greater than zero.";
  }

  if (!Number.isInteger(total) || total < 1) {
    return "Total rooms must be at least one.";
  }

  if (
    !Number.isInteger(available) ||
    available < 0 ||
    available > total
  ) {
    return "Available rooms must be between zero and total rooms.";
  }

  if (photos.length < 3) {
    return "Upload at least three property photos.";
  }

  return "";
}

export default function MyProperties({ account, onBack }) {
  const isOwner = account?.role === "property_owner";

  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [photos, setPhotos] = useState([]);
  const [previewUrls, setPreviewUrls] = useState([]);

  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  const loadProperties = useCallback(async (signal) => {
    setLoading(true);
    setLoadError("");

    try {
      const response = await fetch(OWNER_URL, {
        credentials: "include",
        cache: "no-store",
        signal,
      });

      if (response.status === 401) {
        throw new Error("Your session has expired. Sign in again.");
      }

      if (response.status === 403) {
        throw new Error(
          "Only property owners can view these listings."
        );
      }

      if (response.status === 404) {
        throw new Error(
          "Property listing storage is not connected yet."
        );
      }

      if (!response.ok) {
        throw new Error("Could not load properties from FastAPI.");
      }

      const body = await response.json();

      const rows = Array.isArray(body)
        ? body
        : body?.properties;

      if (!Array.isArray(rows)) {
        throw new Error(
          "The property response format is not recognized."
        );
      }

      if (!signal?.aborted) {
        setProperties(rows);
      }
    } catch (error) {
      if (
        !signal?.aborted &&
        error?.name !== "AbortError"
      ) {
        setLoadError(
          error?.message ||
          "Unable to connect to the property service."
        );
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!isOwner) return undefined;

    const controller = new AbortController();

    loadProperties(controller.signal);

    return () => controller.abort();
  }, [isOwner, loadProperties]);

  // Create and clean up local previews for selected images.
  useEffect(() => {
    const urls = photos.map((file) =>
      URL.createObjectURL(file)
    );

    setPreviewUrls(urls);

    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [photos]);

  function updateField(key, value) {
    setForm((previous) => ({
      ...previous,
      [key]: value,
    }));

    setFormError("");
  }

  function addPhotos(event) {
    const selected = Array.from(event.target.files || []);
    event.target.value = "";

    const combined = [...photos, ...selected];

    if (combined.length > MAX_PHOTOS) {
      setFormError(
        `You can upload a maximum of ${MAX_PHOTOS} photos.`
      );
      return;
    }

    if (
      selected.some(
        (file) =>
          !PHOTO_TYPES.includes(file.type) ||
          file.size > MAX_PHOTO_SIZE
      )
    ) {
      setFormError(
        "Use JPG, PNG or WebP images, maximum 5 MB each."
      );
      return;
    }

    setPhotos(combined);
    setFormError("");
  }

  function closeForm() {
    if (saving) return;

    setFormOpen(false);
    setForm({ ...EMPTY_FORM });
    setPhotos([]);
    setFormError("");
  }

  async function submitListing(event) {
    event.preventDefault();

    if (saving || !isOwner) return;

    const error = validateProperty(form, photos);

    if (error) {
      setFormError(error);
      return;
    }

    setSaving(true);
    setFormError("");
    setNotice("");

    try {
      const csrfResponse = await fetch(
        `${API_BASE}/api/csrf`,
        {
          credentials: "include",
          cache: "no-store",
        }
      );

      if (!csrfResponse.ok) {
        throw new Error(
          "Could not retrieve the form security token."
        );
      }

      const csrf = await csrfResponse.json();

      if (
        typeof csrf?.csrf_token !== "string" ||
        !csrf.csrf_token
      ) {
        throw new Error("The security token is missing.");
      }

      const payload = new FormData();

      Object.entries(form).forEach(([key, value]) => {
        payload.append(key, String(value).trim());
      });

      photos.forEach((photo) => {
        payload.append("photos", photo);
      });

      const response = await fetch(OWNER_URL, {
        method: "POST",
        credentials: "include",
        headers: {
          "X-CSRF-Token": csrf.csrf_token,
        },
        body: payload,
      });

      if (
        response.status === 404 ||
        response.status === 405
      ) {
        throw new Error(
          "Saving is not connected yet. The property was NOT saved."
        );
      }

      if (
        response.status === 401 ||
        response.status === 403
      ) {
        throw new Error(
          "Your account is not authorized to save this property."
        );
      }

      if (!response.ok) {
        throw new Error(
          "The server rejected the listing. Saving was not confirmed."
        );
      }

      setFormOpen(false);
      setForm({ ...EMPTY_FORM });
      setPhotos([]);

      setNotice("Property saved successfully by the server.");

      await loadProperties();
    } catch (error) {
      setFormError(
        error?.message ||
        "Unable to save the property. Please try again later."
      );
    } finally {
      setSaving(false);
    }
  }

  const filtered = properties.filter((item) => {
    const query = search.toLowerCase();

    return (
      String(item.name ?? "").toLowerCase().includes(query) ||
      String(item.address ?? "").toLowerCase().includes(query)
    );
  });

  const totalRooms = properties.every((item) =>
    Number.isFinite(Number(item.total_rooms))
  )
    ? properties.reduce(
        (sum, item) => sum + Number(item.total_rooms),
        0
      )
    : "—";

  const availableRooms = properties.every((item) =>
    Number.isFinite(Number(item.available_rooms))
  )
    ? properties.reduce(
        (sum, item) => sum + Number(item.available_rooms),
        0
      )
    : "—";

  if (!isOwner) {
    return (
      <section role="alert">
        This page is for property-owner accounts only.
      </section>
    );
  }

  return (
    <section className="mp-page">
      <style>{styles}</style>

      <div className="mp-header">
        <div className="mp-heading">
          <h1>My Properties</h1>
          <p>
            Manage your dorm listings, room availability,
            and rental information.
          </p>
        </div>

        <div className="mp-header-actions">
          {onBack && (
            <button
              type="button"
              className="mp-button"
              onClick={onBack}
            >
              <ArrowLeft size={17} />
              Home
            </button>
          )}

          <button
            type="button"
            className="mp-button primary"
            disabled={formOpen}
            onClick={() => {
              setFormOpen(true);
              setNotice("");
            }}
          >
            <Plus size={17} />
            Add Property
          </button>
        </div>
      </div>

      <div className="mp-overview">
        {[
          [
            "My Listings",
            loading || loadError ? "—" : properties.length,
            Building2,
          ],
          [
            "Total Rooms",
            loading || loadError ? "—" : totalRooms,
            DoorOpen,
          ],
          [
            "Available Rooms",
            loading || loadError ? "—" : availableRooms,
            CheckCircle2,
          ],
        ].map(([label, value, Icon]) => (
          <div className="mp-stat" key={label}>
            <div className="mp-stat-heading">
              <span>{label}</span>
              <Icon size={19} />
            </div>

            <p className="mp-stat-value">{value}</p>
          </div>
        ))}
      </div>

      {notice && (
        <div className="mp-notice" role="status">
          {notice}
        </div>
      )}

      {formOpen && (
        <form
          className="mp-form"
          onSubmit={submitListing}
        >
          <div className="mp-form-header">
            <h2>New Property Listing</h2>

            <button
              type="button"
              className="mp-button"
              aria-label="Close form"
              disabled={saving}
              onClick={closeForm}
            >
              <X size={18} />
            </button>
          </div>

          <div className="mp-fields">
            <label className="mp-label wide">
              Dorm / Property Name

              <input
                className="mp-field"
                required
                maxLength={120}
                placeholder="e.g. Greenview Dormitory"
                value={form.name}
                onChange={(e) =>
                  updateField("name", e.target.value)
                }
              />
            </label>

            <label className="mp-label wide">
              Complete Address

              <input
                className="mp-field"
                required
                maxLength={250}
                placeholder="Street, barangay, city"
                value={form.address}
                onChange={(e) =>
                  updateField("address", e.target.value)
                }
              />
            </label>

            <label className="mp-label">
              Monthly Rent (PHP)

              <input
                className="mp-field"
                type="number"
                min="1"
                step="0.01"
                required
                placeholder="3500"
                value={form.monthly_rent}
                onChange={(e) =>
                  updateField("monthly_rent", e.target.value)
                }
              />
            </label>

            <label className="mp-label">
              Total Rooms

              <input
                className="mp-field"
                type="number"
                min="1"
                step="1"
                required
                placeholder="10"
                value={form.total_rooms}
                onChange={(e) =>
                  updateField("total_rooms", e.target.value)
                }
              />
            </label>

            <label className="mp-label">
              Available Rooms

              <input
                className="mp-field"
                type="number"
                min="0"
                step="1"
                required
                placeholder="8"
                value={form.available_rooms}
                onChange={(e) =>
                  updateField("available_rooms", e.target.value)
                }
              />
            </label>

            <label className="mp-label wide">
              Property Description

              <textarea
                className="mp-field"
                required
                maxLength={1500}
                placeholder="Describe rooms, facilities, and property rules."
                value={form.description}
                onChange={(e) =>
                  updateField("description", e.target.value)
                }
              />
            </label>
          </div>

          <div className="mp-photos">
            <h3>
              <Camera
                size={16}
                style={{ verticalAlign: "middle" }}
              />
              {" "}Property Photos
            </h3>

            <p>
              Upload at least three images of your dorm.
              Maximum eight images, 5 MB each.
            </p>

            <label className="mp-upload">
              <ImagePlus size={17} />
              Choose Photos

              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                disabled={saving}
                onChange={addPhotos}
              />
            </label>

            <span className="mp-photo-count">
              {photos.length} / {MAX_PHOTOS} selected
            </span>

            <div className="mp-preview-list">
              {previewUrls.map((url, index) => (
                <div className="mp-preview" key={url}>
                  <img
                    src={url}
                    alt={`Property photo ${index + 1}`}
                  />

                  <button
                    type="button"
                    disabled={saving}
                    aria-label={`Remove photo ${index + 1}`}
                    onClick={() => {
                      setPhotos((previous) =>
                        previous.filter(
                          (_, photoIndex) =>
                            photoIndex !== index
                        )
                      );
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {formError && (
            <div
              className="mp-notice error"
              role="alert"
            >
              {formError}
            </div>
          )}

          <div className="mp-form-actions">
            <button
              type="button"
              className="mp-button"
              disabled={saving}
              onClick={closeForm}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="mp-button primary"
              disabled={saving}
            >
              {saving ? "Saving…" : "Save Property"}
            </button>
          </div>
        </form>
      )}

      <div className="mp-toolbar">
        <h2>Property Listings</h2>

        <label className="mp-search">
          <Search size={16} />

          <input
            type="search"
            placeholder="Search properties"
            aria-label="Search properties"
            value={search}
            onChange={(e) =>
              setSearch(e.target.value)
            }
          />
        </label>
      </div>

      {loading ? (
        <div className="mp-empty" role="status">
          Loading your properties…
        </div>
      ) : loadError ? (
        <div className="mp-empty" role="status">
          <Building2 size={33} />
          <h3>Listings Not Available</h3>
          <p>{loadError}</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="mp-empty">
          <Building2 size={33} />

          <h3>
            {search
              ? "No Matching Properties"
              : "No Properties Yet"}
          </h3>

          <p>
            {search
              ? "Try another name or address."
              : "Click Add Property to create your first dorm listing."}
          </p>
        </div>
      ) : (
        <div className="mp-list">
          {filtered.map((property) => {
            const photo =
              property.cover_photo_url ||
              property.photo_urls?.[0];

            return (
              <article
                className="mp-property"
                key={property.id}
              >
                <div className="mp-property-image">
                  {photo &&
                  /^https?:\/\//.test(photo) ? (
                    <img
                      src={photo}
                      alt={`${property.name} property`}
                    />
                  ) : (
                    <Building2 size={44} />
                  )}
                </div>

                <div className="mp-property-details">
                  <h3>{property.name}</h3>

                  <div className="mp-property-address">
                    <MapPin size={15} />
                    {property.address}
                  </div>

                  <div className="mp-property-meta">
                    <span>
                      <strong>
                        {formatPeso(property.monthly_rent)}
                      </strong>
                      {" "}/ month
                    </span>

                    <span>
                      {property.available_rooms ?? "—"}
                      {" "}rooms available
                    </span>
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
