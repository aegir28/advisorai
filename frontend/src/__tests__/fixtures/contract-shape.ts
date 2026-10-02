import type { z } from "zod";
import {
  AnalysisRunSchema,
  CaseV1Schema,
  PatientReportSchema,
  SCHEMA_VERSIONS,
  SpecialistReportSchema,
  TraceSchema,
} from "@/domain/schemas";
import { DOMAIN_TO_WIRE } from "@/lib/api/http/casing";

/**
 * The SHAPE of each versioned contract, read from the Zod schemas themselves: every object field
 * path (in wire / snake_case spelling) and which of them are optional. The backend test compares
 * this with its Pydantic models, so field names, nesting and optionality cannot drift apart.
 *
 * Path syntax: `findings[].fact_refs` = field `fact_refs` of each item of array `findings`.
 * Free-form records (`extensions`, `meta`) are opaque leaves. Recursion (trace children) stops at
 * the first repeat of an object schema.
 */
export interface ContractShape {
  fields: string[];
  optional: string[];
}

type Def = { type: string; shape?: Record<string, z.ZodType>; element?: z.ZodType; innerType?: z.ZodType };
const defOf = (schema: z.ZodType): Def => (schema as unknown as { _zod: { def: Def } })._zod.def;

function shapeOf(root: z.ZodType): ContractShape {
  const fields = new Set<string>();
  const optional = new Set<string>();

  const walk = (schema: z.ZodType, path: string, stack: z.ZodType[]): void => {
    const def = defOf(schema);
    if (def.type === "optional" && def.innerType) {
      optional.add(path);
      walk(def.innerType, path, stack);
    } else if (def.type === "array" && def.element) {
      walk(def.element, `${path}[]`, stack);
    } else if (def.type === "object" && def.shape) {
      if (stack.includes(schema)) return;
      for (const [key, child] of Object.entries(def.shape)) {
        const childPath = `${path ? `${path}.` : ""}${DOMAIN_TO_WIRE[key] ?? key}`;
        fields.add(childPath);
        walk(child, childPath, [...stack, schema]);
      }
    }
    // Everything else (string, number, enum, literal, union of literals, record) is a leaf.
  };

  walk(root, "", []);
  return { fields: [...fields].sort(), optional: [...optional].sort() };
}

export const CONTRACT_SHAPES: Record<string, ContractShape> = {
  [SCHEMA_VERSIONS.case]: shapeOf(CaseV1Schema),
  [SCHEMA_VERSIONS.specialistReport]: shapeOf(SpecialistReportSchema),
  [SCHEMA_VERSIONS.report]: shapeOf(PatientReportSchema),
  [SCHEMA_VERSIONS.trace]: shapeOf(TraceSchema),
  [SCHEMA_VERSIONS.run]: shapeOf(AnalysisRunSchema),
};
