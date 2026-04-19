import { motion } from "framer-motion";

interface LoadingStateProps {
  message: string;
}

export default function LoadingState({ message }: LoadingStateProps) {
  return (
    <motion.div
      className="flex flex-col items-center justify-center gap-6"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
    >
      {/* Pulsing nautilus */}
      <motion.div
        className="w-16 h-16 rounded-full"
        style={{
          border: "2px solid rgba(59,139,245,0.3)",
          background: "radial-gradient(circle at 40% 40%, rgba(59,139,245,0.2), rgba(59,139,245,0.05) 50%, transparent)",
          boxShadow: "0 0 30px rgba(59,139,245,0.2)",
        }}
        animate={{
          scale: [1, 1.1, 1],
          boxShadow: [
            "0 0 30px rgba(59,139,245,0.2)",
            "0 0 50px rgba(59,139,245,0.35)",
            "0 0 30px rgba(59,139,245,0.2)",
          ],
        }}
        transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
      />

      <div className="font-mono text-sm text-text-dim tracking-wide">
        {message}
      </div>
    </motion.div>
  );
}
