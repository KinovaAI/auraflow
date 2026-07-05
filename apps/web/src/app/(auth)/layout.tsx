import Image from "next/image";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="mb-8">
        <Image
          src="/logo-full.png"
          alt="AuraFlow Studio Management Software"
          width={280}
          height={120}
          style={{ height: "auto" }}
          priority
        />
      </div>
      <div className="w-full max-w-md">{children}</div>
    </div>
  );
}
