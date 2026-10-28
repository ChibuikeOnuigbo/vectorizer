"""Desktop-mode CLI: vectorize an image using the smart model (python
onnxruntime), with --no-model to fall back to the heuristic pipeline.

Usage:
  PYTHONPATH=vendor:. python -m model.cli input.png [--out out.svg] [--no-model]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from app.convert import vectorize
from model.features import image_features, targets_to_params


def model_params(onnx_path: str, img: Image.Image) -> dict:
    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    x = image_features(img).reshape(1, -1).astype(np.float32)
    y = sess.run(None, {"x": x})[0][0]
    return targets_to_params(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out", default=None)
    ap.add_argument("--onnx", default="app/static/model/params.onnx")
    ap.add_argument("--no-model", action="store_true")
    args = ap.parse_args()

    img = Image.open(args.image)
    params = None
    if not args.no_model and Path(args.onnx).exists():
        params = model_params(args.onnx, img)
        print(f"model params: {params}")

    res = vectorize(Path(args.image).read_bytes(), params)
    out = args.out or Path(args.image).with_suffix(".svg")
    Path(out).write_text(res["svg"])
    print(f"wrote {out}  meta: {res['meta']}")


if __name__ == "__main__":
    main()
