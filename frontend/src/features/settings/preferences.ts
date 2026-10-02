/** Small, local-only reading preferences (accessibility). */
const KEY = "advisorai.prefs.v1";

export type TextSize = "normal" | "large" | "xlarge";
const SIZE_PX: Record<TextSize, string> = { normal: "16px", large: "18px", xlarge: "20px" };

export function readTextSize(): TextSize {
  try {
    const v = JSON.parse(window.localStorage.getItem(KEY) ?? "{}")?.textSize;
    return v === "large" || v === "xlarge" ? v : "normal";
  } catch {
    return "normal";
  }
}

export function applyTextSize(size: TextSize) {
  document.documentElement.style.fontSize = SIZE_PX[size];
}

export function saveTextSize(size: TextSize) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ textSize: size }));
  } catch {
    /* ignore: preference only lasts for this page */
  }
  applyTextSize(size);
}
