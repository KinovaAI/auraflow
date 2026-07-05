"use client";

import { useState, type ReactNode } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  Loader2, ArrowLeft, Star, FileText, Download, CheckCircle2, Clock, UserPlus,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { hiringApi, type ApplicationStatus } from "@/lib/hiring-api";
import { usePermission } from "@/hooks/use-permission";
import { HireModal } from "@/components/hiring/hire-modal";

const STATUSES: ApplicationStatus[] = [
  "new", "reviewed", "shortlisted", "interviewed", "offer", "hired", "rejected",
];

function Field({ label, value }: { label: string; value?: ReactNode }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-gray-400">{label}</div>
      <div className="text-sm text-gray-800">{value}</div>
    </div>
  );
}

export default function ApplicationDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const router = useRouter();
  const queryClient = useQueryClient();
  const canManage = usePermission("hiring.manage");
  const canHire = usePermission("hiring.hire");
  const canViewW4 = usePermission("hiring.view_w4");

  const [note, setNote] = useState("");
  const [showHire, setShowHire] = useState(false);

  const { data: app, isLoading } = useQuery({
    queryKey: ["hiring-application", id],
    queryFn: () => hiringApi.get(id),
  });

  const updateMutation = useMutation({
    mutationFn: (data: { status?: string; rating?: number }) => hiringApi.update(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["hiring-application", id] }),
    onError: () => toast.error("Failed to update application"),
  });

  const noteMutation = useMutation({
    mutationFn: () => hiringApi.addNote(id, note),
    onSuccess: () => {
      setNote("");
      queryClient.invalidateQueries({ queryKey: ["hiring-application", id] });
    },
    onError: () => toast.error("Failed to add note"),
  });

  const { data: packet } = useQuery({
    queryKey: ["employee-onboarding", app?.hired_user_id],
    queryFn: () => hiringApi.getEmployeeOnboarding(app!.hired_user_id!),
    enabled: !!app?.hired_user_id,
    retry: false,
  });

  const { data: de34Pending } = useQuery({
    queryKey: ["de34-pending"],
    queryFn: () => hiringApi.getDe34Pending(),
    enabled: !!app?.hired_user_id && canViewW4,
    retry: false,
  });

  const de34Filed = !!app?.hired_user_id && de34Pending !== undefined &&
    !de34Pending.some((p) => p.user_id === app.hired_user_id);
  const de34Row = de34Pending?.find((p) => p.user_id === app?.hired_user_id);

  const markFiledMutation = useMutation({
    mutationFn: () => hiringApi.markDe34Filed(app!.hired_user_id!),
    onSuccess: () => {
      toast.success("DE-34 marked as filed");
      queryClient.invalidateQueries({ queryKey: ["de34-pending"] });
    },
    onError: () => toast.error("Failed to update"),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }
  if (!app) {
    return <div className="py-16 text-center text-gray-500">Application not found.</div>;
  }

  const fullName = `${app.first_name} ${app.last_name}`;

  return (
    <div className="space-y-4">
      {showHire && canHire && (
        <HireModal
          application={app}
          onClose={() => setShowHire(false)}
          onHired={() => {
            setShowHire(false);
            queryClient.invalidateQueries({ queryKey: ["hiring-application", id] });
          }}
        />
      )}

      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push("/dashboard/hiring")} className="rounded-md p-1 text-gray-500 hover:bg-gray-100">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">{fullName}</h1>
            <p className="text-sm text-gray-500">
              {app.position_title || app.position_type.replace("_", " ")} · {app.email}
            </p>
          </div>
        </div>
        {app.status !== "hired" && canHire && (
          <Button onClick={() => setShowHire(true)}>
            <UserPlus className="mr-2 h-4 w-4" /> Hire
          </Button>
        )}
      </div>

      {/* Pipeline controls */}
      <Card>
        <CardContent className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-wide text-gray-400">Stage</span>
            {STATUSES.map((s) => (
              <button
                key={s}
                disabled={!canManage || updateMutation.isPending}
                onClick={() => updateMutation.mutate({ status: s })}
                className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                  app.status === s
                    ? "bg-indigo-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 disabled:opacity-50"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <span className="mr-1 text-xs uppercase tracking-wide text-gray-400">Rating</span>
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                disabled={!canManage}
                onClick={() => updateMutation.mutate({ rating: n })}
                className="disabled:opacity-50"
                aria-label={`Rate ${n}`}
              >
                <Star className={`h-5 w-5 ${app.rating && n <= app.rating ? "fill-amber-400 text-amber-400" : "text-gray-300"}`} />
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Left: applicant details */}
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader><CardTitle className="text-base">Applicant</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-4">
              <Field label="Phone" value={app.phone} />
              <Field label="Email" value={app.email} />
              <Field label="Address" value={[app.address_line1, app.address_line2, [app.city, app.state, app.postal_code].filter(Boolean).join(" ")].filter(Boolean).join(", ")} />
              <Field label="Authorized to work" value={app.authorized_to_work ? "Yes" : "No"} />
              <Field label="Over 18" value={app.over_18 ? "Yes" : "No"} />
              <Field label="Employment type" value={app.employment_type?.replace("_", " ")} />
              <Field label="Availability" value={app.availability} />
              <Field label="Earliest start" value={app.earliest_start_date} />
              <Field label="Desired pay" value={app.desired_pay_text} />
              <Field label="Heard about us" value={app.hear_about_us} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Experience</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <Field label="Years experience" value={app.years_experience?.toString()} />
              <Field label="Specialties" value={app.specialties?.length ? app.specialties.join(", ") : undefined} />
              <Field label="Experience with seniors" value={app.experience_seniors} />
              <Field label="Experience with injuries" value={app.experience_injuries} />
              <Field label="Experience with pain" value={app.experience_pain} />
              {app.work_history?.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide text-gray-400">Work history</div>
                  <ul className="mt-1 space-y-1 text-sm text-gray-800">
                    {app.work_history.map((w, i) => (
                      <li key={i}>{[w.title, w.employer, w.dates].filter(Boolean).join(" · ")}</li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Credentials</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <Field label="Yoga Alliance" value={[app.yoga_alliance_level, app.yoga_alliance_number].filter(Boolean).join(" · ")} />
              <Field label="CPR / First Aid" value={app.cpr_first_aid ? "Yes" : "No"} />
              <Field label="Liability insurance" value={app.liability_insurance ? "Yes" : "No"} />
              {app.certifications?.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide text-gray-400">Certifications</div>
                  <ul className="mt-1 space-y-1 text-sm text-gray-800">
                    {app.certifications.map((c, i) => (
                      <li key={i}>{[c.name, c.issuer, c.issued_on].filter(Boolean).join(" · ")}</li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>

          {app.cover_letter && (
            <Card>
              <CardHeader><CardTitle className="text-base">Cover Letter</CardTitle></CardHeader>
              <CardContent><p className="whitespace-pre-wrap text-sm text-gray-800">{app.cover_letter}</p></CardContent>
            </Card>
          )}

          {app.references?.length > 0 && (
            <Card>
              <CardHeader><CardTitle className="text-base">References</CardTitle></CardHeader>
              <CardContent className="space-y-1 text-sm text-gray-800">
                {app.references.map((r, i) => (
                  <div key={i}>{[r.name, r.relationship, r.phone, r.email].filter(Boolean).join(" · ")}</div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right: documents, W-4, notes, timeline */}
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Documents</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {app.documents.length === 0 ? (
                <p className="text-sm text-gray-400">No documents uploaded.</p>
              ) : app.documents.map((d) => (
                <button
                  key={d.id}
                  onClick={() => hiringApi.openDocument(app.id, d.id).catch(() => toast.error("Could not open document"))}
                  className="flex w-full items-center gap-2 rounded-md border border-gray-200 px-3 py-2 text-left text-sm hover:bg-gray-50"
                >
                  <FileText className="h-4 w-4 text-gray-400" />
                  <span className="flex-1 truncate">{d.filename}</span>
                  <span className="text-xs uppercase text-gray-400">{d.doc_type}</span>
                  <Download className="h-4 w-4 text-gray-400" />
                </button>
              ))}
            </CardContent>
          </Card>

          {app.hired_user_id && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Onboarding{packet ? ` · ${packet.status === "completed" ? "Complete" : "In progress"}` : ""}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {!packet ? (
                  <p className="text-sm text-gray-400">No onboarding packet on file.</p>
                ) : (
                  packet.documents.map((d) => (
                    <div key={d.id} className="flex items-center gap-2 text-sm">
                      {d.status === "completed" ? (
                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                      ) : (
                        <Clock className="h-4 w-4 text-amber-500" />
                      )}
                      <span className="flex-1 text-gray-700">{d.title}</span>
                      {d.status === "completed" && d.has_pdf && canViewW4 && (
                        <button
                          onClick={() => hiringApi.openOnboardingDocPdf(app.hired_user_id!, d.id).catch(() => toast.error("Could not open PDF"))}
                          className="text-gray-400 hover:text-indigo-600"
                          title="View signed PDF"
                        >
                          <Download className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  ))
                )}
                {packet && !canViewW4 && (
                  <p className="pt-1 text-xs text-gray-400">Signed PDFs (incl. SSN) require the W-4 viewer permission.</p>
                )}
              </CardContent>
            </Card>
          )}

          {app.hired_user_id && canViewW4 && (
            <Card>
              <CardHeader><CardTitle className="text-base">DE-34 New-Hire Report</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {de34Filed ? (
                  <div className="flex items-center gap-2 text-sm text-green-700">
                    <CheckCircle2 className="h-4 w-4" /> Filed with the EDD
                  </div>
                ) : (
                  <div className={`flex items-center gap-2 text-sm ${de34Row?.overdue ? "text-red-600" : "text-amber-600"}`}>
                    <Clock className="h-4 w-4" />
                    {de34Row?.due_date
                      ? `Due ${new Date(de34Row.due_date).toLocaleDateString()}${de34Row.overdue ? " — overdue" : de34Row.days_remaining != null ? ` (${de34Row.days_remaining}d)` : ""}`
                      : "Not yet filed"}
                  </div>
                )}
                <div className="flex flex-wrap gap-2 pt-1">
                  <Button variant="outline" size="sm" onClick={() => hiringApi.openDe34Pdf(app.hired_user_id!).catch(() => toast.error("Set your EDD account # in Employer Profile first"))}>
                    <Download className="mr-2 h-4 w-4" /> Generate PDF
                  </Button>
                  {!de34Filed && (
                    <Button size="sm" disabled={markFiledMutation.isPending} onClick={() => markFiledMutation.mutate()}>
                      Mark as filed
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {canManage && (
            <Card>
              <CardHeader><CardTitle className="text-base">Add Note</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={3}
                  placeholder="Interview notes, impressions…"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <Button size="sm" disabled={!note.trim() || noteMutation.isPending} onClick={() => noteMutation.mutate()}>
                  {noteMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Add note
                </Button>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader><CardTitle className="text-base">Activity</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {app.events.slice().reverse().map((e) => (
                <div key={e.id} className="border-l-2 border-gray-200 pl-3">
                  <div className="text-sm text-gray-800">
                    {e.event_type === "status_changed" && <>Moved to <span className="font-medium capitalize">{e.to_status}</span></>}
                    {e.event_type === "created" && "Application submitted"}
                    {e.event_type === "rated" && `Rated ${e.note?.replace("rating=", "")}★`}
                    {e.event_type === "note" && e.note}
                    {e.event_type === "document_uploaded" && `Uploaded ${e.note}`}
                    {e.event_type === "hired" && (e.note || "Hired")}
                  </div>
                  <div className="text-xs text-gray-400">{new Date(e.created_at).toLocaleString()}</div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
