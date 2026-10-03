import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { assertPublicKey, jwtRole } from "@/features/auth/supabase";

const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
const jwt = (role: string) => `${b64({ alg: "HS256" })}.${b64({ role })}.sig`;

describe("the frontend only ever holds public keys", () => {
  it("reads the role claim without verifying", () => {
    expect(jwtRole(jwt("anon"))).toBe("anon");
    expect(jwtRole(jwt("service_role"))).toBe("service_role");
    expect(jwtRole("not-a-jwt")).toBeNull();
    expect(jwtRole("a.%%%.c")).toBeNull();
  });

  it("refuses a service-role or secret key and accepts an anon key", () => {
    expect(() => assertPublicKey(jwt("service_role"))).toThrow(/service-role/);
    expect(() => assertPublicKey("sb_secret_abc123")).toThrow();
    expect(() => assertPublicKey(jwt("anon"))).not.toThrow();
    expect(() => assertPublicKey("sb_publishable_abc123")).not.toThrow();
  });

  it("has no secret-looking environment variable in the source tree", () => {
    const root = fileURLToPath(new URL("../..", import.meta.url));
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.(ts|tsx|mts)$/.test(name) && !p.includes("__tests__")) files.push(p);
      }
    };
    walk(root);
    const secretNames = /NEXT_PUBLIC_[A-Z0-9_]*(SECRET|SERVICE|PRIVATE|OPENAI|GEMINI|API_KEY)|process\.env\.(SUPABASE_SERVICE|OPENAI|GEMINI|GOOGLE_CLIENT_SECRET|[A-Z_]*SECRET)/;
    for (const f of files) expect(readFileSync(f, "utf8"), f).not.toMatch(secretNames);
  });

  it("only reads the public NEXT_PUBLIC variables it documents", () => {
    const root = fileURLToPath(new URL("../..", import.meta.url));
    const used = new Set<string>();
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.(ts|tsx)$/.test(name) && !p.includes("__tests__"))
          for (const m of readFileSync(p, "utf8").matchAll(/process\.env\.(NEXT_PUBLIC_[A-Z0-9_]+)/g)) used.add(m[1]);
      }
    };
    walk(root);
    expect([...used].sort()).toEqual([
      "NEXT_PUBLIC_API_BASE_URL", "NEXT_PUBLIC_API_MODE", "NEXT_PUBLIC_AUTH_MODE", "NEXT_PUBLIC_SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_URL",
    ]);
  });
});
