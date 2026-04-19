import { motion } from "framer-motion";
import type { PipelineEvent } from "../api";

interface RunProgressProps {
  event: PipelineEvent | null;
  confThreshold: number;
}

const STEP_LABELS: Record<string, string> = {
  discovery: "DISCOVERING MODEL",
  download: "DOWNLOADING MODEL",
  inference: "PROCESSING IMAGES",
  done: "COMPLETE",
  error: "ERROR",
};

const STEP_DETAILS: Record<string, string> = {
  discovery: "Searching Roboflow for a matching model...",
  download: "Downloading model artifacts...",
  done: "Pipeline complete",
};

export default function RunProgress({ event, confThreshold }: RunProgressProps) {
  const step = event?.step ?? "discovery";
  const label = STEP_LABELS[step] ?? step.toUpperCase();
  const isIndeterminate = step === "discovery" || step === "download";
  const progress = event?.step === "inference" && event.total
    ? (event.current! / event.total) * 100
    : step === "done" ? 100 : 0;
  const detail = step === "inference" && event?.current != null
    ? `Processing image ${event.current} of ${event.total}`
    : STEP_DETAILS[step] ?? event?.message ?? "";

  return (
    <motion.div
      className="relative w-[460px] max-w-[90vw] rounded-2xl p-12"
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
      `}</style>
    </motion.div>
  );
}
