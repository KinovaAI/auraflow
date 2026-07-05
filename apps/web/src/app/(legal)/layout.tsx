import Link from "next/link";

export default function LegalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <Link
            href="/"
            className="text-xl font-bold text-indigo-600 transition-colors hover:text-indigo-700"
          >
            AuraFlow
          </Link>
          <Link
            href="/"
            className="text-sm font-medium text-gray-500 transition-colors hover:text-gray-900"
          >
            &larr; Back to Home
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-12">{children}</main>
      <footer className="border-t border-gray-200 bg-white">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-4 px-6 py-6 text-sm text-gray-500">
          <p>&copy; {new Date().getFullYear()} AuraFlow, Inc. All rights reserved.</p>
          <nav className="flex gap-6">
            <Link href="/terms" className="hover:text-indigo-600">
              Terms
            </Link>
            <Link href="/privacy" className="hover:text-indigo-600">
              Privacy
            </Link>
            <Link href="/accessibility" className="hover:text-indigo-600">
              Accessibility
            </Link>
            <Link href="/contact" className="hover:text-indigo-600">
              Contact
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
