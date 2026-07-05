import { redirect } from "next/navigation";

export default function CommunicationsRedirect() {
  redirect("/dashboard/settings/integrations");
}
