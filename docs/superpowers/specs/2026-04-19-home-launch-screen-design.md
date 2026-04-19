# Home / Launch Screen Design

**Date:** 2026-04-19
**Status:** Approved

## Overview

Add a home screen to the frontend that replaces the CLI `label.sh` workflow. The user enters a detection prompt and confidence threshold, launches the pipeline, sees live progress via SSE, and transitions to the existing review screen when complete.

## Screen Flow

```
home → running (progress) → review (existing)
                              ↓
                        completion → home (resets confidence to 0.70)
```

All screens share the same root layout — the ocean environment never unmounts, preventing visual flashes during transitions.

## Phase Type

The existing `Phase` type in `App.tsx` expands from:

```
"loading" | "review" | "complete" | "restarting" | "uploading" | "uploaded"
```

to:

```
"home" | "running" | "review" | "complete" | "restarting" | "uploading" | "uploaded"
```

The app starts in `"home"` instead of `"loading"`. The `"loading"` phase is removed — `"running"` replaces it with richer progress.

## Home Screen (`phase === "home"`)

### Layout

Centered form card over the ocean environment. The card uses the same glass-morphism treatment as the review screen (backdrop-filter blur, translucent background, 1px cyan border with corner accents matching ImageCard bounding box style).

### Elements

1. **Title** — "Detection Pipeline" in Syne extrabold, cyan with text-shadow glow. Subtitle "Automated Dataset Labeling" in 9px JetBrains Mono uppercase tracking.

2. **Prompt input** — labeled "What do you want to detect?". Standard text input styled to match the deep-sea glass aesthetic. This value maps directly to the `--prompt` argument in `label.sh` / the pipeline's `prompt` config field.

3. **Confidence slider** — range 0.10 to 1.00, step 0.05, default 0.70. Displays current value in Syne extrabold cyan (same treatment as HUD confidence display on review screen). The slider thumb glows with a breathing animation. A "recommended: 0.70" hint sits below the track.

4. **Launch button** — "Launch Pipeline" in JetBrains Mono uppercase. Cyan background, dark text. Sonar-pulse ring animation on the border. Hover lifts and scales slightly.

5. **Sonar rings** — expanding circular pulses behind the form card for atmosphere.

### Unique Ocean Assets (not shared with review screen)

The home screen has its own ocean environment creatures and floor elements, distinct from the review screen's jellyfish/anglerfish/turtle/kelp:

**Creatures:**
- **Whale** — blue-tinted (`bio-blue`), multi-part CSS (head, body, pectoral fin, fluke). Slow drifting animation. Positioned upper area.
- **Hammerhead shark** — cyan-tinted, with hammer head (eyes on stalks), dorsal fin, tail wag animation. Positioned mid-right area.

**Ocean floor:**
- **Sea fan coral** — pink/cyan branching structures (trunk + angled branches). Gentle swaying.
- **Tube worm clusters** — orange and mint, with blooming head animations.
- **Staghorn coral** — purple branching formations with tip highlights.

**Atmosphere:**
- **Marine snow** — slow-falling white particles (instead of review's plankton dots).
- **Deep haze** — blue-shifted gradient backdrop (instead of review's tri-color caustics).

All creatures must be built with the same level of CSS detail as the review screen's creatures: multi-part anatomy, radial gradients, layered box-shadows, idle animations with multiple keyframe states.

### Behavior

- Pressing Launch sends `POST /api/run` with `{ prompt, conf_threshold }` and transitions to `"running"`.
- Returning to home (from completion screen) resets: confidence to 0.70, prompt retained (so the user can iterate on the same dataset), all review state (kept/discarded counters, image list) cleared.

## Running Screen (`phase === "running"`)

### Layout

The form card transforms into a progress display (same card container, content changes). The ocean environment stays visible.

### Elements

1. **Step indicator** — current pipeline step in 9px JetBrains Mono uppercase: `DISCOVERING MODEL`, `DOWNLOADING MODEL`, `PROCESSING IMAGES`.

2. **Progress bar** — horizontal bar with the same bioluminescent glow as the confidence slider. Width maps to progress percentage. During discovery/download (indeterminate), a shimmer animation plays instead.

3. **Detail text** — contextual info below the bar:
   - Discovery: "Searching Roboflow for a matching model..."
   - Download: "Downloading model artifacts..."
   - Inference: "Processing image 3 of 25"

4. **Confidence display** — the chosen threshold shown in the corner, same style as the review HUD.

### Behavior

- On SSE `done` event → fetch images via existing `GET /api/images`, transition to `"review"`.
- On SSE error → show error in the existing error toast, transition back to `"home"`.

## Backend: New Endpoint

### `POST /api/run`

**Request body:**
```json
{
  "prompt": "basketball",
  "conf_threshold": 0.70
}
```

**Response:** SSE stream (`text/event-stream`). Each event is a JSON object:

```
data: {"step": "discovery", "message": "Finding model..."}

data: {"step": "download", "message": "Downloading model..."}

data: {"step": "inference", "message": "Processing images", "current": 3, "total": 25}

data: {"step": "done", "message": "Pipeline complete", "labeled": 18, "total": 25}
```

On error:
```
data: {"step": "error", "message": "Roboflow discovery failed: ..."}
```

**Implementation:** The endpoint resets server state (`_pipeline_results`, `_conf_threshold`, `_prompt`, `_config`), then calls `run_pipeline()` with a progress callback that yields SSE events. The progress callback is threaded through the pipeline via a new optional `on_progress` parameter on `run_pipeline()`.

The pipeline already logs step transitions (`logger.info`). The progress callback fires at the same points:
1. Before `discover_model()` → `discovery` event
2. Before `local_model.load()` → `download` event
3. Inside the per-image loop, before each image → `inference` event with current/total
4. After the loop completes → `done` event

### Pydantic models

```python
class RunRequest(BaseModel):
    prompt: str
    conf_threshold: float = 0.7
```

No response model needed — SSE streams raw JSON lines.

## Frontend: API Client Addition

```typescript
export function runPipeline(
  prompt: string,
  confThreshold: number,
  onEvent: (event: PipelineEvent) => void
): { cancel: () => void } {
  const controller = new AbortController();
  const url = `/api/run`;

  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, conf_threshold: confThreshold }),
    signal: controller.signal,
  }).then(async (res) => {
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    // Parse SSE stream, call onEvent for each parsed event
    // ...
  });

  return { cancel: () => controller.abort() };
}
```

## Frontend: New Components

1. **`HomeScreen.tsx`** — form card with prompt input, confidence slider, launch button.
2. **`RunProgress.tsx`** — progress display (step indicator, progress bar, detail text).
3. **`HomeOcean.tsx`** — the unique ocean assets (whale, shark, sea fans, tube worms, staghorn coral, marine snow). Rendered instead of `OceanEnvironment` when on the home/running screens.
4. **`home-ocean.css`** — CSS for the unique home screen creatures and coral.

## Frontend: App.tsx Changes

- Initial phase changes from `"loading"` to `"home"`.
- Remove the `useEffect` that fetches images on mount — images are fetched after the pipeline run completes.
- Add `"home"` and `"running"` rendering branches.
- Completion screen gets a "New Dataset" button/link that sets phase back to `"home"` and resets state.

## What Stays the Same

- `OceanEnvironment` component (review screen variant) — unchanged.
- `ImageCard`, `ActionButtons`, `KeyHints`, `HUD`, `ProgressBar`, `RestartModal`, `CompletionScreen` — unchanged (CompletionScreen gets one new button).
- All existing API endpoints — unchanged.
- `run_pipeline()` signature — extended with optional `on_progress` callback, fully backward compatible.
