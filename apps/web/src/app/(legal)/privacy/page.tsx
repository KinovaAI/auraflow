import type { Metadata } from "next";
import { Shield, Database, Share2, Cookie, Clock, Lock, Globe, Users, Baby, RefreshCw, Mail } from "lucide-react";

export const metadata: Metadata = {
  title: "Privacy Policy | AuraFlow",
  description: "Privacy Policy for the AuraFlow studio management platform.",
  alternates: { canonical: "https://auraflow.fit/privacy" },
};

function Section({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
          <Icon className="h-5 w-5" />
        </div>
        <h2 className="text-lg font-bold text-gray-900">{title}</h2>
      </div>
      <div className="space-y-3 text-sm leading-relaxed text-gray-600">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <div>
      <div className="mb-10">
        <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-600">
          <Shield className="h-3.5 w-3.5" />
          Your Privacy Matters
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-gray-900 sm:text-4xl">
          Privacy Policy
        </h1>
        <p className="mt-2 text-sm text-gray-500">Last updated: March 15, 2026</p>
        <p className="mt-4 text-gray-600">
          AuraFlow, Inc. (&ldquo;AuraFlow&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;, or &ldquo;our&rdquo;) is committed to protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our studio management platform (&ldquo;Service&rdquo;).
        </p>
      </div>

      <div className="space-y-6">
        <Section icon={Database} title="1. Information We Collect">
          <p className="font-medium text-gray-700">Information You Provide</p>
          <ul className="ml-4 list-disc space-y-1.5">
            <li><strong className="text-gray-700">Account Information:</strong> Name, email address, phone number, and password when you create an account.</li>
            <li><strong className="text-gray-700">Studio Information:</strong> Business name, address, type of studio, and other details relevant to studio management.</li>
            <li><strong className="text-gray-700">Payment Information:</strong> Billing address and payment method details, processed securely through our third-party payment providers.</li>
            <li><strong className="text-gray-700">Member Data:</strong> Information about your studio members that you upload or enter into the Service, including names, contact information, membership details, and attendance records.</li>
            <li><strong className="text-gray-700">Communications:</strong> Messages, feedback, and support requests you send to us.</li>
          </ul>
          <p className="mt-3 font-medium text-gray-700">Information Collected Automatically</p>
          <ul className="ml-4 list-disc space-y-1.5">
            <li><strong className="text-gray-700">Usage Data:</strong> Pages visited, features used, actions taken, time and date of visits, and other diagnostic data.</li>
            <li><strong className="text-gray-700">Device Information:</strong> Browser type, operating system, IP address, device identifiers, and screen resolution.</li>
            <li><strong className="text-gray-700">Log Data:</strong> Server logs including access times, pages viewed, and referring URLs.</li>
          </ul>
        </Section>

        <Section icon={Users} title="2. How We Use Your Information">
          <p>We use the information we collect to:</p>
          <ul className="ml-4 list-disc space-y-1.5">
            <li>Provide, maintain, and improve the Service.</li>
            <li>Process transactions and send related information.</li>
            <li>Send administrative messages, technical notices, updates, and security alerts.</li>
            <li>Respond to your comments, questions, and customer service requests.</li>
            <li>Monitor and analyze trends, usage, and activities to improve user experience.</li>
            <li>Detect, investigate, and prevent fraudulent transactions and other illegal activities.</li>
            <li>Personalize and improve the Service.</li>
          </ul>
        </Section>

        <Section icon={Share2} title="3. How We Share Your Information">
          <p>We do not sell your personal information. We may share your information in the following circumstances:</p>
          <ul className="ml-4 list-disc space-y-1.5">
            <li><strong className="text-gray-700">Service Providers:</strong> With third-party vendors who perform services on our behalf, such as payment processing, data analytics, email delivery, hosting, and customer service.</li>
            <li><strong className="text-gray-700">Legal Requirements:</strong> When required by law, regulation, legal process, or governmental request.</li>
            <li><strong className="text-gray-700">Business Transfers:</strong> In connection with a merger, acquisition, or sale of all or a portion of our assets.</li>
            <li><strong className="text-gray-700">With Your Consent:</strong> When you have given us explicit consent to share your information.</li>
          </ul>
        </Section>

        <Section icon={Cookie} title="4. Cookies and Tracking Technologies">
          <p>We use cookies and similar tracking technologies to:</p>
          <ul className="ml-4 list-disc space-y-1.5">
            <li>Keep you signed in to your account.</li>
            <li>Remember your preferences and settings.</li>
            <li>Understand how you use our Service.</li>
            <li>Improve our Service and marketing efforts.</li>
          </ul>
          <p className="mt-3">You can control cookies through your browser settings. Note that disabling certain cookies may limit your ability to use some features of the Service. We categorize our cookies as:</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="font-medium text-gray-700">Essential</p>
              <p className="text-xs">Required for the Service to function. Cannot be disabled.</p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="font-medium text-gray-700">Analytics</p>
              <p className="text-xs">Help us understand how visitors interact with the Service.</p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="font-medium text-gray-700">Marketing</p>
              <p className="text-xs">Used to deliver relevant ads and track campaign effectiveness.</p>
            </div>
          </div>
        </Section>

        <Section icon={Clock} title="5. Data Retention">
          <p>We retain your personal information for as long as your account is active or as needed to provide you with the Service. If you cancel your account, we will retain your data for up to <strong className="text-gray-700">30 days</strong> to allow for account recovery, after which it will be securely deleted.</p>
          <p>We may retain certain information as required by law or for legitimate business purposes such as resolving disputes and enforcing agreements.</p>
        </Section>

        <Section icon={Lock} title="6. Data Security">
          <p>We implement appropriate technical and organizational measures to protect your personal information against unauthorized access, alteration, disclosure, or destruction. These measures include:</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <div className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-700">
              <Lock className="h-3.5 w-3.5 shrink-0" /> Encryption in transit and at rest
            </div>
            <div className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-700">
              <Shield className="h-3.5 w-3.5 shrink-0" /> Regular security audits
            </div>
            <div className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-700">
              <Users className="h-3.5 w-3.5 shrink-0" /> Role-based access controls
            </div>
            <div className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-700">
              <Database className="h-3.5 w-3.5 shrink-0" /> Secure development practices
            </div>
          </div>
          <p className="mt-2 text-xs text-gray-500">However, no method of transmission over the Internet or electronic storage is completely secure.</p>
        </Section>

        <Section icon={Globe} title="7. Your Rights Under GDPR (European Users)">
          <p>If you are located in the European Economic Area (EEA), you have the following rights under the General Data Protection Regulation:</p>
          <ul className="ml-4 list-disc space-y-1.5">
            <li><strong className="text-gray-700">Right of Access:</strong> Request a copy of the personal data we hold about you.</li>
            <li><strong className="text-gray-700">Right to Rectification:</strong> Request correction of inaccurate or incomplete data.</li>
            <li><strong className="text-gray-700">Right to Erasure:</strong> Request deletion of your personal data under certain circumstances.</li>
            <li><strong className="text-gray-700">Right to Restrict Processing:</strong> Request that we limit how we use your data.</li>
            <li><strong className="text-gray-700">Right to Data Portability:</strong> Receive your data in a structured, machine-readable format.</li>
            <li><strong className="text-gray-700">Right to Object:</strong> Object to the processing of your personal data for direct marketing purposes.</li>
            <li><strong className="text-gray-700">Right to Withdraw Consent:</strong> Withdraw consent at any time where processing is based on consent.</li>
          </ul>
          <p className="mt-2">To exercise any of these rights, please contact us at <a href="mailto:privacy@auraflow.fit" className="font-medium text-indigo-600 hover:underline">privacy@auraflow.fit</a>. We will respond within 30 days.</p>
        </Section>

        <Section icon={Shield} title="8. Your Rights Under CCPA (California Residents)">
          <p>If you are a California resident, the CCPA provides you with the following rights:</p>
          <ul className="ml-4 list-disc space-y-1.5">
            <li><strong className="text-gray-700">Right to Know:</strong> Request information about the categories and specific pieces of personal information we have collected.</li>
            <li><strong className="text-gray-700">Right to Delete:</strong> Request that we delete your personal information, subject to certain exceptions.</li>
            <li><strong className="text-gray-700">Right to Opt-Out:</strong> Opt out of the sale of your personal information. <em>Note: we do not sell personal information.</em></li>
            <li><strong className="text-gray-700">Right to Non-Discrimination:</strong> We will not discriminate against you for exercising your CCPA rights.</li>
          </ul>
          <p className="mt-2">To exercise your CCPA rights, contact us at <a href="mailto:privacy@auraflow.fit" className="font-medium text-indigo-600 hover:underline">privacy@auraflow.fit</a>.</p>
        </Section>

        <Section icon={Baby} title="9. Children&rsquo;s Privacy">
          <p>The Service is not directed to children under the age of 16. We do not knowingly collect personal information from children under 16. If you become aware that a child has provided us with personal information, please contact us so we can take appropriate steps to remove that information.</p>
        </Section>

        <Section icon={Globe} title="10. International Data Transfers">
          <p>Your information may be transferred to and processed in countries other than the country in which you reside. We ensure that appropriate safeguards are in place to protect your information in compliance with applicable data protection laws, including Standard Contractual Clauses approved by the European Commission.</p>
        </Section>

        <Section icon={RefreshCw} title="11. Changes to This Policy">
          <p>We may update this Privacy Policy from time to time. We will notify you of any material changes by posting the new Privacy Policy on this page and updating the &ldquo;Last updated&rdquo; date. Your continued use of the Service after any changes constitutes your acceptance of the updated policy.</p>
        </Section>

        <Section icon={Mail} title="12. Contact Us">
          <p>If you have any questions about this Privacy Policy or our data practices, please contact us:</p>
          <div className="mt-2 rounded-lg bg-indigo-50 p-4">
            <p className="font-medium text-indigo-900">AuraFlow, Inc.</p>
            <p className="mt-1">Email: <a href="mailto:privacy@auraflow.fit" className="font-medium text-indigo-600 hover:underline">privacy@auraflow.fit</a></p>
            <p>Mail: Attn: Privacy, 123 Wellness Blvd, Suite 400, Wilmington, DE 19801</p>
          </div>
        </Section>
      </div>
    </div>
  );
}
