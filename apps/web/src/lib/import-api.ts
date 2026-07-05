import { apiClient } from "./api-client";

export interface DryRunResult {
  members: { total: number; new: number; existing: number; errors: string[] };
  classes: { total: number; class_types: string[] };
  memberships: { total: number; types: string[] };
  instructors: { total: number; new: number; existing: number };
  schedule: { total: number; series: Array<{ name: string; instructor: string; day: string; time: string; duration: number }> };
}

export interface ImportResult {
  imported?: number;
  created?: number;
  skipped: number;
  errors: Array<{ email?: string; name?: string; error: string }>;
  total: number;
}

export interface MembershipImportResult {
  types_created: number;
  memberships_created: number;
  skipped: number;
  errors: Array<{ email?: string; error: string }>;
  total: number;
}

export interface AttendanceImportResult {
  sessions_created: number;
  errors: Array<{ class?: string; error: string }>;
  total: number;
}

export interface ScheduleImportResult {
  series_created: number;
  sessions_created: number;
  errors: Array<{ class?: string; error: string }>;
  total: number;
}

export interface StripeMatch {
  member_email: string;
  member_name: string;
  member_id: string;
  stripe_customer_id: string;
  stripe_name: string;
  already_has_stripe: boolean;
}

export interface StripeUnmatched {
  stripe_customer_id: string;
  stripe_email: string;
  stripe_name: string;
}

export interface StripeDryRunResult {
  matched: number;
  unmatched_stripe: number;
  already_linked: number;
  total_stripe_customers?: number;
  total_members?: number;
  matches: StripeMatch[];
  unmatched: StripeUnmatched[];
  error?: string;
  // CSV-specific fields
  invalid?: number;
  total_rows?: number;
  errors?: Array<{ email: string; stripe_customer_id: string; error: string }>;
}

export interface StripeImportResult {
  linked: number;
  subscriptions_linked: number;
  already_linked: number;
  unmatched_stripe?: number;
  errors: Array<{ member_id?: string; stripe_customer_id?: string; error: string }>;
  total: number;
}

// ── AI Import Types ─────────────────────────────────────────────────────────

export interface AIAnalysisResult {
  files_analyzed: number;
  total_rows: number;
  column_mappings: Record<string, {
    detected_type: string;
    column_mappings: Record<string, string | null>;
    notes: string;
  }>;
  preview_data: Record<string, {
    headers: string[];
    preview_rows: string[][];
    total_rows: number;
  }>;
  membership_type_mappings: Record<string, string>;
  membership_types_found: string[];
  summary: string;
}

export interface AIPreviewResult {
  members_found: number;
  members_with_existing_account: number;
  members_new: number;
  memberships_found: number;
  membership_type_counts: Record<string, number>;
  membership_type_mappings: Record<string, string>;
  attendance_records: number;
  issues: string[];
  duplicate_emails: string[];
  sample_members: Array<{ name: string; email: string }>;
}

export interface AIImportResult {
  members_created: number;
  members_updated: number;
  user_accounts_created: number;
  memberships_created: number;
  passes_with_credits: number;
  attendance_imported: number;
  errors: Array<{ email?: string; class?: string; error: string }>;
  total_members_processed: number;
}

export interface AIChatResponse {
  response: string;
}

export const importApi = {
  dryRun: (files: { members?: File; classes?: File; memberships?: File; instructors?: File; schedule?: File }) => {
    const form = new FormData();
    if (files.members) form.append("members_file", files.members);
    if (files.classes) form.append("classes_file", files.classes);
    if (files.memberships) form.append("memberships_file", files.memberships);
    if (files.instructors) form.append("instructors_file", files.instructors);
    if (files.schedule) form.append("schedule_file", files.schedule);
    return apiClient.post<{ data: DryRunResult }>("/import/csv/dry-run", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  importMembers: (file: File, studioId: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("studio_id", studioId);
    return apiClient.post<{ data: ImportResult }>("/import/csv/import/members", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  importClassTypes: (file: File, studioId: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("studio_id", studioId);
    return apiClient.post<{ data: ImportResult }>("/import/csv/import/class-types", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  importInstructors: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.post<{ data: ImportResult }>("/import/csv/import/instructors", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  importMemberships: (file: File, studioId: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("studio_id", studioId);
    return apiClient.post<{ data: MembershipImportResult }>("/import/csv/import/memberships", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  importAttendance: (file: File, studioId: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("studio_id", studioId);
    return apiClient.post<{ data: AttendanceImportResult }>("/import/csv/import/attendance", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  importSchedule: (file: File, studioId: string, expandWeeks: number = 4) => {
    const form = new FormData();
    form.append("file", file);
    form.append("studio_id", studioId);
    form.append("expand_weeks", String(expandWeeks));
    return apiClient.post<{ data: ScheduleImportResult }>("/import/csv/import/schedule", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  // Stripe connector import
  stripeDryRunAutoSync: () =>
    apiClient.post<{ data: StripeDryRunResult }>("/import/stripe/dry-run/auto-sync"),

  stripeDryRunCsv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.post<{ data: StripeDryRunResult }>("/import/stripe/dry-run/csv", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  stripeImportAutoSync: (importSubscriptions: boolean = false) =>
    apiClient.post<{ data: StripeImportResult }>("/import/stripe/import/auto-sync", {
      import_subscriptions: importSubscriptions,
    }),

  stripeImportCsv: (file: File, importSubscriptions: boolean = false) => {
    const form = new FormData();
    form.append("file", file);
    form.append("import_subscriptions", String(importSubscriptions));
    return apiClient.post<{ data: StripeImportResult }>("/import/stripe/import/csv", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  // ── AI Import ─────────────────────────────────────────────────────────────

  aiUpload: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return apiClient.post<{ data: AIAnalysisResult }>("/import/ai/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120000,
    });
  },

  aiPreview: (
    files: File[],
    columnMappings: Record<string, unknown>,
    membershipTypeMappings: Record<string, string>,
  ) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    form.append("column_mappings", JSON.stringify(columnMappings));
    form.append("membership_type_mappings", JSON.stringify(membershipTypeMappings));
    return apiClient.post<{ data: AIPreviewResult }>("/import/ai/preview", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120000,
    });
  },

  aiExecute: (
    files: File[],
    columnMappings: Record<string, unknown>,
    membershipTypeMappings: Record<string, string>,
    studioId: string,
  ) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    form.append("column_mappings", JSON.stringify(columnMappings));
    form.append("membership_type_mappings", JSON.stringify(membershipTypeMappings));
    form.append("studio_id", studioId);
    return apiClient.post<{ data: AIImportResult }>("/import/ai/execute", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 300000,
    });
  },

  aiChat: (message: string) =>
    apiClient.post<{ data: AIChatResponse }>("/import/ai/chat", { message }),

  aiStatus: () =>
    apiClient.get<{ data: { status: string; result: AIImportResult | null } }>("/import/ai/status"),
};
