import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { PipelineEvent } from "../api";

interface RunProgressProps {
  event: PipelineEvent | null;
  confThreshold: number;
}

interface LogEntry {
  id: number;
  time: string;
  message: string;
  step: string;
}

const STEP_LABELS: Record<string, string> = {
  discovery: "DISCOVERING MODEL",
  download: "DOWNLOADING MODEL",
  inference: "PROCESSING IMAGES",
  gemini_batch: "GEMINI VERIFICATION",
  done: "COMPLETE",
  error: "ERROR",
  // Acquisition steps
  bootstrap: "BOOTSTRAPPING TOPIC",
  crawling: "CRAWLING IMAGES",
  dedup: "DEDUPLICATING",
  filtering: "FILTERING IMAGES",
  searching: "SEARCHING YOUTUBE",
  scoring: "SCORING VIDEOS",
  downloading: "DOWNLOADING VIDEOS",
  extracting: "EXTRACTING FRAMES",
};

const STEP_DETAILS: Record<string, string> = {
  discovery: "Searching Roboflow for a matching model...",
  download: "Downloading model artifacts...",
  done: "Pipeline complete",
  bootstrap: "Analyzing topic with Gemini...",
};

function stepColor(step: string): string {
  if (step === "error") return "#FF4D8E";
  if (step === "done") return "#2AFFA0";
  return "rgba(255,255,255,0.55)";
}

export default function RunProgress({ event, confThreshold }: RunProgressProps) {
  const [log, setLog] = useState<LogEntry[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(0);
  const lastKeyRef = useRef("");

  const step = event?.step ?? "discovery";
  const label = STEP_LABELS[step] ?? step.toUpperCase();
  const hasProgress = event?.current != null && event?.total;
  const isTerminal = step === "done" || step === "error";
  const isIndeterminate = !hasProgress && !isTerminal;
  const progress = hasProgress
    ? (event.current! / event.total!) * 100
    : step === "done" ? 100 : 0;
  const detail = hasProgress
    ? `${event.current} of ${event.total}`
    : STEP_DETAILS[step] ?? event?.message ?? "";

  // Accumulate log entries — deduplicate same step+message combos (progress ticks)
  useEffect(() => {
    if (!event) return;
    const msg = event.message || STEP_DETAILS[event.step] || "";
    if (!msg) return;

    const key = `${event.step}:${msg}`;
    if (key === lastKeyRef.current) return;
    lastKeyRef.current = key;

    setLog((prev) => [
      ...prev,
      {
        id: idRef.current++,
        time: new Date().toLocaleTimeString("en-US", { hour12: false }),
        message: msg,
        step: event.step,
      },
    ]);
  }, [event]);

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log]);

  return (
    <motion.div
      className="relative w-[520px] max-w-[90vw] max-h-[85vh] flex flex-col rounded-2xl p-12"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
      style={{
        background: "rgba(6,18,34,0.6)",
        backdropFilter: "blur(20px)",
        border: "1px solid rgba(76,224,210,0.1)",
        boxShadow: "0 8px 40px rgba(0,0,0,0.5), 0 0 80px rgba(76,224,210,0.04)",
      }}
    >
      {/* Corner accents */}
      <div className="absolute -top-px -left-px w-5 h-5 border-t-2 border-l-2 border-bio-cyan rounded-tl-2xl" />
      <div className="absolute -top-px -right-px w-5 h-5 border-t-2 border-r-2 border-bio-cyan rounded-tr-2xl" />
      <div className="absolute -bottom-px -left-px w-5 h-5 border-b-2 border-l-2 border-bio-cyan rounded-bl-2xl" />
      <div className="absolute -bottom-px -right-px w-5 h-5 border-b-2 border-r-2 border-bio-cyan rounded-br-2xl" />

      {/* Confidence in corner */}
      <div className="absolute top-5 right-6 text-right">
        <span className="block font-mono text-[9px] tracking-[0.12em] uppercase text-text-dim mb-0.5">
          Confidence
        </span>
        <span
          className="font-syne text-xl font-extrabold text-bio-cyan"
          style={{ textShadow: "0 0 20px rgba(76,224,210,0.4)" }}
        >
          {confThreshold.toFixed(2)}
        </span>
      </div>

      {/* Step indicator */}
      <div className="mb-8">
        <span className="font-mono text-[9px] text-text-dim tracking-[0.12em] uppercase">
          {label}
        </span>
      </div>

      {/* Progress bar */}
      <div className="relative h-1 rounded-sm overflow-hidden mb-3"
        style={{ background: "rgba(76,224,210,0.08)" }}
      >
        {isIndeterminate ? (
          <div
            className="absolute inset-0 rounded-sm"
            style={{
              background: "linear-gradient(90deg, transparent 0%, rgba(76,224,210,0.4) 50%, transparent 100%)",
              backgroundSize: "200% 100%",
              animation: "shimmer 1.5s ease-in-out infinite",
            }}
          />
        ) : (
          <motion.div
            className="h-full rounded-sm"
            style={{
              background: "linear-gradient(90deg, rgba(76,224,210,0.3), rgba(76,224,210,0.5))",
              boxShadow: "0 0 12px rgba(76,224,210,0.2)",
            }}
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.3, ease: "easeOut" }}
          />
        )}
      </div>

      {/* Detail text */}
      <p className="font-mono text-xs text-text-dim">
        {detail}
      </p>

      {/* Activity log */}
      {log.length > 0 && (
        <div
          className="mt-6 min-h-0 flex-1 overflow-y-auto activity-log"
          style={{
            background: "rgba(2,8,16,0.5)",
            border: "1px solid rgba(76,224,210,0.08)",
            borderRadius: "8px",
            padding: "8px 12px",
            maxHeight: "50vh",
          }}
        >
          {log.map((entry) => (
            <motion.div
              key={entry.id}
              className="flex gap-2.5 py-[3px]"
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
            >
              <span className="font-mono text-[9px] leading-[18px] text-text-dim whitespace-nowrap shrink-0">
                {entry.time}
              </span>
              <span
                className="font-mono text-[10px] leading-[18px]"
                style={{ color: stepColor(entry.step) }}
              >
                {entry.message}
              </span>
            </motion.div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}

      {/* Pulsing indicator */}
      {step !== "done" && step !== "error" && (
        <div className="flex justify-center mt-8">
          <motion.div
            className="w-10 h-10 rounded-full"
            style={{
              border: "2px solid rgba(59,139,245,0.3)",
              background: "radial-gradient(circle at 40% 40%, rgba(59,139,245,0.2), rgba(59,139,245,0.05) 50%, transparent)",
            }}
            animate={{
              scale: [1, 1.1, 1],
              boxShadow: [
                "0 0 20px rgba(59,139,245,0.15)",
                "0 0 35px rgba(59,139,245,0.3)",
                "0 0 20px rgba(59,139,245,0.15)",
              ],
            }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          />
        </div>
      )}

      <style>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        .activity-log::-webkit-scrollbar {
          width: 4px;
        }
        .activity-log::-webkit-scrollbar-track {
          background: transparent;
        }
        .activity-log::-webkit-scrollbar-thumb {
          background: rgba(76,224,210,0.15);
          border-radius: 2px;
        }
      `}</style>
    </motion.div>
  );
}
