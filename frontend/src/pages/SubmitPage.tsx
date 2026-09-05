import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch, ApiRequestError } from "../lib/api";
import { useAuthStore } from "../store/auth";

export function SubmitPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [form, setForm] = useState({ name: "", developer_name: "", locality: "", rera_number: "", project_url: "" });
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  if (!user) {
    return (
      <p>
        <a href="/login">Log in</a> to submit a project.
      </p>
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiFetch("/projects", { method: "POST", body: JSON.stringify(form) });
      setSubmitted(true);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        if (err.code === "RERA_INVALID_FORMAT") setError("That RERA number doesn't look right.");
        else if (err.code === "RERA_DUPLICATE") setError("A project with this RERA number already exists.");
        else if (err.code === "RATE_LIMITED") setError("You've submitted the maximum for today — try again tomorrow.");
        else setError(err.message);
      } else {
        setError("Something went wrong.");
      }
    }
  }

  if (submitted) {
    return (
      <div>
        <h1>Submitted</h1>
        <p>
          Your project has been submitted for review. It will not appear on the public leaderboard until an
          admin approves it.
        </p>
        <button onClick={() => navigate("/")}>Back to leaderboard</button>
      </div>
    );
  }

  return (
    <div>
      <h1>Submit a project</h1>
      <p>
        It will be manually verified before the listing goes live — RERA numbers are checked against the
        public Haryana RERA portal by an admin.
      </p>
      <form onSubmit={handleSubmit}>
        <label htmlFor="name">Project name</label>
        <input
          id="name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />

        <label htmlFor="developer_name">Developer name</label>
        <input
          id="developer_name"
          value={form.developer_name}
          onChange={(e) => setForm({ ...form, developer_name: e.target.value })}
          required
        />

        <label htmlFor="locality">Locality</label>
        <input
          id="locality"
          value={form.locality}
          onChange={(e) => setForm({ ...form, locality: e.target.value })}
          required
        />

        <label htmlFor="rera_number">RERA number</label>
        <input
          id="rera_number"
          inputMode="text"
          placeholder="RC/REP/HARERA/GGM/..."
          value={form.rera_number}
          onChange={(e) => setForm({ ...form, rera_number: e.target.value })}
          required
        />

        <label htmlFor="project_url">Project website (optional)</label>
        <input
          id="project_url"
          type="url"
          value={form.project_url}
          onChange={(e) => setForm({ ...form, project_url: e.target.value })}
        />

        {error && <p role="alert">{error}</p>}
        <button type="submit">Submit for review</button>
      </form>
    </div>
  );
}
