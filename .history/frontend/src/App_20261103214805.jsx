
 // Dormora - File 31
 // Public page routes and shared light/dark mode preference.

 import { useEffect, useState } from "react";
 import { BrowserRouter, Routes, Route } from "react-router-dom";
 import LandingPage from "./pages/LandingPage";
 import LoginPage from "./pages/LoginPage";
 import RegisterPage from "./pages/RegisterPage";
 import ForgotPasswordPage from "./pages/ForgotPasswordPage";

 const THEME_STORAGE_KEY = "dormora-theme";

 // Read the theme previously selected in this browser.
 function getSavedTheme() {
   try {
     return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark";
   } catch {
     // Use light mode if browser storage is unavailable.
     return false;
   }
 }

 function App() {
   const [darkMode, setDarkMode] = useState(getSavedTheme);

   // Save the theme preference whenever it changes.
   useEffect(() => {
     try {
       window.localStorage.setItem(
         THEME_STORAGE_KEY,
         darkMode ? "dark" : "light"
       );
     } catch {
       // Theme switching still works when storage is unavailable.
     }
   }, [darkMode]);

   function toggleTheme() {
     setDarkMode((currentMode) => !currentMode);
   }

   return (
     <BrowserRouter>
       <Routes>
         <Route
           path="/"
           element={
             <LandingPage darkMode={darkMode} onToggleTheme={toggleTheme} />
           }
         />

         <Route
           path="/login"
           element={
             <LoginPage darkMode={darkMode} onToggleTheme={toggleTheme} />
           }
         />

         {/* Frontend-only preview: registration submission is still disabled. */}
         <Route
           path="/register"
           element={
             <RegisterPage darkMode={darkMode} onToggleTheme={toggleTheme} />
           }
         />

         {/* Frontend-only preview: account recovery is not connected to FastAPI. */}
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
