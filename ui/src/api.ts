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
