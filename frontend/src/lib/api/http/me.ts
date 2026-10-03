import { z } from "zod";
import type { HttpClient } from "./client";

/** GET /api/v1/me and POST /api/v1/me/consent: the signed-in user's own profile. Strict wire shape. */
export const MeWireSchema = z.strictObject({
  user_id: z.string().min(1),
  display_name: z.string().optional(),
  locale: z.string(),
  consented_at: z.string().optional(),
  consent_version: z.string().optional(),
  data_mode: z.literal("synthetic_only"),
});

export interface Me {
  userId: string;
  displayName: string | null;
  locale: string;
  consentedAt: string | null;
  consentVersion: string | null;
}

export function decodeMe(wire: unknown): Me {
  const w = MeWireSchema.parse(wire);
  return {
    userId: w.user_id,
    displayName: w.display_name ?? null,
    locale: w.locale,
    consentedAt: w.consented_at ?? null,
    consentVersion: w.consent_version ?? null,
  };
}

export async function fetchMe(client: HttpClient): Promise<Me> {
  return decodeMe(await client.request("GET", "/me"));
}

export async function postConsent(client: HttpClient, version: string): Promise<Me> {
  return decodeMe(await client.request("POST", "/me/consent", { body: { version } }));
}
