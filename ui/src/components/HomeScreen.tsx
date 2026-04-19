import { useState } from "react";
import { motion } from "framer-motion";

interface HomeScreenProps {
  onLaunch: (prompt: string, confThreshold: number) => void;
}

export default function HomeScreen({ onLaunch }: HomeScreenProps) {
  const [prompt, setPrompt] = useState("");
  const [confThreshold, setConfThreshold] = useState(0.7);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    onLaunch(prompt.trim(), confThreshold);
  };

  return (
    <motion.div
      className="relative w-[460px] max-w-[90vw]"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Sonar rings */}
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none">
        {[0, 2, 4].map((delay) => (
          <div
            key={delay}
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[520px] h-[520px] rounded-full"
            style={{
              border: "1px solid rgba(76,224,210,0.06)",
              animation: `sonar-ping 6s ease-out ${delay}s infinite`,
            }}
          />
        ))}
      </div>

      {/* Form card */}
      <form
        onSubmit={handleSubmit}
        className="relative rounded-2xl p-12"
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

        {/* Title */}
        <h1
          className="font-syne text-[1.8rem] font-extrabold text-bio-cyan text-center mb-1"
          style={{ textShadow: "0 0 25px rgba(76,224,210,0.4)" }}
        >
          Detection Pipeline
        </h1>
        <p className="font-mono text-[9px] text-text-dim text-center tracking-[0.12em] uppercase mb-9">
          Automated Dataset Labeling
        </p>

        {/* Prompt input */}
        <label className="block font-mono text-[9px] text-text-dim tracking-[0.12em] uppercase mb-2">
          What do you want to detect?
        </label>
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. basketball, car, bird..."
          className="w-full rounded-[10px] px-[18px] py-[14px] font-outfit text-base font-medium text-text-primary outline-none transition-all"
          style={{
            background: "rgba(2,8,16,0.7)",
            border: "1.5px solid rgba(76,224,210,0.15)",
          }}
          onFocus={(e) => {
            e.target.style.borderColor = "rgba(76,224,210,0.35)";
            e.target.style.boxShadow = "0 0 20px rgba(76,224,210,0.08), inset 0 0 12px rgba(76,224,210,0.03)";
          }}
          onBlur={(e) => {
            e.target.style.borderColor = "rgba(76,224,210,0.15)";
            e.target.style.boxShadow = "none";
          }}
        />

        {/* Confidence slider */}
        <div className="mt-7">
          <div className="flex justify-between items-baseline mb-3">
            <span className="font-mono text-[9px] text-text-dim tracking-[0.12em] uppercase">
              Confidence Threshold
            </span>
            <span
              className="font-syne text-2xl font-extrabold text-bio-cyan"
              style={{ textShadow: "0 0 20px rgba(76,224,210,0.4)" }}
            >
              {confThreshold.toFixed(2)}
            </span>
          </div>

          <input
            type="range"
            min="0.10"
            max="1.00"
            step="0.05"
            value={confThreshold}
            onChange={(e) => setConfThreshold(parseFloat(e.target.value))}
            className="w-full h-1 rounded-sm appearance-none cursor-pointer conf-slider"
            style={{
              background: `linear-gradient(90deg, rgba(76,224,210,0.4) 0%, rgba(76,224,210,0.4) ${((confThreshold - 0.1) / 0.9) * 100}%, rgba(76,224,210,0.08) ${((confThreshold - 0.1) / 0.9) * 100}%, rgba(76,224,210,0.08) 100%)`,
            }}
          />

          <div className="flex justify-between items-center mt-1.5">
            <span className="font-mono text-[9px] text-text-dim">0.10</span>
            <span className="font-mono text-[8px]" style={{ color: "rgba(76,224,210,0.35)" }}>
              recommended: 0.70
            </span>
            <span className="font-mono text-[9px] text-text-dim">1.00</span>
          </div>
        </div>

        {/* Launch button */}
        <div className="mt-9 text-center">
          <motion.button
            type="submit"
            disabled={!prompt.trim()}
            className="relative inline-flex items-center px-10 py-[15px] font-mono text-[13px] font-semibold tracking-[0.15em] uppercase text-abyss bg-bio-cyan rounded-xl cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              boxShadow: "0 0 30px rgba(76,224,210,0.3), 0 4px 20px rgba(0,0,0,0.3)",
            }}
            whileHover={prompt.trim() ? { scale: 1.03, y: -2 } : {}}
            whileTap={prompt.trim() ? { scale: 0.97 } : {}}
          >
            Launch Pipeline
            {/* Sonar pulse on button */}
            <span
              className="absolute inset-[-4px] rounded-[16px] pointer-events-none"
              style={{
                border: "1.5px solid rgba(76,224,210,0.2)",
                animation: "btn-pulse 2.5s ease-out infinite",
              }}
            />
          </motion.button>
        </div>
      </form>

      <style>{`
        @keyframes sonar-ping {
          0% { transform: translate(-50%, -50%) scale(0.6); opacity: 0.5; border-color: rgba(76,224,210,0.12); }
          100% { transform: translate(-50%, -50%) scale(1.4); opacity: 0; border-color: rgba(76,224,210,0); }
        }
        @keyframes btn-pulse {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(1.15); opacity: 0; }
        }
        .conf-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: #4CE0D2;
          border: 3px solid #061222;
          box-shadow: 0 0 16px rgba(76,224,210,0.5), 0 0 40px rgba(76,224,210,0.15);
          cursor: grab;
          animation: thumb-breathe 3s ease-in-out infinite;
        }
        .conf-slider::-moz-range-thumb {
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: #4CE0D2;
          border: 3px solid #061222;
          box-shadow: 0 0 16px rgba(76,224,210,0.5), 0 0 40px rgba(76,224,210,0.15);
          cursor: grab;
          animation: thumb-breathe 3s ease-in-out infinite;
        }
        @keyframes thumb-breathe {
          0%, 100% { box-shadow: 0 0 16px rgba(76,224,210,0.5), 0 0 40px rgba(76,224,210,0.15); }
          50% { box-shadow: 0 0 22px rgba(76,224,210,0.65), 0 0 50px rgba(76,224,210,0.25); }
        }
      `}</style>
    </motion.div>
  );
}
