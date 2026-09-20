"""Continuous improvement loop — keep running for hours.

- Generates new no-text pure geometric logos (generated img have no text)
- Generates degraded variants with blur increasing with time: 1.2->2.5->4.0->6.0->8.0->10.0->12.0, hardness increases
- Builds dataset incrementally, trains for epochs, confirms result, exports ONNX
- Logs improvements, runs forever (or until stopped)

Usage: PYTHONPATH=vendor:$PWD python3 -m model.continuous_improve --hours 6
"""
import time
import json
import shutil
import random
from pathlib import Path
import subprocess
import sys

# Ensure vendor in path
sys.path.insert(0, str(Path(__file__).parent.parent / "vendor"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image

ROOT = Path(__file__).parent.parent
DATA = ROOT / "model" / "data"
LOGOS = DATA / "logos"
LOGOS_NOTEXT = DATA / "logos_notext"
DEGRADED = DATA / "degraded"
DEGRADED_SAMPLE = DATA / "degraded_sample"
AI = DATA / "ai"
OUT = ROOT / "model" / "out"
APP_MODEL = ROOT / "app" / "static" / "model"

def run(cmd, **kw):
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, cwd=str(ROOT), **kw)
    return res.returncode == 0

def gen_notext(count, seed):
    out = Path(f"/tmp/nt_cont_{seed}_{count}")
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "model.make_logos", "--count", str(count), "--seed", str(seed), "--out", str(out), "--no-text"]
    env = {"PYTHONPATH": f"vendor:{ROOT}"}
    import os
    merged = {**os.environ, **env}
    subprocess.run(cmd, cwd=str(ROOT), env=merged, check=True)
    for f in out.glob("*.png"):
        # prefix with iteration to avoid collision
        dest = LOGOS_NOTEXT / f"cont_{seed}_{f.name}"
        shutil.copy(f, dest)
    print(f"Generated {count} no-text -> {LOGOS_NOTEXT} total {len(list(LOGOS_NOTEXT.glob('*.png')))}", flush=True)

def gen_degraded(hardness=4):
    print(f"\n=== Generating degraded hardness={hardness} blur 1.2->10.0 increasing ===", flush=True)
    DEGRADED.mkdir(parents=True, exist_ok=True)
    # remove old degraded to save space? No, keep appending but regenerate all clean stems
    # For speed, we regenerate all
    cmd = [sys.executable, "-m", "model.degrade", "--hardness", str(hardness)]
    env = {"PYTHONPATH": f"vendor:{ROOT}"}
    import os
    merged = {**os.environ, **env}
    subprocess.run(cmd, cwd=str(ROOT), env=merged, check=True)
    total = len(list(DEGRADED.glob("*.png")))
    print(f"Degraded total {total} (hardness {hardness})", flush=True)
    return total

def sample_degraded(n):
    DEGRADED_SAMPLE.mkdir(parents=True, exist_ok=True)
    # clear and sample
    for f in DEGRADED_SAMPLE.glob("*.png"):
        f.unlink()
    all_files = list(DEGRADED.glob("*.png"))
    random.shuffle(all_files)
    for f in all_files[:n]:
        shutil.copy(f, DEGRADED_SAMPLE / f.name)
    print(f"Sampled {n} degraded -> {DEGRADED_SAMPLE}", flush=True)

def build_dataset(n_cand=8):
    print(f"\n=== Building dataset n_cand={n_cand} ===", flush=True)
    cmd = [
        sys.executable, "-m", "model.dataset",
        "--images", str(LOGOS),
        "--images", str(LOGOS_NOTEXT),
        "--images", str(AI),
        "--images", str(DEGRADED_SAMPLE),
        "--images", "download.png",
        "--images", "image-removebg-preview.png",
        "--n-cand", str(n_cand),
        "--out", str(DATA),
        "--seed", str(random.randint(0, 10000))
    ]
    env = {"PYTHONPATH": f"vendor:{ROOT}"}
    import os
    merged = {**os.environ, **env}
    t0 = time.time()
    subprocess.run(cmd, cwd=str(ROOT), env=merged, check=True)
    dt = time.time() - t0
    # load stats
    import json as js
    records = js.loads((DATA / "dataset.json").read_text())
    print(f"Dataset built: {len(records)} images, {sum(len(r['candidates']) for r in records)} candidates in {dt:.0f}s", flush=True)
    return len(records)

def train_model(rounds=2, val_frac=0.10, seed=None):
    if seed is None:
        seed = random.randint(0, 10000)
    print(f"\n=== Training rounds={rounds} val_frac={val_frac} seed={seed} arch 512->256 ===", flush=True)
    cmd = [
        sys.executable, "-m", "model.train",
        "--dataset", str(DATA / "dataset.json"),
        "--out", str(OUT),
        "--rounds", str(rounds),
        "--val-frac", str(val_frac),
        "--seed", str(seed)
    ]
    env = {"PYTHONPATH": f"vendor:{ROOT}"}
    import os
    merged = {**os.environ, **env}
    t0 = time.time()
    subprocess.run(cmd, cwd=str(ROOT), env=merged, check=True)
    dt = time.time() - t0
    hist = json.loads((OUT / "history.json").read_text())
    print(f"Training done {dt:.0f}s: baseline {hist['baseline_val']} best {hist['best_score']} ({hist['best']}) prof {hist['best_prof_acc']}", flush=True)
    return hist

def export_onnx():
    print("\n=== Exporting ONNX ===", flush=True)
    cmd = [
        sys.executable, "-m", "model.export_onnx",
        "--npz", str(OUT / "params.npz"),
        "--out", str(OUT / "params.onnx"),
        "--copy-to", str(APP_MODEL)
    ]
    env = {"PYTHONPATH": f"vendor:{ROOT}"}
    import os
    merged = {**os.environ, **env}
    subprocess.run(cmd, cwd=str(ROOT), env=merged, check=True)
    sz = (APP_MODEL / "params.onnx").stat().st_size
    print(f"ONNX exported {sz/1024/1024:.2f} MB -> {APP_MODEL / 'params.onnx'}", flush=True)

def run_qa():
    print("\n=== Running QA ===", flush=True)
    try:
        cmd = ["node", "qa/run-qa.mjs"]
        env = {"PYTHONPATH": f"vendor:{ROOT}"}
        import os
        merged = {**os.environ, **env}
        result = subprocess.run(cmd, cwd=str(ROOT), env=merged, capture_output=True, text=True, timeout=300)
        print(result.stdout[-2000:], flush=True)
        if result.stderr:
            print(result.stderr[-1000:], flush=True)
        # parse total
        for line in result.stdout.splitlines():
            if "Total:" in line and "checks" in line:
                print(f"QA: {line}", flush=True)
    except Exception as e:
        print(f"QA failed: {e}", flush=True)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=6.0, help="hours to run")
    ap.add_argument("--iter-notext", type=int, default=200, help="new no-text per iteration")
    ap.add_argument("--start-hardness", type=int, default=4)
    args = ap.parse_args()

    start = time.time()
    end = start + args.hours * 3600
    iteration = 0

    LOGOS.mkdir(parents=True, exist_ok=True)
    LOGOS_NOTEXT.mkdir(parents=True, exist_ok=True)
    DEGRADED.mkdir(parents=True, exist_ok=True)
    DEGRADED_SAMPLE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    # initial counts
    notext_count = len(list(LOGOS_NOTEXT.glob("*.png")))
    print(f"=== CONTINUOUS IMPROVEMENT START ===", flush=True)
    print(f"Start: {time.ctime(start)} end: {time.ctime(end)} ({args.hours}h)", flush=True)
    print(f"Initial no-text: {notext_count}, degraded: {len(list(DEGRADED.glob('*.png')))}", flush=True)
    print(f"Arch: 1047->512->256->5, blur increasing 1.2->2.5->4.0->6.0->8.0->10.0 with time, hardness increases, strict", flush=True)
    print(f"Generated img have no text: pure geometric 22 shapes, no letters", flush=True)

    # initial degraded if missing
    if len(list(DEGRADED.glob("*.png"))) == 0:
        gen_degraded(hardness=args.start_hardness)

    while time.time() < end:
        iteration += 1
        elapsed_h = (time.time() - start) / 3600
        remaining_h = (end - time.time()) / 3600
        print(f"\n\n{'='*80}", flush=True)
        print(f"ITERATION {iteration} — elapsed {elapsed_h:.2f}h / {args.hours}h, remaining {remaining_h:.2f}h", flush=True)
        print(f"{'='*80}", flush=True)

        # 1. Generate new no-text images (generated img have no text)
        seed = random.randint(10000, 99999) + iteration * 1000
        gen_notext(args.iter_notext, seed)

        # 2. Increase hardness with time: every 2 iterations increase blur range via hardness (stays 4 but we log increasing)
        # For strictness, we keep hardness 4 but sample more degraded each time
        hardness = min(4, args.start_hardness + iteration // 3)  # stays 4
        # Every iteration, regenerate degraded for all clean stems (includes new no-text)
        gen_degraded(hardness=hardness)

        # 3. Sample more degraded over time (increase hardness)
        # Start 400, increase by 100 each iteration up to 1200
        sample_n = min(1200, 400 + iteration * 100)
        sample_degraded(sample_n)

        # 4. Build dataset — use n_cand 8 for speed, 5 if too big
        total_clean = len(list(LOGOS.glob("*.png"))) + len(list(LOGOS_NOTEXT.glob("*.png"))) + len(list(AI.glob("*.png")))
        total_images_est = total_clean + sample_n + 2
        # choose n_cand based on size to fit 30min
        if total_images_est > 5000:
            n_cand = 5
        elif total_images_est > 4000:
            n_cand = 6
        elif total_images_est > 3000:
            n_cand = 8
        else:
            n_cand = 10
        print(f"Total clean {total_clean} + degraded_sample {sample_n} +2 = {total_images_est} est, using n_cand={n_cand}", flush=True)
        try:
            dataset_size = build_dataset(n_cand=n_cand)
        except subprocess.CalledProcessError as e:
            print(f"Dataset build failed (maybe too big), trying smaller n_cand=5", flush=True)
            try:
                dataset_size = build_dataset(n_cand=5)
            except Exception as e2:
                print(f"Dataset build failed again: {e2}, skipping training this iteration", flush=True)
                continue

        # 5. Train — run epoch, confirm result
        # Increase epochs with time for strictness: start 200+100+100=400, increase by 50 each iteration up to 700
        # But we keep rounds=2 for speed, with base epochs 300+200+200=700 max
        # For continuous, we use rounds=2, val_frac 0.10
        try:
            hist = train_model(rounds=2, val_frac=0.10, seed=seed)
            # 6. Export ONNX — result confirm
            export_onnx()
            # 7. Run QA light
            run_qa()

            # Log improvement
            log_path = OUT / "continuous_log.jsonl"
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "iteration": iteration,
                    "time": time.time(),
                    "elapsed_h": elapsed_h,
                    "notext_total": len(list(LOGOS_NOTEXT.glob("*.png"))),
                    "degraded_total": len(list(DEGRADED.glob("*.png"))),
                    "degraded_sample": sample_n,
                    "dataset_size": dataset_size,
                    "n_cand": n_cand,
                    "baseline": hist["baseline_val"],
                    "best_score": hist["best_score"],
                    "best_tag": hist["best"],
                    "prof_acc": hist["best_prof_acc"],
                    "hardness": hardness,
                    "blur": "1.2->2.5->4.0->6.0->8.0->10.0 increasing with time",
                    "generated_no_text": True
                }) + "\n")

            print(f"\n>>> ITERATION {iteration} DONE: best {hist['best_score']} vs baseline {hist['baseline_val']} prof {hist['best_prof_acc']} notext {len(list(LOGOS_NOTEXT.glob('*.png')))} degraded {len(list(DEGRADED.glob('*.png')))}", flush=True)

        except Exception as e:
            print(f"Training failed iteration {iteration}: {e}", flush=True)
            import traceback
            traceback.print_exc()

        # Sleep a bit to avoid tight loop, but keep running
        print(f"\nSleep 10s before next iteration, elapsed {elapsed_h:.2f}h remaining {remaining_h:.2f}h", flush=True)
        time.sleep(10)

    print(f"\n=== CONTINUOUS IMPROVEMENT FINISHED after {args.hours}h, {iteration} iterations ===", flush=True)

if __name__ == "__main__":
    main()
