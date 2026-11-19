
/**
 * Dormora — Frontend File 38
 * Destination: frontend/src/services/dormoraApi.js
 *
 * First safe React/Vite ↔ FastAPI connection.
 * Uses GET only: /api/health and /api/csrf.
 * Does NOT submit registration, passwords, OTPs, or other personal data.
 * Does NOT enable any form, login, or authenticated route.
 *
 * IMPORTANT: Visit React at http://localhost:5173 and use FastAPI at
 * http://localhost:8000. Mixing localhost with 127.0.0.1 can prevent
 * the browser from sending SameSite CSRF cookies.
 *
 * For a future deployment, configure VITE_DORMORA_API_BASE_URL with the
 * public API origin. It is a public URL, NEVER a password or API secret.
 */

const configuredUrl = import.meta.env?.VITE_DORMORA_API_BASE_URL;

export const DORMORA_API_BASE_URL =
  typeof configuredUrl === "string" && configuredUrl.trim()
    ? configuredUrl.trim().replace(/\/+$/, "")
    : "http://localhost:8000";

// Kept only in module memory; never save a CSRF token in localStorage or a URL.
let csrfToken = null;

async function fetchPublicGet(path) {
  let response;
  try {
    response = await fetch(`${DORMORA_API_BASE_URL}${path}`, {
      method: "GET",
      credentials: "include", // Required for the HttpOnly CSRF-binding cookie.
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new Error(
      "Cannot reach the Dormora backend. Check that FastAPI is running on " +
        "http://localhost:8000 and the React page uses http://localhost:5173."
    );
  }

  if (!response.ok) {
    throw new Error(`Dormora backend request failed (HTTP ${response.status}).`);
  }

  try {
    return await response.json();
  } catch {
    throw new Error("Dormora backend returned an unreadable response.");
  }
}

/** Check that the actual FastAPI service is responding (read-only). */
export async function getBackendHealth() {
  const data = await fetchPublicGet("/api/health");
  if (data?.status !== "healthy" || typeof data.service !== "string") {
    throw new Error("Dormora backend health response was unexpected.");
  }
  return { status: data.status, service: data.service };
}

/**
 * Request a signed CSRF token. FastAPI separately sets an HttpOnly cookie.
 * The token remains in JavaScript memory for use by later integration files.
 */
export async function initializeCsrfProtection() {
  // Never retain an older token if retrieving a fresh token fails.
  csrfToken = null;
  const data = await fetchPublicGet("/api/csrf");
  const token = data?.csrf_token;

  if (
    typeof token !== "string" ||
    !/^v1\.[1-9][0-9]{0,15}\.[0-9a-f]{32}\.[0-9a-f]{64}$/.test(token)
  ) {
    throw new Error("Dormora backend returned an invalid CSRF token.");
  }

  csrfToken = token;
  return true;
}

/** Used by future form API integration. Never print its value in logs. */
export function getCsrfToken() {
  return csrfToken;
}

/** Called after logout or other changes that invalidate browser bindings. */
export function clearCsrfToken() {
  csrfToken = null;
}

/**
 * One safe connectivity check to run from the Vite browser console.
 * The returned summary intentionally excludes the actual CSRF token.
 */
export async function checkDormoraConnection() {
  const health = await getBackendHealth();
  const csrfReady = await initializeCsrfProtection();

  return {
    apiUrl: DORMORA_API_BASE_URL,
    backendStatus: health.status,
    backendService: health.service,
    csrfReady,
    registrationEnabled: false,
  };
}
