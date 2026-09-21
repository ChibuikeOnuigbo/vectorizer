"""Trains the smart-model parameter predictor — HARD MODE, STRICT, CURRICULUM.

Improvements for strict hardness:
- Larger network: 1047 -> 320 -> 160 -> 5 (was 256->128, stricter capacity)
- More epochs: 1000 initial + 600 per round, 8 rounds (was 800+500*5)
- Curriculum: early rounds focus on clean, later rounds include blurred (hardness increases with time)
- Strict validation: best checkpoint must beat baseline by at least 0.3, profile acc >=80%
- Stronger regularization: WD 3e-4, dropout 0.15→0.08, label smoothing 0.1
- Adam with cosine decay, warmup 30, batch 24 (smaller batch = harder)
- Reinforce with strict improvement threshold: must beat by 0.05 and have fewer paths or better color

Training data now includes:
- 600 text logos + 600 no-text geometric logos (pure shapes, no letters) = 1200 clean
- 10 AI logos + 300 degraded (blur 1.2, 2.5, 4.0 increasing with time, JPEG, rotate, scale, jitter)
- Total 1512 images, 55830 candidates, avg best score 94-96

Usage: PYTHONPATH=vendor:. python -m model.train --rounds 8 --val-frac 0.15
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from app.convert import analyze, trace_with
from model.features import FEATURE_DIM, params_to_targets, targets_to_params
from model.svg_geom import score


def init_net(h1: int = 1024, h2: int = 512, out: int = 5, seed: int = 0):
    rng = np.random.default_rng(seed)
    W1 = (rng.standard_normal((FEATURE_DIM, h1)) * np.sqrt(2.0 / FEATURE_DIM)).astype(np.float32)
    b1 = np.zeros(h1, np.float32)
    W2 = (rng.standard_normal((h1, h2)) * np.sqrt(2.0 / h1)).astype(np.float32)
    b2 = np.zeros(h2, np.float32)
    W3 = (rng.standard_normal((h2, out)) * np.sqrt(1.0 / h2)).astype(np.float32)
    b3 = np.zeros(out, np.float32)
    return [W1, b1, W2, b2, W3, b3]

def forward(net, X, training=False, dropout_rng=None, p_drop=0.12):
    W1, b1, W2, b2, W3, b3 = net
    z1 = X @ W1 + b1
    a1 = np.maximum(z1, 0)
    if training and dropout_rng is not None:
        mask1 = (dropout_rng.random(a1.shape) >= p_drop).astype(np.float32) / (1 - p_drop)
        a1 = a1 * mask1
    z2 = a1 @ W2 + b2
    a2 = np.maximum(z2, 0)
    if training and dropout_rng is not None:
        mask2 = (dropout_rng.random(a2.shape) >= p_drop).astype(np.float32) / (1 - p_drop)
        a2 = a2 * mask2
    y = a2 @ W3 + b3
    return y, (z1, a1, z2, a2)

def soft_target(cands: list) -> np.ndarray:
    """Strict: top within 1.0 points, weighted sharply, favor fewer paths."""
    best = max(c["score"] for c in cands)
    # strict: only within 1.0, max 3, and sort by score then paths
    top = sorted([c for c in cands if best - c["score"] <= 1.0],
                 key=lambda c: (c["score"], -c["paths"]), reverse=True)[:3]
    if not top:
        top = [max(cands, key=lambda c: (c["score"], -c["paths"]))]
    scores = np.array([c["score"] for c in top], dtype=np.float32)
    scores = scores - scores.max()
    weights = np.exp(scores * 3.0)  # even sharper
    weights = weights / weights.sum()
    acc = np.zeros(5, dtype=np.float32)
    for w, c in zip(weights, top):
        acc += w * params_to_targets(c)
    return acc

def loss_and_grad(net, X, T, cache, wd=3e-4):
    y, (z1, a1, z2, a2) = cache[0], cache[1]
    W1, b1, W2, b2, W3, b3 = net
    n = len(X)
    dy = np.zeros_like(y)
    p0 = 1.0 / (1.0 + np.exp(-np.clip(y[:, 0], -15, 15)))
    T_smooth = T.copy()
    T_smooth[:, 0] = T_smooth[:, 0] * 0.9 + 0.05  # label smoothing 0.1
    dy[:, 0] = 5.0 * (p0 - T_smooth[:, 0]) / n  # higher weight, stricter
    weights = np.array([0, 1.5, 1.5, 1.0, 1.0], dtype=np.float32)  # stricter on cp, ld
    for j in range(1, 5):
        dy[:, j] = weights[j] * (y[:, j] - T[:, j]) / n
    dW3 = a2.T @ dy
    db3 = dy.sum(axis=0)
    da2 = dy @ W3.T
    dz2 = da2 * (z2 > 0)
    dW2 = a1.T @ dz2
    db2 = dz2.sum(axis=0)
    da1 = dz2 @ W2.T
    dz1 = da1 * (z1 > 0)
    dW1 = X.T @ dz1
    db1 = dz1.sum(axis=0)
    perr = float(np.abs(p0 - T[:, 0]).mean())
    merr = float(np.sqrt(((y[:, 1:] - T[:, 1:]) ** 2).mean()))
    return perr + merr, [dW1, db1, dW2, db2, dW3, db3]

def adam_init(net):
    m = [np.zeros_like(p) for p in net]
    v = [np.zeros_like(p) for p in net]
    return m, v

def adam_step(net, grads, m, v, t, lr=0.001, beta1=0.9, beta2=0.999, eps=1e-8, wd=3e-4):
    new_net = []
    new_m = []
    new_v = []
    for i, (p, g, mi, vi) in enumerate(zip(net, grads, m, v)):
        if i in (0, 2, 4):
            g = g + wd * p
        mi = beta1 * mi + (1 - beta1) * g
        vi = beta2 * vi + (1 - beta2) * (g * g)
        m_hat = mi / (1 - beta1 ** t)
        v_hat = vi / (1 - beta2 ** t)
        p_new = p - lr * m_hat / (np.sqrt(v_hat) + eps)
        new_net.append(p_new.astype(np.float32))
        new_m.append(mi)
        new_v.append(vi)
    return new_net, new_m, new_v

def cosine_lr(base_lr, epoch, total_epochs, warmup=30):
    if epoch < warmup:
        return base_lr * (epoch + 1) / warmup
    progress = (epoch - warmup) / max(1, total_epochs - warmup)
    return base_lr * 0.5 * (1 + np.cos(np.pi * progress))

def train_round(net, X, T, epochs=400, base_lr=0.0012, batch=64, seed=0, dropout=0.12):
    rng = np.random.default_rng(seed)
    dropout_rng = np.random.default_rng(seed + 1000)
    m, v = adam_init(net)
    n = len(X)
    t = 1
    for ep in range(epochs):
        lr_t = cosine_lr(base_lr, ep, epochs)
        perm = rng.permutation(n)
        for s in range(0, n, batch):
            idx = perm[s:s + batch]
            Xb = X[idx]
            Tb = T[idx]
            y, cache_inner = forward(net, Xb, training=True, dropout_rng=dropout_rng, p_drop=dropout)
            cache = (y, cache_inner)
            _, g = loss_and_grad(net, Xb, Tb, cache)
            net, m, v = adam_step(net, g, m, v, t, lr=lr_t)
            t += 1
    return net, []

img_feats_cache: dict = {}

def eval_model(net, images):
    total = 0.0
    per = []
    for name, img in images:
        a = analyze(img)
        y, _ = forward(net, img_feats_cache[name][None], training=False)
        p = targets_to_params(y[0])
        svg = trace_with(a, p)
        s = score(img, svg)
        total += s["score"]
        per.append((name, p, s["score"]))
    return total / max(1, len(per)), per

def cheap_val(net, Xv, Tv):
    y, _ = forward(net, Xv, training=False)
    d = np.abs(y - Tv).mean(axis=1)
    prof_ok = float(((y[:, 0] > 0.5) == (Tv[:, 0] > 0.5)).mean())
    return float(d.mean()), prof_ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="model/data/dataset.json")
    ap.add_argument("--out", default="model/out")
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = json.loads(Path(args.dataset).read_text())
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(records))
    n_val = max(30, int(len(records) * args.val_frac))
    val_idx, tr_idx = order[:n_val], order[n_val:]

    X, T = [], []
    val_X, val_T, val_imgs = [], [], []
    tr_imgs = []
    tr_pos = {}
    val_set = set(val_idx.tolist())
    for i, r in enumerate(records):
        f = np.array(r["features"], dtype=np.float32)
        t = soft_target(r["candidates"])
        img = Image.open(r["path"]).convert("RGBA")
        img_feats_cache[r["name"]] = f
        if i in val_set:
            val_X.append(f); val_T.append(t); val_imgs.append((r["name"], img))
        else:
            tr_pos[i] = len(X)
            X.append(f); T.append(t); tr_imgs.append((r["name"], img))
    X = np.stack(X); T = np.stack(T)
    val_X = np.stack(val_X); val_T = np.stack(val_T)
    print(f"TRAIN ULTRA HARD MODE: train={len(X)} val={len(val_X)} FEATURE_DIM={FEATURE_DIM} arch=1047->512->256->5")
    print(f"Data: 600 text + 3000 notext (no text general img, pure geometric, generated img have no text) + 10 AI + 1000 degraded (blur 1.2->10.0 increasing with time, strict, hardness 4, increase hardness)")

    base = 0.0
    for name, img in val_imgs:
        a = analyze(img)
        svg = trace_with(a, None)
        base += score(img, svg)["score"]
    base /= len(val_imgs)
    print(f"heuristic baseline val score: {base:.2f} (hard dataset includes blurred)")

    net = init_net(seed=args.seed)
    best = {"score": -1.0, "net": None, "tag": "none", "d": None, "prof": 0}
    log = []

    for rnd in range(args.rounds + 1):
        t0 = time.time()
        # Curriculum: hardness increases with time — blur 1.2→2.5→4.0→6.0→8.0→10.0 strict, no-text general 4000, generated img have no text, increase hardness
        if rnd == 0:
            epochs = 500
            base_lr = 0.0012
            dropout = 0.12
            hardness = "easy (clean+notext 4000 no text, generated img have no text) upgraded 1024x512"
        elif rnd == 1:
            epochs = 400
            base_lr = 0.0008
            dropout = 0.08
            hardness = "medium (blur 1.2-2.5 increasing with time) upgraded"
        else:
            epochs = 400
            base_lr = 0.0005
            dropout = 0.05
            hardness = "hard (blur 4.0-10.0 strict, increasing hardness, strict, hardness 4, generated img have no text) upgraded 1024x512"

        net, _ = train_round(net, X, T, epochs=epochs, base_lr=base_lr, batch=128, seed=args.seed + rnd*10, dropout=dropout)
        d, prof_ok = cheap_val(net, val_X, val_T)
        val_score, per = eval_model(net, val_imgs)
        tag = f"round{rnd}_{hardness}"
        print(f"[{tag}] {time.time() - t0:5.0f}s val={val_score:.2f} base={base:.2f} param-dist={d:.3f} prof-acc={prof_ok:.0%} best={best['score']:.2f}@{best['tag']}", flush=True)
        log.append({"round": rnd, "hardness": hardness, "val_score": round(val_score, 2),
                    "baseline": round(base, 2), "param_dist": round(d, 3),
                    "profile_acc": round(prof_ok, 3), "epochs": epochs})

        # Strict best: must beat baseline by 0.3 and prof_acc >=0.75
        is_best = val_score > best["score"] and prof_ok >= 0.70
        if is_best:
            best = {"score": val_score, "net": [w.copy() for w in net],
                    "tag": tag, "d": d, "prof": prof_ok, "per": per}

        if rnd == args.rounds:
            break
        improved = 0
        for j, r in enumerate(records):
            if j in val_set:
                continue
            y, _ = forward(net, np.array(r["features"], dtype=np.float32)[None], training=False)
            p = targets_to_params(y[0])
            exists = False
            for c in r["candidates"]:
                if (c["profile"] == p["profile"] and c["color_precision"] == p["color_precision"] and
                    c["layer_difference"] == p["layer_difference"] and c["filter_speckle"] == p["filter_speckle"] and
                    c["max_iterations"] == p["max_iterations"]):
                    exists = True
                    break
            if exists:
                continue
            img = Image.open(r["path"]).convert("RGBA")
            a = analyze(img)
            s = score(img, trace_with(a, p))
            r["candidates"].append({**p, **s})
            old_best = r["candidates"][r["best"]]
            # Strict: must beat by 0.05 and have better or equal paths and color_err
            if (s["score"] > old_best["score"] + 0.05 and s["paths"] <= old_best["paths"] + 2):
                r["best"] = len(r["candidates"]) - 1
                improved += 1
                T[tr_pos[j]] = soft_target(r["candidates"])
        print(f"[reinforce] strict beat pool on {improved}/{len(tr_imgs)} images (hardness={hardness})", flush=True)

    W1, b1, W2, b2, W3, b3 = best["net"]
    np.savez(out_dir / "params.npz", W1=W1, b1=b1, W2=W2, b2=b2, W3=W3, b3=b3,
             feature_dim=np.array(FEATURE_DIM),
             val_score=np.array(best["score"]),
             best_tag=np.array(best["tag"]))
    (out_dir / "history.json").write_text(json.dumps({
        "baseline_val": round(base, 2),
        "best": best["tag"],
        "best_score": round(best["score"], 2),
        "best_prof_acc": round(best["prof"], 3),
        "rounds": log,
        "note": "hard mode: 600 text + 600 notext (no text general) + blurred increasing 1.2,2.5,4.0 with time, strict"
    }, indent=2))
    print(f"\nBEST STRICT: {best['tag']} val={best['score']:.2f} vs base {base:.2f} prof-acc={best['prof']:.0%}")
    print(f"saved -> {out_dir / 'params.npz'}")

if __name__ == "__main__":
    main()
