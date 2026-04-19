# Review UI Design Spec

Post-pipeline image review interface for keeping or discarding detection results before Roboflow upload.

## Goals

- Let the user quickly triage labeled images (keep or discard) after the detection pipeline finishes
- Allow restarting the full pipeline with confidence threshold increased by +0.05
- Provide a deep-ocean bioluminescent theme for FullyHacks 2026
- Make the pipeline's intermediate work visible to judges (bounding boxes, class labels, confidence)

## Non-Goals

- Editing bounding boxes or labels manually
- Running the pipeline from the UI (it's triggered separately; the UI is the review step)
- User authentication or multi-user support

## Architecture

Two processes, one project:

```
FullyHacks2026/
├── detection_pipeline/        # existing Python package (unchanged)
├── api/                       # new — FastAPI server
│   ├── main.py                # endpoints + app setup
│   └── models.py              # Pydantic request/response schemas
├── ui/                        # new — React (Vite) + Tailwind
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   └── ...
│   ├── vite.config.ts         # proxy /api → FastAPI
│   ├── tailwind.config.ts
│   └── package.json
├── dataset/
│   ├── images/
│   └── labels/
├── start.sh                   # launches both processes
└── pyproject.toml             # add fastapi, uvicorn deps
```

**How it runs:**
- `uvicorn api.main:app` on port 8000 — serves API + static images from `dataset/images/`
- `npm run dev` in `ui/` on port 5173 — Vite proxies `/api/*` to FastAPI
- `start.sh` launches both

**Key constraint:** The FastAPI server imports `detection_pipeline` directly — no subprocess calls, no logic duplication. Keep/discard/restart all go through the existing package's functions.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/images` | List all images with their label data (bounding boxes, classes) |
| `GET` | `/api/images/{filename}` | Serve a single image file |
| `GET` | `/api/stats` | Current batch stats: total, labeled, unlabeled, confidence threshold |
| `POST` | `/api/images/{filename}/discard` | Delete the image + its label file from disk |
| `POST` | `/api/restart` | Re-run pipeline with `conf_threshold += 0.05`, return new stats |
| `POST` | `/api/upload` | Trigger Roboflow upload of all remaining images+labels |

### `GET /api/images` response

```json
{
  "images": [
    {
      "filename": "game001.jpg",
      "width": 1920,
      "height": 1080,
      "labels": [
        {
          "class_id": 0,
          "class_name": "basketball",
          "x_center": 0.52,
          "y_center": 0.41,
          "width": 0.15,
          "height": 0.20
        }
      ]
    }
  ],
  "conf_threshold": 0.70,
  "total": 402
}
```

Label data uses the existing YOLO normalized format. The frontend converts to pixel coordinates for bounding box rendering using the image's actual dimensions.

### `POST /api/images/{filename}/discard`

Deletes both the image file and its corresponding label file from disk. Returns `204 No Content`.

### `POST /api/restart`

Re-runs the detection pipeline with `conf_threshold += 0.05`. The server tracks the current threshold (initialized from `PipelineConfig.conf_threshold`, incremented on each restart). This is a full re-run — all existing labels are replaced. The endpoint blocks until the pipeline completes, then returns the new stats including the updated threshold. The frontend should show a loading state during this.

### `POST /api/upload`

Triggers Roboflow upload of all remaining image+label pairs. Returns upload stats.

## UI Design

### Interaction Model

Tinder-style: one image at a time, centered on screen. Three actions:

- **Keep** (right arrow / click) — advance to next image, image stays on disk
- **Discard** (left arrow / click) — delete image + label, advance to next
- **Restart** (R key / click) — re-run entire pipeline at +0.05 confidence, reset review

### Screen Layout

**Top HUD bar:**
- Left: live counters — remaining (white), kept (mint), discarded (pink)
- Right: current confidence threshold, displayed prominently (Syne font, glowing cyan)
- Font: JetBrains Mono for all data/stats

**Progress bar:**
- Thin line below HUD, cyan-to-mint gradient fill
- Glowing dot at the leading edge
- Text: "155 of 402 reviewed"

**Center: image card:**
- Centered, 480-520px wide, 16:11 aspect ratio
- Rounded corners, subtle glassmorphic border (1px cyan at 12% opacity)
- Bounding boxes drawn as overlays: cyan borders with mint corner accents
- Class label tag above each box (cyan background, dark text, JetBrains Mono uppercase)
- Below card: filename, detection count, image dimensions

**Bottom: sea creature action buttons:**
- **Discard = Anglerfish** (pink `#FF4D8E`) — glowing lure, jagged teeth, menacing. Idle sway animation.
- **Restart = Nautilus** (blue `#3B8BF5`) — spiral shell with concentric rings (cycle-back metaphor), small tentacles, bobbing motion.
- **Keep = Sea Turtle** (mint `#2AFFA0`) — hexagonal scute shell pattern, stroking flippers, friendly. Gliding animation.
- All creatures hover-scale to 1.12x with slight upward lift
- Labels below each: "DISCARD", "+0.05", "KEEP" in JetBrains Mono

**Keyboard hints:**
- Bottom of screen, very dim: `← discard` `R restart` `→ keep`

**Upload state:**
- When all images are reviewed, the card area shows a completion screen
- Upload button becomes active (styled as a glowing portal or surface-light)

### Deep Ocean Theme

**Aesthetic direction:** Deep-sea bioluminescence — the interface should feel like operating a submersible's classification terminal at the bottom of the ocean. Not just "dark with cyan" but genuinely atmospheric with visible life.

**Color palette:**
| Token | Hex | Use |
|-------|-----|-----|
| `--abyss` | `#020810` | Page background base |
| `--deep` | `#061222` | Card backgrounds, overlays |
| `--trench` | `#0A1A30` | Secondary surfaces |
| `--current` | `#0F2440` | Borders, tracks |
| `--bio-cyan` | `#4CE0D2` | Primary accent, bounding boxes, progress |
| `--bio-mint` | `#2AFFA0` | Keep/positive, secondary accent |
| `--bio-pink` | `#FF4D8E` | Discard/danger |
| `--bio-blue` | `#3B8BF5` | Restart/neutral |
| `--bio-purple` | `#A855F7` | Jellyfish, decorative coral |
| `--bio-orange` | `#FF6B35` | Anemones, accent creatures |
| `--text-primary` | `#C8DDE8` | Body text |
| `--text-dim` | `#4A6A82` | Secondary text, hints |

**Typography:**
| Font | Weight | Use |
|------|--------|-----|
| Syne | 700-800 | Display: confidence value, completion headers |
| Outfit | 300-700 | Body: labels, descriptions |
| JetBrains Mono | 400-600 | Data: stats, filenames, keyboard hints |

**Ocean life elements (ambient, always present):**
- **Jellyfish** — 2-3 translucent jellyfish floating near the card area, pulsing bodies with trailing tentacles that sway. Purple, cyan, and orange variants at different sizes for depth.
- **Bubbles** — rising from the ocean floor, transparent with refraction borders
- **Light rays** — faint shafts from above, shimmering diagonally
- **Bioluminescent plankton** — scattered glowing dots pulsing at varied rhythms
- **Coral reef floor** — bottom edge of screen. Kelp strands swaying, brain coral lumps, sea fan corals, anemone clusters with waving tentacles
- **Fish school** — small silhouette fish swimming across occasionally
- **Caustic light** — subtle radial gradients drifting slowly, simulating underwater light refraction

**Implementation note:** For the real build, these should be richer than the mockup — more detail in the creatures, more layered depth, potentially canvas-rendered particles for plankton/bubbles for better performance with higher density. The mockup at `.superpowers/brainstorm/59737-1776574377/content/review-screen-v4.html` captures the vibe but the implementation should exceed it.

**Animations:**
| Element | Animation | Duration |
|---------|-----------|----------|
| Jellyfish body | Pulse (scaleX/scaleY) | 3s |
| Jellyfish tentacles | Sway (rotate) | 4s |
| Jellyfish position | Float (translate + rotate) | 15-25s |
| Anglerfish lure | Glow pulse + swing | 1.5s / 2.5s |
| Nautilus | Bob + slight rotate | 4s |
| Sea turtle flippers | Stroke (rotate) | 3s |
| Kelp | Sway (rotate + skew) | 7-10s |
| Anemone | Pulse (scaleX) | 4s |
| Bubbles | Rise (translateY + wobble) | 12-20s |
| Plankton | Glow (opacity + scale) | 3-7s |
| Light rays | Shimmer (skewX + opacity) | 8s |
| Caustics | Drift (translate + scale) | 15s |
| Card swipe | Exit left/right with rotation | 0.3s |
| Card enter | Fade in + scale from 0.95 | 0.3s |

### Swipe Animation

When the user keeps or discards:
1. Card animates off-screen in the chosen direction (left for discard, right for keep) with slight rotation and opacity fade
2. A brief color flash at the edges — mint glow for keep, pink glow for discard
3. Next card enters from center (scale from 0.95 to 1, opacity 0 to 1)
4. Counters update with a number tick animation

### Restart Flow

When the user clicks the nautilus / presses R:
1. Confirmation prompt (modal styled as a bioluminescent portal): "Re-run pipeline at 0.75 confidence? This replaces all current labels."
2. If confirmed: full-screen loading state — the ocean environment stays, the card area shows a pulsing nautilus spiral with "Re-scanning at 0.75..." text
3. Pipeline runs server-side (POST /api/restart)
4. On completion: review resets to image 1, counters reset, threshold updates

### Completion State

When all images have been reviewed:
- Card area shows completion stats: total kept, total discarded
- Upload button appears as a prominent glowing element
- Option to restart at higher confidence if desired

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + uvicorn |
| Frontend | React 18 + TypeScript |
| Build | Vite |
| Styling | Tailwind CSS |
| Components | shadcn/ui (Radix primitives) |
| Animation | Framer Motion (card transitions, number ticks, entrance animations) |
| Icons | Lucide React |
| Image overlay | HTML Canvas or positioned divs for bounding boxes |

## Data Flow

```
Pipeline finishes
    ↓
User opens UI → GET /api/images (loads all image metadata + labels)
    ↓
Review loop:
    Show image N with bounding box overlay
    ↓
    User keeps → advance to N+1, update local state
    User discards → POST /api/images/{filename}/discard → advance to N+1
    User restarts → POST /api/restart → reload all images, reset to image 1
    ↓
All reviewed → POST /api/upload → done
```

**State management:** React state holds the image list, current index, and counters. No external state management needed — the list is loaded once and mutated locally (discards also hit the API for file deletion).

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Image file missing (deleted externally) | Skip to next, show brief toast |
| Discard fails (file already deleted) | Treat as success, advance |
| Restart fails (pipeline error) | Show error in modal, keep current state |
| Upload fails | Show error with retry button |
| No images in dataset | Show empty state: "No images to review. Run the pipeline first." |
| API unreachable | Show connection error overlay with retry |

## Testing Plan

**Backend:**
- Unit tests for each endpoint (mock filesystem)
- Integration test: discard actually removes files
- Integration test: restart calls pipeline with incremented threshold

**Frontend:**
- Component tests for image card with bounding box rendering
- Interaction tests for keep/discard/restart flows
- Visual regression optional — theme is the distinctive element

## Judge-Facing Notes

This UI makes the pipeline visible:
- Bounding boxes show what the model detected and where
- Class labels show what it classified
- Confidence threshold is always visible — judges can see the gating logic
- Restart at +0.05 demonstrates iterative refinement (the user can tune the pipeline)
- The keep/discard flow shows human-in-the-loop quality control before upload
- The ocean creatures as action buttons are the memorable visual element
