export default function EmptySlot({ number, total }) {
  return (
    <div className="sw-card border-dashed flex items-center justify-center text-text-muted text-xs font-[var(--font-ui)] font-medium min-h-[120px]">
      Empty Slot {number}/{total}
    </div>
  );
}
