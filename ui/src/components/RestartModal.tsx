import { motion, AnimatePresence } from "framer-motion";

interface RestartModalProps {
  open: boolean;
  newThreshold: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function RestartModal({ open, newThreshold, onConfirm, onCancel }: RestartModalProps) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-abyss/80 backdrop-blur-sm" onClick={onCancel} />

          {/* Modal */}
          <motion.div
            className="relative z-10 max-w-md w-full mx-4 p-6 rounded-2xl"
            style={{
              background: "rgba(6,18,34,0.95)",
              border: "1px solid rgba(76,224,210,0.2)",
              boxShadow: "0 0 40px rgba(76,224,210,0.08), 0 20px 60px rgba(0,0,0,0.5)",
            }}
            initial={{ scale: 0.9, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, y: 20 }}
          >
            <h3 className="font-syne text-xl font-bold text-bio-cyan mb-2"
              style={{ textShadow: "0 0 15px rgba(76,224,210,0.3)" }}>
              Re-run Pipeline
            </h3>
            <p className="text-text-primary text-sm mb-6 leading-relaxed">
              Re-run pipeline at{" "}
              <span className="font-mono font-semibold text-bio-cyan">{newThreshold.toFixed(2)}</span>{" "}
              confidence? This replaces all current labels.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={onCancel}
                className="px-4 py-2 rounded-lg font-mono text-xs tracking-wide text-text-dim border border-text-dim/20 bg-transparent cursor-pointer hover:border-text-dim/40 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={onConfirm}
                className="px-4 py-2 rounded-lg font-mono text-xs tracking-wide text-abyss bg-bio-cyan cursor-pointer hover:brightness-110 transition-all"
                style={{ boxShadow: "0 0 15px rgba(76,224,210,0.3)" }}
              >
                Confirm
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
