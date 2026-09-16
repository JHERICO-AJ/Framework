"""
time_anchor.py — TIME ANCHORING, in one place.

OmniOps runs one "tick" behind the simulator. Instead of comparing against the
simulator's current value, we keep a history and compare against the value at
the SAME instant (by timestamp). This logic used to be duplicated in the two
watchers.

  history = list of (epoch, kw)
  match_buffer(history, instant) -> ((epoch, kw), gap_in_seconds)

Run the self-check:  python time_anchor.py --self-check
"""

from __future__ import annotations

import sys

from shared.config.settings import BUFFER_S


def match_buffer(buffer, target_epoch):
    """From the history, the value whose time is CLOSEST to the target instant.
    Returns ((epoch, kw), gap) or (None, None) if the history is empty."""
    best, best_gap = None, None
    for ep, kw in buffer:
        gap = abs(ep - target_epoch)
        if best_gap is None or gap < best_gap:
            best, best_gap = (ep, kw), gap
    return best, best_gap


def prune(buffer, now, window_s=BUFFER_S):
    """Keeps only what's newer than `window_s` seconds in the history."""
    buffer[:] = [(e, v) for e, v in buffer if now - e <= window_s]
    return buffer


def _self_check():
    print("(anchoring test — no network)\n")
    # the simulator went through 100,200,300,400,500; OmniOps shows instant 1002
    buffer = [(1000.0, 100), (1001.0, 200), (1002.0, 300),
              (1003.0, 400), (1004.0, 500)]
    (ep, kw), gap = match_buffer(buffer, 1002.0)
    ok = kw == 300 and gap == 0.0
    print(f"  match 1002 -> kw={kw} gap={gap}  {'OK' if ok else 'FAIL'}")
    # pruning: with now=1004 and a 2s window, 1002,1003,1004 should remain
    b = list(buffer)
    prune(b, now=1004.0, window_s=2.0)
    ok2 = [v for _, v in b] == [300, 400, 500]
    print(f"  prune (2s window) -> {[v for _, v in b]}  {'OK' if ok2 else 'FAIL'}")
    print("\n=> " + ("OK ✓" if ok and ok2 else "FAIL ✗"))
    return ok and ok2


if __name__ == "__main__":
    sys.exit(0 if _self_check() else 1)
