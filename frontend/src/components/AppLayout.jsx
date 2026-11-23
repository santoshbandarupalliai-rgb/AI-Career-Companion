import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { MODULES } from "../modules.js";
import Icon from "./Icon.jsx";

// The two assistants live in the header and the floating button, not in the side menu.
const ASSISTANT_PATHS = ["/product-assistant", "/career-assistant"];
const NAV_MODULES = MODULES.filter((m) => !ASSISTANT_PATHS.includes(m.path));

function initials(name) {
  const parts = (name || "?").trim().split(/\s+/);
  return ((parts[0]?.[0] || "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // close the mobile menu after navigating
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  const onCareerPage = location.pathname.startsWith("/career-assistant");

  return (
    <div className="app">
      <header className="header">
        <button className="menu-btn" onClick={() => setOpen((o) => !o)} aria-label="Toggle menu" aria-expanded={open}>
          <Icon name="menu" size={20} />
        </button>
        <Link to="/dashboard" className="brand">
          <span className="brand-mark" aria-hidden="true">CC</span>
          <span className="brand-name">Career Companion</span>
        </Link>
        <div className="header-right">
          <NavLink to="/product-assistant" className="header-pill">
            <Icon name="/product-assistant" size={16} />
            <span>Product Assistant</span>
          </NavLink>
          <div className="user-chip" title={user?.email}>
            <span className="avatar" aria-hidden="true">{initials(user?.full_name)}</span>
            <span className="user-name">{user?.full_name}</span>
          </div>
          <button className="header-btn" onClick={logout} aria-label="Sign out">
            <Icon name="logout" size={16} />
            <span>Sign out</span>
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className={`sidebar${open ? " open" : ""}`}>
          <nav aria-label="Main">
            <NavLink to="/dashboard" className="nav-item">
              <Icon name="dashboard" />
              Dashboard
            </NavLink>
            <div className="nav-section">Modules</div>
            {NAV_MODULES.map((m) => (
              <NavLink key={m.path} to={m.path} className="nav-item">
                <Icon name={m.path} />
                {m.label}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-note small muted">Sample internships are fictional demo data.</div>
        </aside>
        {open && <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
        <main className="content">
          <div className="content-inner">
            <Outlet />
          </div>
        </main>
      </div>

      {!onCareerPage && (
        <Link to="/career-assistant" className="fab" aria-label="Open the Career Assistant">
          <Icon name="/career-assistant" size={20} />
          <span className="fab-label">Career Assistant</span>
        </Link>
      )}
    </div>
  );
}
