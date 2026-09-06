import { Link, Route, Routes } from "react-router-dom";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { SubmitPage } from "./pages/SubmitPage";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { AdminPage } from "./pages/AdminPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { TermsPage } from "./pages/TermsPage";
import { useAuthStore } from "./store/auth";

function roleFromToken(token: string | null): string | null {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.role === "string" ? payload.role : null;
  } catch {
    return null;
  }
}

export function App() {
  const user = useAuthStore((s) => s.user);
  const accessToken = useAuthStore((s) => s.accessToken);
  const clearSession = useAuthStore((s) => s.clearSession);
  const isAdmin = roleFromToken(accessToken) === "admin";

  return (
    <div className="app">
      <nav className="nav">
        <Link to="/" className="brand">Gurgaon<span>Leaderboard</span></Link>
        <Link to="/submit">Submit a project</Link>
        {user ? (
          <>
            <Link to="/dashboard">Dashboard</Link>
            {isAdmin && <Link to="/admin">Admin</Link>}
            <button onClick={clearSession}>Log out</button>
          </>
        ) : (
          <Link to="/login">Log in</Link>
        )}
      </nav>

      <main>
        <Routes>
          <Route path="/" element={<LeaderboardPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/submit" element={<SubmitPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/terms" element={<TermsPage />} />
        </Routes>
      </main>

      <footer className="site-footer">
        <Link to="/privacy">Privacy</Link>
        <Link to="/terms">Terms</Link>
      </footer>
    </div>
  );
}
