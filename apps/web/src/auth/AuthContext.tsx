import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { fetchMe } from "../api/client";

const STORAGE_KEY = "agent-factory:session-token";

export type Role = "viewer" | "approver" | "admin";
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  token: string | null;
  actor: string | null;
  role: Role | null;
  status: AuthStatus;
  setToken: (token: string) => void;
  logout: () => void;
}

const AuthReactContext = createContext<AuthContextValue | null>(null);

// /auth/callback redirects here as `#token=...` (a fragment, so it's never sent to the
// server or logged) rather than a query string.
function consumeTokenFromHash(): string | null {
  const match = /token=([^&]+)/.exec(window.location.hash);
  const rawToken = match?.[1];
  if (!rawToken) {
    return null;
  }
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  return decodeURIComponent(rawToken);
}

export function AuthProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [token, setTokenState] = useState<string | null>(
    () => consumeTokenFromHash() ?? localStorage.getItem(STORAGE_KEY),
  );
  const [actor, setActor] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    if (!token) {
      setStatus("unauthenticated");
      return;
    }
    localStorage.setItem(STORAGE_KEY, token);
    let cancelled = false;

    fetchMe(token)
      .then((session) => {
        if (cancelled) return;
        setActor(session.actor);
        setRole(session.role);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        localStorage.removeItem(STORAGE_KEY);
        setTokenState(null);
        setStatus("unauthenticated");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      actor,
      role,
      status,
      setToken: (next: string) => setTokenState(next),
      logout: () => {
        localStorage.removeItem(STORAGE_KEY);
        setTokenState(null);
        setActor(null);
        setRole(null);
        setStatus("unauthenticated");
      },
    }),
    [token, actor, role, status],
  );

  return <AuthReactContext.Provider value={value}>{children}</AuthReactContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthReactContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
