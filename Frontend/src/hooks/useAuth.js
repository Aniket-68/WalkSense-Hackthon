import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "../config";

const ACCESS_TOKEN_KEY = "walksense_access_token";
const USER_KEY = "walksense_user";

export function useAuth() {
  const [accessToken, setAccessToken] = useState(
    () => sessionStorage.getItem(ACCESS_TOKEN_KEY) || "",
  );
  const [user, setUser] = useState(() => {
    const raw = sessionStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  });
  const [isInitializing, setIsInitializing] = useState(true);
  const [authError, setAuthError] = useState("");

  const tokenRef = useRef(accessToken);
  const refreshInFlightRef = useRef(null);

  useEffect(() => {
    tokenRef.current = accessToken;
    if (accessToken) {
      sessionStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    } else {
      sessionStorage.removeItem(ACCESS_TOKEN_KEY);
    }
  }, [accessToken]);

  useEffect(() => {
    if (user) {
      sessionStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      sessionStorage.removeItem(USER_KEY);
    }
  }, [user]);

  const clearAuthState = useCallback(() => {
    setAccessToken("");
    setUser(null);
  }, []);

  const refreshSession = useCallback(async () => {
    if (refreshInFlightRef.current) return refreshInFlightRef.current;

    refreshInFlightRef.current = (async () => {
      try {
        const response = await fetch(`${API_BASE}/api/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        if (!response.ok) {
          clearAuthState();
          return false;
        }
        const data = await response.json();
        setAccessToken(data.access_token || "");
        setUser(data.user || null);
        setAuthError("");
        return true;
      } catch {
        clearAuthState();
        return false;
      } finally {
        refreshInFlightRef.current = null;
      }
    })();

    return refreshInFlightRef.current;
  }, [clearAuthState]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      await refreshSession();
      if (mounted) setIsInitializing(false);
    })();
    return () => {
      mounted = false;
    };
  }, [refreshSession]);

  const login = useCallback(async (email, password) => {
    setAuthError("");
    const response = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      clearAuthState();
      setAuthError(data.detail || "Login failed");
      return false;
    }
    setAccessToken(data.access_token || "");
    setUser(data.user || null);
    setAuthError("");
    return true;
  }, [clearAuthState]);

  const logout = useCallback(async () => {
    const headers = {};
    if (tokenRef.current) {
      headers.Authorization = `Bearer ${tokenRef.current}`;
    }
    try {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers,
      });
    } finally {
      clearAuthState();
    }
  }, [clearAuthState]);

  const authFetch = useCallback(async (url, options = {}) => {
    let token = tokenRef.current;
    if (!token) {
      const refreshed = await refreshSession();
      if (!refreshed) throw new Error("Not authenticated");
      token = tokenRef.current;
    }

    const headers = new Headers(options.headers || {});
    headers.set("Authorization", `Bearer ${token}`);

    let response = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
    });

    if (response.status !== 401) return response;

    const refreshed = await refreshSession();
    if (!refreshed) {
      throw new Error("Session expired");
    }

    const retriedHeaders = new Headers(options.headers || {});
    retriedHeaders.set("Authorization", `Bearer ${tokenRef.current}`);
    response = await fetch(url, {
      ...options,
      headers: retriedHeaders,
      credentials: "include",
    });

    return response;
  }, [refreshSession]);

  const loginWithBundle = useCallback((bundle) => {
    setAccessToken(bundle.access_token || "");
    setUser(bundle.user || null);
    setAuthError("");
  }, []);

  return {
    user,
    accessToken,
    authError,
    isInitializing,
    isAuthenticated: Boolean(accessToken && user),
    login,
    loginWithBundle,
    logout,
    refreshSession,
    authFetch,
  };
}
