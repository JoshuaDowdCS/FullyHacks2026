import { motion } from "framer-motion";
import "./creatures.css";

interface ActionButtonsProps {
  onDiscard: () => void;
  onRestart: () => void;
  onKeep: () => void;
}

function Anglerfish() {
  return (
    <div className="anglerfish">
      <div className="angler-body">
        <div className="angler-eye" />
        <div className="angler-mouth">
          <div className="angler-teeth-top">
            {[...Array(5)].map((_, i) => <div key={i} className="tooth tooth-down" />)}
          </div>
          <div className="angler-teeth-bottom">
            {[...Array(4)].map((_, i) => <div key={i} className="tooth tooth-up" />)}
          </div>
        </div>
        <div className="angler-fin angler-fin-top" />
        <div className="angler-fin angler-fin-back" />
      </div>
      <div className="angler-lure" />
    </div>
  );
}

function Nautilus() {
  return (
    <div className="nautilus">
      <div className="nautilus-shell">
        <div className="nautilus-spiral spiral-1" />
        <div className="nautilus-spiral spiral-2" />
        <div className="nautilus-spiral spiral-3" />
        <div className="nautilus-eye" />
      </div>
      <div className="naut-tentacles">
        <div className="naut-t" style={{ height: 10, background: "linear-gradient(180deg, rgba(59,139,245,0.25), transparent)" }} />
        <div className="naut-t" style={{ height: 14, background: "linear-gradient(180deg, rgba(59,139,245,0.2), transparent)", animationDelay: "0.3s" }} />
        <div className="naut-t" style={{ height: 8, background: "linear-gradient(180deg, rgba(59,139,245,0.25), transparent)", animationDelay: "0.6s" }} />
      </div>
    </div>
  );
}

function SeaTurtle() {
  return (
    <div className="sea-turtle">
      <div className="turtle-shell">
        <div className="shell-pattern">
          {[...Array(6)].map((_, i) => <div key={i} className="scute" />)}
        </div>
        <div className="flipper flipper-tl" />
        <div className="flipper flipper-bl" />
        <div className="flipper flipper-tr" />
        <div className="flipper flipper-br" />
      </div>
      <div className="turtle-head">
        <div className="turtle-eye" />
      </div>
      <div className="turtle-tail" />
    </div>
  );
}

export default function ActionButtons({ onDiscard, onRestart, onKeep }: ActionButtonsProps) {
  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 flex items-center gap-16 z-20">
      <motion.button
        onClick={onDiscard}
        className="flex flex-col items-center gap-3 cursor-pointer bg-transparent border-none"
        whileHover={{ scale: 1.12, y: -6 }}
        whileTap={{ scale: 0.95 }}
      >
        <div className="h-[56px] flex items-center justify-center"
          style={{ transform: "translateY(-4px)" }}>
          <Anglerfish />
        </div>
        <span className="font-mono text-sm tracking-[0.15em] uppercase font-semibold px-3 py-1 rounded-full"
          style={{
            color: "#FF4D8E",
            background: "rgba(255,77,142,0.12)",
            border: "1px solid rgba(255,77,142,0.2)",
            textShadow: "0 0 12px rgba(255,77,142,0.5)",
          }}>
          Discard
        </span>
      </motion.button>

      <motion.button
        onClick={onRestart}
        className="flex flex-col items-center gap-3 cursor-pointer bg-transparent border-none"
        whileHover={{ scale: 1.12, y: -6 }}
        whileTap={{ scale: 0.95 }}
      >
        <div className="restart-bubble">
          <div className="restart-bubble-inner">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" className="restart-icon">
              <path d="M1 4v6h6" stroke="#3B8BF5" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" stroke="#3B8BF5" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
        </div>
        <span className="font-mono text-sm tracking-[0.15em] uppercase font-semibold px-3 py-1 rounded-full"
          style={{
            color: "#3B8BF5",
            background: "rgba(59,139,245,0.12)",
            border: "1px solid rgba(59,139,245,0.2)",
            textShadow: "0 0 12px rgba(59,139,245,0.5)",
          }}>
          +0.05
        </span>
      </motion.button>

      <motion.button
        onClick={onKeep}
        className="flex flex-col items-center gap-3 cursor-pointer bg-transparent border-none"
        whileHover={{ scale: 1.12, y: -6 }}
        whileTap={{ scale: 0.95 }}
      >
        <div className="h-[56px] flex items-center justify-center"
          style={{ transform: "translateY(3px)" }}>
          <SeaTurtle />
        </div>
        <span className="font-mono text-sm tracking-[0.15em] uppercase font-semibold px-3 py-1 rounded-full"
          style={{
            color: "#2AFFA0",
            background: "rgba(42,255,160,0.12)",
            border: "1px solid rgba(42,255,160,0.2)",
            textShadow: "0 0 12px rgba(42,255,160,0.5)",
          }}>
          Keep
        </span>
      </motion.button>
    </div>
  );
}
