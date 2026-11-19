
/*
 * DORMORA — SYSTEM FUNCTIONALITY FILE 17
 *
 * CREATE:
 * frontend/src/components/renter/DormDiscovery.jsx
 *
 * Renter-facing discovery of published dorm properties.
 * Uses the read-only API created in Files 14–16.
 *
 * File 18 will connect this component to RoleHome.jsx.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CheckCircle2,
  DoorOpen,
  ImageIcon,
  MapPin,
  RefreshCw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const DISCOVERY_API = `${API_BASE}/api/renter/discovery`;

const styles = `
.dd-page {
  width: 100%;
  color: var(--text);
  font-family: inherit;
}
.dd-page * { box-sizing: border-box; }

.dd-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 22px;
}
.dd-header h1 {
  font-size: clamp(25px, 3vw, 32px);
  margin: 0 0 8px;
  font-weight: 800;
}
.dd-header p {
  color: var(--muted);
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
}
.dd-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 11px 15px;
  min-height: 42px;
  border: 1px solid var(--border);
  border-radius: 11px;
  background: var(--card);
  color: var(--text);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity .15s, transform .15s;
}
.dd-button:hover:not(:disabled) { opacity: .85; }
.dd-button:active:not(:disabled) { transform: translateY(1px); }
.dd-button:disabled { opacity: .5; cursor: not-allowed; }
.dd-button.primary {
  background: var(--primary);
  border-color: var(--primary);
  color: var(--background);
}
.dd-button:focus-visible,
.dd-page input:focus-visible,
.dd-page select:focus-visible,
.dd-photo-thumb:focus-visible {
  outline: 3px solid var(--primary);
  outline-offset: 2px;
}

.dd-intro {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 17px;
  padding: 24px;
  margin-bottom: 20px;
}
.dd-intro-top {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 13px;
}
.dd-intro-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border-radius: 12px;
  background: var(--soft);
  color: var(--primary);
}
.dd-intro h2 {
  margin: 0;
  font-size: 19px;
  font-weight: 800;
}
.dd-intro p {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
  margin: 0;
  max-width: 800px;
}

.dd-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin: 20px 0 14px;
}
.dd-search {
  flex: 1;
  min-width: 210px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: 11px;
  background: var(--card);
  padding: 0 13px;
  color: var(--muted);
}
.dd-search input {
  border: 0;
  outline: none;
  flex: 1;
  min-width: 0;
  padding: 13px 0;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 13px;
}
.dd-search button {
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  padding: 4px;
}
.dd-select-wrap {
  display: flex;
  align-items: center;
  gap: 9px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 0 12px;
}
.dd-select-wrap svg { color: var(--primary); }
.dd-select {
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 13px;
  padding: 12px 4px;
  cursor: pointer;
}
.dd-select option {
  color: var(--text);
  background: var(--card);
}
.dd-filter-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 17px;
}
.dd-filter-row p {
  color: var(--muted);
  font-size: 13px;
  margin: 0;
}
.dd-filter {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
}
.dd-filter input {
  width: 16px;
  height: 16px;
  accent-color: var(--primary);
}

.dd-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 17px;
}
.dd-card {
  overflow: hidden;
  min-width: 0;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
}
.dd-card-photo {
  position: relative;
  width: 100%;
  height: 235px;
  background: var(--soft);
}
.dd-photo {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.dd-photo-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 9px;
  background: var(--soft);
  color: var(--muted);
  font-size: 12px;
}
.dd-card-badge {
  position: absolute;
  top: 13px;
  left: 13px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 800;
  background: rgba(9, 33, 27, .86);
  color: #b8ffe2;
  backdrop-filter: blur(5px);
}
.dd-card-badge.full {
  color: #fff;
  background: rgba(38, 45, 43, .86);
}
.dd-card-content {
  padding: 18px;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.dd-card-content h3 {
  font-size: 18px;
  margin: 0 0 9px;
  line-height: 1.4;
}
.dd-address {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}
.dd-address svg {
  flex-shrink: 0;
  margin-top: 2px;
}
.dd-description {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
  margin: 15px 0;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  overflow: hidden;
}
.dd-card-bottom {
  margin-top: auto;
  padding-top: 15px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.dd-price {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dd-price strong {
  font-size: 20px;
  color: var(--primary);
}
.dd-price span {
  color: var(--muted);
  font-size: 11px;
}
.dd-card-bottom .dd-button {
  flex-shrink: 0;
}

.dd-state {
  padding: 48px 24px;
  background: var(--card);
  border: 1px dashed var(--border);
  border-radius: 16px;
  text-align: center;
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 12px;
}
.dd-state svg { color: var(--primary); }
.dd-state h3 {
  margin: 0;
  font-size: 18px;
}
.dd-state p {
  max-width: 500px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--muted);
  margin: 0;
}

.dd-detail {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 17px;
  overflow: hidden;
}
.dd-detail-gallery {
  padding: 16px;
}
.dd-detail-main-photo {
  width: 100%;
  height: clamp(240px, 42vw, 430px);
  border-radius: 12px;
  overflow: hidden;
  background: var(--soft);
}
.dd-gallery-thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  margin-top: 12px;
}
.dd-photo-thumb {
  width: 83px;
  height: 65px;
  border: 2px solid var(--border);
  background: var(--soft);
  border-radius: 9px;
  padding: 0;
  overflow: hidden;
  cursor: pointer;
}
.dd-photo-thumb.active {
  border-color: var(--primary);
}
.dd-photo-thumb .dd-photo {
  width: 100%;
  height: 100%;
}
.dd-detail-body {
  padding: 6px 24px 25px;
}
.dd-detail-heading {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
  margin-bottom: 19px;
}
.dd-detail-heading h2 {
  font-size: 25px;
  margin: 0 0 10px;
}
.dd-detail-rent {
  color: var(--primary);
  font-size: 24px;
  font-weight: 800;
  white-space: nowrap;
}
.dd-detail-rent span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
  text-align: right;
}
.dd-detail-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.dd-detail-stat {
  background: var(--soft);
  border-radius: 12px;
  padding: 15px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.dd-detail-stat svg {
  color: var(--primary);
  flex-shrink: 0;
}
.dd-detail-stat strong {
  display: block;
  font-size: 19px;
}
.dd-detail-stat span {
  font-size: 12px;
  color: var(--muted);
}
.dd-detail-body h3 {
  margin: 20px 0 9px;
  font-size: 17px;
}
.dd-full-description {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.8;
}
.dd-info {
  margin-top: 22px;
  background: var(--soft);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.7;
}
@media (max-width: 900px) {
  .dd-grid { grid-template-columns: 1fr; }
}
@media (max-width: 650px) {
  .dd-header { flex-direction: column; }
  .dd-toolbar { flex-direction: column; align-items: stretch; }
  .dd-search { width: 100%; }
  .dd-detail-heading { flex-direction: column; }
  .dd-detail-rent span { text-align: left; }
  .dd-detail-body { padding: 4px 16px 20px; }
  .dd-detail-stats { grid-template-columns: 1fr; }
  .dd-card-bottom { flex-wrap: wrap; }
}
`;

function formatPeso(value) {
  const number = Number(value);

  if (!Number.isFinite(number) || number < 0) {
    return "—";
  }

  return new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(number);
}

function PropertyImage({ src, alt }) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [src]);

  if (!src || failed) {
    return (
      <div className="dd-photo-fallback">
        <ImageIcon size={36} />
        <span>No photo available</span>
      </div>
    );
  }

  return (
    <img
      className="dd-photo"
      src={src}
      alt={alt}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

function AvailabilityBadge({ available }) {
  const count = Number(available) || 0;
  const hasRooms = count > 0;

  return (
    <span className={`dd-card-badge ${hasRooms ? "" : "full"}`}>
      {hasRooms ? <CheckCircle2 size={13} /> : <DoorOpen size={13} />}
      {hasRooms
        ? `${count} ${count === 1 ? "room" : "rooms"} available`
        : "No available rooms"}
    </span>
  );
}

function PropertyCard({ property, onView }) {
  return (
    <article className="dd-card">
      <div className="dd-card-photo">
        <PropertyImage
          src={property.cover_photo_url}
          alt={`${property.name} exterior`}
        />
        <AvailabilityBadge available={property.available_rooms} />
      </div>

      <div className="dd-card-content">
        <h3>{property.name}</h3>

        <div className="dd-address">
          <MapPin size={15} />
          <span>{property.address}</span>
        </div>

        <p className="dd-description">
          {property.description || "No description provided."}
        </p>

        <div className="dd-card-bottom">
          <div className="dd-price">
            <strong>{formatPeso(property.monthly_rent)}</strong>
            <span>Monthly rental price</span>
          </div>

          <button
            type="button"
            className="dd-button primary"
            onClick={() => onView(property.id)}
          >
            View Details
            <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </article>
  );
}

function DiscoveryDetail({ property, onBack }) {
  const [photoIndex, setPhotoIndex] = useState(0);
  const images = Array.isArray(property.photo_urls)
    ? property.photo_urls
    : [];

  const activeImage = images[photoIndex] || images[0] || "";

  return (
    <>
      <div className="dd-header">
        <div>
          <h1>Property Details</h1>
          <p>View the property information and available rooms.</p>
        </div>

        <button type="button" className="dd-button" onClick={onBack}>
          <ArrowLeft size={17} />
          Back to Results
        </button>
      </div>

      <article className="dd-detail">
        <div className="dd-detail-gallery">
          <div className="dd-detail-main-photo">
            <PropertyImage
              src={activeImage}
              alt={`${property.name} photo ${photoIndex + 1}`}
            />
          </div>

          {images.length > 1 && (
            <div className="dd-gallery-thumbs">
              {images.map((url, index) => (
                <button
                  key={`${url}-${index}`}
                  type="button"
                  className={`dd-photo-thumb ${
                    photoIndex === index ? "active" : ""
                  }`}
                  aria-label={`View property photo ${index + 1}`}
                  aria-pressed={photoIndex === index}
                  onClick={() => setPhotoIndex(index)}
                >
                  <PropertyImage
                    src={url}
                    alt={`Property thumbnail ${index + 1}`}
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="dd-detail-body">
          <div className="dd-detail-heading">
            <div>
              <h2>{property.name}</h2>
              <div className="dd-address">
                <MapPin size={16} />
                <span>{property.address}</span>
              </div>
            </div>

            <div className="dd-detail-rent">
              {formatPeso(property.monthly_rent)}
              <span>per month</span>
            </div>
          </div>

          <div className="dd-detail-stats">
            <div className="dd-detail-stat">
              <Building2 size={23} />
              <div>
                <strong>{property.total_rooms ?? "—"}</strong>
                <span>Total Rooms</span>
              </div>
            </div>

            <div className="dd-detail-stat">
              <DoorOpen size={23} />
              <div>
                <strong>{property.available_rooms ?? "—"}</strong>
                <span>Available Rooms</span>
              </div>
            </div>
          </div>

          <h3>About This Property</h3>
          <p className="dd-full-description">
            {property.description || "No property description available."}
          </p>

          <div className="dd-info">
            This listing is published by a registered Dormora
            property owner. Rental inquiries and tenant assignment
            will be introduced in the next functionality stage.
            No reservation or payment has been made by viewing
            this listing.
          </div>
        </div>
      </article>
    </>
  );
}

async function getErrorMessage(response) {
  if (response.status === 401) {
    return "Your session has expired. Please log in again.";
  }

  if (response.status === 403) {
    return "Dorm Discovery is available to renter accounts only.";
  }

  if (response.status === 404) {
    return "The requested property is no longer available.";
  }

  try {
    const data = await response.json();

    if (typeof data.detail === "string") {
      return data.detail;
    }
  } catch {
    // The backend did not return a JSON error.
  }

  return "Unable to retrieve dorm listings from the server.";
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
    if (!isRenter) {
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();

    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");

      try {
        const params = new URLSearchParams({
          search: search.trim(),
          limit: "50",
        });

        const response = await fetch(
          `${DISCOVERY_API}?${params.toString()}`,
          {
            method: "GET",
            credentials: "include",
            cache: "no-store",
            mode: "cors",
            redirect: "error",
            signal: controller.signal,
          }
        );

        if (!response.ok) {
          throw new Error(await getErrorMessage(response));
        }

        const data = await response.json();

        if (!Array.isArray(data.properties)) {
          throw new Error("Invalid property list returned by the server.");
        }

        if (!controller.signal.aborted) {
          setProperties(data.properties);
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setError(
            caught.message || "Could not connect to Dormora's backend."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }, search.trim() ? 350 : 0);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [isRenter, search, reloadCount]);

  useEffect(() => {
    if (!isRenter || selectedId === null) {
      return undefined;
    }

    const controller = new AbortController();

    async function loadDetails() {
      setDetailLoading(true);
      setDetailError("");
      setSelectedProperty(null);

      try {
        const response = await fetch(
          `${DISCOVERY_API}/${selectedId}`,
          {
            method: "GET",
            credentials: "include",
            cache: "no-store",
            mode: "cors",
            redirect: "error",
            signal: controller.signal,
          }
        );

        if (!response.ok) {
          throw new Error(await getErrorMessage(response));
        }

        const data = await response.json();

        if (!data.property || typeof data.property !== "object") {
          throw new Error("Invalid property details received.");
        }

        if (!controller.signal.aborted) {
          setSelectedProperty(data.property);
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setDetailError(
            caught.message || "Unable to load property details."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setDetailLoading(false);
        }
      }
    }

    loadDetails();

    return () => controller.abort();
  }, [isRenter, selectedId]);

  const visibleProperties = useMemo(() => {
    const results = properties.filter((property) => {
      if (!availableOnly) return true;
      return Number(property.available_rooms) > 0;
    });

    if (sortOrder === "price-low") {
      results.sort(
        (a, b) => Number(a.monthly_rent) - Number(b.monthly_rent)
      );
    } else if (sortOrder === "price-high") {
      results.sort(
        (a, b) => Number(b.monthly_rent) - Number(a.monthly_rent)
      );
    } else if (sortOrder === "rooms") {
      results.sort(
        (a, b) =>
          Number(b.available_rooms) - Number(a.available_rooms)
      );
    }

    return results;
  }, [properties, availableOnly, sortOrder]);

  function refresh() {
    setReloadCount((count) => count + 1);
  }

  function showProperty(propertyId) {
    setSelectedId(propertyId);
    setSelectedProperty(null);
    setDetailError("");
  }

  function returnToResults() {
    setSelectedId(null);
    setSelectedProperty(null);
    setDetailError("");
  }

  if (!isRenter) {
    return (
      <section className="dd-page">
        <style>{styles}</style>
        <div className="dd-state" role="alert">
          <Building2 size={36} />
          <h3>Renter Access Required</h3>
          <p>This page is available to registered renter accounts.</p>
        </div>
      </section>
    );
  }

  if (selectedId !== null) {
    return (
      <section className="dd-page">
        <style>{styles}</style>

        {detailLoading ? (
          <div className="dd-state" role="status">
            <RefreshCw size={33} />
            <h3>Loading Property Details</h3>
            <p>Retrieving the latest information from Dormora.</p>
          </div>
        ) : detailError ? (
          <div className="dd-state" role="alert">
            <Building2 size={33} />
            <h3>Property Unavailable</h3>
            <p>{detailError}</p>
            <button
              type="button"
              className="dd-button"
              onClick={returnToResults}
            >
              <ArrowLeft size={16} />
              Back to Results
            </button>
          </div>
        ) : selectedProperty ? (
          <DiscoveryDetail
            key={selectedProperty.id}
            property={selectedProperty}
            onBack={returnToResults}
          />
        ) : null}
      </section>
    );
  }

  return (
    <section className="dd-page">
      <style>{styles}</style>

      <div className="dd-header">
        <div>
          <h1>Discover Dorms</h1>
          <p>
            Find a rental property that matches your location,
            budget, and room availability.
          </p>
        </div>

        <div style={{ display: "flex", gap: 9, flexWrap: "wrap" }}>
          {onBack && (
            <button
              type="button"
              className="dd-button"
              onClick={onBack}
            >
              <ArrowLeft size={17} />
              Home
            </button>
          )}

          <button
            type="button"
            className="dd-button"
            onClick={refresh}
            disabled={loading}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </div>

      <div className="dd-intro">
        <div className="dd-intro-top">
          <div className="dd-intro-icon">
            <Building2 size={24} />
          </div>
          <h2>Find Your Next Place</h2>
        </div>

        <p>
          Explore dormitories, apartments, boarding houses,
          and rental rooms published by registered Dormora
          property owners. View photos, compare monthly
          rental prices, and check available rooms.
        </p>
      </div>

      <div className="dd-toolbar">
        <label className="dd-search">
          <Search size={18} />

          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by property name or location"
            aria-label="Search dorm properties"
            maxLength={100}
          />

          {search && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setSearch("")}
            >
              <X size={16} />
            </button>
          )}
        </label>

        <label className="dd-select-wrap">
          <SlidersHorizontal size={17} />

          <select
            className="dd-select"
            value={sortOrder}
            onChange={(event) => setSortOrder(event.target.value)}
            aria-label="Sort properties"
          >
            <option value="newest">Newest Listings</option>
            <option value="price-low">Lowest Price</option>
            <option value="price-high">Highest Price</option>
            <option value="rooms">Most Available Rooms</option>
          </select>
        </label>
      </div>

      <div className="dd-filter-row">
        <p>
          {loading
            ? "Loading published listings..."
            : error
              ? "Listings unavailable"
              : `${visibleProperties.length} ${
                  visibleProperties.length === 1
                    ? "property"
                    : "properties"
                } found`}
        </p>

        <label className="dd-filter">
          <input
            type="checkbox"
            checked={availableOnly}
            onChange={(event) =>
              setAvailableOnly(event.target.checked)
            }
          />
          Show available rooms only
        </label>
      </div>

      {loading ? (
        <div className="dd-state" role="status">
          <RefreshCw size={34} />
          <h3>Searching Dormora Properties</h3>
          <p>Retrieving published listings from the server.</p>
        </div>
      ) : error ? (
        <div className="dd-state" role="alert">
          <Building2 size={36} />
          <h3>Unable to Load Dorms</h3>
          <p>{error}</p>

          <button
            type="button"
            className="dd-button primary"
            onClick={refresh}
          >
            <RefreshCw size={16} />
            Try Again
          </button>
        </div>
      ) : visibleProperties.length === 0 ? (
        <div className="dd-state">
          <Search size={36} />
          <h3>No Matching Properties</h3>

          <p>
            {search.trim() || availableOnly
              ? "No published properties match your current search or filters."
              : "No properties have been published yet. Check again when property owners publish their listings."}
          </p>

          {(search || availableOnly) && (
            <button
              type="button"
              className="dd-button"
              onClick={() => {
                setSearch("");
                setAvailableOnly(false);
              }}
            >
              Clear Filters
            </button>
          )}
        </div>
      ) : (
        <div className="dd-grid">
          {visibleProperties.map((property) => (
            <PropertyCard
              key={property.id}
              property={property}
              onView={showProperty}
            />
          ))}
        </div>
      )}
    </section>
  );
}
