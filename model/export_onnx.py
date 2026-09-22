"""Export the trained MLP to ONNX (runs everywhere: python on desktop,
onnxruntime-web in the browser).

Supports both old 2-layer (1047->160->5) and new 3-layer (1047->256->128->5) models.

Graph v2: x(1,F) -> Gemm(W1,b1) -> Relu -> Gemm(W2,b2) -> Relu -> Gemm(W3,b3) -> y(1,5)

Usage:  PYTHONPATH=vendor:. python -m model.export_onnx [--copy-to app/static/model]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


def build_onnx_2layer(W1, b1, W2, b2, feature_dim):
    X = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, feature_dim])
    Y = helper.make_tensor_value_info("out", TensorProto.FLOAT, [1, W2.shape[1]])
    w1t = numpy_helper.from_array(W1.T.astype(np.float32), name="w1")
    b1t = numpy_helper.from_array(b1.astype(np.float32), name="b1")
    w2t = numpy_helper.from_array(W2.T.astype(np.float32), name="w2")
    b2t = numpy_helper.from_array(b2.astype(np.float32), name="b2")
    n1 = helper.make_node("Gemm", ["x", "w1", "b1"], ["z1"], transB=1, name="gemm1")
    n2 = helper.make_node("Relu", ["z1"], ["a1"], name="relu1")
    n3 = helper.make_node("Gemm", ["a1", "w2", "b2"], ["out"], transB=1, name="gemm2")
    g = helper.make_graph([n1, n2, n3], "vectorizer-params", [X], [Y], [w1t, b1t, w2t, b2t])
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)])
    m.ir_version = 8
    onnx.checker.check_model(m)
    return m

def build_onnx_3layer(W1, b1, W2, b2, W3, b3, feature_dim):
    X = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, feature_dim])
    Y = helper.make_tensor_value_info("out", TensorProto.FLOAT, [1, W3.shape[1]])
    w1t = numpy_helper.from_array(W1.T.astype(np.float32), name="w1")
    b1t = numpy_helper.from_array(b1.astype(np.float32), name="b1")
    w2t = numpy_helper.from_array(W2.T.astype(np.float32), name="w2")
    b2t = numpy_helper.from_array(b2.astype(np.float32), name="b2")
    w3t = numpy_helper.from_array(W3.T.astype(np.float32), name="w3")
    b3t = numpy_helper.from_array(b3.astype(np.float32), name="b3")
    n1 = helper.make_node("Gemm", ["x", "w1", "b1"], ["z1"], transB=1, name="gemm1")
    n2 = helper.make_node("Relu", ["z1"], ["a1"], name="relu1")
    n3 = helper.make_node("Gemm", ["a1", "w2", "b2"], ["z2"], transB=1, name="gemm2")
    n4 = helper.make_node("Relu", ["z2"], ["a2"], name="relu2")
    n5 = helper.make_node("Gemm", ["a2", "w3", "b3"], ["out"], transB=1, name="gemm3")
    g = helper.make_graph([n1, n2, n3, n4, n5], "vectorizer-params-v2", [X], [Y],
                          [w1t, b1t, w2t, b2t, w3t, b3t])
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)])
    m.ir_version = 8
    onnx.checker.check_model(m)
    return m

def build_onnx_4layer(W1, b1, W2, b2, W3, b3, W4, b4, feature_dim):
    X = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, feature_dim])
    Y = helper.make_tensor_value_info("out", TensorProto.FLOAT, [1, W4.shape[1]])
    w1t = numpy_helper.from_array(W1.T.astype(np.float32), name="w1")
    b1t = numpy_helper.from_array(b1.astype(np.float32), name="b1")
    w2t = numpy_helper.from_array(W2.T.astype(np.float32), name="w2")
    b2t = numpy_helper.from_array(b2.astype(np.float32), name="b2")
    w3t = numpy_helper.from_array(W3.T.astype(np.float32), name="w3")
    b3t = numpy_helper.from_array(b3.astype(np.float32), name="b3")
    w4t = numpy_helper.from_array(W4.T.astype(np.float32), name="w4")
    b4t = numpy_helper.from_array(b4.astype(np.float32), name="b4")
    n1 = helper.make_node("Gemm", ["x", "w1", "b1"], ["z1"], transB=1, name="gemm1")
    n2 = helper.make_node("Relu", ["z1"], ["a1"], name="relu1")
    n3 = helper.make_node("Gemm", ["a1", "w2", "b2"], ["z2"], transB=1, name="gemm2")
    n4 = helper.make_node("Relu", ["z2"], ["a2"], name="relu2")
    n5 = helper.make_node("Gemm", ["a2", "w3", "b3"], ["z3"], transB=1, name="gemm3")
    n6 = helper.make_node("Relu", ["z3"], ["a3"], name="relu3")
    n7 = helper.make_node("Gemm", ["a3", "w4", "b4"], ["out"], transB=1, name="gemm4")
    g = helper.make_graph([n1, n2, n3, n4, n5, n6, n7], "vectorizer-params-v3", [X], [Y],
                          [w1t, b1t, w2t, b2t, w3t, b3t, w4t, b4t])
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)])
    m.ir_version = 8
    onnx.checker.check_model(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", default="model/out/params.npz")
    ap.add_argument("--out", default="model/out/params.onnx")
    ap.add_argument("--copy-to", default="app/static/model")
    args = ap.parse_args()

    z = np.load(args.npz, allow_pickle=True)
    F = int(z["feature_dim"])
    if "W4" in z:
        W1, b1, W2, b2, W3, b3, W4, b4 = z["W1"], z["b1"], z["W2"], z["b2"], z["W3"], z["b3"], z["W4"], z["b4"]
        model = build_onnx_4layer(W1, b1, W2, b2, W3, b3, W4, b4, F)
        print(f"Building 4-layer model: {F}->{W1.shape[1]}->{W2.shape[1]}->{W3.shape[1]}->{W4.shape[1]}")
        def numpy_forward(x):
            return (np.maximum(np.maximum(np.maximum(x @ W1 + b1, 0) @ W2 + b2, 0) @ W3 + b3, 0) @ W4 + b4)
    elif "W3" in z:
        W1, b1, W2, b2, W3, b3 = z["W1"], z["b1"], z["W2"], z["b2"], z["W3"], z["b3"]
        model = build_onnx_3layer(W1, b1, W2, b2, W3, b3, F)
        print(f"Building 3-layer model: {F}->{W1.shape[1]}->{W2.shape[1]}->{W3.shape[1]}")
        def numpy_forward(x):
            return (np.maximum(np.maximum(x @ W1 + b1, 0) @ W2 + b2, 0) @ W3 + b3)
    else:
        W1, b1, W2, b2 = z["W1"], z["b1"], z["W2"], z["b2"]
        model = build_onnx_2layer(W1, b1, W2, b2, F)
        print(f"Building 2-layer model: {F}->{W1.shape[1]}->{W2.shape[1]}")
        def numpy_forward(x):
            return np.maximum(x @ W1 + b1, 0) @ W2 + b2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, out)
    print(f"onnx saved -> {out}  ({out.stat().st_size / 1024:.0f} KB)")

    # validate against the numpy forward
    import onnxruntime as ort
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(0)
    ok = True
    max_err = 0
    for _ in range(30):
        x = rng.random((1, F), dtype=np.float32)
        y_onnx = sess.run(None, {"x": x})[0]
        y_np = numpy_forward(x)
        d = float(np.abs(y_onnx - y_np).max())
        max_err = max(max_err, d)
        if d > 1e-4:
            ok = False
            print(f"MISMATCH {d}")
    print(f"onnx vs numpy: {'OK' if ok else 'FAILED'} max_err={max_err:.6f}")

    if args.copy_to:
        dest = Path(args.copy_to)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(out, dest / "params.onnx")
        print(f"copied -> {dest / 'params.onnx'}")

if __name__ == "__main__":
    main()
