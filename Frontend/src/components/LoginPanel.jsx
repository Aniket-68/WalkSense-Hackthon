import { useState } from "react";

export default function LoginPanel({ onLogin, error, onSwitchToSignup }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      await onLogin(email.trim().toLowerCase(), password);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-screen">
      <form className="login-card card" onSubmit={handleSubmit}>
        <h2>WalkSense Login</h2>
        <p>Sign in to access the camera, voice, and control APIs.</p>

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
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && <div className="login-error">{error}</div>}

        <button type="submit" disabled={loading}>
          {loading ? "Signing in..." : "Sign In"}
        </button>

        <p className="login-switch">
          Don&apos;t have an account?{" "}
          <button
            type="button"
            className="link-btn"
            onClick={onSwitchToSignup}
          >
            Create one
          </button>
        </p>
      </form>
    </div>
  );
}
