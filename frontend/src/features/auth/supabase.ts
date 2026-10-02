import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Real authentication is Google sign-in through Supabase Auth, switched on with NEXT_PUBLIC_AUTH_MODE=supabase.
 * The default is the Phase 1 mock, which needs no configuration.
 *
 * ONLY the project URL and the public ANON key are used here. They are designed to be public: the anon key
 * grants nothing by itself (the database has no client policies and the Data API is switched off; every read
 * and write goes through the backend with the user's own token). A service-role key must NEVER be placed in
 * the frontend or any NEXT_PUBLIC_* variable, so `assertPublicKey` refuses to start with one.
 */
export type AuthMode = "mock" | "supabase";

export const AUTH_MODE: AuthMode = process.env.NEXT_PUBLIC_AUTH_MODE === "supabase" ? "supabase" : "mock";

/** The role claim of a JWT, without verifying it (the point is only to refuse an obviously wrong key). */
export function jwtRole(token: string): string | null {
  const part = token.split(".")[1];
  if (!part) return null;
  try {
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(part.length / 4) * 4, "="));
    const role = (JSON.parse(json) as { role?: unknown }).role;
    return typeof role === "string" ? role : null;
  } catch {
    return null;
  }
}

export function assertPublicKey(key: string): void {
  if (jwtRole(key) === "service_role" || /service[_-]?role/i.test(key) || key.startsWith("sb_secret_")) {
    throw new Error("A service-role / secret key was configured for the frontend. Use the public anon key only.");
  }
}

let cached: SupabaseClient | null = null;

export function supabase(): SupabaseClient {
  if (cached) return cached;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) throw new Error("NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are required for Supabase auth.");
  assertPublicKey(anonKey);
  cached = createClient(url, anonKey, {
    auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  return cached;
}
