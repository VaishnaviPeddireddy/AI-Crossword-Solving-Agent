from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
W, H, FPS = 1280, 720, 24
BG = (11, 17, 32)
PANEL = (19, 29, 49)
MUTED = (157, 173, 198)
WHITE = (241, 246, 255)
TEAL = (68, 224, 195)
AMBER = (255, 197, 92)
RED = (255, 116, 131)


def font(size: int, bold: bool = False):
    options = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in options:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


F = {"title": font(42, True), "h": font(29, True), "body": font(21), "mono": font(18), "small": font(16), "big": font(50, True)}


def round_rect(draw, box, fill, outline=None, radius=18, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def base_frame(kicker: str, headline: str, sub: str, frame_no: int, total: int):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    # restrained radial-like accent and progress strip
    d.ellipse((920, -370, 1550, 260), fill=(17, 36, 53))
    d.rectangle((0, 0, W, 7), fill=(32, 48, 72))
    d.rectangle((0, 0, round(W * frame_no / max(total, 1)), 7), fill=TEAL)
    d.text((62, 42), kicker.upper(), font=F["small"], fill=TEAL)
    d.text((62, 78), headline, font=F["title"], fill=WHITE)
    d.text((64, 136), sub, font=F["body"], fill=MUTED)
    d.line((62, 180, W - 62, 180), fill=(42, 57, 79), width=2)
    d.text((62, H - 38), "CROSSWORD AGENT  ·  DEMO FIXTURE  ·  DETERMINISTIC CONSTRAINT CHECKS", font=F["small"], fill=(117, 137, 165))
    return im, d


def panel(draw, title, box):
    round_rect(draw, box, PANEL, outline=(43, 59, 83), radius=16, width=2)
    draw.text((box[0] + 22, box[1] + 18), title, font=F["small"], fill=MUTED)
    draw.line((box[0] + 20, box[1] + 52, box[2] - 20, box[1] + 52), fill=(43, 59, 83), width=1)


def parse_actual():
    demo = subprocess.run([sys.executable, "run.py"], cwd=ROOT, check=True, text=True, capture_output=True).stdout
    report = json.loads(subprocess.run([sys.executable, "run.py", "--compare", "--json"], cwd=ROOT, check=True, text=True, capture_output=True).stdout)
    return demo, report.get("strategies", report) if isinstance(report, dict) else report


def scene_image(scene: int, frame_no: int, total: int, demo: str, reports: list[dict]) -> Image.Image:
    headlines = [
        ("An agent, not a one-shot guess", "Semantic proposals in; deterministic grid validation out."),
        ("Start with ranked candidates", "Plausible answers are hypotheses, not commitments."),
        ("Crossings do the hard checking", "A letter mismatch prunes a candidate and updates neighbors."),
        ("Validate the completed grid", "Every Across/Down intersection agrees before SOLVED."),
        ("Measure each added capability", "One gold-labelled smoke fixture; results are measured, not extrapolated."),
        ("Search can recover from a bad branch", "The adversarial unit test verifies undo and retry behavior."),
    ]
    kicker, sub = headlines[scene]
    im, d = base_frame("Forward deployed engineer  /  crossword agent", kicker, sub, frame_no, total)
    if scene == 0:
        panel(d, "DESIGN", (62, 220, 1218, 638))
        steps = [("01", "Parse", "grid · clues · entry coordinates"), ("02", "Propose", "ranked answers with confidence"), ("03", "Constrain", "crossing letters + AC-3 propagation"), ("04", "Recover", "MRV search · backtrack · validate")]
        for i, (n, label, detail) in enumerate(steps):
            y = 290 + i * 77
            d.ellipse((94, y, 138, y + 44), fill=(22, 58, 69), outline=TEAL, width=2)
            d.text((104, y + 9), n, font=F["small"], fill=TEAL)
            d.text((162, y + 2), label, font=F["h"], fill=WHITE)
            d.text((330, y + 8), detail, font=F["body"], fill=MUTED)
    elif scene == 1:
        panel(d, "REAL CLI CANDIDATE TRACE", (62, 220, 790, 638))
        candidates = [line for line in demo.splitlines() if " pattern=" in line][:6]
        y = 300
        for line in candidates:
            match = re.match(r"\s*(\S+)\s+(.+?)\s+pattern=\S+\s+(.+)", line)
            if match:
                choices = re.sub(r"\s*\((0?\.\d+)\)", r" \1", match.group(3)).replace(", ", " · ")
                clue_label = match.group(2)
                if len(clue_label) > 12:
                    clue_label = clue_label[:11] + "…"
                display = f"{match.group(1):<3} {clue_label:<12} {choices}"[:58]
            else:
                display = line.strip()[:58]
            d.text((88, y), display, font=F["mono"], fill=WHITE if "CAR" not in line and "AGE" not in line else AMBER)
            y += 44
        panel(d, "TOP PROPOSALS", (820, 220, 1218, 638))
        d.text((850, 318), "1-Across", font=F["small"], fill=MUTED)
        d.text((850, 348), "CAR", font=F["h"], fill=AMBER)
        d.text((945, 353), "0.96", font=F["mono"], fill=MUTED)
        d.text((850, 399), "4-Across", font=F["small"], fill=MUTED)
        d.text((850, 429), "AGE", font=F["h"], fill=AMBER)
        d.text((945, 434), "0.93", font=F["mono"], fill=MUTED)
        d.text((850, 520), "High confidence ≠", font=F["body"], fill=WHITE)
        d.text((850, 551), "correct answer", font=F["body"], fill=AMBER)
    elif scene == 2:
        panel(d, "ACTUAL CROSSING PRUNES", (62, 220, 790, 638))
        prunes = [line for line in demo.splitlines() if line.strip().startswith("PRUNE")]
        for i, line in enumerate(prunes[:7]):
            d.text((90, 294 + i * 43), line.strip()[:67], font=F["mono"], fill=RED if i < 3 else WHITE)
        panel(d, "CONSTRAINT LOOP", (820, 220, 1218, 638))
        d.text((854, 304), "Candidate", font=F["h"], fill=WHITE)
        d.text((854, 354), "↓", font=F["h"], fill=TEAL)
        d.text((854, 395), "Crossing check", font=F["h"], fill=WHITE)
        d.text((854, 445), "↓", font=F["h"], fill=TEAL)
        d.text((854, 485), "Prune + propagate", font=F["body"], fill=TEAL)
        d.text((854, 548), "not enough letters? backtrack", font=F["small"], fill=MUTED)
    elif scene == 3:
        panel(d, "SOLVED GRID · 6 OF 6 ENTRIES", (62, 220, 770, 638))
        grid = ["CAT", "ARE", "TEN"]
        cell = 96
        left, top = 218, 291
        for r, row in enumerate(grid):
            for c, ch in enumerate(row):
                x, y = left + c * (cell + 5), top + r * (cell + 5)
                round_rect(d, (x, y, x + cell, y + cell), (22, 48, 66), outline=(66, 147, 143), radius=8, width=2)
                d.text((x + 31, y + 17), ch, font=F["big"], fill=TEAL)
        panel(d, "DETERMINISTIC VALIDATION", (805, 220, 1218, 638))
        d.text((840, 320), "6 / 6 entries", font=F["h"], fill=WHITE)
        d.text((840, 383), "9 / 9 crossings", font=F["h"], fill=WHITE)
        round_rect(d, (838, 470, 1184, 552), (17, 72, 62), outline=TEAL, radius=14, width=2)
        d.text((878, 490), "SOLVED  ✓", font=F["h"], fill=TEAL)
    elif scene == 4:
        panel(d, "MEASURED WORD ACCURACY", (62, 220, 790, 638))
        colors = [AMBER, TEAL, TEAL]
        labels = ["Baseline", "Crossings", "Full agent"]
        for i, report in enumerate(reports):
            y = 298 + 92 * i
            d.text((90, y), labels[i], font=F["body"], fill=WHITE)
            val = report["word_accuracy"]
            d.rounded_rectangle((250, y + 6, 250 + int(370 * val), y + 34), radius=10, fill=colors[i])
            d.text((650, y), f"{val:.1%}", font=F["body"], fill=WHITE)
        d.text((90, 585), "One 3×3 fixture only — a smoke test, not generalization.", font=F["small"], fill=AMBER)
        panel(d, "EVALUATION", (820, 220, 1218, 638))
        d.text((850, 300), "6 clues · 1 puzzle", font=F["body"], fill=WHITE)
        d.text((850, 355), "Calls: 6 per run", font=F["body"], fill=WHITE)
        d.text((850, 410), "Gold labels known", font=F["body"], fill=WHITE)
        d.text((850, 485), "API cost: n/a", font=F["h"], fill=AMBER)
        d.text((850, 540), "No rate card configured", font=F["small"], fill=MUTED)
    else:
        panel(d, "WHAT THE TESTS VERIFY", (62, 220, 790, 638))
        for i, line in enumerate(["Grid numbering and crossings", "Distractors removed by AC-3", "Full puzzle matches gold answers", "Bad branch is undone; lower-ranked branch solves"]):
            d.text((92, 292 + i * 70), "✓", font=F["h"], fill=TEAL)
            d.text((140, 298 + i * 70), line, font=F["body"], fill=WHITE)
        panel(d, "NEXT STEP", (820, 220, 1218, 638))
        d.text((850, 310), "Evaluate on a", font=F["body"], fill=MUTED)
        d.text((850, 348), "held-out set", font=F["h"], fill=WHITE)
        d.text((850, 402), "difficulty · latency", font=F["small"], fill=TEAL)
        d.text((850, 438), "tokens · exact solves", font=F["small"], fill=TEAL)
        d.text((850, 494), "MODEL PROPOSES.", font=F["h"], fill=WHITE)
        d.text((850, 536), "PYTHON VERIFIES.", font=F["h"], fill=TEAL)
    return im


def main():
    demo, all_reports = parse_actual()
    reports = all_reports
    narration = OUT / "narration.wav"
    if not narration.exists():
        raise SystemExit("Missing demo/narration.wav. Add the narration WAV before building the video.")
    with wave.open(str(narration), "rb") as wav:
        audio_duration = wav.getnframes() / wav.getframerate()
    # Preserve a sub-minute ceiling even if generated speech runs longer than expected.
    final_duration = min(59.0, audio_duration + 0.8)
    frame_total = math.ceil(final_duration * FPS)
    scene_weights = [0.12, 0.18, 0.23, 0.15, 0.18, 0.14]
    boundaries, acc = [], 0.0
    for weight in scene_weights:
        acc += weight
        boundaries.append(acc)
    frames_dir = OUT / "frames"
    frames_dir.mkdir(exist_ok=True)
    for index in range(frame_total):
        t = index / FPS
        progress = t / final_duration
        scene = next((i for i, edge in enumerate(boundaries) if progress < edge), len(boundaries) - 1)
        im = scene_image(scene, index, frame_total, demo, reports)
        im.save(frames_dir / f"frame-{index:05d}.png", optimize=False)
    silent = OUT / "silent.mp4"
    final = OUT / "crossword-agent-demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames_dir / "frame-%05d.png"), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", str(silent)], check=True)
    # Audio longer than video is trimmed by -shortest. If it exceeds the 59s ceiling, speed it up modestly.
    if audio_duration > 58.2:
        tempo = audio_duration / 58.2
        audio_filter = f"atempo={tempo:.4f}"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent), "-i", str(narration), "-filter:a", audio_filter, "-c:v", "copy", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent), "-i", str(narration), "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    silent.unlink(missing_ok=True)
    for frame in frames_dir.glob("*.png"):
        frame.unlink()
    frames_dir.rmdir()
    print(f"Created {final} (narration={audio_duration:.2f}s, video cap=59s)")


if __name__ == "__main__":
    main()
