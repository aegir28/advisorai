"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/**
 * Mock authentication. The blueprint specifies email OTP / magic link via
 * Supabase Auth; this mock mirrors that flow (no passwords) and stores a
 * fake session in localStorage. Nothing here is secure — it is a prototype.
 */

export interface SessionUser {
  email: string;
  displayName: string;
  consentedAt: string;
}

type AuthStatus = "loading" | "authed" | "anon";

interface AuthContextValue {
  status: AuthStatus;
  user: SessionUser | null;
  /** The demo one-time code (shown on screen because no email is sent). */
  demoCode: string;
  signIn: (email: string, consentedAt?: string) => void;
  signOut: () => void;
}

const SESSION_KEY = "advisorai.session.v1";
export const DEMO_OTP = "123456";

const AuthContext = createContext<AuthContextValue | null>(null);

function readSession(): SessionUser | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    const existing = readSession();
    setUser(existing);
    setStatus(existing ? "authed" : "anon");
  }, []);

  const signIn = useCallback((email: string, consentedAt?: string) => {
    const previous = readSession();
    const next: SessionUser = {
      email,
      displayName: email.split("@")[0] || "Demo user",
      consentedAt: consentedAt ?? previous?.consentedAt ?? new Date().toISOString(),
    };
    try {
      window.localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    } catch {
      /* storage unavailable: the session lasts for this page only */
    }
    setUser(next);
    setStatus("authed");
  }, []);

  const signOut = useCallback(() => {
    try {
      window.localStorage.removeItem(SESSION_KEY);
    } catch {
      /* ignore */
    }
    setUser(null);
    setStatus("anon");
  }, []);

  const value = useMemo(() => ({ status, user, demoCode: DEMO_OTP, signIn, signOut }), [status, user, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
