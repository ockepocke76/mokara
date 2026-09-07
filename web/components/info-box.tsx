import { cn } from "@/lib/utils";

/**
 * Soft banner boxes replicating the old app's st.info / st.warning look.
 */
export function InfoBox({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg px-4 py-3 text-sm",
        "bg-[var(--info-bg)] text-[var(--info-fg)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function WarningBox({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg px-4 py-3 text-sm",
        "bg-[var(--warning-bg)] text-[var(--warning-fg)]",
        className,
      )}
    >
      {children}
    </div>
  );
}
