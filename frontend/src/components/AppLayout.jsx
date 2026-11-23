import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { MODULES } from "../modules.js";

export default function AppLayout() {
  const { user, logout } = useAuth();
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">Career Companion</div>
        <nav>
          <NavLink to="/dashboard" className="nav-item">
            Dashboard
          </NavLink>
          {MODULES.map((m) => (
            <NavLink key={m.path} to={m.path} className="nav-item">
              <span className="nav-num">{m.num ?? "?"}</span>
              {m.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-name" title={user?.email}>
            {user?.full_name}
          </div>
          <button className="btn btn-ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
