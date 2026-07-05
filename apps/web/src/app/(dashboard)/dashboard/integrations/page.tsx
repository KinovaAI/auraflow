import { redirect } from "next/navigation";

export default function IntegrationsRedirect() {
  redirect("/dashboard/settings/integrations");
}
