import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Accessibility Statement | AuraFlow",
  description:
    "Accessibility statement and WCAG 2.1 AA commitment for the AuraFlow platform.",
  alternates: { canonical: "https://auraflow.fit/accessibility" },
};

export default function AccessibilityPage() {
  return (
    <article className="prose prose-gray max-w-none prose-headings:text-gray-900 prose-a:text-indigo-600 prose-a:no-underline hover:prose-a:underline">
      <h1>Accessibility Statement</h1>
      <p className="text-sm text-gray-500">Last updated: March 15, 2026</p>

      <p>
        AuraFlow is committed to ensuring digital accessibility for people of
        all abilities. We continually improve the user experience for everyone
        and apply the relevant accessibility standards to make our platform
        inclusive and usable.
      </p>

      <h2>Our Commitment</h2>
      <p>
        We strive to conform to the{" "}
        <strong>
          Web Content Accessibility Guidelines (WCAG) 2.1 Level AA
        </strong>{" "}
        standards. These guidelines explain how to make web content more
        accessible to people with a wide range of disabilities, including visual,
        auditory, physical, speech, cognitive, language, learning, and
        neurological disabilities.
      </p>

      <h2>Accessibility Features</h2>
      <p>
        We have implemented the following accessibility features across the
        AuraFlow platform:
      </p>
      <ul>
        <li>
          <strong>Keyboard Navigation:</strong> All functionality is accessible
          via keyboard. Interactive elements have visible focus indicators for
          users who navigate without a mouse.
        </li>
        <li>
          <strong>Screen Reader Compatibility:</strong> We use semantic HTML,
          ARIA labels, and landmark regions to ensure compatibility with
          assistive technologies such as screen readers.
        </li>
        <li>
          <strong>Color Contrast:</strong> Text and interactive elements meet
          WCAG 2.1 AA minimum contrast ratios to ensure readability for users
          with low vision or color vision deficiencies.
        </li>
        <li>
          <strong>Responsive Design:</strong> The platform adapts to various
          screen sizes and supports text resizing up to 200% without loss of
          content or functionality.
        </li>
        <li>
          <strong>Alt Text:</strong> Images include descriptive alternative text
          to convey meaning for users who cannot see them.
        </li>
        <li>
          <strong>Form Labels:</strong> All form inputs have associated labels
          to ensure clarity when using assistive technologies.
        </li>
        <li>
          <strong>Error Identification:</strong> Form errors are clearly
          identified and described in text to help users correct mistakes.
        </li>
        <li>
          <strong>Reduced Motion:</strong> We respect the{" "}
          <code>prefers-reduced-motion</code> system setting and minimize
          animations for users who are sensitive to motion.
        </li>
      </ul>

      <h2>Conformance Status</h2>
      <p>
        The WCAG guidelines define three levels of conformance: A, AA, and AAA.
        AuraFlow targets WCAG 2.1 Level AA conformance. We conduct regular
        audits using both automated testing tools and manual assessments to
        identify and address accessibility issues.
      </p>

      <h2>Known Limitations</h2>
      <p>
        While we strive for comprehensive accessibility, some areas may not yet
        fully conform to WCAG 2.1 AA standards. We are actively working to
        address these limitations:
      </p>
      <ul>
        <li>
          Some third-party embedded content may not meet all accessibility
          standards.
        </li>
        <li>
          Older PDF documents may not be fully accessible. We are working to
          update these documents.
        </li>
      </ul>

      <h2>Feedback and Assistance</h2>
      <p>
        We welcome your feedback on the accessibility of the AuraFlow platform.
        If you encounter any accessibility barriers or have suggestions for
        improvement, please contact us:
      </p>
      <ul>
        <li>
          Email:{" "}
          <a href="mailto:accessibility@auraflow.fit">
            accessibility@auraflow.fit
          </a>
        </li>
        <li>
          Mail: AuraFlow, Inc., Attn: Accessibility, 123 Wellness Blvd, Suite
          400, Wilmington, DE 19801
        </li>
      </ul>
      <p>
        We aim to respond to accessibility feedback within 5 business days and
        to resolve reported issues as quickly as possible.
      </p>

      <h2>Third-Party Content</h2>
      <p>
        Our platform may link to or integrate with third-party services that are
        not under our control. While we encourage our partners to follow
        accessibility best practices, we cannot guarantee the accessibility of
        external content.
      </p>

      <h2>Assessment and Testing</h2>
      <p>
        AuraFlow assesses the accessibility of our platform through a
        combination of:
      </p>
      <ul>
        <li>Automated accessibility testing during development.</li>
        <li>Manual testing with keyboard-only navigation.</li>
        <li>Testing with screen readers (NVDA, VoiceOver, JAWS).</li>
        <li>Periodic third-party accessibility audits.</li>
        <li>User feedback and usability testing.</li>
      </ul>
    </article>
  );
}
