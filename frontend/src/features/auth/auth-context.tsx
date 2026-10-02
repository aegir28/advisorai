"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/**
 * Mock authentication. The product will use Google sign-in (OAuth) with no
 * separate AdvisorAI password. This mock mirrors that flow: a simulated
 * account chooser, then a required consent step. The fake session lives in
 * localStorage. Nothing here is secure: it is a prototype.
 */

export interface SessionUser {
  email: string;
  displayName: string;
  /** Null until the person has accepted the prototype / consent notice. */
  consentedAt: string | null;
}

type AuthStatus = "loading" | "authed" | "anon";

interface AuthContextValue {
  status: AuthStatus;
  user: SessionUser | null;
  /** Sign in with the (simulated) Google account. Pass `consent` when it was just given. */
  signIn: (account: { email: string; displayName: string }, consent?: boolean) => void;
  acceptConsent: () => void;
  signOut: () => void;
}

const SESSION_KEY = "advisorai.session.v2";

const AuthContext = createContext<AuthContextValue | null>(null);

function readSession(): SessionUser | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  } catch {
    return null;
  }
}

function writeSession(user: SessionUser | null) {
  try {
    if (user) window.localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    /* storage unavailable: the session lasts for this page only */
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

  const signIn = useCallback<AuthContextValue["signIn"]>((account, consent) => {
    const previous = readSession();
    const next: SessionUser = {
      ...account,
      consentedAt: consent ? new Date().toISOString() : (previous?.email === account.email ? previous.consentedAt : null),
    };
    writeSession(next);
    setUser(next);
    setStatus("authed");
  }, []);

  const acceptConsent = useCallback(() => {
    setUser((current) => {
      if (!current) return current;
      const next = { ...current, consentedAt: new Date().toISOString() };
      writeSession(next);
      return next;
    });
  }, []);

  const signOut = useCallback(() => {
    writeSession(null);
    setUser(null);
    setStatus("anon");
  }, []);

  const value = useMemo(() => ({ status, user, signIn, acceptConsent, signOut }), [status, user, signIn, acceptConsent, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
