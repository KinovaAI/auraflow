import { apiClient } from "./api-client";

export const onboardingApi = {
  checklist: () => apiClient.get("/onboarding/checklist"),
  complete: (stepKey: string) =>
    apiClient.post(`/onboarding/checklist/${stepKey}/complete`),
  detect: () => apiClient.post("/onboarding/checklist/detect"),
};
