import { motion } from "framer-motion";

interface CompletionScreenProps {
  kept: number;
  discarded: number;
  onUpload: () => void;
  onRestart: () => void;
  uploading: boolean;
  uploaded: boolean;
  uploadProject?: string;
}

export default function CompletionScreen({
  kept,
  discarded,
  onUpload,
  onRestart,
  uploading,
  uploaded,
  uploadProject,
}: CompletionScreenProps) {
  return (
    <motion.div
      className="flex flex-col items-center justify-center gap-8"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
    >
      <h2
        className="font-syne text-3xl font-extrabold text-bio-cyan"
        style={{ textShadow: "0 0 25px rgba(76,224,210,0.4)" }}
      >
        Review Complete
      </h2>

      <div className="flex gap-8 font-mono text-sm">
        <div className="text-center">
          <div className="text-2xl font-semibold text-bio-mint" style={{ textShadow: "0 0 12px rgba(42,255,160,0.3)" }}>
            {kept}
          </div>
          <div className="text-text-dim text-[10px] uppercase tracking-[0.12em] mt-1">Kept</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-semibold text-bio-pink" style={{ textShadow: "0 0 12px rgba(255,77,142,0.3)" }}>
            {discarded}
          </div>
          <div className="text-text-dim text-[10px] uppercase tracking-[0.12em] mt-1">Discarded</div>
        </div>
      </div>

      {uploaded ? (
        <div className="text-center">
          <div className="font-mono text-sm text-bio-mint mb-1">
            Uploaded to {uploadProject}
          </div>
          <div className="text-text-dim text-xs">Done!</div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3">
          <motion.button
            onClick={onUpload}
            disabled={uploading}
            className="px-8 py-3 rounded-xl font-mono text-sm font-semibold tracking-wide text-abyss bg-bio-cyan cursor-pointer disabled:opacity-50 disabled:cursor-wait"
            style={{ boxShadow: "0 0 25px rgba(76,224,210,0.3), 0 0 50px rgba(76,224,210,0.1)" }}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            {uploading ? "Uploading..." : "Upload to Roboflow"}
          </motion.button>

          <button
            onClick={onRestart}
            disabled={uploading}
            className="font-mono text-[10px] tracking-wide text-text-dim hover:text-bio-blue transition-colors bg-transparent border-none cursor-pointer"
          >
            or restart at higher confidence
          </button>
        </div>
      )}
    </motion.div>
  );
}
