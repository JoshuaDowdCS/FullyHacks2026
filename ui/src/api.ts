export interface ImageLabel {
  class_id: number;
  class_name: string;
  x_center: number;
  y_center: number;
  width: number;
  height: number;
}

export interface ImageInfo {
  filename: string;
  width: number;
  height: number;
  labels: ImageLabel[];
}

export interface ImagesResponse {
  images: ImageInfo[];
  conf_threshold: number;
  total: number;
}

export interface StatsResponse {
  total: number;
  labeled: number;
  conf_threshold: number;
}

export interface RestartResponse {
  stats: StatsResponse;
  new_threshold: number;
}

export interface UploadResponse {
  uploaded: number;
  project: string;
}

export async function fetchImages(): Promise<ImagesResponse> {
  const res = await fetch("/api/images");
  if (!res.ok) throw new Error(`Failed to fetch images: ${res.status}`);
  return res.json();
}

export function imageUrl(filename: string): string {
  return `/api/images/${encodeURIComponent(filename)}`;
}

export async function keepImage(filename: string): Promise<{ new_filename: string }> {
  const res = await fetch(`/api/images/${encodeURIComponent(filename)}/keep`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to keep: ${res.status}`);
  return res.json();
}

export async function discardImage(filename: string): Promise<void> {
  const res = await fetch(`/api/images/${encodeURIComponent(filename)}/discard`, {
    method: "POST",
  });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Failed to discard: ${res.status}`);
  }
}

export async function undoAction(): Promise<{ action: string; filename: string }> {
  const res = await fetch("/api/undo", { method: "POST" });
  if (!res.ok) throw new Error(`Undo failed: ${res.status}`);
  return res.json();
}

export async function restartPipeline(): Promise<RestartResponse> {
  const res = await fetch("/api/restart", { method: "POST" });
  if (!res.ok) throw new Error(`Restart failed: ${res.status}`);
  return res.json();
}

export async function uploadToRoboflow(): Promise<UploadResponse> {
  const res = await fetch("/api/upload", { method: "POST" });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

// ── SSE Pipeline Events ──

export interface PipelineEvent {
  step: "discovery" | "download" | "inference" | "done" | "error";
  message: string;
  current?: number;
  total?: number;
  labeled?: number;
}

export function runPipeline(
  prompt: string,
  confThreshold: number,
  onEvent: (event: PipelineEvent) => void,
): { cancel: () => void } {
  const controller = new AbortController();

  fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, conf_threshold: confThreshold }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        onEvent({ step: "error", message: `Server error: ${res.status}` });
        return;
      }
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop()!;
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            try {
              const event: PipelineEvent = JSON.parse(trimmed.slice(6));
              onEvent(event);
            } catch {
              // skip malformed lines
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onEvent({ step: "error", message: err.message });
      }
    });

  return { cancel: () => controller.abort() };
}
