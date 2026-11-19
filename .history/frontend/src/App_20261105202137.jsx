
//
// Dormora — Frontend File 59
// Public routes with Privacy Notice integration.
// Preserves all existing pages and theme preferences.
//

import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import PrivacyNoticePage from "./pages/PrivacyNoticePage";

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
      window.localStorage.setItem(
        THEME_STORAGE_KEY,
        darkMode ? "dark" : "light"
      );
    } catch {
      // Theme switching continues even if storage is unavailable.
    }
  }, [darkMode]);

  function toggleTheme() {
    setDarkMode((currentMode) => !currentMode);
  }

  return (
    <BrowserRouter>
      <Routes>
        {/* Landing page */}
        <Route
          path="/"
          element={
            <LandingPage
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />

        {/* Login page */}
        <Route
          path="/login"
          element={
            <LoginPage
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />

        {/* Registration remains a frontend preview */}
        <Route
          path="/register"
          element={
            <RegisterPage
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />

        {/* File 58 Privacy Notice */}
        <Route
          path="/privacy"
          element={
            <PrivacyNoticePage
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />

        {/* Account recovery remains a frontend preview */}
        <Route
          path="/forgot-password"
          element={
            <ForgotPasswordPage
              darkMode={darkMode}
              onToggleTheme={toggleTheme}
            />
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
