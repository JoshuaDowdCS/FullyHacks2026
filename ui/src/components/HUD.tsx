import { motion, AnimatePresence } from "framer-motion";

interface HUDProps {
  remaining: number;
  kept: number;
  discarded: number;
  confThreshold: number;
}

function AnimatedNumber({ value, className }: { value: number; className?: string }) {
  return (
    <span className="inline-flex overflow-hidden" style={{ height: "1.75em" }}>
      <AnimatePresence mode="popLayout">
        <motion.span
          key={value}
          initial={{ y: -12, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 12, opacity: 0 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className={className}
        >
          {value}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

export default function HUD({ remaining, kept, discarded, confThreshold }: HUDProps) {
  return (
    <div className="fixed top-0 left-0 right-0 z-20 flex justify-between items-center px-16 py-5"
      style={{ background: "linear-gradient(180deg, rgba(2,8,16,0.92) 0%, transparent 100%)" }}>
      <div className="flex gap-7 font-mono text-xs font-medium">
        <div>
          <span className="block text-text-dim uppercase text-[9px] tracking-[0.12em] mb-0.5">
            Remaining
          </span>
          <AnimatedNumber value={remaining} className="text-lg font-semibold text-text-primary" />
        </div>
        <div>
          <span className="block text-text-dim uppercase text-[9px] tracking-[0.12em] mb-0.5">
            Kept
          </span>
          <AnimatedNumber
            value={kept}
            className="text-lg font-semibold text-bio-mint"
          />
        </div>
        <div>
          <span className="block text-text-dim uppercase text-[9px] tracking-[0.12em] mb-0.5">
            Discarded
          </span>
          <AnimatedNumber
            value={discarded}
            className="text-lg font-semibold text-bio-pink"
          />
        </div>
      </div>
      <div className="text-right">
        <span className="block font-mono text-[9px] tracking-[0.12em] uppercase text-text-dim mb-0.5">
          Confidence
        </span>
        <span className="font-syne text-2xl font-extrabold text-bio-cyan"
          style={{ textShadow: "0 0 20px rgba(76,224,210,0.4)" }}>
          {confThreshold.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
