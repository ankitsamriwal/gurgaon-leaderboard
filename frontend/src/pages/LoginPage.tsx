import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch, ApiRequestError } from "../lib/api";
import { useAuthStore } from "../store/auth";

export function LoginPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const [phone, setPhone] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [otp, setOtp] = useState("");
  const [debugOtp, setDebugOtp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function requestOtp(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const resp = await apiFetch<{ request_id: string; debug_otp: string | null }>("/auth/otp/request", {
        method: "POST",
        body: JSON.stringify({ phone }),
      });
      setRequestId(resp.request_id);
      setDebugOtp(resp.debug_otp);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Could not request an OTP.");
    }
  }

  async function verifyOtp(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const resp = await apiFetch<{
        access_token: string;
        refresh_token: string;
        user: { id: string; display_name: string };
      }>("/auth/otp/verify", {
        method: "POST",
        body: JSON.stringify({ request_id: requestId, otp }),
      });
      setSession({ accessToken: resp.access_token, refreshToken: resp.refresh_token, user: resp.user });
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Could not verify that code.");
    }
  }

  return (
    <div>
      <h1>Log in</h1>
      {!requestId ? (
        <form onSubmit={requestOtp}>
          <label htmlFor="phone">Phone number</label>
          <input
            id="phone"
            type="tel"
            inputMode="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+919999999999"
            required
          />
          <button type="submit">Send code</button>
        </form>
      ) : (
        <form onSubmit={verifyOtp}>
          <label htmlFor="otp">Enter the 6-digit code</label>
          <input
            id="otp"
            type="text"
            inputMode="numeric"
            pattern="[0-9]{6}"
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
            required
          />
          {debugOtp && <p className="dev-hint">Dev build — code is {debugOtp}</p>}
          <button type="submit">Verify</button>
        </form>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
