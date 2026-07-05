import { apiClient } from "./api-client";

export interface PortalSetupStatus {
  tenant_slug: string;
  tenant_name: string;
  current_brand: {
    name: string;
    logo_url: string | null;
    primary_color: string;
    on_primary_color: string;
    surface_color: string;
    on_surface_color: string;
  };
  checklist: {
    brand: { done: boolean; has_logo: boolean; has_color: boolean };
    api_key: { done: boolean; active_count: number };
    origins: { done: boolean; origins: string[] };
    stripe_connect: {
      done: boolean;
      account_id: string | null;
      charges_enabled: boolean;
    };
  };
  next_step: "brand" | "api_key" | "origins" | "stripe" | "deploy";
  next_step_label: string;
  ready_to_deploy: boolean;
}

export interface DeployConfig {
  env_block: string;
  vercel_deploy_url: string;
  github_repo: string;
  docker_compose_snippet: string;
}

export interface BrandUpdate {
  name?: string;
  primary_color?: string;
  on_primary_color?: string;
  surface_color?: string;
  on_surface_color?: string;
  logo_url?: string;
}

export const portalSetupApi = {
  status: () => apiClient.get<PortalSetupStatus>("/admin/portal-setup/status"),
  updateBrand: (data: BrandUpdate) =>
    apiClient.put<{ brand: Record<string, unknown> }>(
      "/admin/portal-setup/brand", data,
    ),
  mintApiKey: () =>
    apiClient.post<{ raw_key: string; key_prefix: string; warning: string }>(
      "/admin/portal-setup/api-key",
    ),
  addOrigin: (origin: string) =>
    apiClient.post<{ allowed_portal_origins: string[] }>(
      "/admin/portal-setup/origins",
      { origin },
    ),
  removeOrigin: (origin: string) =>
    apiClient.delete<{ allowed_portal_origins: string[] }>(
      "/admin/portal-setup/origins",
      { data: { origin } },
    ),
  deployConfig: () =>
    apiClient.get<DeployConfig>("/admin/portal-setup/deploy-config"),
};
