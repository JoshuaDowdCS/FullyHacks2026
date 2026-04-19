import { motion, AnimatePresence } from "framer-motion";
import type { ImageInfo } from "../api";
import { imageUrl } from "../api";

interface ImageCardProps {
  image: ImageInfo;
  direction: "left" | "right" | null;
}

const variants = {
  enter: {
    scale: 0.95,
    opacity: 0,
  },
  center: {
    scale: 1,
    opacity: 1,
    x: 0,
    rotate: 0,
  },
  exitLeft: {
    x: -400,
    rotate: -12,
    opacity: 0,
    transition: { duration: 0.3 },
  },
  exitRight: {
    x: 400,
    rotate: 12,
    opacity: 0,
    transition: { duration: 0.3 },
  },
};

export default function ImageCard({ image, direction }: ImageCardProps) {
  return (
    <div className="flex flex-col items-center">
      <AnimatePresence mode="wait" custom={direction}>
        <motion.div
          key={image.filename}
          className="relative w-[480px] max-w-[85vw] rounded-2xl overflow-hidden cursor-grab"
          style={{
            border: "1px solid rgba(76,224,210,0.12)",
            boxShadow: "0 8px 40px rgba(0,0,0,0.6), 0 0 60px rgba(76,224,210,0.06)",
          }}
          variants={variants}
          initial="enter"
          animate="center"
          exit={direction === "left" ? "exitLeft" : "exitRight"}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        >
          {/* Image + bounding boxes in a relative wrapper so boxes align to the image */}
          <div className="relative">
            <img
              src={imageUrl(image.filename)}
              alt={image.filename}
              className="w-full block"
              draggable={false}
            />

          {image.labels.map((label, i) => (
            <div
              key={i}
              className="absolute"
              style={{
                left: `${(label.x_center - label.width / 2) * 100}%`,
                top: `${(label.y_center - label.height / 2) * 100}%`,
                width: `${label.width * 100}%`,
                height: `${label.height * 100}%`,
                border: "2px solid #4CE0D2",
                borderRadius: "3px",
                boxShadow:
                  "0 0 12px rgba(76,224,210,0.25), inset 0 0 12px rgba(76,224,210,0.05)",
              }}
            >
              {/* Corner accents */}
              <div className="absolute -top-px -left-px w-2.5 h-2.5 border-t-2 border-l-2 border-bio-mint" />
              <div className="absolute -top-px -right-px w-2.5 h-2.5 border-t-2 border-r-2 border-bio-mint" />
              <div className="absolute -bottom-px -left-px w-2.5 h-2.5 border-b-2 border-l-2 border-bio-mint" />
              <div className="absolute -bottom-px -right-px w-2.5 h-2.5 border-b-2 border-r-2 border-bio-mint" />

              {/* Class label */}
              <div
                className="absolute -top-7 -left-0.5 bg-bio-cyan text-abyss font-mono text-[10px] font-semibold px-2 py-0.5 uppercase tracking-wide"
                style={{ borderRadius: "4px 4px 4px 0" }}
              >
                {label.class_name}
              </div>
            </div>
          ))}
          </div>
        </motion.div>
      </AnimatePresence>

    </div>
  );
}
