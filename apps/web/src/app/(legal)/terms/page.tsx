import type { Metadata } from "next";
import { FileText, UserCheck, Laptop, CreditCard, XCircle, Award, ShieldCheck, AlertTriangle, Scale, Users, Gavel, Mail } from "lucide-react";

export const metadata: Metadata = {
  title: "Terms of Service | AuraFlow",
  description: "Terms of Service for the AuraFlow studio management platform.",
  alternates: { canonical: "https://auraflow.fit/terms" },
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

export default function TermsPage() {
  return (
    <div>
      <div className="mb-10">
        <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-600">
          <FileText className="h-3.5 w-3.5" />
          Legal Agreement
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-gray-900 sm:text-4xl">
          Terms of Service
        </h1>
        <p className="mt-2 text-sm text-gray-500">Last updated: March 15, 2026</p>
        <p className="mt-4 text-gray-600">
          These Terms of Service (&ldquo;Terms&rdquo;) govern your access to and use of the AuraFlow platform (&ldquo;Service&rdquo;), operated by AuraFlow, Inc. (&ldquo;AuraFlow&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;, or &ldquo;our&rdquo;). By accessing or using the Service, you agree to be bound by these Terms.
        </p>
      </div>

      <div className="space-y-6">
        <Section icon={UserCheck} title="1. Acceptance of Terms">
          <p>By creating an account, accessing, or using our Service, you acknowledge that you have read, understood, and agree to be bound by these Terms and our <a href="/privacy" className="font-medium text-indigo-600 hover:underline">Privacy Policy</a>. If you are using the Service on behalf of an organization, you represent and warrant that you have the authority to bind that organization to these Terms.</p>
          <p>If you do not agree to these Terms, you may not access or use the Service. We reserve the right to modify these Terms at any time. We will notify you of material changes by posting the updated Terms on our website or by sending you an email. Your continued use of the Service after such notification constitutes your acceptance of the updated Terms.</p>
        </Section>

        <Section icon={Users} title="2. Account Terms">
          <p>You must provide accurate, complete, and current information when creating your account. You are responsible for maintaining the security of your account credentials and for all activities that occur under your account. You must immediately notify AuraFlow of any unauthorized use of your account.</p>
          <div className="mt-2 rounded-lg bg-amber-50 p-3">
            <p className="text-xs text-amber-800"><strong>Important:</strong> You must be at least 18 years of age to use the Service. Each account may only be used by one person — sharing login credentials between multiple users is not permitted.</p>
          </div>
        </Section>

        <Section icon={Laptop} title="3. Use of the Service">
          <p>AuraFlow provides a cloud-based studio management platform designed for yoga, fitness, and wellness studios. The Service includes features such as:</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs">Class scheduling &amp; booking</div>
            <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs">Membership management</div>
            <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs">Payment processing &amp; POS</div>
            <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs">Member portals &amp; self-service</div>
            <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs">Instructor management</div>
            <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs">Marketing &amp; analytics</div>
          </div>
          <p className="mt-3">You agree to use the Service only for lawful purposes and in compliance with all applicable laws and regulations. You shall not use the Service to transmit harmful, offensive, or infringing content, or to interfere with the operation of the Service.</p>
        </Section>

        <Section icon={CreditCard} title="4. Payment Terms">
          <p>Certain features of the Service require a paid subscription. By subscribing to a paid plan, you agree to pay all applicable fees as described on our pricing page. Fees are billed in advance on a monthly or annual basis, depending on your chosen plan.</p>
          <p>All fees are non-refundable except as expressly stated in these Terms or required by applicable law. We reserve the right to change our pricing with <strong className="text-gray-700">30 days&rsquo; prior notice</strong>. If you do not agree to a price change, you may cancel your subscription before the change takes effect.</p>
          <p>Payment processing is handled by third-party providers (Stripe). You agree to comply with their terms of service. AuraFlow is not responsible for errors or issues arising from third-party payment processing.</p>
        </Section>

        <Section icon={XCircle} title="5. Cancellation and Termination">
          <p>You may cancel your subscription at any time through your account settings. Cancellation takes effect at the end of your current billing period. Upon cancellation, you will retain access to the Service until the end of the paid period.</p>
          <div className="mt-2 rounded-lg bg-blue-50 p-3">
            <p className="text-xs text-blue-800"><strong>Data retention:</strong> Upon termination, we will make your data available for export for <strong>30 days</strong>, after which it may be permanently deleted.</p>
          </div>
          <p className="mt-2">We may suspend or terminate your account if you violate these Terms, fail to pay applicable fees, or if required by law.</p>
        </Section>

        <Section icon={Award} title="6. Intellectual Property">
          <p>The Service, including its original content, features, and functionality, is owned by AuraFlow and is protected by international copyright, trademark, patent, trade secret, and other intellectual property laws.</p>
          <p>You retain all rights to the data and content you upload to the Service (&ldquo;Your Content&rdquo;). By using the Service, you grant AuraFlow a limited license to use, store, and process Your Content <strong className="text-gray-700">solely for the purpose of providing and improving the Service</strong>.</p>
        </Section>

        <Section icon={ShieldCheck} title="7. Data Protection">
          <p>We take data protection seriously. Our collection and use of personal information is described in our <a href="/privacy" className="font-medium text-indigo-600 hover:underline">Privacy Policy</a>.</p>
          <p>When you use the Service to process personal data of your members, students, or clients, you act as the <strong className="text-gray-700">data controller</strong> and AuraFlow acts as the <strong className="text-gray-700">data processor</strong>. You are responsible for ensuring that you have obtained appropriate consent from your members for the processing of their personal data.</p>
        </Section>

        <Section icon={AlertTriangle} title="8. Limitation of Liability">
          <p>To the maximum extent permitted by law, AuraFlow shall not be liable for any indirect, incidental, special, consequential, or punitive damages, including but not limited to loss of profits, data, use, goodwill, or other intangible losses, resulting from your access to or use of (or inability to access or use) the Service.</p>
          <div className="mt-2 rounded-lg bg-gray-50 p-3">
            <p className="text-xs text-gray-600">In no event shall AuraFlow&rsquo;s total aggregate liability exceed the amount you paid to AuraFlow in the <strong>twelve (12) months</strong> preceding the claim. This limitation applies regardless of the legal theory on which the claim is based.</p>
          </div>
        </Section>

        <Section icon={Scale} title="9. Disclaimer of Warranties">
          <p>The Service is provided &ldquo;as is&rdquo; and &ldquo;as available&rdquo; without warranties of any kind, whether express or implied, including but not limited to implied warranties of merchantability, fitness for a particular purpose, and non-infringement. AuraFlow does not warrant that the Service will be uninterrupted, secure, or error-free.</p>
        </Section>

        <Section icon={ShieldCheck} title="10. Indemnification">
          <p>You agree to indemnify, defend, and hold harmless AuraFlow and its officers, directors, employees, and agents from and against any claims, liabilities, damages, losses, and expenses arising out of or in connection with your use of the Service, your violation of these Terms, or your violation of any rights of a third party.</p>
        </Section>

        <Section icon={Gavel} title="11. Governing Law">
          <p>These Terms shall be governed by and construed in accordance with the laws of the <strong className="text-gray-700">State of Delaware, United States</strong>, without regard to its conflict of law provisions. Any disputes arising under these Terms shall be resolved exclusively in the state or federal courts located in Wilmington, Delaware.</p>
        </Section>

        <Section icon={Mail} title="12. Contact Information">
          <p>If you have any questions about these Terms, please contact us:</p>
          <div className="mt-2 rounded-lg bg-indigo-50 p-4">
            <p className="font-medium text-indigo-900">AuraFlow, Inc.</p>
            <p className="mt-1">Email: <a href="mailto:legal@auraflow.fit" className="font-medium text-indigo-600 hover:underline">legal@auraflow.fit</a></p>
            <p>Mail: Attn: Legal, 123 Wellness Blvd, Suite 400, Wilmington, DE 19801</p>
          </div>
        </Section>
      </div>
    </div>
  );
}
