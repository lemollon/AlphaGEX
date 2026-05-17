export default function EmptySlot({ number, total }) {
  return (
    <div className="sw-empty-card">
      <div>
        <div className="text-text-tertiary text-[13px] font-bold">Empty Slot</div>
        <div className="sw-mono text-text-muted text-[12px] mt-1">{number} / {total}</div>
      </div>
    </div>
  );
}
