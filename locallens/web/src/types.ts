export type Tag = "metric" | "dimension" | "date" | "ignore";

export interface User { id: number; username: string; role: "admin" | "user"; must_change_password: boolean; active: boolean; last_login: string | null; created_at: string }

export interface DatasetSummary { id: string; name: string; visibility: "private" | "shared"; owner: string; can_edit: boolean; updated_at: string; created_at: string }

export interface Column { table: string; name: string; flat_name: string; tag: Tag; description: string; expression: string; error: string; synonyms: string[]; samples: string[]; values: string[] }
export interface Join { left: string; left_key: string; right: string; right_key: string }
export interface Measure { name: string; expression: string; label: string; description: string; synonyms: string[]; format: "number" | "currency" | "percent"; additive: boolean; error: string }
export interface Rule { name: string; condition: string; phrases: string[]; description: string; enabled: boolean; error: string }
export interface Example { question: string; frame: Record<string, unknown> }
export interface Registry {
  name: string; description: string; main_table: string; tables: Record<string, string>;
  columns: Column[]; joins: Join[]; fiscal_start_month: number; measures: Measure[]; rules: Rule[]; examples: Example[];
}
export interface DatasetDetail extends DatasetSummary {
  registry: Registry; problems: string[];
  stats: { tables?: Record<string, number>; date_ranges?: Record<string, [string, string]>; error?: string };
}

export interface ColumnInfo { name: string; kind: "temporal" | "numeric" | "categorical" }
export type Cell = string | number | boolean | null;
export interface TablePayload { columns: ColumnInfo[]; rows: Cell[][]; row_count: number; truncated: boolean }

export interface Frame {
  intent: string; metric: { column: string; agg: string }; dimension: string | null;
  time: { column: string; grain: string | null; start: string | null; end: string | null } | null;
  filters: { column: string; op: string; value: string }[]; top_n: number | null; order: string; rules: string[];
}
export interface Clarification { message: string; field: string; options: string[]; question: string }
export interface Answer extends TablePayload {
  question: string; error: string; corrections: [string, string][]; semantic?: [string, string][]; timings_ms: Record<string, number>;
  clarification: Clarification | null; frame: Frame | null; sql: string; followup?: boolean;
  rules: { name: string; description: string; always: boolean }[];
  chart: { type: string; reason: string; fallback: boolean; spec: Record<string, unknown> } | null;
  kpi: { value: number | null; label: string } | null;
  metric: { name: string; label: string; format: "number" | "currency" | "percent"; agg: string | null; description: string } | null;
  exports: string[];
}
export interface Message { id: string; rating: number | null; created_at: string; response: Answer }
export interface ConversationSummary { id: string; title: string; updated_at: string }
export interface Conversation { id: string; title: string; dataset_id: string; messages: Message[] }
export interface Prefs { sort: "asc" | "desc"; chart_overrides: Record<string, string>; choices: Record<string, string[]> }
export interface Feedback { id: string; user: string; dataset_id: string; question: string; rating: number; note: string; created_at: string; frame: Frame | null; sql: string | null; error: string | null }
export interface CheckResult { ok: boolean; error?: string; preview?: { value?: number | null; values?: string[]; matching?: number; of?: number } }
