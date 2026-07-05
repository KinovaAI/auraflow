import { Skeleton, SkeletonCard } from "@/components/ui/skeleton";

export default function PortalLoading() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6">
      <div>
        <Skeleton className="h-7 w-48" />
        <Skeleton className="mt-2 h-4 w-64" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <SkeletonCard />
        <SkeletonCard />
      </div>
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <Skeleton className="h-5 w-32" />
        <div className="mt-4 space-y-3">
          <Skeleton className="h-16 w-full rounded-md" />
          <Skeleton className="h-16 w-full rounded-md" />
          <Skeleton className="h-16 w-full rounded-md" />
        </div>
      </div>
    </div>
  );
}
