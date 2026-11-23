import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext.jsx";
import AppLayout from "./components/AppLayout.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import ComingSoonPage from "./pages/ComingSoonPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";
import ResumePage from "./pages/ResumePage.jsx";
import InternshipsPage from "./pages/InternshipsPage.jsx";
import ProductAssistantPage from "./pages/ProductAssistantPage.jsx";
import MatchingPage from "./pages/MatchingPage.jsx";
import SkillGapPage from "./pages/SkillGapPage.jsx";
import { MODULES } from "./modules.js";

// Modules that are built; the rest show a "coming in phase N" page.
const PAGES = {
  "/profile": ProfilePage,
  "/resume": ResumePage,
  "/internships": InternshipsPage,
  "/product-assistant": ProductAssistantPage,
  "/matching": MatchingPage,
  "/skill-gap": SkillGapPage,
};

function RequireAuth({ children }) {
  const { user, loading, bootError, retry } = useAuth();
  const location = useLocation();
  if (loading) return <div className="center-screen muted">Loading…</div>;
  if (bootError)
    return (
      <div className="center-screen">
        <div className="card stack">
          <div className="alert">{bootError} Is the backend running on port 8000?</div>
          <button className="btn btn-primary" onClick={retry}>
            Try again
          </button>
        </div>
      </div>
    );
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

function GuestOnly({ children }) {
  const { user, loading, bootError } = useAuth();
  if (loading) return <div className="center-screen muted">Loading…</div>;
  if (user || bootError) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
      <Route path="/register" element={<GuestOnly><RegisterPage /></GuestOnly>} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        {MODULES.map((m) => {
          const Page = PAGES[m.path];
          return <Route key={m.path} path={m.path} element={Page ? <Page /> : <ComingSoonPage module={m} />} />;
        })}
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
