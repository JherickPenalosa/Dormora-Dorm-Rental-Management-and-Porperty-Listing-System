
import { useState } from "react";
import {
  ArrowRight,
  BedDouble,
  Building2,
  CalendarDays,
  Calculator,
  CheckCircle2,
  Coins,
  House,
  MapPin,
  Search,
  Wallet,
} from "lucide-react";

import Navbar from "../components/Navbar";
import dashboardImage from "../assets/dormora-hero-laptop.png";
import "../App.css";

// Temporary sample listings. Real listings will be loaded from FastAPI later.
const sampleRentals = [
  {
    id: 1,
    name: "Riverside Dormitory",
    location: "Near the university",
    price: 4500,
    type: "Shared room",
    imageStyle: "rental-image-one",
  },
  {
    id: 2,
    name: "Maple Residences",
    location: "City center",
    price: 5000,
    type: "Private room",
    imageStyle: "rental-image-two",
  },
  {
    id: 3,
    name: "Central Stay Dorm",
    location: "Near public transport",
    price: 4800,
    type: "Dormitory",
    imageStyle: "rental-image-three",
  },
];

function LandingPage() {
  // Keep state here for now; Navbar receives it through props.
  const [darkMode, setDarkMode] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  function closeMenu() {
    setMenuOpen(false);
  }

  return (
    <div className={darkMode ? "dormora dark-mode" : "dormora light-mode"}>

      {/* FILE 9: Reusable navbar from File 8. */}
      <Navbar
        darkMode={darkMode}
        menuOpen={menuOpen}
        onToggleTheme={() => setDarkMode(!darkMode)}
        onToggleMenu={() => setMenuOpen(!menuOpen)}
        onCloseMenu={closeMenu}
      />

      <main>
        {/* 2. Hero section */}
        <section className="hero-section" id="home">
          <div className="page-container hero-layout">
            <div className="hero-text">
              <span className="eyebrow">For renters and property owners aged 18+</span>
              <h1>
                Find your space.
                <span> Track your rent.</span>
              </h1>
              <p>
                Discover places to rent, manage your monthly payments, and
                keep your rental records organized in one convenient place.
              </p>
              <div className="hero-buttons">
                <a className="button button-primary" href="#featured-rentals">
                  <Search size={19} /> Explore Rentals
                </a>
                <a className="button button-outline" href="#features">
                  See Our Features <ArrowRight size={18} />
                </a>
              </div>
              <div className="hero-highlights">
                <span><CheckCircle2 size={17} /> Personal rent tracking</span>
                <span><CheckCircle2 size={17} /> Owner-managed listings</span>
              </div>
            </div>

            {/* Temporary laptop asset, to be replaced with a real dashboard screenshot. */}
            <div className="hero-preview">
              <img
                src={dashboardImage}
                className="hero-laptop-image"
                alt="Dormora rent dashboard displayed on a laptop"
              />
            </div>
          </div>
        </section>

        {/* 3. Feature cards */}
        <section className="features-section page-container" id="features">
          <div className="feature-grid">
            <article className="feature-card">
              <div className="feature-icon"><House size={25} /></div>
              <div>
                <h3>Dorm Discovery</h3>
                <p>Browse available places with owner-submitted photos and details.</p>
              </div>
            </article>
            <article className="feature-card">
              <div className="feature-icon"><CalendarDays size={25} /></div>
              <div>
                <h3>Rent Tracker</h3>
                <p>Track due dates, recorded payments, and remaining balances.</p>
              </div>
            </article>
            <article className="feature-card">
              <div className="feature-icon"><Coins size={25} /></div>
              <div>
                <h3>Deposit Tracker</h3>
                <p>Keep a private record of your deposit and its return status.</p>
              </div>
            </article>
            <article className="feature-card">
              <div className="feature-icon"><Calculator size={25} /></div>
              <div>
                <h3>Move-in Estimator</h3>
                <p>Estimate advance rent, deposits, and initial moving costs.</p>
              </div>
            </article>
          </div>
        </section>

        {/* 4. Temporary rental previews */}
        <section className="rentals-section page-container" id="featured-rentals">
          <div className="section-heading">
            <div>
              <h2>Featured Rentals</h2>
              <p>Examples of how available properties will appear in Dormora.</p>
            </div>
            <span className="preview-note">Sample listings only</span>
          </div>
          <div className="rental-grid">
            {sampleRentals.map((rental) => (
              <article className="rental-card" key={rental.id}>
                <div className={`rental-image ${rental.imageStyle}`}>
                  <BedDouble size={43} strokeWidth={1.4} />
                  <span>Photo preview</span>
                </div>
                <div className="rental-details">
                  <span className="rental-type">{rental.type}</span>
                  <h3>{rental.name}</h3>
                  <p><MapPin size={15} /> {rental.location}</p>
                  <strong>
                    ₱{rental.price.toLocaleString("en-PH")}
                    <small> / month</small>
                  </strong>
                </div>
              </article>
            ))}
          </div>
        </section>

        {/* 5. Renter and owner overview */}
        <section className="how-section page-container" id="how-it-works">
          <div className="section-heading">
            <div>
              <h2>How Dormora Works</h2>
              <p>Simple tools for the two types of users.</p>
            </div>
          </div>
          <div className="role-grid">
            <article className="role-card renter-role">
              <div className="role-icon"><Wallet size={30} /></div>
              <div>
                <h3>For Renters</h3>
                <p>
                  Find available rentals, plan move-in costs, and track your rent
                  and deposit privately.
                </p>
              </div>
            </article>
            <article className="role-card owner-role">
              <div className="role-icon"><Building2 size={30} /></div>
              <div>
                <h3>For Property Owners</h3>
                <p>
                  Publish rental listings with photos, update prices, and manage
                  availability.
                </p>
              </div>
            </article>
          </div>
        </section>

        {/* 6. About banner */}
        <section className="about-section page-container" id="about">
          <div className="about-banner">
            <div>
              <h2>Find your next place. Stay organized.</h2>
              <p>
                Designed to make rental discovery and personal rent tracking simpler.
              </p>
            </div>
            <a className="button button-white" href="#home">
              Back to Top <ArrowRight size={18} />
            </a>
          </div>
        </section>
      </main>

      {/* 7. Footer (will become Footer.jsx in a later file) */}
      <footer className="site-footer">
        <div className="page-container footer-content">
          <div className="footer-brand"><House size={21} /> <strong>Dormora</strong></div>
          <p>© 2026 Dormora. All rights reserved.</p>
          <div className="footer-links">
            <a href="#home">Home</a>
            <a href="#features">Features</a>
            <a href="#about">About</a>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default LandingPage;
