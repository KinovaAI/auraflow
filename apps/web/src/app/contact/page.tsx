"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Send, CheckCircle, AlertCircle } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SUBJECT_OPTIONS = [
  { value: "", label: "Select a topic..." },
  { value: "General", label: "General Inquiry" },
  { value: "Billing", label: "Billing & Payments" },
  { value: "Technical", label: "Technical Support" },
  { value: "Partnership", label: "Partnership Opportunity" },
];

interface FormData {
  name: string;
  email: string;
  subject: string;
  message: string;
}

interface FormErrors {
  name?: string;
  email?: string;
  subject?: string;
  message?: string;
}

function validateForm(data: FormData): FormErrors {
  const errors: FormErrors = {};

  if (!data.name.trim() || data.name.trim().length < 2) {
    errors.name = "Name must be at least 2 characters.";
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!data.email.trim() || !emailRegex.test(data.email.trim())) {
    errors.email = "Please enter a valid email address.";
  }

  if (!data.subject) {
    errors.subject = "Please select a topic.";
  }

  if (!data.message.trim() || data.message.trim().length < 10) {
    errors.message = "Message must be at least 10 characters.";
  }

  return errors;
}

export default function ContactPage() {
  const [form, setForm] = useState<FormData>({
    name: "",
    email: "",
    subject: "",
    message: "",
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    // Clear field error on change
    if (errors[name as keyof FormErrors]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage("");

    const validationErrors = validateForm(form);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setErrors({});
    setStatus("submitting");

    try {
      const res = await fetch(`${API_URL}/api/v1/support/contact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name.trim(),
          email: form.email.trim(),
          subject: form.subject,
          message: form.message.trim(),
        }),
      });

      if (res.status === 429) {
        setStatus("error");
        setErrorMessage("Too many submissions. Please try again later.");
        return;
      }

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setStatus("error");
        setErrorMessage(
          data?.detail || "Something went wrong. Please try again."
        );
        return;
      }

      setStatus("success");
      setForm({ name: "", email: "", subject: "", message: "" });
    } catch {
      setStatus("error");
      setErrorMessage("Unable to reach the server. Please try again later.");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white">
      {/* Nav */}
      <nav className="border-b border-gray-100 bg-white/80 backdrop-blur-lg">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/logo.png" alt="AuraFlow" width={110} height={32} />
          </Link>
          <div className="flex items-center gap-5">
            <Link href="/" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">
              Home
            </Link>
            <Link href="/login" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">
              Log in
            </Link>
            <Link
              href="/signup"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 transition-all hover:bg-indigo-700"
            >
              Start Free Trial
            </Link>
          </div>
        </div>
      </nav>

      <div className="mx-auto max-w-2xl px-6 py-16">
        {/* Back link */}
        <Link
          href="/"
          className="mb-8 inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to home
        </Link>

        {/* Header */}
        <div className="mb-10">
          <h1 className="text-3xl font-extrabold text-gray-900">Contact Us</h1>
          <p className="mt-3 text-gray-500">
            Have a question or need help? Fill out the form below and our team
            will get back to you within one business day.
          </p>
        </div>

        {/* Success state */}
        {status === "success" ? (
          <div className="rounded-2xl border border-green-200 bg-green-50 p-8 text-center">
            <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
            <h2 className="mt-4 text-xl font-bold text-gray-900">
              Message sent!
            </h2>
            <p className="mt-2 text-gray-600">
              Thank you for reaching out. We&apos;ll get back to you soon.
            </p>
            <button
              onClick={() => setStatus("idle")}
              className="mt-6 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 transition-all hover:bg-indigo-700"
            >
              Send another message
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-6" noValidate>
            {/* Error banner */}
            {status === "error" && errorMessage && (
              <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4">
                <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" />
                <p className="text-sm text-red-700">{errorMessage}</p>
              </div>
            )}

            {/* Name */}
            <div>
              <label
                htmlFor="name"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Name
              </label>
              <input
                id="name"
                name="name"
                type="text"
                value={form.name}
                onChange={handleChange}
                placeholder="Your full name"
                className={`w-full rounded-lg border px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${
                  errors.name
                    ? "border-red-300 focus:border-red-400"
                    : "border-gray-200 focus:border-indigo-400"
                }`}
              />
              {errors.name && (
                <p className="mt-1.5 text-xs text-red-600">{errors.name}</p>
              )}
            </div>

            {/* Email */}
            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                placeholder="you@example.com"
                className={`w-full rounded-lg border px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${
                  errors.email
                    ? "border-red-300 focus:border-red-400"
                    : "border-gray-200 focus:border-indigo-400"
                }`}
              />
              {errors.email && (
                <p className="mt-1.5 text-xs text-red-600">{errors.email}</p>
              )}
            </div>

            {/* Subject */}
            <div>
              <label
                htmlFor="subject"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Topic
              </label>
              <select
                id="subject"
                name="subject"
                value={form.subject}
                onChange={handleChange}
                className={`w-full rounded-lg border px-4 py-2.5 text-sm text-gray-900 shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${
                  errors.subject
                    ? "border-red-300 focus:border-red-400"
                    : "border-gray-200 focus:border-indigo-400"
                } ${!form.subject ? "text-gray-400" : ""}`}
              >
                {SUBJECT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {errors.subject && (
                <p className="mt-1.5 text-xs text-red-600">{errors.subject}</p>
              )}
            </div>

            {/* Message */}
            <div>
              <label
                htmlFor="message"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Message
              </label>
              <textarea
                id="message"
                name="message"
                rows={5}
                value={form.message}
                onChange={handleChange}
                placeholder="How can we help?"
                className={`w-full rounded-lg border px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/20 resize-y ${
                  errors.message
                    ? "border-red-300 focus:border-red-400"
                    : "border-gray-200 focus:border-indigo-400"
                }`}
              />
              {errors.message && (
                <p className="mt-1.5 text-xs text-red-600">{errors.message}</p>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={status === "submitting"}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 transition-all hover:bg-indigo-700 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-60"
            >
              {status === "submitting" ? (
                <>
                  <svg
                    className="h-4 w-4 animate-spin"
                    viewBox="0 0 24 24"
                    fill="none"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Sending...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  Send Message
                </>
              )}
            </button>
          </form>
        )}
      </div>

      {/* Minimal footer */}
      <footer className="border-t border-gray-100 bg-white px-6 py-8">
        <div className="mx-auto max-w-7xl text-center text-xs text-gray-400">
          &copy; {new Date().getFullYear()} AuraFlow. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
