"""Topic-agnostic image-dataset gatherer.

Pass any topic (e.g. "basketball", "golden retriever", "art deco building",
"sunset over ocean"). A single Gemini call bootstraps the topic into a spec
(search queries, CLIP scene distractors, matching COCO class for YOLO, and a
VLM-friendly object description), then the pipeline runs:

    crawl -> dedup -> CLIP -> [YOLO -> VLM cascade] -> finalize

The top-level out_dir is the working area; anything surviving every active
filter ends up in <out_dir>/review/keep/. Everything else is sorted into
named review subfolders (maybe_keep, maybe_remove, yolo_uncertain,
yolo_no_object, vlm_rejected, vlm_uncertain, ...) so nothing is lost.

Setup:
    python3 -m pip install icrawler open_clip_torch torch
    python3 -m pip install ultralytics google-genai   # YOLO + Gemini
    export GEMINI_API_KEY=...                         # for bootstrap + VLM
    # The 'openimages' engine uses only the Python stdlib — no extra deps.

Usage:
    # Bing only (fast, small):
    python3 webscraper.py basketball --engines bing --per-query 100 \\
        --require-yolo --vlm-review

    # All sources (Bing + Baidu + Open Images Dataset):
    python3 webscraper.py basketball --engines bing baidu openimages \\
        --per-query 100 --openimages-max 5000 --require-yolo --vlm-review

    # Skip the LLM bootstrap (use hardcoded PRESETS):
    python3 webscraper.py basketball --no-bootstrap --require-yolo --vlm-review

    # Force a fresh spec (topic drifted, or you edited the prompt):
    python3 webscraper.py basketball --refresh-spec ...
"""

import argparse
import hashlib
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from icrawler import ImageDownloader
from icrawler.builtin import BaiduImageCrawler, BingImageCrawler, GoogleImageCrawler


class FastDownloader(ImageDownloader):
    """Trim retry count so one dead host doesn't stall a job, but keep the
    HTTP timeout long enough for real image transfers. Overriding signature
    defaults is NOT enough — icrawler's worker_exec passes these explicitly,
    so we ignore the incoming values and hardcode."""

    def download(self, task, default_ext, timeout=5, max_retry=3, overwrite=False, **kwargs):
        return super().download(
            task, default_ext,
            timeout=5, max_retry=1, overwrite=overwrite, **kwargs,
        )


ENGINES = {
    "google": GoogleImageCrawler,
    "bing": BingImageCrawler,
    "baidu": BaiduImageCrawler,
}

NEGATIVE_KEYWORDS = (
    "-cartoon -clipart -illustration -drawing -vector -painting -render -3d -sketch -logo"
)


def _build_basketball_queries() -> list[str]:
    base = [
        "basketball game photo",
        "nba game action shot",
        "ncaa basketball game",
        "wnba game action",
        "high school basketball game",
        "pickup basketball game",
        "basketball street game",
        "kid playing basketball",
        "person holding a basketball",
        "spalding basketball close up",
        "wilson basketball close up",
        "leather basketball photo",
        "rubber basketball photo",
        "outdoor basketball on court",
        "basketball on hardwood floor",
        "basketball going through hoop",
        "basketball bouncing on court",
        "worn basketball on pavement",
        "new basketball in store",
        "basketball in player's hands",
    ]
    actions = [
        "dribbling", "shooting", "dunking", "passing",
        "rebounding", "blocking", "defending", "layup",
    ]
    subjects = ["player", "kid", "athlete", "team", "woman", "man"]
    for a in actions:
        for s in subjects:
            base.append(f"{s} {a} basketball")
    for setting in ["outdoor court", "indoor gym", "playground", "school gym", "park"]:
        base.append(f"basketball game {setting}")
        base.append(f"pickup basketball {setting}")
    return sorted(set(base))


PRESETS: dict[str, list[str] | str] = {
    "basketball": _build_basketball_queries(),
    "basketballs": "basketball",
}

GENERIC_TEMPLATES = [
    "{q} photo",
    "person with {q}",
    "playing with {q}",
    "{q} in real life",
    "{q} close up photo",
    "{q} outdoors",
    "{q} indoors",
]

PHOTO_PROMPTS = [
    "a photograph of {q}",
    "a real photo of {q}",
    "a candid photo of {q}",
]

NONPHOTO_PROMPTS = [
    "a cartoon of {q}",
    "an illustration of {q}",
    "a drawing of {q}",
    "a painting of {q}",
    "clipart of {q}",
    "a 3d render of {q}",
    "a sketch of {q}",
    "a vector graphic of {q}",
    "a logo of {q}",
]

# Distractor photos: real photos of *other* subjects. CLIP ignores negation
# ("a photo that does not contain X" scores high for X), so we use positive
# photo prompts of unrelated/similar subjects and require the target to beat
# them. Keep them broad-but-plausible — too specific and it's fragile, too
# generic ("a photograph") and it always wins.
DISTRACTOR_PROMPTS = [
    "a photograph of a soccer ball",
    "a photograph of a volleyball",
    "a photograph of a football",
    "a photograph of a baseball",
    "a photograph of a tennis ball",
    "a photograph of a bowling ball",
    "a photograph of a person",
    "a photograph of a car",
    "a photograph of food",
    "a photograph of a building",
    "a photograph of a tree",
    "a photograph of an empty room",
]

# Topic-specific SCENE distractors: photos that match the topic's setting but
# don't actually show the target object. CLIP thinks "basketball" includes
# jerseys/arenas/players; these prompts split those off so a player-without-
# ball shot loses to "a photograph of a basketball jersey" instead of winning
# "a photograph of a basketball".
TOPIC_SCENE_DISTRACTORS: dict[str, list[str]] = {
    "basketball": [
        "a photograph of a basketball court without a ball",
        "a photograph of a basketball jersey",
        "a photograph of basketball sneakers",
        "a photograph of a basketball hoop without a ball",
        "a photograph of basketball fans in a crowd",
        "a photograph of a basketball scoreboard",
        "a photograph of a basketball player standing",
        "a photograph of a basketball arena",
        "a photograph of a basketball coach",
    ],
}
TOPIC_SCENE_DISTRACTORS["basketballs"] = TOPIC_SCENE_DISTRACTORS["basketball"]


# The 80 COCO class names used by standard YOLO weights. The bootstrap LLM
# must pick from this exact list or return null.
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana",
    "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table",
    "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]

TopicType = Literal["object", "scene", "style", "abstract", "person"]


@dataclass
class TopicSpec:
    """Topic-agnostic pipeline config generated by bootstrap_topic(). Any
    field can be overridden by a CLI arg; otherwise these values drive the
    pipeline. The type drives routing (object -> full stack, scene/style ->
    skip YOLO, abstract -> VLM-only, person -> warn)."""
    topic: str
    type: TopicType
    queries: list[str]
    scene_distractors: list[str]
    yolo_class: str | None          # None if no COCO match
    vlm_object: str                 # short noun phrase, e.g. "a basketball"
    # Photo prompts that score high only when the target is the MAIN subject.
    # These stack on top of the generic PHOTO_PROMPTS so a ball-centered action
    # shot beats same-scene distractors like "a photograph of a jersey".
    photo_prompts: list[str] = field(default_factory=list)
    open_images_class: str | None = None  # Open Images V7 class name, e.g. "Basketball"
    notes: str = ""                 # freeform LLM reasoning, for debugging

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "TopicSpec":
        data = json.loads(text)
        return cls(**data)


BOOTSTRAP_PROMPT = """You are designing an image-dataset gathering pipeline for a user-supplied topic.

Return ONLY a single JSON object (no prose, no markdown fences) with these fields:

{{
  "type": "object" | "scene" | "style" | "abstract" | "person",
  "queries": [30-60 diverse search-engine queries, each a complete phrase,
              that would surface high-quality real-world photos of the topic.
              Cover different actions, settings, subjects, perspectives,
              close-ups, and contexts. Avoid near-duplicates.],
  "photo_prompts": [4-6 short CLIP-style captions in which the TARGET IS THE
                    MAIN SUBJECT of the photo (prominent, unambiguous, not
                    just present in the background). Use phrasings like
                    "a close-up photograph of {{topic}}", "a photograph of
                    {{topic}} as the main subject", "a photograph featuring
                    {{topic}} prominently", "a photograph centered on
                    {{topic}}". These score an image UP — keep them specific
                    so they only fire on genuinely target-centric photos.
                    Include the literal topic word(s) in each caption.],
  "scene_distractors": [5-10 short photo captions describing RELATED-BUT-WRONG
                        content that CLIP should DOWN-WEIGHT. CRITICAL RULE:
                        each distractor must describe something that WOULD
                        NOT TYPICALLY CO-OCCUR with the target in real photos.
                        BAD distractor for "basketball": "a photograph of a
                        basketball jersey" (jerseys appear in almost every
                        basketball action photo, so this misfires on good
                        images). GOOD distractors for "basketball": "a
                        basketball trophy", "a basketball scoreboard with no
                        game in progress", "a basketball ticket stub", "a
                        basketball-themed birthday cake". Think: what looks
                        like the topic's world but happens ON ITS OWN without
                        the actual target object? Do NOT use negation words
                        like "without" or "no" — CLIP ignores them.],
  "yolo_class": one of the 80 COCO class names below that best matches the
                topic, or null if no reasonable match. Do NOT invent classes.
  "vlm_object": short noun phrase describing the topic as a VLM would see it,
                e.g. "a basketball", "a sunset over water", "a person wearing
                art deco clothing". Keep under 8 words.,
  "open_images_class": name of the best-matching Open Images V7 boxable class
                (there are ~600; use TitleCase exactly as Open Images writes
                them, e.g. "Basketball", "Golden retriever", "Skateboard",
                "Vintage car"), or null if no reasonable match. If unsure,
                prefer null over guessing — we validate against the real list.,
  "notes": one short sentence explaining your type choice and any edge cases.
}}

Topic type rules:
- "object": a discrete, photographable thing (basketball, golden retriever, vintage car)
- "scene": a setting or landscape (sunset, Tokyo skyline, forest clearing)
- "style": a visual aesthetic (art deco, film noir, watercolor painting style)
- "abstract": a non-visual concept (happiness, freedom, productivity)
- "person": a specific named individual (LeBron James, Taylor Swift)

Available COCO classes (pick EXACTLY one by name, or null):
{coco_classes}

Topic: "{topic}"
"""


def bootstrap_topic(topic: str, model: str = "gemini-2.5-flash") -> TopicSpec:
    """One Gemini call that returns a complete TopicSpec for any topic.
    Costs roughly $0.001; cached to .topic_spec.json after the first call."""
    from google import genai

    client = genai.Client()  # reads GEMINI_API_KEY / GOOGLE_API_KEY
    prompt = BOOTSTRAP_PROMPT.format(
        topic=topic,
        coco_classes=", ".join(sorted(COCO_CLASSES)),
    )
    resp = client.models.generate_content(model=model, contents=[prompt])
    raw = (resp.text or "").strip()
    # Strip optional markdown fences
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()
    data = json.loads(raw)
    # Normalize / validate
    tp = data.get("type", "object")
    if tp not in ("object", "scene", "style", "abstract", "person"):
        tp = "object"
    yc = data.get("yolo_class")
    if yc is not None and yc not in COCO_CLASSES:
        yc = None
    oic = data.get("open_images_class")
    if isinstance(oic, str):
        oic = oic.strip() or None
    else:
        oic = None
    return TopicSpec(
        topic=topic,
        type=tp,
        queries=list(data.get("queries", []))[:80] or [topic],
        photo_prompts=[p for p in (data.get("photo_prompts") or []) if isinstance(p, str)][:8],
        scene_distractors=list(data.get("scene_distractors", []))[:12],
        yolo_class=yc,
        vlm_object=(data.get("vlm_object") or f"a {topic}").strip(),
        open_images_class=oic,
        notes=(data.get("notes") or "").strip(),
    )


def load_or_bootstrap_spec(
    out_dir: Path,
    topic: str,
    model: str = "gemini-2.5-flash",
    refresh: bool = False,
) -> TopicSpec:
    """Load cached spec from out_dir/.topic_spec.json or call the LLM and
    save. Pass refresh=True to force a new LLM call."""
    cache = out_dir / ".topic_spec.json"
    if cache.exists() and not refresh:
        try:
            spec = TopicSpec.from_json(cache.read_text())
            if spec.topic.lower().strip() == topic.lower().strip():
                print(f"Loaded cached spec from {cache} (type={spec.type}, "
                      f"{len(spec.queries)} queries).")
                return spec
        except Exception as exc:
            print(f"Couldn't read cached spec ({exc}); regenerating.")
    print(f"Bootstrapping topic spec via {model}...")
    spec = bootstrap_topic(topic, model=model)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(spec.to_json() + "\n")
    # Validate open_images_class against the real OID class list, since the
    # LLM can return plausible-looking-but-wrong names ("Basketballs" plural,
    # "basketball" lowercase, "Basketball ball" invented). Any mismatch gets
    # nulled out so the openimages engine silently skips instead of erroring
    # at crawl time. Only fetches the tiny class-descriptions CSV (50KB).
    if spec.open_images_class:
        try:
            if oid_class_to_mid(spec.open_images_class) is None:
                print(
                    f"  spec.open_images_class={spec.open_images_class!r} not in "
                    f"Open Images V7 class list; clearing it. (Edit "
                    f"{cache} manually if you know the right name.)"
                )
                spec.open_images_class = None
                cache.write_text(spec.to_json() + "\n")
        except Exception as exc:
            print(f"  couldn't validate open_images_class ({exc}); leaving as-is.")

    print(f"  type={spec.type} | yolo_class={spec.yolo_class} | "
          f"vlm_object={spec.vlm_object!r}")
    print(f"  open_images_class={spec.open_images_class!r}")
    print(f"  {len(spec.queries)} queries, {len(spec.scene_distractors)} scene distractors.")
    if spec.notes:
        print(f"  notes: {spec.notes}")
    return spec


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "query"


def resolve_queries(
    topic: str,
    override: list[str] | None,
    expand: bool,
    spec: TopicSpec | None = None,
) -> list[str]:
    """Precedence: CLI --queries > bootstrap spec.queries > PRESETS > GENERIC_TEMPLATES."""
    if override:
        return override
    if not expand:
        return [topic]
    if spec is not None and spec.queries:
        return spec.queries
    key = topic.lower().strip()
    preset = PRESETS.get(key)
    if isinstance(preset, str):
        preset = PRESETS.get(preset)
    if isinstance(preset, list):
        return preset
    return [t.format(q=topic) for t in GENERIC_TEMPLATES]


def dedupe_by_hash(out_dir: Path) -> int:
    """Remove byte-identical duplicates from the top-level (new crawl output).
    Also seeds the 'seen' set from already-categorized review buckets so a
    re-crawl doesn't pull in copies of images you've already sorted.
    Returns number removed."""
    seen: dict[str, Path] = {}
    removed = 0
    review_root = out_dir / "review"
    if review_root.is_dir():
        for seed_dir in review_root.iterdir():
            if not seed_dir.is_dir():
                continue
            for path in seed_dir.iterdir():
                if not path.is_file() or path.name.startswith("."):
                    continue
                try:
                    h = hashlib.md5(path.read_bytes()).hexdigest()
                except OSError:
                    continue
                seen.setdefault(h, path)
    for path in sorted(out_dir.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            h = hashlib.md5(path.read_bytes()).hexdigest()
        except OSError:
            continue
        if h in seen:
            path.unlink()
            removed += 1
        else:
            seen[h] = path
    return removed


def classify_and_prune(
    out_dir: Path,
    query: str,
    batch_size: int = 32,
    review_margin: float = 0.02,
    scene_distractors: list[str] | None = None,
    extra_photo_prompts: list[str] | None = None,
) -> tuple[int, int, int]:
    """Score each image's CLIP similarity to photo/nonphoto/distractor prompts.
    margin = best_photo_score - best_reject_score.
      margin >=  review_margin  -> keep in place
      margin <= -review_margin  -> move to review/clip_rejected/ (no hard delete)
      otherwise                 -> review/maybe_keep/ or review/maybe_remove/
    If scene_distractors is provided (e.g. from the bootstrap spec) it's used
    in place of the hardcoded TOPIC_SCENE_DISTRACTORS lookup.
    Returns (kept, rejected, uncertain)."""
    import open_clip
    import torch
    from PIL import Image

    if torch.cuda.is_available():
        device = "cuda"
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    print(f"Loading CLIP on {device} (first run downloads ~150MB)...")
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="openai"
    )
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    model.eval().to(device)

    photo_text = [p.format(q=query) for p in PHOTO_PROMPTS]
    if extra_photo_prompts:
        # Spec-generated prompts typically embed the topic literally so we
        # don't .format() them. Skip anything empty or obviously malformed.
        photo_text += [p for p in extra_photo_prompts if isinstance(p, str) and p.strip()]
    nonphoto_text = [p.format(q=query) for p in NONPHOTO_PROMPTS]
    distractor_text = list(DISTRACTOR_PROMPTS)
    if scene_distractors:
        distractor_text += scene_distractors
    else:
        distractor_text += TOPIC_SCENE_DISTRACTORS.get(query.lower().strip(), [])
    n_photo = len(photo_text)
    n_nonphoto = len(nonphoto_text)

    with torch.no_grad():
        tokens = tokenizer(photo_text + nonphoto_text + distractor_text).to(device)
        text_feats = model.encode_text(tokens)
        text_feats = text_feats / text_feats.norm(dim=-1, keepdim=True)

    maybe_keep_dir = out_dir / "review" / "maybe_keep"
    maybe_remove_dir = out_dir / "review" / "maybe_remove"
    rejected_dir = out_dir / "review" / "clip_rejected"
    maybe_keep_dir.mkdir(parents=True, exist_ok=True)
    maybe_remove_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in sorted(out_dir.iterdir())
        if p.is_file() and not p.name.startswith(".")
    ]
    total = len(files)
    kept = rejected = maybe_keep = maybe_remove = 0
    print(f"Scoring {total} images in batches of {batch_size} (review margin ±{review_margin:.3f})...")

    def _review_name(margin: float, name: str) -> str:
        # Prefix with abs(margin) so files sort from most-confident to least
        # within each review bucket. Sign is implied by the bucket.
        return f"m{abs(margin):.4f}_{name}"

    for start in range(0, total, batch_size):
        chunk = files[start:start + batch_size]
        tensors = []
        valid = []
        for path in chunk:
            try:
                img = Image.open(path).convert("RGB")
                tensors.append(preprocess(img))
                valid.append(path)
            except Exception:
                # Image is corrupt/unreadable — safe to hard-delete.
                path.unlink(missing_ok=True)
                rejected += 1
        if not tensors:
            continue
        with torch.no_grad():
            batch = torch.stack(tensors).to(device)
            feats = model.encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            sims = (feats @ text_feats.T).cpu()
        for path, row in zip(valid, sims):
            photo_score = row[:n_photo].max().item()
            nonphoto_score = row[n_photo:n_photo + n_nonphoto].max().item()
            distractor_score = row[n_photo + n_nonphoto:].max().item()
            reject = max(nonphoto_score, distractor_score)
            margin = photo_score - reject
            if margin >= review_margin:
                kept += 1
            elif margin <= -review_margin:
                # Don't permanently delete — CLIP false-negatives are the
                # single biggest risk in this pipeline. Move to a review
                # bucket so a downstream filter (or the user) can rescue.
                path.rename(rejected_dir / _review_name(margin, path.name))
                rejected += 1
            elif margin >= 0:
                path.rename(maybe_keep_dir / _review_name(margin, path.name))
                maybe_keep += 1
            else:
                path.rename(maybe_remove_dir / _review_name(margin, path.name))
                maybe_remove += 1
        done = min(start + batch_size, total)
        print(
            f"  {done}/{total} (kept={kept} maybe_keep={maybe_keep} "
            f"maybe_remove={maybe_remove} rejected={rejected})"
        )
    uncertain = maybe_keep + maybe_remove
    return kept, rejected, uncertain


def require_object_detection(
    out_dir: Path,
    object_query: str,
    confidence: float = 0.15,
    edge_fraction: float = 0.005,
) -> tuple[int, int, int]:
    """Strict pass: use OWL-ViT (zero-shot open-vocabulary detector) to
    require a fully-in-frame bounding box for `object_query`.
      - at least one detection score >= confidence whose box is NOT touching
        any image edge  -> keep
      - detection(s) found but all are edge-touching  -> review/ball_cropped/
      - no detection above confidence                 -> review/no_object_detected/
    A box is considered "edge-touching" if any of its sides lies within
    `edge_fraction` of image width/height (min 2px) from the border.
    Returns (kept, cropped, no_object)."""
    from PIL import Image
    from transformers import pipeline

    print(f"Loading OWL-ViT detector (first run downloads ~600MB) — query {object_query!r}")
    detector = pipeline(
        model="google/owlvit-base-patch32",
        task="zero-shot-object-detection",
    )

    no_obj_dir = out_dir / "review" / "no_object_detected"
    cropped_dir = out_dir / "review" / "ball_cropped"
    no_obj_dir.mkdir(parents=True, exist_ok=True)
    cropped_dir.mkdir(parents=True, exist_ok=True)

    files = [p for p in sorted(out_dir.iterdir()) if p.is_file() and not p.name.startswith(".")]
    total = len(files)
    kept = cropped = no_obj = 0
    print(f"Detecting {object_query!r} in {total} images (conf >= {confidence}, edge>={edge_fraction:.3f})...")

    for i, path in enumerate(files, 1):
        try:
            img = Image.open(path).convert("RGB")
        except Exception:
            path.unlink(missing_ok=True)
            continue
        W, H = img.size
        mx = max(2.0, W * edge_fraction)
        my = max(2.0, H * edge_fraction)
        try:
            results = detector(img, candidate_labels=[object_query])
        except Exception as exc:
            print(f"  detector error on {path.name}: {exc}; keeping in place")
            kept += 1
            continue
        qualifying = [r for r in results if r["score"] >= confidence]
        whole = [
            r for r in qualifying
            if r["box"]["xmin"] > mx
            and r["box"]["ymin"] > my
            and r["box"]["xmax"] < W - mx
            and r["box"]["ymax"] < H - my
        ]
        if whole:
            kept += 1
        elif qualifying:
            path.rename(cropped_dir / path.name)
            cropped += 1
        else:
            path.rename(no_obj_dir / path.name)
            no_obj += 1
        if i % 50 == 0 or i == total:
            print(f"  {i}/{total} (kept={kept} cropped={cropped} no_object={no_obj})")
    return kept, cropped, no_obj


def require_yolo_detection(
    out_dir: Path,
    coco_class: str = "sports ball",
    confident_threshold: float = 0.45,
    uncertain_threshold: float = 0.20,
    edge_fraction: float = 0.005,
    model_name: str = "yolov8s.pt",
) -> tuple[int, int, int]:
    """Cheap, local first-pass detector using YOLO (COCO classes).
      - max-confidence target box >= confident_threshold AND not edge-touching
        -> stays in place (verified)
      - some box >= uncertain_threshold but lower-conf or edge-touching
        -> review/yolo_uncertain/  (candidate for VLM verification)
      - no qualifying box                                        -> review/yolo_no_ball/
    Returns (kept, uncertain, no_object)."""
    from PIL import Image
    from ultralytics import YOLO

    print(f"Loading YOLO ({model_name}; downloads on first run, ~25MB)...")
    model = YOLO(model_name)

    target_idx = next(
        (idx for idx, name in model.names.items() if name == coco_class),
        None,
    )
    if target_idx is None:
        raise ValueError(
            f"COCO class {coco_class!r} not in YOLO model. "
            f"Available: {sorted(model.names.values())}"
        )

    uncertain_dir = out_dir / "review" / "yolo_uncertain"
    no_obj_dir = out_dir / "review" / "yolo_no_object"
    uncertain_dir.mkdir(parents=True, exist_ok=True)
    no_obj_dir.mkdir(parents=True, exist_ok=True)

    files = [p for p in sorted(out_dir.iterdir()) if p.is_file() and not p.name.startswith(".")]
    total = len(files)
    kept = uncertain = no_obj = 0
    print(
        f"YOLO scanning {total} images for {coco_class!r} "
        f"(conf>={confident_threshold}, maybe>={uncertain_threshold})..."
    )

    for i, path in enumerate(files, 1):
        try:
            img = Image.open(path).convert("RGB")
        except Exception:
            path.unlink(missing_ok=True)
            continue
        W, H = img.size
        mx, my = max(2.0, W * edge_fraction), max(2.0, H * edge_fraction)
        try:
            res = model.predict(img, verbose=False)[0]
        except Exception as exc:
            print(f"  {path.name}: predict error {exc}; keeping in place")
            kept += 1
            continue
        target_boxes = []  # list of (xyxy, conf)
        for j in range(len(res.boxes)):
            if int(res.boxes.cls[j]) == target_idx:
                target_boxes.append(
                    (res.boxes.xyxy[j].tolist(), float(res.boxes.conf[j]))
                )
        whole = [
            (xyxy, c) for xyxy, c in target_boxes
            if xyxy[0] > mx and xyxy[1] > my
            and xyxy[2] < W - mx and xyxy[3] < H - my
        ]
        if whole and max(c for _, c in whole) >= confident_threshold:
            kept += 1
        elif target_boxes and max(c for _, c in target_boxes) >= uncertain_threshold:
            path.rename(uncertain_dir / path.name)
            uncertain += 1
        else:
            path.rename(no_obj_dir / path.name)
            no_obj += 1
        if i % 100 == 0 or i == total:
            print(f"  {i}/{total} (kept={kept} uncertain={uncertain} no_object={no_obj})")
    return kept, uncertain, no_obj


def vlm_review(
    out_dir: Path,
    topic: str,
    model: str = "gemini-2.5-flash",
    source_dir: Path | None = None,
    concurrency: int = 10,
) -> tuple[int, int, int]:
    """Use Gemini's vision model as a reviewer, in parallel.
      - source_dir=None: scan out_dir's top level; yes stays in place,
        no -> review/vlm_rejected/, error -> review/vlm_uncertain/
      - source_dir=PATH: scan that folder (e.g. yolo_uncertain) and
        *promote* yes-images back to out_dir's top level (cascade mode).
    Requests run in a thread pool of size `concurrency`. At concurrency=10
    and paid-tier limits, throughput is ~200-400 RPM (vs ~25 RPM sequential).
    Returns (kept, rejected, uncertain)."""
    from google import genai
    from PIL import Image

    client = genai.Client()  # reads GEMINI_API_KEY (or GOOGLE_API_KEY)
    rejected_dir = out_dir / "review" / "vlm_rejected"
    uncertain_dir = out_dir / "review" / "vlm_uncertain"
    rejected_dir.mkdir(parents=True, exist_ok=True)
    uncertain_dir.mkdir(parents=True, exist_ok=True)

    scan_dir = source_dir if source_dir is not None else out_dir
    cascade = source_dir is not None
    # In cascade mode "yes" promotes the image to out_dir top level so it joins
    # the verified set; in standalone mode "yes" just stays where it is.
    yes_dir = out_dir if cascade else None

    files = [p for p in sorted(scan_dir.iterdir()) if p.is_file() and not p.name.startswith(".")]
    total = len(files)
    prompt_text = (
        f"Does this photo clearly show a {topic} that is fully visible within "
        f"the frame (not cut off at any edge)? Answer with only the single "
        f"word 'yes' or 'no' — no punctuation, no explanation."
    )
    label = f"cascade from {scan_dir.name}" if cascade else "top-level"
    print(f"VLM review ({label}): {total} images with {model} (concurrency={concurrency})...")

    import time as _time

    # Disable thinking tokens: Gemini 2.5 Flash emits reasoning tokens by
    # default (billed at output rate, $2.50/MTok) that dominate cost for a
    # simple yes/no task. thinking_budget=0 turns them off with no quality
    # loss on binary visual questions.
    try:
        from google.genai import types as _genai_types
        _gen_config = _genai_types.GenerateContentConfig(
            thinking_config=_genai_types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=5,
        )
    except Exception:
        _gen_config = None

    def _classify_one(path: Path) -> str:
        """Return one of 'yes', 'no', or 'err:<msg>'. Retries 429s with backoff."""
        try:
            img = Image.open(path).convert("RGB")
        except Exception as exc:
            return f"err:open:{exc}"
        delay = 2.0
        for attempt in range(6):
            try:
                resp = client.models.generate_content(
                    model=model, contents=[img, prompt_text],
                    config=_gen_config,
                )
                answer = (resp.text or "").strip().lower()
                if answer.startswith("yes"):
                    return "yes"
                if answer.startswith("no"):
                    return "no"
                return f"err:bad-answer:{answer[:30]}"
            except Exception as exc:
                msg = str(exc)
                status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                is_rate_limit = status == 429 or "429" in msg or "RESOURCE_EXHAUSTED" in msg
                if is_rate_limit and attempt < 5:
                    _time.sleep(delay)
                    delay = min(delay * 2, 60)
                    continue
                return f"err:{exc}"
        return "err:retries-exhausted"

    kept = rejected = uncertain = 0
    processed = 0
    # File moves need to be serialized (os rename is atomic but we update
    # shared counters) — use a lock.
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        future_to_path = {ex.submit(_classify_one, p): p for p in files}
        for fut in as_completed(future_to_path):
            path = future_to_path[fut]
            verdict = fut.result()
            with lock:
                processed += 1
                if verdict == "yes":
                    if yes_dir is not None:
                        path.rename(yes_dir / path.name)
                    kept += 1
                elif verdict == "no":
                    path.rename(rejected_dir / path.name)
                    rejected += 1
                else:
                    path.rename(uncertain_dir / path.name)
                    uncertain += 1
                if processed % 25 == 0 or processed == total:
                    tag = f" last={verdict}" if verdict.startswith("err:") else ""
                    print(f"  {processed}/{total} (kept={kept} rejected={rejected} uncertain={uncertain}){tag}")
    return kept, rejected, uncertain


def finalize_to_keep(out_dir: Path) -> int:
    """Move whatever remains at the top level into review/keep/ — this is the
    final, verified set after every filter pass."""
    keep_dir = out_dir / "review" / "keep"
    keep_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for p in sorted(out_dir.iterdir()):
        if p.is_file() and not p.name.startswith("."):
            p.rename(keep_dir / p.name)
            moved += 1
    return moved


def _run_one_job(
    out_dir: Path,
    engine: str,
    query: str,
    per_query: int,
    job_idx: int,
    downloader_threads: int,
) -> None:
    """Run a single crawl. file_idx_offset is disjoint per job (job_idx *
    per_query * 4) so concurrent jobs can't clobber each other's filenames
    even if they download more than per_query (×4 leaves slack)."""
    refined = f"{query} {NEGATIVE_KEYWORDS}"
    crawler = ENGINES[engine](
        downloader_cls=FastDownloader,
        storage={"root_dir": str(out_dir)},
        feeder_threads=1,
        parser_threads=4,
        downloader_threads=downloader_threads,
    )
    # Each engine supports different filter values. Bing/Google accept
    # {"type": "photo"}; Baidu only accepts portrait/face/clipart/linedrawing/
    # animated/static and rejects "photo" with a ValueError that kills the
    # feeder thread (so the whole job silently yields zero images).
    filters: dict | None
    if engine in ("bing", "google"):
        filters = {"type": "photo"}
    else:
        filters = None
    crawler.crawl(
        keyword=refined,
        max_num=per_query,
        filters=filters,
        file_idx_offset=job_idx * per_query * 4,
    )


# --- Open Images Dataset V7 support (pure stdlib, no fiftyone dep) ----------
# We cache the class-name→MID lookup and the image-level labels CSV to
# ~/.cache/webscraper/openimages/. Images are fetched from the CVDF mirror
# which hosts all OID training images at a predictable URL.

OID_CACHE_DIR = Path.home() / ".cache" / "webscraper" / "openimages"
# Boxable subset (~600 classes, 50KB) is preferred since these have richer
# annotations, but V7 dropped some classes that V6 had. Fall back to the full
# class list (~20k classes, ~800KB) when the topic isn't in the boxable set.
OID_CLASS_DESC_URL = (
    "https://storage.googleapis.com/openimages/v7/"
    "oidv7-class-descriptions-boxable.csv"
)
OID_CLASS_DESC_URL_FULL = (
    "https://storage.googleapis.com/openimages/v7/"
    "oidv7-class-descriptions.csv"
)
# Human-verified image-level labels — ~330MB vs 1.6GB for bbox annotations,
# and every row is either Confidence=1 (positive) or 0 (negative).
OID_IMAGELABELS_URL = (
    "https://storage.googleapis.com/openimages/v7/"
    "oidv7-train-annotations-human-imagelabels.csv"
)
# CVDF public mirror; predictable-URL per ImageID.
OID_IMAGE_CDN = "https://storage.googleapis.com/open-images-dataset/train/{image_id}.jpg"


def _oid_cache_file(url: str) -> Path:
    """Download an OID metadata file if not cached; return the local path."""
    import urllib.request

    OID_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    name = url.rsplit("/", 1)[-1]
    path = OID_CACHE_DIR / name
    if path.exists():
        return path
    size_hint = "50 KB" if "class-descriptions" in name else "~330 MB"
    print(f"  Downloading Open Images metadata: {name} ({size_hint}, one-time)...")
    tmp = path.with_suffix(path.suffix + ".partial")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(path)
    return path


def oid_class_to_mid(class_name: str) -> str | None:
    """Look up the OID machine-ID (e.g. '/m/05r655') for a human-readable
    class name. Case-insensitive exact match. Tries the boxable subset first
    (smaller, higher-quality annotations), then the full class list (~20k
    classes) as a fallback. Returns None if not found in either."""
    import csv

    target = class_name.strip().lower()
    for url in (OID_CLASS_DESC_URL, OID_CLASS_DESC_URL_FULL):
        try:
            path = _oid_cache_file(url)
        except Exception:
            continue
        # utf-8-sig swallows a BOM if the CSV has one.
        with path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[1].strip().lower() == target:
                    return row[0]
    return None


def _oid_image_ids_for_mid(mid: str, max_ids: int) -> list[str]:
    """Stream the image-level labels CSV and collect ImageIDs for rows with
    LabelName == mid and Confidence == '1' (human-verified positive)."""
    import csv

    path = _oid_cache_file(OID_IMAGELABELS_URL)
    ids: list[str] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return ids
        # Column indices in case Open Images reorders columns in future versions.
        idx_iid = header.index("ImageID")
        idx_label = header.index("LabelName")
        idx_conf = header.index("Confidence")
        for row in reader:
            if row[idx_label] == mid and row[idx_conf] == "1":
                ids.append(row[idx_iid])
                if len(ids) >= max_ids:
                    break
    return ids


def _oid_download_one(image_id: str, out_dir: Path) -> bool:
    """Fetch a single OID image from the CVDF mirror. Returns True on success.
    False for any failure (404, timeout, etc.) — we over-fetch to compensate."""
    import urllib.request

    dst = out_dir / f"oid_{image_id}.jpg"
    if dst.exists():
        return True
    url = OID_IMAGE_CDN.format(image_id=image_id)
    req = urllib.request.Request(url, headers={"User-Agent": "webscraper/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return False
            data = resp.read()
    except Exception:
        return False
    try:
        dst.write_bytes(data)
        return True
    except OSError:
        return False


def openimages_crawl(
    out_dir: Path,
    open_images_class: str,
    max_samples: int = 5000,
    workers: int = 16,
    overfetch: float = 1.5,
) -> int:
    """Pull images from Open Images Dataset V7 via raw CSV + CVDF CDN.

    Over-fetches by `overfetch`x to compensate for dead URLs (common — OID
    images link back to original hosts, many of which 404'd over time).
    Downloads run in parallel chunks so they don't become the wall-clock
    bottleneck versus the Bing/Baidu crawl."""
    import random

    mid = oid_class_to_mid(open_images_class)
    if mid is None:
        print(
            f"  Open Images class {open_images_class!r} not found in V7. "
            f"Skipping. (Edit .topic_spec.json if you know the correct name.)"
        )
        return 0
    print(f"  Open Images: {open_images_class!r} -> {mid}")

    target_ids = int(max_samples * overfetch)
    image_ids = _oid_image_ids_for_mid(mid, max_ids=target_ids * 2)
    if not image_ids:
        print(f"  No image-level labels found for {mid}; skipping.")
        return 0
    random.seed(42)
    random.shuffle(image_ids)
    image_ids = image_ids[:target_ids]
    print(f"  Found {len(image_ids)} candidate ImageIDs (over-fetching {overfetch}x)...")

    chunk_size = 200
    ok = fail = 0
    for start in range(0, len(image_ids), chunk_size):
        if ok >= max_samples:
            break
        chunk = image_ids[start:start + chunk_size]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_oid_download_one, iid, out_dir) for iid in chunk]
            for fut in as_completed(futures):
                if fut.result():
                    ok += 1
                else:
                    fail += 1
        done = min(start + chunk_size, len(image_ids))
        print(f"    {done}/{len(image_ids)} (ok={ok} fail={fail})")
    print(f"  Open Images done. Downloaded {ok} images ({fail} dead URLs).")
    return ok


def crawl_jobs(
    out_dir: Path,
    engines: list[str],
    queries: list[str],
    per_query: int,
    done_path: Path,
    workers: int,
    downloader_threads: int,
) -> None:
    """Run (engine, query) pairs in parallel, persisting completion so the
    script resumes on rerun."""
    done: set[str] = set()
    if done_path.exists():
        done = {line for line in done_path.read_text().splitlines() if line}

    all_jobs = [(e, q) for e in engines for q in queries]
    todo = [(i, e, q) for i, (e, q) in enumerate(all_jobs) if f"{e}\t{q}" not in done]
    print(
        f"Planning {len(all_jobs)} jobs ({len(engines)} engines × {len(queries)} queries); "
        f"{len(todo)} to run, {len(all_jobs) - len(todo)} already done. "
        f"Per-query target {per_query}, {workers} parallel workers, "
        f"{downloader_threads} download threads/job."
    )

    done_lock = threading.Lock()
    completed = 0
    total = len(todo)

    def _persist():
        done_path.write_text("\n".join(sorted(done)) + "\n")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(_run_one_job, out_dir, e, q, per_query, idx, downloader_threads): (e, q)
            for idx, e, q in todo
        }
        for fut in as_completed(futures):
            engine, query = futures[fut]
            completed += 1
            try:
                fut.result()
            except Exception as exc:
                print(f"  [{completed}/{total}] FAIL  {engine} {query!r}: {exc}")
                continue
            with done_lock:
                done.add(f"{engine}\t{query}")
                _persist()
            print(f"  [{completed}/{total}] ok    {engine} {query!r}")


def _format_elapsed(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{seconds:.1f}s"


def main() -> int:
    import time
    started = time.monotonic()

    def _stamp(code: int) -> int:
        elapsed = time.monotonic() - started
        print(f"\nTotal pipeline time: {_format_elapsed(elapsed)}")
        return code

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Topic, e.g. 'basketball'")
    parser.add_argument("--count", type=int, default=None,
                        help="Total images to fetch across all jobs (split evenly). Ignored if --per-query is set.")
    parser.add_argument("--per-query", type=int, default=None,
                        help="Images per (engine, query) job. Default 50 in scale mode.")
    parser.add_argument("--out", default="images", help="Parent output directory")
    parser.add_argument(
        "--engines", nargs="+",
        choices=list(ENGINES.keys()) + ["openimages"],
        default=["bing"],
        help="Image sources. Search engines (bing, baidu, google) use icrawler; "
             "'openimages' pulls pre-labeled images from Open Images Dataset V7 "
             "via raw CSVs + CVDF CDN (stdlib only, no extra dep; 330MB one-time "
             "cache to ~/.cache/webscraper/openimages/).",
    )
    parser.add_argument("--openimages-max", type=int, default=5000,
                        help="Max samples to request from Open Images when "
                             "'openimages' is in --engines (default 5000)")
    parser.add_argument("--queries", nargs="+", help="Override the search queries used for the topic")
    parser.add_argument("--no-expand", action="store_true",
                        help="Skip multi-query expansion; just search the topic verbatim")
    parser.add_argument("--no-classify", action="store_true",
                        help="Skip CLIP-based photo-vs-illustration filtering")
    parser.add_argument("--classify-only", action="store_true",
                        help="Skip crawl; just dedupe and run CLIP on existing files")
    parser.add_argument("--reset-resume", action="store_true",
                        help="Forget which jobs completed previously and recrawl them")
    parser.add_argument("--workers", type=int, default=8,
                        help="How many crawl jobs to run in parallel (default 8)")
    parser.add_argument("--downloader-threads", type=int, default=16,
                        help="Download threads per job (default 16)")
    parser.add_argument("--review-margin", type=float, default=0.02,
                        help="CLIP score margin below which an image is sent to review/ "
                             "for manual inspection instead of kept or deleted (default 0.02)")
    parser.add_argument("--require-object", action="store_true",
                        help="Strict mode: after CLIP, run OWL-ViT object detection and "
                             "move images without a detected object to review/no_object_detected/. "
                             "Requires: pip install transformers")
    parser.add_argument("--object-query", default=None,
                        help="Text for object detection (default: 'a <topic>'). "
                             "Use something visually concrete, e.g. 'a basketball' not 'basketball game'.")
    parser.add_argument("--object-confidence", type=float, default=0.15,
                        help="Minimum detection confidence for --require-object (default 0.15)")
    parser.add_argument("--edge-fraction", type=float, default=0.005,
                        help="Require detected object's bounding box to be at least this "
                             "fraction of width/height away from every image edge. "
                             "Set to 0 to allow edge-touching boxes (default 0.005 = 0.5%%)")
    parser.add_argument("--require-yolo", action="store_true",
                        help="Cheap local detector: YOLO (COCO classes). "
                             "Splits into kept / review/yolo_uncertain/ / review/yolo_no_object/. "
                             "Requires: pip install ultralytics")
    parser.add_argument("--yolo-class", default=None,
                        help="COCO class name for --require-yolo. If unset, comes from the "
                             "bootstrap spec; if the spec has no match, falls back to 'sports ball'. "
                             "Use the exact COCO class name, e.g. 'cat', 'dog', 'car'.")
    parser.add_argument("--yolo-confidence", type=float, default=0.45,
                        help="Min YOLO confidence to keep without VLM review (default 0.45)")
    parser.add_argument("--yolo-uncertain-conf", type=float, default=0.05,
                        help="Min YOLO confidence to be a 'maybe' (default 0.05). "
                             "Below this -> review/yolo_no_object/, no VLM call. "
                             "Low default trades VLM spend for recall — many real "
                             "basketballs score 0.05-0.20 depending on angle/occlusion.")
    parser.add_argument("--yolo-model", default="yolov8m.pt",
                        help="YOLO weights file (default yolov8m.pt; ~50MB; "
                             "noticeably better recall than yolov8s.pt on small/angled objects)")
    parser.add_argument("--vlm-review", action="store_true",
                        help="Use Gemini vision as a reviewer. With --require-yolo it cascades: "
                             "only review the yolo_uncertain bucket and promote yes-answers. "
                             "Without --require-yolo, reviews all top-level images. "
                             "Requires GEMINI_API_KEY env var + pip install google-genai")
    parser.add_argument("--vlm-model", default="gemini-2.5-flash",
                        help="Gemini model for --vlm-review (default: gemini-2.5-flash). "
                             "Use gemini-2.5-pro for higher accuracy at higher cost, "
                             "gemini-2.5-flash-lite for cheapest.")
    parser.add_argument("--vlm-rescue", action="store_true",
                        help="After the main VLM pass, also review CLIP's review buckets "
                             "(maybe_keep, maybe_remove, clip_rejected) and promote "
                             "yes-answers back to the verified set. Catches CLIP false "
                             "negatives (e.g. NBA action shots where CLIP scores jerseys "
                             "higher than the ball). Costs ~$1-3 extra on Gemini Flash.")
    parser.add_argument("--vlm-concurrency", type=int, default=10,
                        help="How many Gemini requests to run in parallel (default 10). "
                             "On paid-tier keys this pushes throughput from ~25 RPM to "
                             "200-400 RPM. On free tier (10 RPM cap), drop to 1-2.")
    parser.add_argument("--no-bootstrap", action="store_true",
                        help="Skip the LLM call that auto-generates topic-specific queries/"
                             "distractors/yolo-class/vlm-object. Falls back to PRESETS + "
                             "GENERIC_TEMPLATES for queries and CLI defaults elsewhere.")
    parser.add_argument("--bootstrap-model", default="gemini-2.5-flash",
                        help="Gemini model used to generate the topic spec (default: gemini-2.5-flash)")
    parser.add_argument("--refresh-spec", action="store_true",
                        help="Force a fresh bootstrap LLM call even if .topic_spec.json is cached.")
    args = parser.parse_args()

    out_dir = Path(args.out) / slugify(args.query)
    out_dir.mkdir(parents=True, exist_ok=True)
    done_path = out_dir / ".done.txt"
    if args.reset_resume and done_path.exists():
        done_path.unlink()

    # Bootstrap: ask Gemini for topic-type + queries + distractors + yolo class.
    spec: TopicSpec | None = None
    if not args.no_bootstrap:
        try:
            spec = load_or_bootstrap_spec(
                out_dir, args.query,
                model=args.bootstrap_model,
                refresh=args.refresh_spec,
            )
        except Exception as exc:
            print(f"Bootstrap failed ({exc}); falling back to hardcoded defaults.")

    # Topic-type gate: this pipeline is built for discrete photographable
    # objects. Hard-fail on anything else so the user doesn't burn hours
    # crawling + running detectors that can't work for non-object topics.
    if spec is not None:
        if spec.type != "object":
            explanations = {
                "scene": "a setting/landscape (no object to detect per image)",
                "style": "a visual aesthetic (no object to detect)",
                "abstract": "a non-visual concept (not photographable as an object)",
                "person": "a specific individual (needs face recognition, not object detection)",
            }
            reason = explanations.get(spec.type, f"type={spec.type!r}")
            sys.stderr.write(
                f"\nERROR: topic {args.query!r} classified as {spec.type!r} — "
                f"{reason}.\n"
                f"This pipeline only handles discrete photographable objects "
                f"(e.g. 'basketball', 'golden retriever', 'bicycle').\n"
                f"If Gemini misclassified, edit {out_dir/'.topic_spec.json'} "
                f"(set 'type' to 'object') or rerun with --refresh-spec after "
                f"rephrasing the topic.\n"
            )
            if spec.notes:
                sys.stderr.write(f"Gemini's notes: {spec.notes}\n")
            return _stamp(2)
        if spec.yolo_class is None and args.require_yolo and not args.yolo_class:
            print(
                "NOTE: no matching COCO class for this object; --require-yolo "
                "will auto-fall-back to OWL-ViT (open-vocabulary) so the rest "
                "of the pipeline still works transparently."
            )

    if not args.classify_only:
        # Split engines: icrawler-based (go through crawl_jobs) vs openimages
        # (goes through fiftyone zoo loader).
        icrawler_engines = [e for e in args.engines if e in ENGINES]
        use_openimages = "openimages" in args.engines

        if use_openimages:
            oi_class = spec.open_images_class if spec is not None else None
            if not oi_class:
                print(
                    "Skipping openimages engine: no Open Images class matched "
                    "this topic. Pass --no-bootstrap and set it manually, or "
                    "edit .topic_spec.json's 'open_images_class' field."
                )
            else:
                openimages_crawl(
                    out_dir, oi_class, max_samples=args.openimages_max,
                )

        queries = resolve_queries(
            args.query, args.queries, expand=not args.no_expand, spec=spec,
        )
        if not icrawler_engines:
            print("No search-engine sources active; skipping web crawl.")
        else:
            n_jobs = len(icrawler_engines) * len(queries)
            if args.per_query is not None:
                per_query = args.per_query
            elif args.count is not None:
                per_query = max(1, args.count // n_jobs)
            else:
                per_query = 50
            crawl_jobs(
                out_dir, icrawler_engines, queries, per_query, done_path,
                workers=args.workers, downloader_threads=args.downloader_threads,
            )

    raw = sum(1 for p in out_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    print(f"Raw files: {raw}. Deduping...")
    dupes = dedupe_by_hash(out_dir)
    after_dedupe = raw - dupes
    print(f"Removed {dupes} duplicates ({after_dedupe} unique).")

    if after_dedupe == 0:
        print(f"Done. 0 file(s) in {out_dir}/")
        return _stamp(0)

    spec_scene = spec.scene_distractors if spec is not None else None
    spec_photo_prompts = spec.photo_prompts if spec is not None else None
    spec_vlm_obj = spec.vlm_object if spec is not None else None
    spec_yolo = spec.yolo_class if spec is not None else None

    if not args.no_classify:
        kept, rejected, uncertain = classify_and_prune(
            out_dir, args.query,
            review_margin=args.review_margin,
            scene_distractors=spec_scene,
            extra_photo_prompts=spec_photo_prompts,
        )
        print(
            f"CLIP pass done. Kept {kept}; sent {rejected} to review/clip_rejected/; "
            f"{uncertain} to maybe_keep/ or maybe_remove/."
        )
    else:
        print("Skipping CLIP classification (--no-classify).")

    if args.require_object:
        obj_q = args.object_query or spec_vlm_obj or f"a {args.query}"
        strict_kept, cropped, no_obj = require_object_detection(
            out_dir, obj_q,
            confidence=args.object_confidence,
            edge_fraction=args.edge_fraction,
        )
        print(
            f"OWL-ViT pass ({obj_q!r}) done. Kept {strict_kept} fully-framed; "
            f"moved {cropped} to review/ball_cropped/ and "
            f"{no_obj} to review/no_object_detected/."
        )

    # Auto-fallback: --require-yolo with no matching COCO class would pick
    # "sports ball" (nearly always wrong). Silently swap to OWL-ViT, which
    # takes the topic as open-vocabulary text and works for any object.
    yolo_auto_fellback = False
    if args.require_yolo and not args.yolo_class and (spec_yolo is None):
        obj_q = args.object_query or spec_vlm_obj or f"a {args.query}"
        print(
            f"--require-yolo active but no COCO class matches this topic; "
            f"auto-swapping to OWL-ViT with query {obj_q!r}. "
            f"Images go to the same review/yolo_uncertain/ bucket so the "
            f"VLM cascade (if on) still runs."
        )
        strict_kept, cropped, no_obj = require_object_detection(
            out_dir, obj_q,
            confidence=args.object_confidence,
            edge_fraction=args.edge_fraction,
        )
        # Relabel OWL-ViT's outputs under the YOLO review folder names so
        # the downstream VLM-cascade lookup finds them.
        src_cropped = out_dir / "review" / "ball_cropped"
        src_noobj = out_dir / "review" / "no_object_detected"
        dst_uncertain = out_dir / "review" / "yolo_uncertain"
        dst_noobj = out_dir / "review" / "yolo_no_object"
        dst_uncertain.mkdir(parents=True, exist_ok=True)
        dst_noobj.mkdir(parents=True, exist_ok=True)
        for src, dst in ((src_cropped, dst_uncertain), (src_noobj, dst_noobj)):
            if src.is_dir():
                for p in src.iterdir():
                    if p.is_file() and not p.name.startswith("."):
                        p.rename(dst / p.name)
        print(
            f"OWL-ViT (as yolo fallback) done. Kept {strict_kept} fully-framed; "
            f"{cropped} -> review/yolo_uncertain/, {no_obj} -> review/yolo_no_object/."
        )
        yolo_auto_fellback = True

    if args.require_yolo and not yolo_auto_fellback:
        yc = args.yolo_class or spec_yolo or "sports ball"
        yolo_kept, yolo_uncertain, yolo_no_obj = require_yolo_detection(
            out_dir,
            coco_class=yc,
            confident_threshold=args.yolo_confidence,
            uncertain_threshold=args.yolo_uncertain_conf,
            edge_fraction=args.edge_fraction,
            model_name=args.yolo_model,
        )
        print(
            f"YOLO pass ({yc!r}) done. Kept {yolo_kept} confidently; "
            f"moved {yolo_uncertain} to review/yolo_uncertain/ and "
            f"{yolo_no_obj} to review/yolo_no_object/."
        )

    if args.vlm_review:
        vlm_topic = spec_vlm_obj or args.query
        if args.require_yolo:
            uncertain_dir = out_dir / "review" / "yolo_uncertain"
            if uncertain_dir.is_dir() and any(
                p for p in uncertain_dir.iterdir() if p.is_file() and not p.name.startswith(".")
            ):
                vlm_kept, vlm_rejected, vlm_uncertain = vlm_review(
                    out_dir, vlm_topic, model=args.vlm_model,
                    source_dir=uncertain_dir,
                    concurrency=args.vlm_concurrency,
                )
                print(
                    f"VLM cascade done. Promoted {vlm_kept} from yolo_uncertain; "
                    f"moved {vlm_rejected} to review/vlm_rejected/ and "
                    f"{vlm_uncertain} to review/vlm_uncertain/."
                )
            else:
                print("VLM cascade: nothing in review/yolo_uncertain/ to review, skipping.")
        else:
            vlm_kept, vlm_rejected, vlm_uncertain = vlm_review(
                out_dir, vlm_topic, model=args.vlm_model,
                concurrency=args.vlm_concurrency,
            )
            print(
                f"VLM review done. Kept {vlm_kept}; moved {vlm_rejected} to "
                f"review/vlm_rejected/ and {vlm_uncertain} to review/vlm_uncertain/."
            )

        # Rescue pass: VLM re-reviews CLIP's uncertain/rejected buckets. A
        # yes-answer promotes back to top-level (which finalize will move into
        # review/keep/). Catches CLIP false negatives like NBA action shots
        # where jerseys outscored the ball.
        if args.vlm_rescue:
            rescue_buckets = ["maybe_keep", "maybe_remove", "clip_rejected"]
            for bucket in rescue_buckets:
                source = out_dir / "review" / bucket
                if not source.is_dir():
                    continue
                if not any(p for p in source.iterdir()
                           if p.is_file() and not p.name.startswith(".")):
                    continue
                r_kept, r_rejected, r_uncertain = vlm_review(
                    out_dir, vlm_topic, model=args.vlm_model, source_dir=source,
                    concurrency=args.vlm_concurrency,
                )
                print(
                    f"VLM rescue ({bucket}): promoted {r_kept}; "
                    f"moved {r_rejected} to review/vlm_rejected/, "
                    f"{r_uncertain} to review/vlm_uncertain/."
                )

    # Finalize: any filter ran means the top-level images are the verified set.
    # Consolidate them into review/keep/.
    if not args.no_classify or args.require_object or args.require_yolo or args.vlm_review:
        moved = finalize_to_keep(out_dir)
        if moved:
            print(f"Moved {moved} verified image(s) -> {out_dir / 'review' / 'keep'}/")
    return _stamp(0)


if __name__ == "__main__":
    sys.exit(main())
