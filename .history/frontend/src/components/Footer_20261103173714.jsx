
 // Dormora - File 10
 // Reusable footer for the public-facing pages.

 import { House } from "lucide-react";

 function Footer() {
   return (
     <footer className="site-footer">
       <div className="page-container footer-content">
         <div className="footer-brand">
           <House size={21} />
           <strong>Dormora</strong>
         </div>

         <p>© 2026 Dormora. All rights reserved.</p>

         <nav className="footer-links" aria-label="Footer navigation">
           <a href="#home">Home</a>
           <a href="#features">Features</a>
           <a href="#about">About</a>
         </nav>
       </div>
     </footer>
   );
 }

 export default Footer;
