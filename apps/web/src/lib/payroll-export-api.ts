import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface PayrollProviderStatus {
  connected: boolean;
  company_id?: string;
  realm_id?: string;
  connected_at?: string;
}

export interface PayrollExportStatus {
  gusto: PayrollProviderStatus;
  quickbooks: PayrollProviderStatus;
}

export interface ExternalEmployee {
  id: string;
  first_name: string;
  last_name: string;
  email?: string;
}

export interface EmployeeMapping {
  id: string;
  instructor_id: string;
  instructor_name?: string;
  provider: string;
  external_employee_id: string;
  external_employee_name?: string;
  mapped_at: string;
}

export interface PushResult {
  success: boolean;
  submitted: string[];
  skipped: string[];
}

// ── API ──────────────────────────────────────────────────────────────────────

export const payrollExportApi = {
  // CSV Export
  downloadCsv: (runId: string) =>
    apiClient.get(`/payroll-export/csv/${runId}`, {
      responseType: "blob",
    }),

  // Combined status
  getStatus: () =>
    apiClient.get<{ data: PayrollExportStatus }>("/payroll-export/status"),

  // Gusto
  gustoAuthorize: () =>
    apiClient.get<{ data: { authorize_url: string } }>(
      "/payroll-export/gusto/authorize"
    ),

  gustoDisconnect: () =>
    apiClient.delete("/payroll-export/gusto/disconnect"),

  gustoEmployees: () =>
    apiClient.get<{ data: ExternalEmployee[] }>(
      "/payroll-export/gusto/employees"
    ),

  gustoPush: (runId: string) =>
    apiClient.post<{ data: PushResult }>(
      `/payroll-export/gusto/push/${runId}`
    ),

  // QuickBooks
  qbAuthorize: () =>
    apiClient.get<{ data: { authorize_url: string } }>(
      "/payroll-export/quickbooks/authorize"
    ),

  qbDisconnect: () =>
    apiClient.delete("/payroll-export/quickbooks/disconnect"),

  qbEmployees: () =>
    apiClient.get<{ data: ExternalEmployee[] }>(
      "/payroll-export/quickbooks/employees"
    ),

  qbPush: (runId: string) =>
    apiClient.post<{ data: PushResult }>(
      `/payroll-export/quickbooks/push/${runId}`
    ),

  // Employee Mappings
  listMappings: (provider: string) =>
    apiClient.get<{ data: EmployeeMapping[] }>(
      `/payroll-export/mappings/${provider}`
    ),

  createMapping: (
    provider: string,
    data: {
      instructor_id: string;
      external_employee_id: string;
      external_employee_name?: string;
    }
  ) =>
    apiClient.post<{ data: EmployeeMapping }>(
      `/payroll-export/mappings/${provider}`,
      data
    ),

  deleteMapping: (provider: string, instructorId: string) =>
    apiClient.delete(
      `/payroll-export/mappings/${provider}/${instructorId}`
    ),
};
