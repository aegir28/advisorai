"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { defaultHttpClient, setAccessTokenGetter } from "@/lib/api/http";
import { fetchMe, postConsent } from "@/lib/api/http/me";
import { CONSENT_VERSION, PENDING_CONSENT_KEY } from "./consent";
import { AUTH_MODE, supabase, type AuthMode } from "./supabase";

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
  /** Real Google sign-in (supabase mode): redirects to Google. `consent` = ticked before leaving. */
  signInWithGoogle: (options?: { consent?: boolean }) => Promise<void>;
  acceptConsent: () => void;
  signOut: () => void;
  mode: AuthMode;
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
  return AUTH_MODE === "supabase" ? <SupabaseAuthProvider>{children}</SupabaseAuthProvider> : <MockAuthProvider>{children}</MockAuthProvider>;
}

function SupabaseAuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const refresh = useCallback(async (session: { user: { email?: string; user_metadata?: Record<string, unknown> } } | null) => {
    if (!session) {
      setUser(null);
      setStatus("anon");
      return;
    }
    try {
      const client = defaultHttpClient();
      let me = await fetchMe(client);
      // Consent ticked on the sign-up screen before the redirect is recorded now, once, with the user's token.
      if (!me.consentedAt && window.sessionStorage.getItem(PENDING_CONSENT_KEY) === "1") {
        me = await postConsent(client, CONSENT_VERSION);
      }
      window.sessionStorage.removeItem(PENDING_CONSENT_KEY);
      const meta = session.user.user_metadata ?? {};
      const fallbackName = typeof meta.full_name === "string" ? meta.full_name : typeof meta.name === "string" ? meta.name : "";
      setUser({ email: session.user.email ?? "", displayName: me.displayName ?? fallbackName, consentedAt: me.consentedAt });
      setStatus("authed");
    } catch {
      // The backend could not be reached or refused the token: treat as signed out rather than half signed in.
      setUser(null);
      setStatus("anon");
    }
  }, []);

  useEffect(() => {
    const sb = supabase();
    setAccessTokenGetter(async () => (await sb.auth.getSession()).data.session?.access_token ?? null);
    void sb.auth.getSession().then(({ data }) => refresh(data.session));
    const { data } = sb.auth.onAuthStateChange((_event, session) => {
      // Never call Supabase from inside this callback (it can deadlock); defer.
      setTimeout(() => void refresh(session), 0);
    });
    return () => {
      data.subscription.unsubscribe();
      setAccessTokenGetter(undefined);
    };
  }, [refresh]);

  const signInWithGoogle = useCallback<AuthContextValue["signInWithGoogle"]>(async (options) => {
    if (options?.consent) window.sessionStorage.setItem(PENDING_CONSENT_KEY, "1");
    await supabase().auth.signInWithOAuth({ provider: "google", options: { redirectTo: `${window.location.origin}/home` } });
  }, []);

  const acceptConsent = useCallback(() => {
    void postConsent(defaultHttpClient(), CONSENT_VERSION).then((me) => {
      setUser((current) => (current ? { ...current, consentedAt: me.consentedAt } : current));
    });
  }, []);

  const signOut = useCallback(() => {
    void supabase().auth.signOut();
    setUser(null);
    setStatus("anon");
  }, []);

  const signIn = useCallback<AuthContextValue["signIn"]>(() => {
    throw new Error("The account chooser is only available in mock auth mode.");
  }, []);

  const value = useMemo(
    () => ({ status, user, signIn, signInWithGoogle, acceptConsent, signOut, mode: "supabase" as const }),
    [status, user, signIn, signInWithGoogle, acceptConsent, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function MockAuthProvider({ children }: { children: React.ReactNode }) {
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

  const signInWithGoogle = useCallback<AuthContextValue["signInWithGoogle"]>(async () => {
    throw new Error("Real Google sign-in needs NEXT_PUBLIC_AUTH_MODE=supabase.");
  }, []);

  const value = useMemo(
    () => ({ status, user, signIn, signInWithGoogle, acceptConsent, signOut, mode: "mock" as const }),
    [status, user, signIn, signInWithGoogle, acceptConsent, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
