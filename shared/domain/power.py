"""PURE power domain: compare the expected value (sum from the simulator)
against the real one (API/UI), with tolerances. No network — testable standalone."""
from __future__ import annotations

from shared.config.settings import TOL_ABS_KW, TOL_REL


def matches(expected_kw, actual_kw, abs_tol=TOL_ABS_KW, rel_tol=TOL_REL):
    """True if actual ≈ expected within absolute OR relative tolerance."""
    if expected_kw is None or actual_kw is None:
        return False
    diff = abs(actual_kw - expected_kw)
    tol = max(abs_tol, abs(expected_kw) * rel_tol)
    return diff <= tol


def _self_check():
    ok = matches(2500, 2480) and not matches(2500, 1000) and matches(0, 10)
    print("power.matches:", "OK ✓" if ok else "FAIL ✗")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if _self_check() else 1)
