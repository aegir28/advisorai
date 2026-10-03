const MAX_CONTEXT = 90;

/**
 * Accessible name for a "source" control. It starts with the visible label
 * (so voice-control users can say what they see) and adds the statement it
 * supports, in plain words. It never contains internal item ids; the id stays
 * in the link target (?evidence=<id>), so traceability is unchanged.
 */
export function evidenceAriaLabel(label: string, describes?: string): string {
  const context = describes?.replace(/\s+/g, " ").trim();
  if (!context) return label;
  const short = context.length > MAX_CONTEXT ? `${context.slice(0, MAX_CONTEXT - 1).trimEnd()}…` : context;
  return `${label}: shows where this came from, for “${short}”`;
}
