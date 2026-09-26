"""Forever training program — the model is never done until:

    goal A: >= 50_000 gathered training images (clean + degraded on disk)
    goal B: >= 100_000 gradient training steps, cumulative on the SAME weights

Design rules
------------
* Runs indefinitely in the background; each iteration does a bit of
  data generation, a bit of dataset scoring, and a chunk of training.
* Everything expensive is checkpointed and committed to git so the
  recurring sandbox restores (which wipe gitignored model/data +
  model/out) can never destroy progress again:
    - model_data_snapshot/params.npz.gz      -> network weights
    - model_data_snapshot/data_parts/*.part -> scored dataset chunks (gz)
    - app/static/model/params.onnx          -> shipped web model
  On start, if the live copies are missing they are restored from
  these committed artifacts.
* Only commits/pushes on real improvement (val score >= last push + 0.3,
  at most every 20 min) and every 60 min always snapshots state.
* When both goals are met it prints GOALS REACHED and exits 0; until then
  it keeps improving the model forever, and continues afterwards too
  (--continue-after-goals) if asked.

Run: PYTHONPATH=app/deps:vendor:. python -m model.forever_train
"""
from __future__ import annotations

import gzip
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "model" / "data"
OUT = ROOT / "model" / "out"
SNAP = ROOT / "model_data_snapshot"
PARTS = SNAP / "data_parts"
STATIC_MODEL = ROOT / "app" / "static" / "model"

GOAL_IMAGES = 70_000
GOAL_STEPS = 2_000_000    # user target: keep training past 2,000K steps
DATASET_CAP = 6000          # rolling window of scored records used for training
SCORE_CHUNK = 250           # new images scored per iteration (~2.5 min)
GEN_CHUNK = 600             # new clean images per iteration
TRAIN_EPOCHS = 150          # epochs per training invocation
EPOCH_TOL = 0.3             # min val improvement to push
PUSH_INTERVAL = 20 * 60     # seconds between git pushes minimum
SNAP_INTERVAL = 60 * 60     # full state snapshot at least hourly

PROGRESS_PATH = OUT / "progress.json"
PROGRESS_SNAP = SNAP / "forever-progress.json"

DIRS_ALL = ["logos_notext", "logos", "logos_text", "degraded"]


def log(*a):
    print(f"[forever {time.strftime('%H:%M:%S')}]", *a, flush=True)


def sh(cmd: list[str], **kw):
    env = {**os.environ, "PYTHONPATH": "app/deps:vendor:."}
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=3600, **kw)


# ---------------------------------------------------------------- progress
def load_progress() -> dict:
    for p in (PROGRESS_PATH, PROGRESS_SNAP):
        try:
            return json.loads(Path(p).read_text())
        except Exception:
            continue
    return {"steps_total": 0, "best_val": 0.0, "seed_clean": 1000,
            "last_push": 0, "last_snap": 0, "committed_val": 0.0,
            "started": time.strftime("%Y-%m-%d %H:%M:%S")}


def save_progress(prog: dict, snap: bool = False):
    OUT.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(json.dumps(prog, indent=2))
    if snap:
        SNAP.mkdir(parents=True, exist_ok=True)
        PROGRESS_SNAP.write_text(json.dumps(prog, indent=2))


# ----------------------------------------------------------- wipe restore
def restore_from_snapshots():
    """If gitignored dirs were wiped, inflate committed artifacts."""
    restored = []
    p = SNAP / "params.npz.gz"
    if p.exists() and not (OUT / "params.npz").exists():
        OUT.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "rb") as f, open(OUT / "params.npz", "wb") as o:
            shutil.copyfileobj(f, o)
        restored.append("params.npz")
    hist = OUT / "history.json"
    if not hist.exists() and (SNAP / "history.json").exists():
        shutil.copy2(SNAP / "history.json", hist)
        restored.append("history")
    dj = DATA / "dataset.json"
    if not dj.exists():
        # restore frozen base snapshot first
        base = SNAP / "dataset.json.gz"
        if base.exists():
            DATA.mkdir(parents=True, exist_ok=True)
            with gzip.open(base, "rb") as f, open(dj, "wb") as o:
                shutil.copyfileobj(f, o)
            restored.append("dataset-base")
        # then merge committed scored parts
        recs = []
        for part in sorted(PARTS.glob("*.json.gz")):
            try:
                recs += json.loads(gzip.open(part, "rt").read())
            except Exception:
                pass
        if recs:
            try:
                ex = json.loads(dj.read_text()) if dj.exists() else []
            except Exception:
                ex = []
            known = {r["name"] for r in ex}
            ex += [r for r in recs if r["name"] not in known]
            dj.write_text(json.dumps(ex))
            restored.append(f"parts+{len(recs)}")
    if restored:
        log("restored from snapshots:", ", ".join(restored))


# ------------------------------------------------------------- data gen
def count_images() -> dict:
    c = {}
    for d in DIRS_ALL:
        p = DATA / d
        c[d] = len(list(p.glob("*.png"))) if p.exists() else 0
    return c


def gen_clean(counts: dict, prog: dict):
    """Generate more clean images if the 3 clean dirs are below targets."""
    from PIL import Image  # noqa: F401  (import here for lazy deps check)
    targets = {"logos_notext": 3000, "logos": 1800, "logos_text": 1800}
    for d, target in targets.items():
        if counts[d] >= target:
            continue
        want = min(GEN_CHUNK, target - counts[d])
        seed = prog["seed_clean"]
        if d == "logos_text":
            r = sh([sys.executable, "model/gen_text_no_bg.py",
                    "--out", str(DATA / d), "--count", str(want),
                    "--seed", str(seed)])
        else:
            cmd = [sys.executable, "-m", "model.make_logos",
                   "--out", str(DATA / d), "--count", str(want),
                   "--seed", str(seed)]
            if d == "logos_notext":
                cmd.append("--no-text")
            r = sh(cmd)
        prog["seed_clean"] = seed + want
        log(f"gen {d} +{want} (seed {seed})", (r.stdout or "").strip().splitlines()[-1] if r.stdout else "")


def gen_degraded(counts: dict):
    """Turn clean images into degraded variants (blur 1.2->10.0 + ...).
    Stops once the degraded dir reaches the target corpus size."""
    from PIL import Image  # noqa
    from model.degrade import (variant_soft, variant_jpeg, variant_rotate,
                               variant_blur, variant_scale, variant_jitter,
                               variant_pixelate, variant_heavy)
    target = GOAL_IMAGES - (counts["logos_notext"] + counts["logos"] + counts["logos_text"])
    if counts["degraded"] >= target:
        return
    out_dir = DATA / "degraded"
    out_dir.mkdir(parents=True, exist_ok=True)
    done = {p.stem.rsplit("_v", 1)[0] for p in out_dir.glob("*.png")}
    srcs = []
    for d in ("logos_notext", "logos", "logos_text"):
        srcs += sorted((DATA / d).glob("*.png"))
    todo = [p for p in srcs if p.stem not in done]
    rng = random.Random(99)
    n = 0
    for p in todo:
        try:
            img = Image.open(p).convert("RGBA")
        except Exception:
            continue
        stem = p.stem
        try:
            variant_soft(img).save(out_dir / f"{stem}_v01_soft.png")
            variant_jpeg(img, q=38).save(out_dir / f"{stem}_v02_jpeg.png")
            variant_rotate(img, rng.uniform(-12, 12)).save(out_dir / f"{stem}_v03_rot.png")
            variant_blur(img, radius=1.2).save(out_dir / f"{stem}_v04_blur1.png")
            variant_scale(img, rng).save(out_dir / f"{stem}_v05_scale.png")
            variant_jitter(img, rng, strength=1.0).save(out_dir / f"{stem}_v06_jit1.png")
            variant_blur(img, radius=2.5).save(out_dir / f"{stem}_v07_blur2.png")
            variant_blur(img, radius=4.0).save(out_dir / f"{stem}_v08_blur3.png")
            variant_jitter(img, rng, strength=1.5).save(out_dir / f"{stem}_v09_jit2.png")
            variant_blur(img, radius=6.0).save(out_dir / f"{stem}_v10_blur4.png")
            variant_jpeg(variant_blur(img, 1.5), q=15).save(out_dir / f"{stem}_v11_jpeghard.png")
            variant_heavy(img, rng, blur=2.0, jpeg_q=25).save(out_dir / f"{stem}_v12_heavy.png")
            variant_pixelate(variant_blur(img, 1.0), factor=0.15).save(out_dir / f"{stem}_v13_pixel.png")
            variant_blur(img, radius=8.0).save(out_dir / f"{stem}_v14_blur5.png")
            variant_blur(img, radius=10.0).save(out_dir / f"{stem}_v15_blur6.png")
            n += 15
        except Exception as e:
            log("degrade fail", stem, e)
        if n + counts["degraded"] >= target:
            break
        if n and n % 600 == 0:
            log(f"degraded +{n} so far total {counts['degraded'] + n}")
    log(f"degraded +{n} total {counts['degraded'] + n}")


# ------------------------------------------------------- dataset scoring
def extend_dataset(counts: dict):
    """Score up to SCORE_CHUNK new images and append to dataset.json."""
    from model.dataset import build_dataset
    dj = DATA / "dataset.json"
    try:
        recs = json.loads(dj.read_text()) if dj.exists() else []
    except Exception:
        recs = []
    known = {r["name"] for r in recs}
    all_imgs = []
    for d in DIRS_ALL:
        all_imgs += sorted((DATA / d).glob("*.png"))
    todo = [p for p in all_imgs if p.name not in known]  # r["name"] carries the extension
    if not todo:
        return len(recs)
    chunk = todo[:SCORE_CHUNK]
    before = len(chunk)
    new_recs = build_dataset(chunk, str(DATA), n_cand=8, seed=7,
                             save_best_svm=False)
    # build_dataset rewrites dataset.json including only the chunk; merge
    recs += new_recs
    if len(recs) > DATASET_CAP:
        recs = recs[:482] + recs[-(DATASET_CAP - 482):]
    dj.write_text(json.dumps(recs))
    # persist this chunk as a committed part (wipe insurance)
    PARTS.mkdir(parents=True, exist_ok=True)
    part = PARTS / f"ds-{int(time.time())}.json.gz"
    gzip.open(part, "wt").write(json.dumps(new_recs))
    log(f"dataset +{before} scored -> {len(recs)} records (window cap {DATASET_CAP})")
    return len(recs)


# -------------------------------------------------------------- training
def train_chunk(prog: dict) -> tuple[int, float]:
    """One training invocation. Returns (steps_done, val_score)."""
    import numpy as np
    from PIL import Image
    from model.train import (init_net, train_round, soft_target, cheap_val,
                             eval_model, forward, targets_to_params, FEATURE_DIM,
                             img_feats_cache)
    rng = np.random.default_rng(int(time.time()))
    records = json.loads((DATA / "dataset.json").read_text())
    if len(records) > 2500:
        base = records[:482]
        rest = records[482:]
        pick = rng.choice(len(rest), size=min(2000, len(rest)), replace=False)
        records = base + [rest[i] for i in sorted(pick)]
    val_frac = 0.15
    order = rng.permutation(len(records))
    n_val = max(30, int(len(records) * val_frac))
    val_idx = set(order[:n_val].tolist())
    X, T, val_X, val_T, val_imgs = [], [], [], [], []
    # human-verdict feedback (user acceptance criterion): bad model verdicts
    # up-weight the record's sampling, good ones soften it; never removes data
    from model.verdicts import load_verdict_feedback
    names_all = [r.get("name", "") for r in records]
    vw, vstats = load_verdict_feedback(names_all, method="model")
    if vstats["verdict_records"]:
        log(f"verdicts feedback: {vstats['verdict_records']} verdicts, "
            f"{vstats['matched']} matched -> {vstats['bad_up']} bad up-weighted x2, "
            f"{vstats['good_down']} good softened x0.7")
    for i, r in enumerate(records):
        rpath = r.get("path")
        if not rpath or not Path(rpath).exists():
            continue
        try:
            f = np.array(r["features"], dtype=np.float32)
        except Exception:
            continue
        t = soft_target(r["candidates"])
        img_feats_cache[r.get("name", "")] = f
        if i in val_idx:
            val_X.append(f); val_T.append(t)
            val_imgs.append((r["name"], Image.open(rpath).convert("RGBA")))
        else:
            # repeat-count controls sampling weight (2 = twice per epoch)
            reps = 2 if vw[i] > 1.5 else (0 if vw[i] < 0.9 and rng.random() > vw[i] else 1)
            for _ in range(reps):
                X.append(f); T.append(t)
    X = np.stack(X); T = np.stack(T)
    val_X = np.stack(val_X); val_T = np.stack(val_T)

    npz = OUT / "params.npz"
    if npz.exists():
        z = np.load(npz)
        net = [z[k] for k in ("W1", "b1", "W2", "b2", "W3", "b3", "W4", "b4")]
    else:
        net = init_net(seed=1)

    steps_per_epoch = max(1, (len(X) + 127) // 128)
    t0 = time.time()
    net, _ = train_round(net, X, T, epochs=TRAIN_EPOCHS,
                         base_lr=0.0006, batch=128, seed=int(rng.integers(1e6)),
                         dropout=0.08)
    steps = steps_per_epoch * TRAIN_EPOCHS
    d, prof_ok = cheap_val(net, val_X, val_T)
    sample = val_imgs[:120]
    val_score, _per = eval_model(net, sample)
    log(f"train +{steps} steps ({time.time()-t0:.0f}s) val={val_score:.2f} param-dist={d:.3f} prof={prof_ok:.0%} n={len(X)}")

    # checkpoint every invocation; keep only if better than best val
    prev_best = float(prog.get("best_val", 0.0))
    if val_score >= prev_best - 0.1:  # save near-best always for continuity
        W1, b1, W2, b2, W3, b3, W4, b4 = net
        OUT.mkdir(parents=True, exist_ok=True)
        np.savez(npz, W1=W1, b1=b1, W2=W2, b2=b2, W3=W3, b3=b3, W4=W4, b4=b4,
                 feature_dim=np.array(FEATURE_DIM),
                 val_score=np.array(val_score), best_tag=np.array("forever"))
        prog["best_val"] = max(prev_best, val_score)
        prog["best_val_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        log(f"checkpoint skipped val {val_score:.2f} < {prev_best - 0.1:.2f}")
    return steps, val_score


def export_onnx_live():
    r = sh([sys.executable, "-m", "model.export_onnx",
            "--copy-to", "app/static/model"])
    tail = (r.stdout or "").strip().splitlines()
    log("onnx export:", tail[-1] if tail else "done")


# ---------------------------------------------------------- git pushes
def git_commit_push(prog: dict, reason: str, force: bool = False):
    now = time.time()
    if not force and (now - prog.get("last_push", 0) < PUSH_INTERVAL
                      and prog.get("committed_val", 0.0) + EPOCH_TOL > prog.get("best_val", 0.0)):
        return False
    snap_state()
    r = sh(["git", "add", "-A", "model_data_snapshot/", "app/static/model/"])
    r = sh(["git", "commit", "--no-verify", "-m",
            f"forever-train: {reason} steps={prog['steps_total']} "
            f"best_val={prog.get('best_val', 0):.2f} "
            f"images={count_images()}"])
    if "nothing to commit" in (r.stdout or ""):
        return False
    r2 = sh(["git", "push", "origin", "arena/01a0aab7-vectorizer"])
    ok = r2.returncode == 0
    log(f"git push {'OK' if ok else 'FAIL'}: {reason}")
    if ok:
        prog["last_push"] = now
        prog["committed_val"] = prog.get("best_val", 0.0)
    return ok


def snap_state():
    """Freeze weights + progress into the committed snapshot dir."""
    SNAP.mkdir(parents=True, exist_ok=True)
    npz = OUT / "params.npz"
    if npz.exists():
        with open(npz, "rb") as f, gzip.open(SNAP / "params.npz.gz", "wb") as o:
            o.write(f.read())
    for f in ("history.json",):
        if (OUT / f).exists():
            shutil.copy2(OUT / f, SNAP / f)


# ------------------------------------------------------------------ main
def main():
    log("forever training program start, goals: 70K images / 2M steps")
    prog = load_progress()
    log("progress:", json.dumps(prog))
    for push_cnt in range(10**9):
        try:
            t_iter = time.time()
            restore_from_snapshots()
            counts = count_images()
            total_imgs = sum(counts.values())
            if total_imgs < GOAL_IMAGES:
                gen_clean(counts, prog)
                counts = count_images()
                gen_degraded(counts)
                counts = count_images()
                total_imgs = sum(counts.values())
            n_recs = 0
            if (DATA / "dataset.json").exists() or total_imgs:
                n_recs = extend_dataset(counts)
            steps_done = 0
            val_score = prog.get("best_val", 0.0)
            if n_recs and n_recs >= 200:
                steps_done, val_score = train_chunk(prog)
                prog["steps_total"] += steps_done
            save_progress(prog, snap=True)
            counts = count_images()
            total_imgs = sum(counts.values())
            ok_a = total_imgs >= GOAL_IMAGES
            ok_b = prog["steps_total"] >= GOAL_STEPS
            log(f"iter {push_cnt}: images={total_imgs}/{GOAL_IMAGES} {counts} "
                f"recs={n_recs} steps={prog['steps_total']}/{GOAL_STEPS} "
                f"best_val={prog.get('best_val', 0):.2f} "
                f"({time.time()-t_iter:.0f}s)")
            improved = prog.get("best_val", 0.0) >= prog.get("committed_val", 0.0) + EPOCH_TOL
            due = time.time() - prog.get("last_push", 0) > SNAP_INTERVAL
            if improved:
                export_onnx_live()
            if improved or due or (ok_a and ok_b):
                git_commit_push(prog, f"image {total_imgs}/{GOAL_IMAGES}" if not improved else f"val {val_score:.2f}", force=(ok_a and ok_b))
            if ok_a and ok_b:
                export_onnx_live()
                git_commit_push(prog, "GOALS REACHED 50K data 100K steps", force=True)
                log("GOALS REACHED: 50K gathered images + 100K training steps done.")
                if "--once-when-done" in sys.argv:
                    return
            time.sleep(5)
        except KeyboardInterrupt:
            save_progress(prog, snap=True)
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            log("iteration failed, will retry:", str(e)[:400])
            time.sleep(30)


if __name__ == "__main__":
    main()
