interface ProgressBarProps {
  reviewed: number;
  total: number;
}

export default function ProgressBar({ reviewed, total }: ProgressBarProps) {
  const pct = total > 0 ? (reviewed / total) * 100 : 0;

  return (
    <div className="fixed top-[76px] left-16 right-16 z-20">
      <div className="h-0.5 bg-current/60 rounded-sm overflow-visible">
        <div
          className="h-full rounded-sm relative transition-[width] duration-500 ease-out"
          style={{
            width: `${pct}%`,
            background: "linear-gradient(90deg, #4CE0D2, #2AFFA0)",
          }}
        >
          <div
            className="absolute -right-px -top-[3px] w-2 h-2 rounded-full bg-bio-mint"
            style={{ boxShadow: "0 0 12px #2AFFA0, 0 0 24px rgba(42,255,160,0.3)" }}
          />
        </div>
      </div>
      <div className="font-mono text-[10px] text-text-dim mt-1.5 tracking-wide">
        {reviewed} of {total} reviewed
      </div>
    </div>
  );
}
