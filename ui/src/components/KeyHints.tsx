export default function KeyHints() {
  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-20 flex gap-6 font-mono text-[13px] px-5 py-2.5 rounded-lg"
      style={{ background: "rgba(0,0,0,0.85)", color: "rgba(200,221,232,0.8)" }}>
      <span className="flex items-center gap-1.5">
        <kbd className="inline-block px-2 py-0.5 rounded text-[11px]"
          style={{ background: "rgba(255,255,255,0.1)" }}>
          &larr;
        </kbd>
        discard
      </span>
      <span className="flex items-center gap-1.5">
        <kbd className="inline-block px-2 py-0.5 rounded text-[11px]"
          style={{ background: "rgba(255,255,255,0.1)" }}>
          R
        </kbd>
        restart
      </span>
      <span className="flex items-center gap-1.5">
        <kbd className="inline-block px-2 py-0.5 rounded text-[11px]"
          style={{ background: "rgba(255,255,255,0.1)" }}>
          &rarr;
        </kbd>
        keep
      </span>
    </div>
  );
}
