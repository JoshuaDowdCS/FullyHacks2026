"""YouTube -> frame dataset pipeline.

Same topic-agnostic shape as webscraper.py, but ingests YouTube videos
instead of web-crawled images.

Pipeline:
  1. Bootstrap topic spec via Gemini (shared w/ webscraper.py)
  2. yt-dlp search across every spec.query
  3. Metadata heuristic filter (duration, not livestream/short)
  4. Text-only Gemini scoring of title+description -> top-K videos
  5. Download each survivor, extract frames at 1 frame/sec with ffmpeg,
     delete the video file
  6. Byte-identical + perceptual frame dedup
  7. YOLO cascade on frames -> review/yolo_uncertain/
  8. Gemini VLM verifies yolo_uncertain (same parallel logic as webscraper)
  9. Finalize -> frames/<topic>/review/keep/

Setup:
    python3 -m pip install yt-dlp imagehash
    brew install ffmpeg            # or apt-get install ffmpeg
    # plus existing deps: ultralytics google-genai torch open_clip_torch
    export GEMINI_API_KEY=...

Usage:
    python3 ytwebscraper.py basketball --max-videos 15
    python3 ytwebscraper.py "vintage camera" --max-videos 10 --frame-fps 0.5
"""

import argparse
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from webscraper import (
    TopicSpec,
    _format_elapsed,
    dedupe_by_hash,
    finalize_to_keep,
    load_or_bootstrap_spec,
    require_object_detection,
    require_yolo_detection,
    slugify,
    vlm_review,
)

YTDLP_CMD = "yt-dlp"
FFMPEG_CMD = "ffmpeg"


# --------------------------------------------------------------------------- #
# Step 1: search
# --------------------------------------------------------------------------- #

def ytdlp_search(query: str, limit: int = 20) -> list[dict]:
    """Search YouTube via yt-dlp. Returns a list of flat metadata dicts
    (id, title, duration, channel, etc.). No video is downloaded."""
    cmd = [
        YTDLP_CMD,
        f"ytsearch{limit}:{query}",
        "--dump-json",
        "--flat-playlist",
        "--no-warnings",
        "--no-check-certificate",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90,
        )
    except FileNotFoundError:
        sys.stderr.write("ERROR: yt-dlp not installed. pip install yt-dlp\n")
        return []
    except subprocess.TimeoutExpired:
        print(f"  search timeout: {query!r}")
        return []
    videos: list[dict] = []
    for line in result.stdout.splitlines():
        try:
            videos.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return videos


def search_all_queries(
    queries: list[str],
    per_query: int,
    workers: int = 6,
) -> dict[str, dict]:
    """Fan out searches, dedupe by video id. Returns {id: metadata}."""
    out: dict[str, dict] = {}
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(ytdlp_search, q, per_query): q for q in queries}
        done = 0
        for fut in as_completed(futures):
            done += 1
            q = futures[fut]
            try:
                vids = fut.result()
            except Exception as exc:
                print(f"  [{done}/{len(queries)}] search err {q!r}: {exc}")
                continue
            with lock:
                for v in vids:
                    vid = v.get("id")
                    if vid:
                        out.setdefault(vid, v)
            print(f"  [{done}/{len(queries)}] {q!r} -> {len(vids)} videos "
                  f"(unique so far: {len(out)})")
    return out


# --------------------------------------------------------------------------- #
# Step 2: metadata filter
# --------------------------------------------------------------------------- #

def pass_metadata_filter(v: dict, min_sec: int, max_sec: int) -> bool:
    if v.get("is_live"):
        return False
    # "shorts" are <=60s and usually poor source material
    dur = v.get("duration")
    if not isinstance(dur, (int, float)):
        return True  # unknown -> keep, we'll learn during download
    return min_sec <= dur <= max_sec


# --------------------------------------------------------------------------- #
# Step 3: Gemini text scoring of title+description
# --------------------------------------------------------------------------- #

def score_candidates_with_gemini(
    candidates: list[dict],
    topic: str,
    vlm_object: str,
    model: str = "gemini-2.5-flash-lite",
    concurrency: int = 20,
) -> list[tuple[dict, float]]:
    """Ask Gemini to rate 0-10 how likely each video contains many clear,
    in-frame shots of the target object. Very cheap — text only, ~50 tokens
    per call. Returns [(video_dict, score), ...]."""
    from google import genai
    try:
        from google.genai import types as _types
        cfg = _types.GenerateContentConfig(
            thinking_config=_types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=10,
        )
    except Exception:
        cfg = None

    client = genai.Client()

    def _score(v: dict) -> tuple[dict, float]:
        title = (v.get("title") or "")[:200]
        desc = (v.get("description") or "")[:600]
        dur = v.get("duration") or 0
        prompt = (
            f"Rate from 0 to 10 how likely this YouTube video contains MANY "
            f"clear, in-frame shots of {vlm_object}. Consider title, "
            f"description, and duration. A tutorial or review of the object "
            f"scores high; a compilation scores high; a music video about the "
            f"topic but without real shots scores low; a meme video scores "
            f"low. Respond with ONLY the integer 0-10, nothing else.\n\n"
            f"Title: {title}\n"
            f"Description: {desc}\n"
            f"Duration: {int(dur)} seconds\n"
            f"Topic: {topic}\n"
            f"Score (0-10):"
        )
        delay = 2.0
        for attempt in range(5):
            try:
                resp = client.models.generate_content(
                    model=model, contents=[prompt], config=cfg,
                )
                text = (resp.text or "").strip()
                # First integer 0-10 we find in the response
                digits = ""
                for ch in text:
                    if ch.isdigit():
                        digits += ch
                    elif digits:
                        break
                if digits:
                    score = min(10.0, float(digits))
                    return (v, score)
                return (v, 5.0)
            except Exception as exc:
                msg = str(exc)
                if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < 4:
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue
                return (v, 5.0)  # neutral on unknown error
        return (v, 5.0)

    results: list[tuple[dict, float]] = []
    total = len(candidates)
    done = 0
    lock = threading.Lock()
    print(f"  Scoring {total} candidates with {model}...")
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(_score, v) for v in candidates]
        for fut in as_completed(futures):
            res = fut.result()
            with lock:
                results.append(res)
                done += 1
                if done % 25 == 0 or done == total:
                    print(f"    scored {done}/{total}")
    return results


# --------------------------------------------------------------------------- #
# Step 4: video download
# --------------------------------------------------------------------------- #

def download_video(
    video_id: str,
    out_dir: Path,
    max_height: int = 720,
) -> Path | None:
    """Download one YouTube video at <= max_height. Returns path or None."""
    out_dir.mkdir(parents=True, exist_ok=True)
    template = str(out_dir / f"{video_id}.%(ext)s")
    cmd = [
        YTDLP_CMD,
        f"https://www.youtube.com/watch?v={video_id}",
        "-o", template,
        "-f", (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]"
            f"/best[height<={max_height}][ext=mp4]/best[height<={max_height}]/best"
        ),
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-warnings",
        "--no-check-certificate",
        "--quiet",
    ]
    try:
        subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "")[:200]
        print(f"    download failed {video_id}: {stderr}")
        return None
    except subprocess.TimeoutExpired:
        print(f"    download timeout {video_id}")
        return None
    except FileNotFoundError:
        sys.stderr.write("ERROR: yt-dlp not installed\n")
        return None
    for ext in ("mp4", "mkv", "webm"):
        p = out_dir / f"{video_id}.{ext}"
        if p.exists():
            return p
    return None


# --------------------------------------------------------------------------- #
# Step 5: frame extraction
# --------------------------------------------------------------------------- #

def extract_frames(
    video_path: Path,
    out_dir: Path,
    frame_fps: float = 1.0,
    max_frames: int | None = None,
) -> int:
    """ffmpeg: extract frames at `frame_fps` (default 1/sec). File layout:
    out_dir/<videoid>_fNNNNN.jpg. Returns frame count."""
    out_dir.mkdir(parents=True, exist_ok=True)
    vid = video_path.stem
    pattern = str(out_dir / f"{vid}_f%05d.jpg")
    cmd = [
        FFMPEG_CMD,
        "-i", str(video_path),
        "-vf", f"fps={frame_fps}",
        "-q:v", "3",  # 1-31, lower=better; 3 is visually lossless-ish
        "-hide_banner",
        "-loglevel", "error",
    ]
    if max_frames is not None:
        cmd += ["-frames:v", str(max_frames)]
    cmd.append(pattern)
    try:
        subprocess.run(cmd, check=True, timeout=900)
    except subprocess.CalledProcessError as exc:
        print(f"    ffmpeg failed: {exc}")
        return 0
    except FileNotFoundError:
        sys.stderr.write("ERROR: ffmpeg not installed\n")
        return 0
    except subprocess.TimeoutExpired:
        print(f"    ffmpeg timeout")
        return 0
    count = sum(1 for _ in out_dir.glob(f"{vid}_f*.jpg"))
    return count


# --------------------------------------------------------------------------- #
# Step 6: perceptual dedup
# --------------------------------------------------------------------------- #

def dedupe_perceptual(out_dir: Path, threshold: int = 5) -> int:
    """Perceptual-hash dedup. Two frames with phash Hamming distance <=
    `threshold` are considered duplicates; we keep the first. Typical
    basketball-in-motion frames sampled at 1fps rarely collide; this mostly
    catches static/title frames repeated across videos."""
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        print("  perceptual dedup needs: pip install imagehash Pillow")
        return 0

    files = sorted(
        p for p in out_dir.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )
    seen: list = []
    removed = 0
    for path in files:
        try:
            h = imagehash.phash(Image.open(path))
        except Exception:
            continue
        dup = any((h - prev) <= threshold for prev in seen)
        if dup:
            path.unlink()
            removed += 1
        else:
            seen.append(h)
    return removed


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    started = time.monotonic()

    def _stamp(code: int) -> int:
        print(f"\nTotal pipeline time: {_format_elapsed(time.monotonic() - started)}")
        return code

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Topic, e.g. 'basketball'")
    parser.add_argument("--out", default="frames",
                        help="Parent output directory (default: frames/)")
    parser.add_argument("--max-videos", type=int, default=15,
                        help="How many videos to download+process after scoring (default 15)")
    parser.add_argument("--search-per-query", type=int, default=20,
                        help="How many results to fetch per search query (default 20)")
    parser.add_argument("--min-duration", type=int, default=60,
                        help="Drop videos shorter than this many seconds (default 60)")
    parser.add_argument("--max-duration", type=int, default=1800,
                        help="Drop videos longer than this many seconds (default 1800 = 30 min)")
    parser.add_argument("--frame-fps", type=float, default=1.0,
                        help="Frames per second to extract from each video (default 1.0)")
    parser.add_argument("--max-frames-per-video", type=int, default=None,
                        help="Optional cap on extracted frames per video")
    parser.add_argument("--max-height", type=int, default=720,
                        help="Max video resolution to download (default 720)")
    parser.add_argument("--keep-videos", action="store_true",
                        help="Don't delete video files after frame extraction (for debugging)")
    parser.add_argument("--perceptual-dedup-threshold", type=int, default=5,
                        help="phash Hamming distance below which frames are duplicates (default 5)")
    # Filter stack (mirrors webscraper flags)
    parser.add_argument("--require-yolo", action="store_true", default=True,
                        help="Run YOLO detection (on by default for video)")
    parser.add_argument("--no-yolo", dest="require_yolo", action="store_false",
                        help="Disable YOLO step")
    parser.add_argument("--yolo-class", default=None,
                        help="Override COCO class (comes from spec by default)")
    parser.add_argument("--yolo-confidence", type=float, default=0.45)
    parser.add_argument("--yolo-uncertain-conf", type=float, default=0.05)
    parser.add_argument("--yolo-model", default="yolov8m.pt")
    parser.add_argument("--edge-fraction", type=float, default=0.005)
    parser.add_argument("--vlm-review", action="store_true", default=True,
                        help="VLM cascade on yolo_uncertain (on by default)")
    parser.add_argument("--no-vlm", dest="vlm_review", action="store_false")
    parser.add_argument("--vlm-model", default="gemini-2.5-flash-lite")
    parser.add_argument("--vlm-concurrency", type=int, default=20)
    # Bootstrap
    parser.add_argument("--bootstrap-model", default="gemini-2.5-flash")
    parser.add_argument("--no-bootstrap", action="store_true")
    parser.add_argument("--refresh-spec", action="store_true")
    # Skip stages
    parser.add_argument("--skip-download", action="store_true",
                        help="Use frames already staged at out_dir top level")
    args = parser.parse_args()

    out_dir = Path(args.out) / slugify(args.query)
    out_dir.mkdir(parents=True, exist_ok=True)
    video_dir = out_dir / ".videos"

    # -- Bootstrap topic spec (reuses webscraper) --
    spec: TopicSpec | None = None
    if not args.no_bootstrap:
        try:
            spec = load_or_bootstrap_spec(
                out_dir, args.query,
                model=args.bootstrap_model, refresh=args.refresh_spec,
            )
        except Exception as exc:
            print(f"Bootstrap failed ({exc}); continuing with fallbacks.")

    if spec is not None and spec.type != "object":
        sys.stderr.write(
            f"\nERROR: topic {args.query!r} classified as {spec.type!r}. "
            f"This pipeline only handles concrete object topics.\n"
        )
        return _stamp(2)

    queries = (spec.queries if spec else [args.query])
    vlm_object = spec.vlm_object if spec else f"a {args.query}"
    spec_yolo_class = spec.yolo_class if spec else None

    # -- Stage 1-5: search, filter, score, download, extract --
    if not args.skip_download:
        print(f"\nSearching YouTube for {len(queries)} queries...")
        all_candidates = search_all_queries(
            queries, per_query=args.search_per_query, workers=6,
        )
        filtered = [
            v for v in all_candidates.values()
            if pass_metadata_filter(v, args.min_duration, args.max_duration)
        ]
        print(f"  {len(filtered)}/{len(all_candidates)} pass metadata filter "
              f"(duration {args.min_duration}-{args.max_duration}s, not live/short).")

        if not filtered:
            print("No videos passed metadata filter; nothing to do.")
            return _stamp(0)

        # Score with Gemini text (cheap) and take the top-K
        scored = score_candidates_with_gemini(
            filtered, args.query, vlm_object,
            model=args.vlm_model, concurrency=args.vlm_concurrency,
        )
        scored.sort(key=lambda x: -x[1])
        top = scored[:args.max_videos]
        if top:
            cut = top[-1][1]
            print(f"  Top {len(top)} after scoring (lowest accepted score: {cut:.1f}).")
            for v, s in top[:5]:
                title = (v.get("title") or "")[:60]
                print(f"    {s:.1f}  {v['id']}  {title}")

        # Download + extract frames per video
        print(f"\nProcessing {len(top)} videos...")
        total_frames = 0
        for i, (v, score) in enumerate(top, 1):
            vid = v["id"]
            title = (v.get("title") or "")[:60]
            dur = v.get("duration") or "?"
            print(f"\n[{i}/{len(top)}] {vid} (score={score:.1f}, dur={dur}s) {title}")

            video_path = download_video(vid, video_dir, max_height=args.max_height)
            if video_path is None:
                continue
            size_mb = video_path.stat().st_size / 1e6
            print(f"    downloaded {size_mb:.1f} MB -> extracting frames...")

            nframes = extract_frames(
                video_path, out_dir,
                frame_fps=args.frame_fps,
                max_frames=args.max_frames_per_video,
            )
            print(f"    extracted {nframes} frames at {args.frame_fps} fps")
            total_frames += nframes

            if not args.keep_videos:
                video_path.unlink(missing_ok=True)

        print(f"\nTotal frames extracted across all videos: {total_frames}")
    else:
        print("--skip-download: reusing frames already in out_dir")

    # -- Stage 6: dedup (bytewise, then perceptual) --
    raw = sum(1 for p in out_dir.iterdir()
              if p.is_file() and not p.name.startswith("."))
    print(f"\nRaw frames: {raw}. Dedup passes...")
    dupes_exact = dedupe_by_hash(out_dir)
    print(f"  Byte-identical dupes removed: {dupes_exact}")
    dupes_phash = dedupe_perceptual(out_dir, threshold=args.perceptual_dedup_threshold)
    print(f"  Perceptual near-dupes removed: {dupes_phash}")
    after_dedup = raw - dupes_exact - dupes_phash
    print(f"  Unique frames remaining: {after_dedup}")

    if after_dedup == 0:
        print(f"Done. 0 frames in {out_dir}/")
        return _stamp(0)

    # -- Stage 7: YOLO (with OWL-ViT auto-fallback) --
    yolo_class = args.yolo_class or spec_yolo_class
    yolo_auto_fellback = False
    if args.require_yolo and not args.yolo_class and yolo_class is None:
        obj_q = vlm_object
        print(f"\nNo COCO class matches {args.query!r}; auto-swapping to OWL-ViT "
              f"with query {obj_q!r}...")
        try:
            kept, cropped, no_obj = require_object_detection(
                out_dir, obj_q,
                confidence=0.15, edge_fraction=args.edge_fraction,
            )
            # Relabel OWL-ViT outputs into the yolo_* buckets so the VLM
            # cascade finds them.
            dst_u = out_dir / "review" / "yolo_uncertain"
            dst_n = out_dir / "review" / "yolo_no_object"
            dst_u.mkdir(parents=True, exist_ok=True)
            dst_n.mkdir(parents=True, exist_ok=True)
            for src, dst in (
                (out_dir / "review" / "ball_cropped", dst_u),
                (out_dir / "review" / "no_object_detected", dst_n),
            ):
                if src.is_dir():
                    for p in src.iterdir():
                        if p.is_file() and not p.name.startswith("."):
                            p.rename(dst / p.name)
            print(f"  OWL-ViT done. Kept {kept}, cropped->uncertain {cropped}, "
                  f"none->no_object {no_obj}")
            yolo_auto_fellback = True
        except Exception as exc:
            print(f"  OWL-ViT fallback failed ({exc}); skipping detection.")
    elif args.require_yolo and not yolo_auto_fellback:
        yc = yolo_class or "sports ball"
        print(f"\nRunning YOLO ({yc!r}, model={args.yolo_model})...")
        try:
            ykept, yun, yno = require_yolo_detection(
                out_dir,
                coco_class=yc,
                confident_threshold=args.yolo_confidence,
                uncertain_threshold=args.yolo_uncertain_conf,
                edge_fraction=args.edge_fraction,
                model_name=args.yolo_model,
            )
            print(f"  YOLO done. Kept {ykept}, uncertain {yun}, no_object {yno}")
        except Exception as exc:
            print(f"  YOLO failed ({exc}); skipping.")

    # -- Stage 8: VLM cascade on yolo_uncertain --
    if args.vlm_review:
        unc_dir = out_dir / "review" / "yolo_uncertain"
        if unc_dir.is_dir() and any(
            p for p in unc_dir.iterdir()
            if p.is_file() and not p.name.startswith(".")
        ):
            print(f"\nVLM cascade on yolo_uncertain...")
            kept, rej, unc = vlm_review(
                out_dir, vlm_object,
                model=args.vlm_model,
                source_dir=unc_dir,
                concurrency=args.vlm_concurrency,
            )
            print(f"  VLM cascade done. Promoted {kept}, rejected {rej}, uncertain {unc}")
        else:
            print("\nNothing in yolo_uncertain/; skipping VLM cascade.")

    # -- Stage 9: finalize --
    moved = finalize_to_keep(out_dir)
    if moved:
        print(f"\nMoved {moved} verified frames -> {out_dir / 'review' / 'keep'}/")
    return _stamp(0)


if __name__ == "__main__":
    sys.exit(main())
