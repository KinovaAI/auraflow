"use client";

import { useState, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  CreditCard,
  Link2,
  Zap,
  Sparkles,
  Send,
  ArrowRight,
  MessageCircle,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  importApi,
  type DryRunResult,
  type ImportResult,
  type MembershipImportResult,
  type AttendanceImportResult,
  type ScheduleImportResult,
  type StripeDryRunResult,
  type StripeImportResult,
  type AIAnalysisResult,
  type AIPreviewResult,
  type AIImportResult,
} from "@/lib/import-api";
import { studiosApi } from "@/lib/scheduling-api";

type Step = "upload" | "preview" | "importing" | "done";

interface ImportResults {
  instructors?: ImportResult;
  members?: ImportResult;
  classTypes?: ImportResult;
  memberships?: MembershipImportResult;
  attendance?: AttendanceImportResult;
  schedule?: ScheduleImportResult;
}

type ImportTab = "ai" | "csv" | "stripe";
type AIStep = "upload" | "review" | "importing" | "done";
type StripeMode = "auto" | "csv";
type StripeStep = "choose" | "preview" | "importing" | "done";

export default function ImportPage() {
  const [activeTab, setActiveTab] = useState<ImportTab>("ai");

  // CSV import state
  const [step, setStep] = useState<Step>("upload");
  const [membersFile, setMembersFile] = useState<File | null>(null);
  const [classesFile, setClassesFile] = useState<File | null>(null);
  const [instructorsFile, setInstructorsFile] = useState<File | null>(null);
  const [membershipsFile, setMembershipsFile] = useState<File | null>(null);
  const [attendanceFile, setAttendanceFile] = useState<File | null>(null);
  const [scheduleFile, setScheduleFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<DryRunResult | null>(null);
  const [results, setResults] = useState<ImportResults>({});
  const [importProgress, setImportProgress] = useState("");
  const [studioId, setStudioId] = useState("");
  const membersRef = useRef<HTMLInputElement>(null);
  const classesRef = useRef<HTMLInputElement>(null);
  const instructorsRef = useRef<HTMLInputElement>(null);
  const membershipsRef = useRef<HTMLInputElement>(null);
  const attendanceRef = useRef<HTMLInputElement>(null);
  const scheduleRef = useRef<HTMLInputElement>(null);

  // Stripe import state
  const [stripeStep, setStripeStep] = useState<StripeStep>("choose");
  const [stripeMode, setStripeMode] = useState<StripeMode>("auto");
  const [stripeCsvFile, setStripeCsvFile] = useState<File | null>(null);
  const [stripePreview, setStripePreview] = useState<StripeDryRunResult | null>(null);
  const [stripeResults, setStripeResults] = useState<StripeImportResult | null>(null);
  const [importSubscriptions, setImportSubscriptions] = useState(true);
  const stripeCsvRef = useRef<HTMLInputElement>(null);

  // AI import state
  const [aiStep, setAiStep] = useState<AIStep>("upload");
  const [aiFiles, setAiFiles] = useState<File[]>([]);
  const [aiAnalysis, setAiAnalysis] = useState<AIAnalysisResult | null>(null);
  const [aiPreview, setAiPreview] = useState<AIPreviewResult | null>(null);
  const [aiResults, setAiResults] = useState<AIImportResult | null>(null);
  const [aiTypeMappings, setAiTypeMappings] = useState<Record<string, string>>({});
  const [aiChatMessages, setAiChatMessages] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);
  const [aiChatInput, setAiChatInput] = useState("");
  const [aiChatLoading, setAiChatLoading] = useState(false);
  const aiFileRef = useRef<HTMLInputElement>(null);
  const aiDropRef = useRef<HTMLDivElement>(null);

  const { data: studios } = useQuery({
    queryKey: ["studios"],
    queryFn: () => studiosApi.list().then((r) => r.data),
  });

  // Auto-select first studio
  if (studios?.length && !studioId) {
    setStudioId(studios[0].id);
  }

  const hasAnyFile = !!(membersFile || classesFile || instructorsFile || membershipsFile || attendanceFile || scheduleFile);

  const dryRunMutation = useMutation({
    mutationFn: () =>
      importApi.dryRun({
        members: membersFile || undefined,
        classes: classesFile || undefined,
        instructors: instructorsFile || undefined,
        memberships: membershipsFile || undefined,
        schedule: scheduleFile || undefined,
      }),
    onSuccess: (resp) => {
      setPreview(resp.data.data);
      setStep("preview");
    },
    onError: () => toast.error("Failed to preview import"),
  });

  const importMutation = useMutation({
    mutationFn: async () => {
      const res: ImportResults = {};

      // Import in dependency order: Instructors → Members → Class Types → Memberships → Attendance
      if (instructorsFile) {
        setImportProgress("Importing instructors...");
        const r = await importApi.importInstructors(instructorsFile);
        res.instructors = r.data.data;
      }
      if (membersFile) {
        setImportProgress("Importing members...");
        const r = await importApi.importMembers(membersFile, studioId);
        res.members = r.data.data;
      }
      if (classesFile) {
        setImportProgress("Importing class types...");
        const r = await importApi.importClassTypes(classesFile, studioId);
        res.classTypes = r.data.data;
      }
      if (scheduleFile) {
        setImportProgress("Creating recurring schedule...");
        const r = await importApi.importSchedule(scheduleFile, studioId);
        res.schedule = r.data.data;
      }
      if (membershipsFile) {
        setImportProgress("Importing memberships...");
        const r = await importApi.importMemberships(membershipsFile, studioId);
        res.memberships = r.data.data;
      }
      if (attendanceFile) {
        setImportProgress("Importing attendance history...");
        const r = await importApi.importAttendance(attendanceFile, studioId);
        res.attendance = r.data.data;
      }
      return res;
    },
    onSuccess: (res) => {
      setResults(res);
      setStep("done");
      setImportProgress("");
      toast.success("Import complete!");
    },
    onError: () => {
      setImportProgress("");
      toast.error("Import failed");
    },
  });

  const reset = () => {
    setStep("upload");
    setMembersFile(null);
    setClassesFile(null);
    setInstructorsFile(null);
    setMembershipsFile(null);
    setAttendanceFile(null);
    setScheduleFile(null);
    setPreview(null);
    setResults({});
    setImportProgress("");
  };

  // Stripe mutations
  const stripeDryRunMutation = useMutation({
    mutationFn: async () => {
      if (stripeMode === "auto") {
        return importApi.stripeDryRunAutoSync();
      } else {
        if (!stripeCsvFile) throw new Error("No CSV file");
        return importApi.stripeDryRunCsv(stripeCsvFile);
      }
    },
    onSuccess: (resp) => {
      const data = resp.data.data;
      if (data.error) {
        toast.error(data.error);
        return;
      }
      setStripePreview(data);
      setStripeStep("preview");
    },
    onError: () => toast.error("Failed to preview Stripe sync"),
  });

  const stripeImportMutation = useMutation({
    mutationFn: async () => {
      if (stripeMode === "auto") {
        return importApi.stripeImportAutoSync(importSubscriptions);
      } else {
        if (!stripeCsvFile) throw new Error("No CSV file");
        return importApi.stripeImportCsv(stripeCsvFile, importSubscriptions);
      }
    },
    onSuccess: (resp) => {
      setStripeResults(resp.data.data);
      setStripeStep("done");
      toast.success("Stripe connector import complete!");
    },
    onError: () => toast.error("Stripe import failed"),
  });

  const resetStripe = () => {
    setStripeStep("choose");
    setStripeCsvFile(null);
    setStripePreview(null);
    setStripeResults(null);
  };

  // AI Import mutations
  const aiUploadMutation = useMutation({
    mutationFn: () => importApi.aiUpload(aiFiles),
    onSuccess: (resp) => {
      const data = resp.data.data;
      setAiAnalysis(data);
      setAiTypeMappings(data.membership_type_mappings || {});
      setAiStep("review");
      toast.success(`Analyzed ${data.files_analyzed} file(s) - ${data.total_rows} rows found`);
    },
    onError: () => toast.error("Failed to analyze files. Please try again."),
  });

  const aiPreviewMutation = useMutation({
    mutationFn: () => {
      if (!aiAnalysis) throw new Error("No analysis");
      return importApi.aiPreview(aiFiles, aiAnalysis.column_mappings, aiTypeMappings);
    },
    onSuccess: (resp) => {
      setAiPreview(resp.data.data);
    },
    onError: () => toast.error("Failed to generate preview"),
  });

  const aiExecuteMutation = useMutation({
    mutationFn: () => {
      if (!aiAnalysis) throw new Error("No analysis");
      return importApi.aiExecute(aiFiles, aiAnalysis.column_mappings, aiTypeMappings, studioId);
    },
    onSuccess: (resp) => {
      setAiResults(resp.data.data);
      setAiStep("done");
      toast.success("AI import complete!");
    },
    onError: () => {
      toast.error("Import failed");
      setAiStep("review");
    },
  });

  const handleAiChat = async () => {
    if (!aiChatInput.trim()) return;
    const msg = aiChatInput.trim();
    setAiChatInput("");
    setAiChatMessages((prev) => [...prev, { role: "user", text: msg }]);
    setAiChatLoading(true);
    try {
      const resp = await importApi.aiChat(msg);
      setAiChatMessages((prev) => [
        ...prev,
        { role: "assistant", text: resp.data.data.response },
      ]);
    } catch {
      setAiChatMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry, I encountered an error. Please try again." },
      ]);
    } finally {
      setAiChatLoading(false);
    }
  };

  const resetAi = () => {
    setAiStep("upload");
    setAiFiles([]);
    setAiAnalysis(null);
    setAiPreview(null);
    setAiResults(null);
    setAiTypeMappings({});
    setAiChatMessages([]);
    setAiChatInput("");
  };

  const handleAiDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const dropped = Array.from(e.dataTransfer.files).filter((f) =>
      f.name.toLowerCase().endsWith(".csv")
    );
    if (dropped.length > 0) {
      setAiFiles((prev) => [...prev, ...dropped]);
    } else {
      toast.error("Please drop CSV files only");
    }
  };

  function FileUploadCard({
    title,
    file,
    setFile,
    inputRef,
    label,
  }: {
    title: string;
    file: File | null;
    setFile: (f: File | null) => void;
    inputRef: React.RefObject<HTMLInputElement>;
    label: string;
  }) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          {file ? (
            <div className="flex items-center justify-between rounded-md bg-green-50 p-3">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-green-600" />
                <span className="text-sm text-green-700">{file.name}</span>
              </div>
              <button
                onClick={() => setFile(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={() => inputRef.current?.click()}
              className="flex w-full items-center justify-center gap-2 rounded-md border-2 border-dashed border-gray-300 py-8 text-gray-500 hover:border-indigo-300 hover:text-indigo-500"
            >
              <Upload className="h-5 w-5" />
              <span className="text-sm">{label}</span>
            </button>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Import Data</h1>
        <p className="text-sm text-gray-500">
          Import data from MomoYoga, Stripe, or any platform
        </p>
      </div>

      {/* Tab Switcher */}
      <div className="flex rounded-lg border bg-gray-50 p-1">
        <button
          onClick={() => setActiveTab("ai")}
          className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "ai"
              ? "bg-white text-gray-900 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          <Sparkles className="mr-2 inline-block h-4 w-4" />
          AI Import
        </button>
        <button
          onClick={() => setActiveTab("csv")}
          className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "csv"
              ? "bg-white text-gray-900 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          <Upload className="mr-2 inline-block h-4 w-4" />
          Manual CSV
        </button>
        <button
          onClick={() => setActiveTab("stripe")}
          className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "stripe"
              ? "bg-white text-gray-900 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          <CreditCard className="mr-2 inline-block h-4 w-4" />
          Stripe
        </button>
      </div>

      {/* ── AI Import Tab ────────────────────────────────────────────────── */}
      {activeTab === "ai" && (
        <div className="space-y-4">
          {/* Step indicator */}
          <div className="flex items-center gap-2">
            {(["upload", "review", "importing", "done"] as const)
              .filter((s) => s !== "importing")
              .map((s, idx) => (
                <div key={s} className="flex items-center gap-2">
                  <div
                    className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium ${
                      aiStep === s || (aiStep === "importing" && s === "review")
                        ? "bg-indigo-600 text-white"
                        : aiStep === "done" || (idx === 0 && aiStep !== "upload")
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-400"
                    }`}
                  >
                    {idx + 1}
                  </div>
                  <span className="text-sm text-gray-500 capitalize">
                    {s === "review" ? "Review" : s}
                  </span>
                  {idx < 2 && <div className="mx-2 h-px w-8 bg-gray-200" />}
                </div>
              ))}
          </div>

          {/* ── Step 1: Upload ──────────────────────────────────────────────── */}
          {aiStep === "upload" && (
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Sparkles className="h-5 w-5 text-indigo-600" />
                    AI-Powered CSV Import
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-gray-600">
                    Upload CSV files from any studio management platform (MomoYoga, Mindbody,
                    WellnessLiving, Glofox, etc.). AI will automatically identify columns
                    and map them to AuraFlow fields.
                  </p>

                  {/* Drag & Drop Zone */}
                  <div
                    ref={aiDropRef}
                    onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                    onDrop={handleAiDrop}
                    onClick={() => aiFileRef.current?.click()}
                    className="flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 py-10 transition-colors hover:border-indigo-400 hover:bg-indigo-50/50"
                  >
                    <Upload className="h-8 w-8 text-gray-400" />
                    <div className="text-center">
                      <p className="text-sm font-medium text-gray-700">
                        Drag & drop CSV files here
                      </p>
                      <p className="text-xs text-gray-400">or click to browse</p>
                    </div>
                  </div>
                  <input
                    ref={aiFileRef}
                    type="file"
                    accept=".csv"
                    multiple
                    className="hidden"
                    onChange={(e) => {
                      const selected = Array.from(e.target.files || []);
                      if (selected.length > 0) setAiFiles((prev) => [...prev, ...selected]);
                      e.target.value = "";
                    }}
                  />

                  {/* Selected files */}
                  {aiFiles.length > 0 && (
                    <div className="space-y-2">
                      {aiFiles.map((f, i) => (
                        <div
                          key={`${f.name}-${i}`}
                          className="flex items-center justify-between rounded-md bg-green-50 px-3 py-2"
                        >
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 text-green-600" />
                            <span className="text-sm text-green-700">{f.name}</span>
                            <span className="text-xs text-gray-400">
                              ({(f.size / 1024).toFixed(1)} KB)
                            </span>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setAiFiles((prev) => prev.filter((_, idx) => idx !== i));
                            }}
                            className="text-gray-400 hover:text-gray-600"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Button
                onClick={() => aiUploadMutation.mutate()}
                disabled={aiFiles.length === 0 || aiUploadMutation.isPending}
                className="w-full"
              >
                {aiUploadMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Analyzing files with AI...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Upload & Analyze
                  </>
                )}
              </Button>
            </div>
          )}

          {/* ── Step 2: Review Mappings ─────────────────────────────────────── */}
          {aiStep === "review" && aiAnalysis && (
            <div className="space-y-4">
              {/* AI Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Sparkles className="h-4 w-4 text-indigo-600" />
                    AI Analysis
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-sm text-gray-700">{aiAnalysis.summary}</p>
                  <div className="flex gap-4 text-sm">
                    <span className="text-indigo-600 font-medium">
                      {aiAnalysis.files_analyzed} file(s)
                    </span>
                    <span className="text-gray-500">
                      {aiAnalysis.total_rows} total rows
                    </span>
                  </div>
                </CardContent>
              </Card>

              {/* Column Mappings per file */}
              {Object.entries(aiAnalysis.column_mappings).map(([filename, fileInfo]) => (
                <Card key={filename}>
                  <CardHeader>
                    <CardTitle className="text-base">
                      <FileText className="mr-2 inline-block h-4 w-4 text-gray-400" />
                      {filename}
                      <span className="ml-2 rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-normal text-indigo-700">
                        {fileInfo.detected_type}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {fileInfo.notes && (
                      <p className="mb-3 text-xs text-gray-500 italic">{fileInfo.notes}</p>
                    )}
                    <div className="max-h-60 overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-xs text-gray-500">
                            <th className="pb-2 font-medium">CSV Column</th>
                            <th className="pb-2 font-medium">
                              <ArrowRight className="mr-1 inline-block h-3 w-3" />
                              AuraFlow Field
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(fileInfo.column_mappings).map(([csvCol, afField]) => (
                            <tr key={csvCol} className="border-b last:border-0">
                              <td className="py-1.5 font-mono text-xs text-gray-700">
                                {csvCol}
                              </td>
                              <td className="py-1.5">
                                {afField ? (
                                  <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                                    {afField}
                                  </span>
                                ) : (
                                  <span className="text-xs text-gray-400 italic">
                                    not mapped
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              ))}

              {/* Membership Type Mappings */}
              {Object.keys(aiTypeMappings).length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Membership Type Mappings</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="mb-3 text-xs text-gray-500">
                      Map membership names from your old system to AuraFlow names. Edit as needed.
                    </p>
                    <div className="space-y-2 max-h-60 overflow-y-auto">
                      {Object.entries(aiTypeMappings).map(([oldName, newName]) => (
                        <div
                          key={oldName}
                          className="flex items-center gap-2 rounded border px-3 py-2"
                        >
                          <span className="flex-1 text-sm text-gray-700 truncate" title={oldName}>
                            {oldName}
                          </span>
                          <ArrowRight className="h-4 w-4 flex-shrink-0 text-gray-300" />
                          <input
                            type="text"
                            value={newName}
                            onChange={(e) =>
                              setAiTypeMappings((prev) => ({
                                ...prev,
                                [oldName]: e.target.value,
                              }))
                            }
                            className="flex-1 rounded border border-gray-200 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          />
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Preview Stats (loaded after clicking preview) */}
              {aiPreview && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Import Preview</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                        <span>{aiPreview.members_new} new members</span>
                      </div>
                      {aiPreview.members_with_existing_account > 0 && (
                        <div className="flex items-center gap-2">
                          <AlertCircle className="h-4 w-4 text-yellow-500" />
                          <span>{aiPreview.members_with_existing_account} already exist</span>
                        </div>
                      )}
                      {aiPreview.memberships_found > 0 && (
                        <div className="flex items-center gap-2">
                          <CheckCircle2 className="h-4 w-4 text-purple-500" />
                          <span>{aiPreview.memberships_found} memberships</span>
                        </div>
                      )}
                      {aiPreview.attendance_records > 0 && (
                        <div className="flex items-center gap-2">
                          <CheckCircle2 className="h-4 w-4 text-blue-500" />
                          <span>{aiPreview.attendance_records} attendance records</span>
                        </div>
                      )}
                    </div>

                    {/* Membership type breakdown */}
                    {Object.keys(aiPreview.membership_type_counts).length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-gray-500 mb-1">Membership breakdown:</p>
                        <div className="flex flex-wrap gap-1.5">
                          {Object.entries(aiPreview.membership_type_counts).map(([name, count]) => (
                            <span
                              key={name}
                              className="rounded-full bg-purple-50 px-2 py-0.5 text-xs text-purple-700"
                            >
                              {name} ({count})
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Issues */}
                    {aiPreview.issues.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-yellow-600 mb-1">
                          {aiPreview.issues.length} issue(s) found:
                        </p>
                        <div className="max-h-32 overflow-y-auto rounded bg-yellow-50 p-2 text-xs text-yellow-700">
                          {aiPreview.issues.slice(0, 10).map((issue, i) => (
                            <p key={i}>{issue}</p>
                          ))}
                          {aiPreview.issues.length > 10 && (
                            <p className="mt-1 font-medium">
                              ...and {aiPreview.issues.length - 10} more
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Sample members */}
                    {aiPreview.sample_members.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-gray-500 mb-1">Sample members:</p>
                        <div className="max-h-32 overflow-y-auto space-y-1">
                          {aiPreview.sample_members.map((m, i) => (
                            <div key={i} className="flex justify-between text-xs rounded bg-gray-50 px-2 py-1">
                              <span className="text-gray-700">{m.name}</span>
                              <span className="text-gray-400">{m.email}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Action buttons */}
              <div className="flex gap-2">
                <Button variant="ghost" onClick={resetAi}>
                  Back
                </Button>
                {!aiPreview ? (
                  <Button
                    onClick={() => aiPreviewMutation.mutate()}
                    disabled={aiPreviewMutation.isPending}
                    variant="outline"
                    className="flex-1"
                  >
                    {aiPreviewMutation.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Generating preview...
                      </>
                    ) : (
                      "Preview Import"
                    )}
                  </Button>
                ) : (
                  <Button
                    onClick={() => {
                      setAiStep("importing");
                      aiExecuteMutation.mutate();
                    }}
                    disabled={aiExecuteMutation.isPending || !studioId}
                    className="flex-1"
                  >
                    {aiExecuteMutation.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Importing...
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="mr-2 h-4 w-4" />
                        Looks Good, Import!
                      </>
                    )}
                  </Button>
                )}
              </div>

              {!studioId && (
                <p className="text-center text-xs text-red-500">
                  No studio found. Please create a studio first before importing.
                </p>
              )}
            </div>
          )}

          {/* ── Step 3: Importing ──────────────────────────────────────────── */}
          {aiStep === "importing" && (
            <div className="flex flex-col items-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
              <p className="mt-4 text-sm font-medium text-gray-700">
                Importing your data...
              </p>
              <p className="mt-2 text-xs text-gray-400">
                Processing members one at a time. This may take a few minutes for large files.
              </p>
            </div>
          )}

          {/* ── Step 4: Results ────────────────────────────────────────────── */}
          {aiStep === "done" && aiResults && (
            <div className="space-y-4">
              <div className="flex flex-col items-center py-8">
                <CheckCircle2 className="h-12 w-12 text-green-500" />
                <h2 className="mt-4 text-lg font-semibold text-gray-900">
                  Import Complete!
                </h2>
              </div>

              {/* Results Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Results</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1.5 text-sm">
                  {aiResults.members_created > 0 && (
                    <p className="text-green-600">
                      {aiResults.members_created} members created
                    </p>
                  )}
                  {aiResults.members_updated > 0 && (
                    <p className="text-blue-600">
                      {aiResults.members_updated} existing members updated
                    </p>
                  )}
                  {aiResults.user_accounts_created > 0 && (
                    <p className="text-indigo-600">
                      {aiResults.user_accounts_created} login accounts created (password: example-studio)
                    </p>
                  )}
                  {aiResults.memberships_created > 0 && (
                    <p className="text-purple-600">
                      {aiResults.memberships_created} memberships assigned
                    </p>
                  )}
                  {aiResults.passes_with_credits > 0 && (
                    <p className="text-teal-600">
                      {aiResults.passes_with_credits} class passes with credits
                    </p>
                  )}
                  {aiResults.attendance_imported > 0 && (
                    <p className="text-cyan-600">
                      {aiResults.attendance_imported} attendance records imported
                    </p>
                  )}
                  {aiResults.errors.length > 0 && (
                    <div className="mt-2">
                      <p className="text-red-600">{aiResults.errors.length} errors</p>
                      <div className="mt-1 max-h-32 overflow-y-auto rounded bg-red-50 p-2 text-xs text-red-700">
                        {aiResults.errors.slice(0, 10).map((e, i) => (
                          <p key={i}>
                            {e.email || e.class}: {e.error}
                          </p>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Chat Box */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <MessageCircle className="h-4 w-4 text-indigo-600" />
                    Ask AI About Your Import
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* Chat messages */}
                  {aiChatMessages.length > 0 && (
                    <div className="max-h-60 space-y-2 overflow-y-auto rounded border bg-gray-50 p-3">
                      {aiChatMessages.map((msg, i) => (
                        <div
                          key={i}
                          className={`rounded-lg px-3 py-2 text-sm ${
                            msg.role === "user"
                              ? "ml-8 bg-indigo-100 text-indigo-900"
                              : "mr-8 bg-white text-gray-700 shadow-sm"
                          }`}
                        >
                          {msg.text}
                        </div>
                      ))}
                      {aiChatLoading && (
                        <div className="mr-8 flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm text-gray-400 shadow-sm">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Thinking...
                        </div>
                      )}
                    </div>
                  )}

                  {/* Chat input */}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={aiChatInput}
                      onChange={(e) => setAiChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleAiChat()}
                      placeholder="e.g. How many people have class packs?"
                      className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <Button
                      onClick={handleAiChat}
                      disabled={!aiChatInput.trim() || aiChatLoading}
                      size="sm"
                    >
                      <Send className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-gray-400">
                    Ask questions like &quot;How many active memberships were imported?&quot; or
                    &quot;Which members had errors?&quot;
                  </p>
                </CardContent>
              </Card>

              <Button onClick={resetAi} variant="outline" className="w-full">
                Import More
              </Button>
            </div>
          )}
        </div>
      )}

      {/* ── Stripe Connector Tab ──────────────────────────────────────────── */}
      {activeTab === "stripe" && (
        <div className="space-y-4">
          {stripeStep === "choose" && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Migrate Stripe Payment Data</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-gray-600">
                    Link your members&apos; existing Stripe payment information so they don&apos;t
                    need to re-enter card details after migrating to AuraFlow.
                  </p>
                  <p className="text-xs text-gray-400">
                    This works because your studio&apos;s Stripe account is the same one used by
                    your previous software. Customer IDs, payment methods, and subscriptions
                    carry over automatically.
                  </p>
                </CardContent>
              </Card>

              {/* Mode Selection */}
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => setStripeMode("auto")}
                  className={`rounded-lg border-2 p-4 text-left transition-colors ${
                    stripeMode === "auto"
                      ? "border-indigo-500 bg-indigo-50"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <Zap className={`mb-2 h-5 w-5 ${stripeMode === "auto" ? "text-indigo-600" : "text-gray-400"}`} />
                  <p className="text-sm font-medium text-gray-900">Auto-Sync</p>
                  <p className="mt-1 text-xs text-gray-500">
                    Automatically match Stripe customers to members by email
                  </p>
                </button>
                <button
                  onClick={() => setStripeMode("csv")}
                  className={`rounded-lg border-2 p-4 text-left transition-colors ${
                    stripeMode === "csv"
                      ? "border-indigo-500 bg-indigo-50"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <FileText className={`mb-2 h-5 w-5 ${stripeMode === "csv" ? "text-indigo-600" : "text-gray-400"}`} />
                  <p className="text-sm font-medium text-gray-900">CSV Upload</p>
                  <p className="mt-1 text-xs text-gray-500">
                    Upload a CSV mapping emails to Stripe customer IDs
                  </p>
                </button>
              </div>

              {/* CSV file upload (only in CSV mode) */}
              {stripeMode === "csv" && (
                <Card>
                  <CardContent className="pt-6">
                    {stripeCsvFile ? (
                      <div className="flex items-center justify-between rounded-md bg-green-50 p-3">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-green-600" />
                          <span className="text-sm text-green-700">{stripeCsvFile.name}</span>
                        </div>
                        <button
                          onClick={() => setStripeCsvFile(null)}
                          className="text-gray-400 hover:text-gray-600"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => stripeCsvRef.current?.click()}
                        className="flex w-full items-center justify-center gap-2 rounded-md border-2 border-dashed border-gray-300 py-8 text-gray-500 hover:border-indigo-300 hover:text-indigo-500"
                      >
                        <Upload className="h-5 w-5" />
                        <span className="text-sm">Upload Stripe mapping CSV (email, stripe_customer_id)</span>
                      </button>
                    )}
                    <input
                      ref={stripeCsvRef}
                      type="file"
                      accept=".csv"
                      className="hidden"
                      onChange={(e) => setStripeCsvFile(e.target.files?.[0] || null)}
                    />
                  </CardContent>
                </Card>
              )}

              {/* Options */}
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={importSubscriptions}
                  onChange={(e) => setImportSubscriptions(e.target.checked)}
                  className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                Also import active Stripe subscriptions and link to membership types
              </label>

              <Button
                onClick={() => stripeDryRunMutation.mutate()}
                disabled={
                  stripeDryRunMutation.isPending ||
                  (stripeMode === "csv" && !stripeCsvFile)
                }
                className="w-full"
              >
                {stripeDryRunMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                {stripeMode === "auto" ? "Scan & Preview Matches" : "Preview CSV Mapping"}
              </Button>
            </>
          )}

          {/* Stripe Preview */}
          {stripeStep === "preview" && stripePreview && (
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Stripe Sync Preview</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center gap-2 text-sm">
                    <Link2 className="h-4 w-4 text-green-500" />
                    <span className="font-medium text-green-700">
                      {stripePreview.matched} members matched to Stripe customers
                    </span>
                  </div>
                  {stripePreview.already_linked > 0 && (
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <CheckCircle2 className="h-4 w-4" />
                      <span>{stripePreview.already_linked} already linked (will be skipped)</span>
                    </div>
                  )}
                  {(stripePreview.unmatched_stripe ?? 0) > 0 && (
                    <div className="flex items-center gap-2 text-sm text-yellow-600">
                      <AlertCircle className="h-4 w-4" />
                      <span>
                        {stripePreview.unmatched_stripe} Stripe customers with no matching AuraFlow member
                      </span>
                    </div>
                  )}
                  {(stripePreview.errors?.length ?? 0) > 0 && (
                    <div className="flex items-center gap-2 text-sm text-red-600">
                      <AlertCircle className="h-4 w-4" />
                      <span>{stripePreview.errors!.length} rows with errors</span>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Matched members list */}
              {stripePreview.matches.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Members to Link</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="max-h-60 space-y-1.5 overflow-y-auto">
                      {stripePreview.matches.map((m) => (
                        <div
                          key={m.member_id}
                          className="flex items-center justify-between rounded border px-3 py-2 text-sm"
                        >
                          <div>
                            <span className="font-medium text-gray-900">{m.member_name}</span>
                            <span className="ml-2 text-gray-400">{m.member_email}</span>
                          </div>
                          <span className="font-mono text-xs text-gray-500">
                            {m.stripe_customer_id}
                          </span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Errors list */}
              {(stripePreview.errors?.length ?? 0) > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base text-red-700">Errors</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="max-h-40 overflow-y-auto rounded bg-red-50 p-2 text-xs text-red-700">
                      {stripePreview.errors!.map((e, i) => (
                        <p key={i}>{e.email}: {e.error}</p>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              <div className="flex gap-2">
                <Button variant="ghost" onClick={resetStripe}>
                  Back
                </Button>
                <Button
                  onClick={() => {
                    setStripeStep("importing");
                    stripeImportMutation.mutate();
                  }}
                  disabled={stripeImportMutation.isPending || stripePreview.matched === 0}
                  className="flex-1"
                >
                  {stripeImportMutation.isPending && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Link {stripePreview.matched} Members
                </Button>
              </div>
            </div>
          )}

          {/* Stripe Importing */}
          {stripeStep === "importing" && (
            <div className="flex flex-col items-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
              <p className="mt-4 text-sm text-gray-500">
                Linking Stripe customers and importing subscriptions...
              </p>
            </div>
          )}

          {/* Stripe Done */}
          {stripeStep === "done" && stripeResults && (
            <div className="space-y-4">
              <div className="flex flex-col items-center py-8">
                <CheckCircle2 className="h-12 w-12 text-green-500" />
                <h2 className="mt-4 text-lg font-semibold text-gray-900">
                  Stripe Import Complete!
                </h2>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Results</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  <p className="text-green-600">
                    {stripeResults.linked} members linked to Stripe customers
                  </p>
                  {stripeResults.subscriptions_linked > 0 && (
                    <p className="text-indigo-600">
                      {stripeResults.subscriptions_linked} active subscriptions imported
                    </p>
                  )}
                  {stripeResults.already_linked > 0 && (
                    <p className="text-gray-500">
                      {stripeResults.already_linked} were already linked
                    </p>
                  )}
                  {(stripeResults.errors?.length ?? 0) > 0 && (
                    <div>
                      <p className="text-red-600">{stripeResults.errors.length} errors</p>
                      <div className="mt-2 max-h-40 overflow-y-auto rounded border bg-red-50 p-2 text-xs text-red-700">
                        {stripeResults.errors.map((e, i) => (
                          <p key={i}>{e.error}</p>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              <p className="text-center text-xs text-gray-400">
                Members can now make payments without re-entering their card details.
              </p>

              <Button onClick={resetStripe} variant="outline" className="w-full">
                Done
              </Button>
            </div>
          )}
        </div>
      )}

      {/* ── CSV Import Tab ────────────────────────────────────────────────── */}
      {activeTab === "csv" && (
      <>

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {(["upload", "preview", "done"] as const).map((s, idx) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium ${
                step === s || (step === "importing" && s === "preview")
                  ? "bg-indigo-600 text-white"
                  : step === "done" || (idx === 0 && step !== "upload")
                    ? "bg-green-100 text-green-700"
                    : "bg-gray-100 text-gray-400"
              }`}
            >
              {idx + 1}
            </div>
            <span className="text-sm text-gray-500 capitalize">{s}</span>
            {idx < 2 && <div className="mx-2 h-px w-8 bg-gray-200" />}
          </div>
        ))}
      </div>

      {/* Upload Step */}
      {step === "upload" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <FileUploadCard
              title="Members CSV"
              file={membersFile}
              setFile={setMembersFile}
              inputRef={membersRef}
              label="Upload members"
            />
            <FileUploadCard
              title="Classes CSV"
              file={classesFile}
              setFile={setClassesFile}
              inputRef={classesRef}
              label="Upload classes"
            />
            <FileUploadCard
              title="Instructors CSV"
              file={instructorsFile}
              setFile={setInstructorsFile}
              inputRef={instructorsRef}
              label="Upload instructors"
            />
            <FileUploadCard
              title="Memberships CSV"
              file={membershipsFile}
              setFile={setMembershipsFile}
              inputRef={membershipsRef}
              label="Upload memberships"
            />
            <FileUploadCard
              title="Attendance CSV"
              file={attendanceFile}
              setFile={setAttendanceFile}
              inputRef={attendanceRef}
              label="Upload attendance"
            />
            <FileUploadCard
              title="Schedule CSV"
              file={scheduleFile}
              setFile={setScheduleFile}
              inputRef={scheduleRef}
              label="Upload schedule (recurring)"
            />
          </div>

          <p className="text-center text-xs text-gray-400">
            Upload at least one file. Import order: Instructors, Members, Class Types, Schedule, Memberships, Attendance.
          </p>

          <Button
            onClick={() => dryRunMutation.mutate()}
            disabled={!hasAnyFile || dryRunMutation.isPending}
            className="w-full"
          >
            {dryRunMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Preview Import
          </Button>
        </div>
      )}

      {/* Preview Step */}
      {step === "preview" && preview && (
        <div className="space-y-4">
          {preview.instructors.total > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Instructors</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                  <span>{preview.instructors.new} new instructors to import</span>
                </div>
                {preview.instructors.existing > 0 && (
                  <div className="flex items-center gap-2 text-sm text-yellow-600">
                    <AlertCircle className="h-4 w-4" />
                    <span>
                      {preview.instructors.existing} already exist (will be skipped)
                    </span>
                  </div>
                )}
                <p className="text-xs text-gray-400">
                  Total rows: {preview.instructors.total}
                </p>
              </CardContent>
            </Card>
          )}

          {preview.members.total > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Members</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                  <span>{preview.members.new} new members to import</span>
                </div>
                {preview.members.existing > 0 && (
                  <div className="flex items-center gap-2 text-sm text-yellow-600">
                    <AlertCircle className="h-4 w-4" />
                    <span>
                      {preview.members.existing} already exist (will be skipped)
                    </span>
                  </div>
                )}
                {(preview.members as any).with_memberships > 0 && (
                  <div className="flex items-center gap-2 text-sm text-purple-600">
                    <CheckCircle2 className="h-4 w-4" />
                    <span>
                      {(preview.members as any).with_memberships} have membership data to assign
                    </span>
                  </div>
                )}
                {(preview.members as any).membership_types_found?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {(preview.members as any).membership_types_found.map((t: string) => (
                      <span
                        key={t}
                        className="rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                )}
                <p className="text-xs text-gray-400">
                  Total rows: {preview.members.total}
                </p>
              </CardContent>
            </Card>
          )}

          {preview.classes.total > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Classes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-sm">
                  {preview.classes.class_types.length} class types found:
                </p>
                <div className="flex flex-wrap gap-2">
                  {preview.classes.class_types.map((ct) => (
                    <span
                      key={ct}
                      className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700"
                    >
                      {ct}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-gray-400">
                  From {preview.classes.total} class rows
                </p>
              </CardContent>
            </Card>
          )}

          {preview.memberships.total > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Memberships</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-sm">
                  {preview.memberships.types.length} membership types found:
                </p>
                <div className="flex flex-wrap gap-2">
                  {preview.memberships.types.map((t) => (
                    <span
                      key={t}
                      className="rounded-full bg-purple-50 px-3 py-1 text-xs font-medium text-purple-700"
                    >
                      {t}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-gray-400">
                  From {preview.memberships.total} membership rows
                </p>
              </CardContent>
            </Card>
          )}

          {preview.schedule.total > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Recurring Schedule</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-sm">
                  {preview.schedule.total} recurring series to create:
                </p>
                <div className="space-y-1.5 max-h-60 overflow-y-auto">
                  {preview.schedule.series.map((s, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded border px-3 py-2 text-sm"
                    >
                      <div>
                        <span className="font-medium text-gray-900">{s.name}</span>
                        {s.instructor && (
                          <span className="text-gray-500"> with {s.instructor}</span>
                        )}
                      </div>
                      <span className="text-xs text-gray-400">
                        {s.day}s at {s.time} · {s.duration}min
                      </span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-400">
                  Each will generate 4 weeks of upcoming sessions
                </p>
              </CardContent>
            </Card>
          )}

          <div className="flex gap-2">
            <Button variant="ghost" onClick={reset}>
              Back
            </Button>
            <Button
              onClick={() => {
                setStep("importing");
                importMutation.mutate();
              }}
              disabled={importMutation.isPending}
              className="flex-1"
            >
              {importMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Confirm Import
            </Button>
          </div>
        </div>
      )}

      {/* Importing Step */}
      {step === "importing" && (
        <div className="flex flex-col items-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
          <p className="mt-4 text-sm text-gray-500">
            {importProgress || "Importing your data..."}
          </p>
        </div>
      )}

      {/* Done Step */}
      {step === "done" && (
        <div className="space-y-4">
          <div className="flex flex-col items-center py-8">
            <CheckCircle2 className="h-12 w-12 text-green-500" />
            <h2 className="mt-4 text-lg font-semibold text-gray-900">
              Import Complete!
            </h2>
          </div>

          {results.instructors && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Instructors</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p className="text-green-600">
                  {results.instructors.created} created
                </p>
                {results.instructors.skipped > 0 && (
                  <p className="text-yellow-600">
                    {results.instructors.skipped} skipped (already exist)
                  </p>
                )}
                {(results.instructors.errors?.length ?? 0) > 0 && (
                  <p className="text-red-600">
                    {results.instructors.errors.length} errors
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {results.members && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Members</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p className="text-green-600">
                  {results.members.imported ?? results.members.created} imported
                </p>
                {results.members.skipped > 0 && (
                  <p className="text-yellow-600">
                    {results.members.skipped} skipped (already exist)
                  </p>
                )}
                {(results.members as any).user_accounts_created > 0 && (
                  <p className="text-indigo-600">
                    {(results.members as any).user_accounts_created} login accounts created (password: example-studio)
                  </p>
                )}
                {(results.members as any).memberships_assigned > 0 && (
                  <p className="text-purple-600">
                    {(results.members as any).memberships_assigned} memberships assigned
                  </p>
                )}
                {(results.members as any).bookings_created > 0 && (
                  <p className="text-blue-600">
                    {(results.members as any).bookings_created} attendance records imported
                  </p>
                )}
                {(results.members.errors?.length ?? 0) > 0 && (
                  <p className="text-red-600">
                    {results.members.errors.length} errors
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {results.classTypes && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Class Types</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p className="text-green-600">
                  {results.classTypes.imported ?? results.classTypes.created} created
                </p>
                {results.classTypes.skipped > 0 && (
                  <p className="text-yellow-600">
                    {results.classTypes.skipped} skipped (already exist)
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {results.schedule && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Recurring Schedule</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p className="text-green-600">
                  {results.schedule.series_created} series created
                </p>
                <p className="text-green-600">
                  {results.schedule.sessions_created} sessions generated
                </p>
                {(results.schedule.errors?.length ?? 0) > 0 && (
                  <div>
                    <p className="text-red-600">
                      {results.schedule.errors.length} errors
                    </p>
                    <div className="mt-2 max-h-40 overflow-y-auto rounded border bg-red-50 p-2 text-xs text-red-700">
                      {results.schedule.errors.map((e, i) => (
                        <p key={i}>{e.class}: {e.error}</p>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {results.memberships && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Memberships</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p className="text-green-600">
                  {results.memberships.types_created} types created,{" "}
                  {results.memberships.memberships_created} assigned
                </p>
                {results.memberships.skipped > 0 && (
                  <p className="text-yellow-600">
                    {results.memberships.skipped} skipped
                  </p>
                )}
                {(results.memberships.errors?.length ?? 0) > 0 && (
                  <p className="text-red-600">
                    {results.memberships.errors.length} errors
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {results.attendance && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Attendance History</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p className="text-green-600">
                  {results.attendance.sessions_created} sessions created
                </p>
                {(results.attendance.errors?.length ?? 0) > 0 && (
                  <p className="text-red-600">
                    {results.attendance.errors.length} errors
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          <Button onClick={reset} variant="outline" className="w-full">
            Import More
          </Button>
        </div>
      )}

      </>
      )}
    </div>
  );
}
