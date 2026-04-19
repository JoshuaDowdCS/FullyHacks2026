# Detection labeling pipeline — design spec

**Date:** 2026-04-18  
**Status:** Written — pending human review of this file before implementation planning  
**Scope:** Batch tool: given a folder of images and a user prompt, discover (or fall back) a detection model, run it **locally**, optionally call a **Gemini HTTP endpoint**, and write **YOLO-format** label files under `dataset/labels/`. Upstream code guarantees this path is **detection-only** (no classification branch here).

---

## 1. Goals and non-goals

**Goals**

- Process every image in a configurable images directory (default `dataset/images/`).
- Select **one** Roboflow Universe–style object-detection model per batch using the **user prompt** and documented heuristics.
- **Download** that model’s weights/artifacts, **run inference locally** (avoid hosted Roboflow predict API failures), apply a **confidence threshold** to Roboflow outputs, and write **normalized YOLO** `.txt` files under `dataset/labels/` (basename aligned with each image).
- If Roboflow outputs no boxes **after** thresholding, call a **Gemini endpoint** (implemented elsewhere).
- If the Gemini response is **`OBJECT NOT FOUND`**, **delete** the image and any matching label file.
- Log enough per-image and batch-level detail for demos and debugging (including “show your own math”: explicit counts before/after threshold, chosen model id).

**Non-goals**

- Deciding classification vs detection (caller’s responsibility).
- Training or validating a full detector; hosting a long-lived inference service.
- Guaranteeing Gemini’s internal prompting (only the **HTTP contract** is specified here).

---

## 2. User-visible shape (Approach 1: single Python CLI)

One entrypoint, e.g. `python -m <package> ...`, that orchestrates discovery, download, local inference, optional Gemini calls, filesystem writes, and cleanup.

**Primary inputs**

- `--images-dir` (default: `dataset/images`)
- `--labels-dir` (default: `dataset/labels`)
- `--prompt` (**required**): used for Roboflow discovery and forwarded to Gemini when invoked
- `--conf-threshold` (default: `0.7`): applied **only** to **Roboflow** box scores
- Roboflow credentials via environment variables (exact names in implementation)
- Gemini base URL (and optional auth header) via environment variables

**Optional flags**

- `--refresh-model`: force re-download of the selected model even if cached artifacts exist at batch start.
- `--keep-model-cache`: skip **end-of-batch** deletion of the model artifacts for this run (debugging / intentional reuse).
- `--expand-query-with-gemini` (default: off): optionally call Gemini once per batch to rewrite the user prompt into a **shorter Roboflow search query**; if off, use a lightly normalized prompt string directly.

---

## 3. Label file format

Per image `images/<name>.<ext>` → `labels/<name>.txt`.

Each non-empty line:

```text
<class_id> <x_center> <y_center> <width> <height>
```

All five numbers are **normalized** to the image width and height (YOLO convention, values typically in `[0, 1]`). Multiple detections = multiple lines.

**Class IDs**

- **Roboflow path:** `class_id` comes from the **selected model’s** class index map (consistent for the batch because one model is chosen).
- **Gemini path:** endpoint returns consistent integer `class_id` values for that batch (typically `0..K-1`). Optional separate `classes.txt` for human-readable names is **out of scope** unless added later.

---

## 4. End-to-end pipeline

### 4.1 Batch setup

1. **Optional query expansion:** If `--expand-query-with-gemini`, call Gemini once to produce a search string; else use normalized `--prompt`.
2. **Roboflow discovery:** Query official Roboflow discovery/search APIs for **object detection** models relevant to the search string.
3. **Hard filters:** Must be object detection; must be **downloadable** and **runnable locally** with the project’s chosen stack (implementation picks the concrete mechanism, e.g. Universe → weights compatible with the local runner).
4. **Ranking (transparent heuristics):** Prefer stronger textual relevance (name/tags/description) to the query; break ties with secondary signals if available (popularity, recency).
5. **Select one winning model** for the entire batch (stable `class_id` across images).

**If no model passes hard filters / minimum relevance**

- Run **Gemini-only** for **every** image (skip Roboflow download/inference entirely for this batch). This does **not** imply deletions by itself.

### 4.2 Model cache lifecycle (approved policy A + cleanup)

- **Cache directory:** configurable (implementation default under e.g. `.cache/` or `~/.cache/...` — pick one and document it).
- **At batch start:** If artifacts for the chosen `(model id, version)` exist **and** `--refresh-model` is **not** set, **reuse** them. Otherwise **download** into the cache.
- **Inference:** Load locally and run object detection on each image (CPU/GPU configurable; default sensible for hackathon laptops).
- **At batch end:** In a `finally`-style path, **delete the artifacts for the model actually used in this run** unless `--keep-model-cache` is set.

### 4.3 Per-image processing (Roboflow available)

1. Run **local** inference.
2. Convert predictions to YOLO lines (normalized coordinates).
3. **Filter** detections: keep only boxes with **confidence ≥ `--conf-threshold`**.
4. If **filtered set non-empty:** write `labels/<stem>.txt` with **only** filtered lines. **Do not** call Gemini.
5. If **filtered set empty:** call **Gemini** for this image (same `--prompt` and image payload per contract below).

### 4.4 Per-image processing (Gemini-only batch)

- For each image, call **Gemini** directly; then apply **§5 Gemini outcomes**.

### 4.5 Gemini HTTP contract

**Request (minimum):** image bytes (or base64) + `prompt` + optional filename / dimensions for logging.

**Response (two logical outcomes only — agreed contract):**

1. **Detections:** a list of one or more **valid YOLO lines** (strings). The CLI writes **all** lines **with no further confidence filtering**.
2. **`OBJECT NOT FOUND`:** explicit sentinel (exact spelling) meaning the target concept is absent → **§6 deletion**.

If the body is malformed, missing, or neither parseable detections nor the sentinel, treat as **§7.1 Gemini transport/contract error** (non-destructive).

---

## 5. Filesystem side effects

| Event | `images/` | `labels/` |
|------|-----------|-----------|
| Roboflow (or Gemini) produced ≥1 line | unchanged | write/update `<stem>.txt` |
| Gemini returns `OBJECT NOT FOUND` | **delete** image | **delete** `<stem>.txt` if it exists |
| Error paths (§7) | unchanged | no write / no delete |

Ensure `labels/` exists before writing.

---

## 6. Deletion semantics (authoritative)

- **Only** trigger image+label deletion when Gemini returns **`OBJECT NOT FOUND`** (explicit negative).
- **Do not** delete on “zero boxes” from Gemini unless that zero-box case is represented by the sentinel (per contract, it always is).
- On deletion, remove **`dataset/images/<file>`** and **`dataset/labels/<stem>.txt`** if present (keep stems consistent).

---

## 7. Error handling

### 7.1 Non-destructive errors (never delete image)

- **Roboflow discovery hard failure** (auth, total API outage): if Gemini is configured, fall back to **Gemini-only** for the batch; if Gemini is **not** configured, **abort with a clear error** before mutating images.
- **Model download failure**, **corrupt artifact**, **local load failure**, **inference exception** for a single image: log, **skip** that image (no label write), continue batch.
- **Gemini transport/contract errors** (timeout, 5xx, malformed): log, **skip** label write, continue.

### 7.2 Cleanup

- Model artifact deletion runs **after** the batch completes (or process exits), per §4.2, unless `--keep-model-cache`.

---

## 8. Logging

**Per image:** route taken; Roboflow model id (if any); raw detection count; count after threshold; Gemini outcome (lines count vs `OBJECT NOT FOUND` vs error); final action (wrote / deleted / skipped).

**Batch summary:** labeled count, deleted count, skipped error count; whether the batch was **Roboflow+local**, **Gemini-only (no model)**, or **Gemini-only (discovery failed)**.

---

## 9. Testing plan

- **Unit:** YOLO line validation, basename mapping, Roboflow confidence filtering (including multiple boxes mixed above/below threshold), routing on `OBJECT NOT FOUND` vs lines.
- **Mocked HTTP:** discovery returns ranked list; download stub; local inference mocked at the adapter boundary if needed; Gemini returns lines vs sentinel vs garbage.
- **Temp directory integration:** writes labels, deletes **only** on sentinel, preserves images on errors.

---

## 10. Judge-facing “what we built” notes (aligned with `what-actually-wins.md`)

- **Own logic:** discovery **ranking and hard filters**, **confidence gating**, **route state machine**, and **deterministic filesystem rules** are all specified and should be implemented as readable code (not buried in prompts).
- **Beyond LLM:** **local CV inference** + optional LLM for **query expansion** and **fallback labeling** — multi-system pipeline.
- **Rich input:** image folders (and future UI can wrap the same CLI).
- **Visible pipeline:** logs and batch summary should be demo-friendly; optional later: a small progress UI — out of scope for this spec.

---

## 11. Self-review checklist (completed)

- **Placeholders:** None intentional; env var **names** left to implementation (acceptable).
- **Consistency:** Local Roboflow inference matches “avoid hosted predict errors”; deletion only on `OBJECT NOT FOUND`; threshold applies only to Roboflow-filtered path before Gemini.
- **Scope:** Single CLI batch tool; teammate owns Gemini service behavior inside the stated contract.
- **Ambiguity resolved:** “Classification finished” clarified as **end of labeling batch** for model cleanup; optional `--keep-model-cache` preserves weights across runs when needed.
