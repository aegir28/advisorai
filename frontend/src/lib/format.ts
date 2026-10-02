const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });

export const formatDate = (iso: string) => dateFmt.format(new Date(iso));
export const formatMonth = (iso: string) => monthFmt.format(new Date(iso));

export function formatSize(kb: number): string {
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB`;
}

export function sexLabel(sex: "F" | "M" | "X"): string {
  return sex === "F" ? "Female" : sex === "M" ? "Male" : "Other";
}
