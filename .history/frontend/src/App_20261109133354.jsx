
/*
 * Dormora Frontend File 118 — route and theme-only application entry.
 * REPLACE: frontend/src/App.jsx (File 116).
 *
 * File 117 now owns the original ProtectedWorkspace implementation,
 * including server-verified role checks, session expiry, CSRF-protected
 * refresh/logout, and rendering the admin dashboard and password form.
 * No backend/database/API changes and no UI redesign.
 *
 * Note: AUTHORIZATION remains enforced by FastAPI, never by this router.
 */

import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ProtectedWorkspace from "./components/auth/ProtectedWorkspace";

const THEME_STORAGE_KEY = "dormora-theme";

function getSavedTheme() {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark";
  } catch {
    return false;
  }
}

function App() {
  const [darkMode, setDarkMode] = useState(getSavedTheme);

  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, darkMode ? "dark" : "light");
    } catch {
      // Theme switching works even when preference storage is unavailable.
    }
  }, [darkMode]);

  function toggleTheme() {
    setDarkMode((currentMode) => !currentMode);
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/login" element={<LoginPage darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/register" element={<RegisterPage darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/dashboard" element={<ProtectedWorkspace darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/renter" element={<ProtectedWorkspace requiredRole="renter" darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/owner" element={<ProtectedWorkspace requiredRole="property_owner" darkMode={darkMode} onToggleTheme={toggleTheme} />} />
        <Route path="/admin" element={<ProtectedWorkspace requiredRole="admin" darkMode={darkMode} onToggleTheme={toggleTheme} />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
