import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch, ApiRequestError } from "../lib/api";
import { useAuthStore } from "../store/auth";

const AMENITY_OPTIONS = [
  "Clubhouse",
  "Swimming pool",
  "Gym",
  "Kids' play area",
  "Landscaped gardens",
  "Sports facilities",
  "24x7 security",
  "Power backup",
  "Concierge",
  "Spa",
];

const PROPERTY_TYPES = [
  { value: "apartment", label: "Apartment" },
  { value: "villa", label: "Villa" },
  { value: "townhouse", label: "Townhouse" },
] as const;

/** The standardized listing template: every entry on the board follows
 * this same shape - logo, project name, location, property type + unit
 * sizes, amenities. Submitting lists the project live with its Rs 500
 * mock opening bid ("bidding starts from Rs 500"). */
export function SubmitPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [form, setForm] = useState({
    name: "",
    developer_name: "",
    locality: "",
    rera_number: "",
    project_url: "",
    logo_url: "",
    property_type: "apartment" as string,
    unit_sizes: "",
  });
  const [amenities, setAmenities] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  if (!user) {
    return (
      <p>
        <Link to="/login?next=/submit">Log in</Link> to list a project.
      </p>
    );
  }

  function toggleAmenity(a: string) {
    setAmenities((cur) => (cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a]));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await apiFetch("/projects", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          developer_name: form.developer_name,
          locality: form.locality,
          rera_number: form.rera_number,
          project_url: form.project_url || null,
          logo_url: form.logo_url || null,
          property_type: form.property_type,
          unit_sizes: form.unit_sizes || null,
          amenities: amenities.length ? amenities.join(", ") : null,
        }),
      });
      setSubmitted(true);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        if (err.code === "RERA_INVALID_FORMAT") setError("That RERA number doesn't look right.");
        else if (err.code === "RERA_DUPLICATE") setError("A project with this RERA number already exists.");
        else if (err.code === "RATE_LIMITED") setError("You've submitted the maximum for today - try again tomorrow.");
        else setError(err.message);
      } else {
        setError("Something went wrong.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="submit-done">
        <h1>You're on the board</h1>
        <p>
          Your project is live with its ₹500 opening bid (mock payment - no real money moved). Outbid the
          leader by ₹1 to take the crown.
        </p>
        <button onClick={() => navigate("/")}>See the leaderboard</button>
      </div>
    );
  }

  return (
    <div className="submit-page">
      <h1>List your project</h1>
      <p>
        Every entry follows the same template. Listing costs a ₹500 opening bid - mock payment, no real
        money moves.
      </p>
      <form onSubmit={handleSubmit} className="template-form">
        <fieldset>
          <legend>1 · Logo</legend>
          <label htmlFor="logo_url">Logo image URL</label>
          <input
            id="logo_url"
            type="url"
            placeholder="https://…/logo.png"
            value={form.logo_url}
            onChange={(e) => setForm({ ...form, logo_url: e.target.value })}
          />
          <div className="logo-preview" aria-hidden="true">
            {form.logo_url ? (
              <img src={form.logo_url} alt="" onError={(e) => ((e.target as HTMLImageElement).style.display = "none")} />
            ) : (
              <span>{form.name ? form.name.charAt(0).toUpperCase() : "₹"}</span>
            )}
          </div>
          <small>No logo? Leave it blank - the board shows the project's initial instead.</small>
        </fieldset>

        <fieldset>
          <legend>2 · Project name</legend>
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
          <label htmlFor="rera_number">RERA number</label>
          <input
            id="rera_number"
            inputMode="text"
            placeholder="RC/REP/HARERA/GGM/..."
            value={form.rera_number}
            onChange={(e) => setForm({ ...form, rera_number: e.target.value })}
            required
          />
        </fieldset>

        <fieldset>
          <legend>3 · Location</legend>
          <label htmlFor="locality">Sector / locality, Gurgaon</label>
          <input
            id="locality"
            placeholder="Sector 106, Dwarka Expressway"
            value={form.locality}
            onChange={(e) => setForm({ ...form, locality: e.target.value })}
            required
          />
        </fieldset>

        <fieldset>
          <legend>4 · Amenities &amp; size</legend>
          <span className="field-label">Property type</span>
          <div className="chip-row" role="radiogroup" aria-label="Property type">
            {PROPERTY_TYPES.map((t) => (
              <button
                key={t.value}
                type="button"
                role="radio"
                aria-checked={form.property_type === t.value}
                className={form.property_type === t.value ? "chip chip-on" : "chip"}
                onClick={() => setForm({ ...form, property_type: t.value })}
              >
                {t.label}
              </button>
            ))}
          </div>
          <label htmlFor="unit_sizes">Unit sizes</label>
          <input
            id="unit_sizes"
            placeholder="3 & 4 BHK"
            value={form.unit_sizes}
            onChange={(e) => setForm({ ...form, unit_sizes: e.target.value })}
          />
          <span className="field-label">Amenities</span>
          <div className="chip-row">
            {AMENITY_OPTIONS.map((a) => (
              <button
                key={a}
                type="button"
                aria-pressed={amenities.includes(a)}
                className={amenities.includes(a) ? "chip chip-on" : "chip"}
                onClick={() => toggleAmenity(a)}
              >
                {a}
              </button>
            ))}
          </div>
        </fieldset>

        <label htmlFor="project_url">Project website (optional)</label>
        <input
          id="project_url"
          type="url"
          value={form.project_url}
          onChange={(e) => setForm({ ...form, project_url: e.target.value })}
        />

        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <button type="submit" disabled={submitting}>
          {submitting ? "Listing…" : "List it for ₹500 (mock)"}
        </button>
      </form>
    </div>
  );
}
