"""Check that PyTorch can see the GPU and run fp16 math.

Usage:  python scripts\\check_gpu.py
PyTorch is installed separately (Week 3); see docs/SETUP_WINDOWS.md.
"""

from __future__ import annotations

import platform
import sys
import time


def main() -> int:
    print(f"Python  : {sys.version.split()[0]} ({platform.system()} {platform.release()})")
    try:
        import torch
    except ImportError:
        print("PyTorch : not installed (expected until Week 3). See docs/SETUP_WINDOWS.md.")
        return 0

    print(f"PyTorch : {torch.__version__}")
    print(f"CUDA    : built for {torch.version.cuda}, available={torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        print("No CUDA device visible. Install the CUDA build of PyTorch and a recent driver.")
        return 1

    props = torch.cuda.get_device_properties(0)
    print(
        f"Device  : {props.name}, {props.total_memory / 1024**3:.1f} GiB, "
        f"compute {props.major}.{props.minor}"
    )
    print(f"bf16    : {torch.cuda.is_bf16_supported()}")

    a = torch.randn(4096, 4096, device="cuda", dtype=torch.float16)
    b = torch.randn(4096, 4096, device="cuda", dtype=torch.float16)
    torch.cuda.synchronize()
    start = time.perf_counter()
    for _ in range(10):
        _ = a @ b
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    tflops = 10 * 2 * 4096**3 / elapsed / 1e12
    print(f"fp16 matmul: {tflops:.1f} TFLOP/s (rough)")
    print("GPU check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
