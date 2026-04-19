import { useCallback, useEffect, useState } from "react";
import type { ImageInfo } from "./api";
import { discardImage, fetchImages, keepImage, restartPipeline, uploadToRoboflow } from "./api";
import OceanEnvironment from "./components/OceanEnvironment";
import HUD from "./components/HUD";
import ProgressBar from "./components/ProgressBar";
import ImageCard from "./components/ImageCard";
import ActionButtons from "./components/ActionButtons";
import KeyHints from "./components/KeyHints";
import RestartModal from "./components/RestartModal";
import CompletionScreen from "./components/CompletionScreen";
import LoadingState from "./components/LoadingState";

type Phase = "loading" | "review" | "complete" | "restarting" | "uploading" | "uploaded";

export default function App() {
  const [images, setImages] = useState<ImageInfo[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [kept, setKept] = useState(0);
  const [discarded, setDiscarded] = useState(0);
  const [confThreshold, setConfThreshold] = useState(0.7);
  const [phase, setPhase] = useState<Phase>("loading");
  const [direction, setDirection] = useState<"left" | "right" | null>(null);
  const [showRestartModal, setShowRestartModal] = useState(false);
  const [uploadProject, setUploadProject] = useState<string>();
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "uploaded">("idle");
  const [error, setError] = useState<string>();

  // Load images on mount
  useEffect(() => {
    fetchImages()
      .then((data) => {
        setImages(data.images);
        setConfThreshold(data.conf_threshold);
        setPhase(data.images.length > 0 ? "review" : "complete");
      })
      .catch((err) => setError(err.message));
  }, []);

  const currentImage = images[currentIndex];
  const remaining = images.length - currentIndex;

  const handleKeep = useCallback(() => {
    if (phase !== "review" || !currentImage) return;
    setDirection("right");
    setKept((k) => k + 1);
    keepImage(currentImage.filename).catch(() => {});
    setTimeout(() => {
      if (currentIndex + 1 >= images.length) {
        setPhase("complete");
      } else {
        setCurrentIndex((i) => i + 1);
      }
    }, 50);
  }, [phase, currentImage, currentIndex, images.length]);

  const handleDiscard = useCallback(() => {
    if (phase !== "review" || !currentImage) return;
    setDirection("left");
    setDiscarded((d) => d + 1);
    discardImage(currentImage.filename).catch(() => {});
    // Remove from array so it doesn't appear again
    const newImages = images.filter((_, i) => i !== currentIndex);
    setImages(newImages);
    // Don't increment index since array shifted
    if (currentIndex >= newImages.length) {
      setPhase("complete");
    }
  }, [phase, currentImage, currentIndex, images]);

  const handleRestart = useCallback(() => {
    setShowRestartModal(true);
  }, []);

  const confirmRestart = useCallback(async () => {
    setShowRestartModal(false);
    setConfThreshold(Math.round((confThreshold + 0.05) * 100) / 100);
    setPhase("restarting");
    try {
      const result = await restartPipeline();
      setConfThreshold(result.new_threshold);
      // Reload images
      const data = await fetchImages();
      setImages(data.images);
      setCurrentIndex(0);
      setKept(0);
      setDiscarded(0);
      setPhase(data.images.length > 0 ? "review" : "complete");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restart failed");
      setPhase("review");
    }
  }, [confThreshold]);

  const handleUpload = useCallback(async () => {
    if (uploadStatus === "uploading") return;
    setUploadStatus("uploading");
    if (phase === "complete") setPhase("uploading");
    try {
      const result = await uploadToRoboflow();
      setUploadProject(result.project);
      setUploadStatus("uploaded");
      if (phase === "complete") setPhase("uploaded");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploadStatus("idle");
      if (phase !== "review") setPhase("complete");
    }
  }, [phase, uploadStatus]);

  // Keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (showRestartModal) return;
      if (phase !== "review") return;

      switch (e.key) {
        case "ArrowRight":
          handleKeep();
          break;
        case "ArrowLeft":
          handleDiscard();
          break;
        case "r":
        case "R":
          handleRestart();
          break;
        case "u":
        case "U":
          handleUpload();
          break;
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [phase, showRestartModal, handleKeep, handleDiscard, handleRestart, handleUpload]);

  return (
    <>
      <OceanEnvironment />

      <div className="relative z-10">
        <HUD
          remaining={remaining}
          kept={kept}
          discarded={discarded}
          confThreshold={confThreshold}
        />

        <ProgressBar
          reviewed={kept + discarded}
          total={kept + discarded + remaining}
        />

        {phase === "review" && (
          <button
            onClick={handleUpload}
            disabled={uploadStatus !== "idle"}
            className="fixed top-[88px] right-16 z-20 font-mono text-sm font-semibold tracking-wide px-5 py-2.5 rounded-xl cursor-pointer transition-all disabled:cursor-default"
            style={{
              border: uploadStatus === "uploaded"
                ? "1.5px solid rgba(42,255,160,0.4)"
                : "1.5px solid rgba(76,224,210,0.3)",
              background: uploadStatus === "uploaded"
                ? "rgba(42,255,160,0.12)"
                : "rgba(6,18,34,0.9)",
              backdropFilter: "blur(8px)",
              color: uploadStatus === "uploaded"
                ? "#2AFFA0"
                : uploadStatus === "uploading"
                  ? "#4A6A82"
                  : "#4CE0D2",
              boxShadow: uploadStatus === "idle"
                ? "0 0 20px rgba(76,224,210,0.1), 0 4px 12px rgba(0,0,0,0.3)"
                : "none",
            }}
          >
            {uploadStatus === "uploaded"
              ? <>Uploaded to {uploadProject}</>
              : uploadStatus === "uploading"
                ? "Uploading..."
                : "Upload to Roboflow"}
          </button>
        )}

        <div className="flex flex-col items-center justify-center min-h-screen px-16 pt-[100px] pb-[260px]">
          {phase === "loading" && <LoadingState message="Loading images..." />}

          {phase === "restarting" && (
            <LoadingState message={`Re-scanning at ${confThreshold.toFixed(2)}...`} />
          )}

          {phase === "review" && currentImage && (
            <ImageCard image={currentImage} direction={direction} />
          )}

          {(phase === "complete" || phase === "uploading" || phase === "uploaded") && (
            <CompletionScreen
              kept={kept}
              discarded={discarded}
              onUpload={handleUpload}
              onRestart={handleRestart}
              uploading={uploadStatus === "uploading"}
              uploaded={uploadStatus === "uploaded"}
              uploadProject={uploadProject}
            />
          )}

          {error && (
            <div
              className="fixed bottom-24 left-1/2 -translate-x-1/2 z-30 font-mono text-xs text-bio-pink px-4 py-2 rounded-lg"
              style={{
                background: "rgba(255,77,142,0.1)",
                border: "1px solid rgba(255,77,142,0.2)",
              }}
            >
              {error}
              <button
                onClick={() => setError(undefined)}
                className="ml-3 text-text-dim hover:text-text-primary bg-transparent border-none cursor-pointer"
              >
                &times;
              </button>
            </div>
          )}
        </div>

        {phase === "review" && (
          <>
            <ActionButtons
              onDiscard={handleDiscard}
              onRestart={handleRestart}
              onKeep={handleKeep}
            />
            <KeyHints />
          </>
        )}
      </div>

      <RestartModal
        open={showRestartModal}
        newThreshold={Math.round((confThreshold + 0.05) * 100) / 100}
        onConfirm={confirmRestart}
        onCancel={() => setShowRestartModal(false)}
      />
    </>
  );
}
