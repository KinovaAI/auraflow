import { cn } from "@/lib/utils";

/**
 * Skeleton loading primitive. Use as a shimmering placeholder for
 * content that's loading. Supports arbitrary sizing via className.
 *
 * @example
 *   <Skeleton className="h-4 w-32" />
 *   <Skeleton className="h-40 w-full rounded-lg" />
 */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-gray-200/80",
        className
      )}
      {...props}
    />
  );
}

/**
 * Table-row skeleton — matches the height + spacing of a typical
 * members/transactions/bookings list row.
 */
export function SkeletonRow({ cols = 4 }: { cols?: number }) {
  return (
    <div className="flex items-center gap-4 border-b border-gray-100 py-3">
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn(
            "h-4",
            i === 0 ? "w-32" : i === cols - 1 ? "w-20" : "w-24"
          )}
        />
      ))}
    </div>
  );
}

/**
 * Card skeleton — matches the shape of KPI tiles and summary cards
 * on the dashboard.
 */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-lg border border-gray-200 bg-white p-5",
        className
      )}
    >
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-3 h-7 w-32" />
      <Skeleton className="mt-2 h-3 w-20" />
    </div>
  );
}

/**
 * Full page skeleton — title, KPI row, content area.
 * Matches most admin dashboard pages.
 */
export function SkeletonPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Skeleton className="h-7 w-48" />
        <Skeleton className="mt-2 h-4 w-72" />
      </div>
      {/* KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
      {/* Content area */}
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <Skeleton className="h-5 w-40" />
        <div className="mt-4 space-y-2">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      </div>
    </div>
  );
}
