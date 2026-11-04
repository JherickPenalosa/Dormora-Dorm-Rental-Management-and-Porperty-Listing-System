
 // Dormora - File 19
 // App routes and one shared light/dark mode preference.

 import { useEffect, useState } from "react";
 import { BrowserRouter, Routes, Route } from "react-router-dom";
 import LandingPage from "./pages/LandingPage";
 import LoginPage from "./pages/LoginPage";

 const THEME_STORAGE_KEY = "dormora-theme";

 // Read the theme previously selected in this browser.
 function getSavedTheme() {
   try {
     return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark";
   } catch {
     // If browser storage is unavailable, use light mode.
     return false;
   }
 }

 function App() {
   const [darkMode, setDarkMode] = useState(getSavedTheme);

   // Remember the selected theme when it changes.
   useEffect(() => {
     try {
       window.localStorage.setItem(
         THEME_STORAGE_KEY,
         darkMode ? "dark" : "light"
       );
     } catch {
       // The app can still switch themes without browser storage.
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
       </Routes>
     </BrowserRouter>
   );
 }

 export default App;
