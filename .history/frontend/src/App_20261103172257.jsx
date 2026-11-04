
 // Dormora - File 7
 // Main application router. Each page will have its own file.

 import { BrowserRouter, Routes, Route } from "react-router-dom";
 import LandingPage from "./pages/LandingPage";

 function App() {
   return (
     <BrowserRouter>
       <Routes>
         {/* Public landing page */}
         <Route path="/" element={<LandingPage />} />

         {/* Login, registration, and role-based pages will be added later. */}
       </Routes>
     </BrowserRouter>
   );
 }

 export default App;
