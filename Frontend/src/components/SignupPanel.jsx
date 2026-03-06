import { useState } from "react";
import { API_BASE } from "../config";

export default function SignupPanel({ onSignup, onSwitchToLogin }) {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (username.trim().length < 3) {
      setError("Username must be at least 3 characters");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          username: username.trim().toLowerCase(),
          password,
          confirm_password: confirmPassword,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail || "Registration failed");
        return;
      }

      // Auto-login: pass token bundle up to App
      onSignup(data);
    } catch {
      setError("Network error — please try again");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-screen">
      <form className="login-card card" onSubmit={handleSubmit}>
        <h2>Create Account</h2>
        <p>Join WalkSense to access navigation assistance.</p>

        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
          />
        </label>

        <label>
          Username
          <input
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Choose a username"
            minLength={3}
            required
          />
        </label>

        <label>
          Password
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            minLength={8}
            required
          />
        </label>

        <label>
          Confirm Password
          <input
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Repeat your password"
            minLength={8}
            required
          />
        </label>

        {error && <div className="login-error">{error}</div>}

        <button type="submit" disabled={loading}>
          {loading ? "Creating account..." : "Create Account"}
        </button>

        <p className="login-switch">
          Already have an account?{" "}
          <button
            type="button"
            className="link-btn"
            onClick={onSwitchToLogin}
          >
            Sign in
          </button>
        </p>
      </form>
    </div>
  );
}
