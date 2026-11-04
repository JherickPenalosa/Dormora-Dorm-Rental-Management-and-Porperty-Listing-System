/*
  Dormora - File 23
  Registration page appearance only.

  No account is created and no data is sent to a server.
  The final security questions, validation limits, and additional
  system fields must match the approved proposal and student seed.
*/

import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Eye,
  EyeOff,
  House,
  LockKeyhole,
  Moon,
  ShieldCheck,
  Sun,
  UserRoundPlus,
} from "lucide-react";
import "../App.css";

// Age is displayed for convenience. FastAPI must calculate and verify it again.
function calculateAge(birthdate) {
  if (!birthdate) return null;

  const birth = new Date(`${birthdate}T00:00:00`);
  if (Number.isNaN(birth.getTime())) return null;

  const today = new Date();
  if (birth > today) return null;

  let age = today.getFullYear() - birth.getFullYear();
  const monthDifference = today.getMonth() - birth.getMonth();

  if (
    monthDifference < 0 ||
    (monthDifference === 0 && today.getDate() < birth.getDate())
  ) {
    age -= 1;
  }

  return age;
}

function RegisterPage({ darkMode, onToggleTheme }) {
  const [accountType, setAccountType] = useState("renter");
  const [birthdate, setBirthdate] = useState("");
  const [extension, setExtension] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);

  const age = calculateAge(birthdate);
  const isOwner = accountType === "owner";

  // No registration request is sent from this frontend-only preview.
  function handlePreviewSubmit(event) {
    event.preventDefault();
  }

  return (
    <div
      className={
        darkMode
          ? "dormora dark-mode register-page"
          : "dormora light-mode register-page"
      }
    >
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>

      <header className="site-header">
        <div className="page-container header-content register-header-content">
          <Link className="brand" to="/">
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </Link>

          <nav className="register-header-nav" aria-label="Registration navigation">
            <Link to="/">Home</Link>
            <Link to="/login">Log In</Link>
            <button
              className="theme-button"
              type="button"
              onClick={onToggleTheme}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              title={darkMode ? "Light mode" : "Dark mode"}
            >
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>