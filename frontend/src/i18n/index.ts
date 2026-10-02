import { BRAND } from "@/config/brand";
import { en, type MessageKey } from "./en";

export type { MessageKey };
export type Locale = "en";

const catalogues: Record<Locale, Record<string, string>> = { en };
let activeLocale: Locale = "en";

export function setLocale(locale: Locale) {
  activeLocale = locale;
}

/** Translate a key. `{brand}` and any `{vars}` are interpolated. */
export function t(key: MessageKey, vars: Record<string, string | number> = {}): string {
  const template = catalogues[activeLocale][key] ?? en[key] ?? key;
  const all: Record<string, string | number> = { brand: BRAND.name, ...vars };
  return template.replace(/\{(\w+)\}/g, (_, name: string) => String(all[name] ?? `{${name}}`));
}

/** Dynamic-key helper for keys built from data (e.g. `verify.${status}`). */
export function tk(key: string, vars?: Record<string, string | number>): string {
  return t(key as MessageKey, vars);
}
