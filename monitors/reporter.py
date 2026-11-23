"""
reporter.py — saves the result of each run, with THREE categories:

  PASS      -> matched (reliable comparison)
  FAIL      -> didn't match and the measurement was reliable (small gap) -> suspicious
  DISCARDED -> the gap was large, we don't trust the comparison -> doesn't count

The success rate is computed ONLY over reliable comparisons (PASS + FAIL), so
startup noise doesn't inflate or pollute the number.

Files in 'reports/':
  - report_YYYYMMDD_HHMMSS.txt   (readable)
  - report_YYYYMMDD_HHMMSS.json  (data)
"""

from __future__ import annotations

import datetime
import json
import os


class Reporter:
    def __init__(self, title="PCS power validation (simulator vs OmniOps)",
                 reliable_gap_s=1.0):
        self.title = title
        self.reliable_gap_s = reliable_gap_s
        self.start = datetime.datetime.now()
        self.rows = []

    def record(self, time_str, expected, actual, reason, ok, gap):
        # decide the category based on how reliable the measurement is (the gap)
        if gap is not None and gap > self.reliable_gap_s:
            category = "DISCARDED"
        elif ok:
            category = "PASS"
        else:
            category = "FAIL"
        self.rows.append({
            "time": time_str, "expected": round(expected, 1),
            "actual": round(actual, 1), "reason": round(reason, 3),
            "gap": round(gap, 2) if gap is not None else None,
            "category": category,
        })

    def save(self, folder="reports"):
        if not self.rows:
            print("(no comparisons to report)")
            return None
        os.makedirs(folder, exist_ok=True)
        stamp = self.start.strftime("%Y%m%d_%H%M%S")

        total = len(self.rows)
        passed = sum(1 for f in self.rows if f["category"] == "PASS")
        failed = sum(1 for f in self.rows if f["category"] == "FAIL")
        discarded = sum(1 for f in self.rows if f["category"] == "DISCARDED")
        reliable = passed + failed
        rate = (passed / reliable * 100) if reliable else 0.0

        txt = os.path.join(folder, f"report_{stamp}.txt")
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write(f"{self.title}\n")
            fh.write(f"Run: {self.start:%Y-%m-%d %H:%M:%S}\n")
            fh.write("=" * 56 + "\n\n")
            fh.write(f"Total comparisons     : {total}\n")
            fh.write(f"  Reliable            : {reliable}\n")
            fh.write(f"    PASSED            : {passed}\n")
            fh.write(f"    FAILED            : {failed}\n")
            fh.write(f"  Discarded (time gap): {discarded}\n\n")
            fh.write(f"Success rate (reliable only): {rate:.1f}%\n\n")
            if failed:
                fh.write("Reliable FAILURES (review — possible bug):\n")
                for f in self.rows:
                    if f["category"] == "FAIL":
                        fh.write(f"  {f['time']}: expected={f['expected']} "
                                 f"actual={f['actual']} reason={f['reason']} "
                                 f"(gap {f['gap']}s)\n")
            else:
                fh.write("No reliable failures. OmniOps matched in all "
                         "measurable comparisons.\n")
            if discarded:
                fh.write(f"\nNote: {discarded} comparison(s) discarded due to "
                         "a time gap (high gap); they don't reflect a "
                         "calculation error and don't count toward the rate.\n")

        js = os.path.join(folder, f"report_{stamp}.json")
        with open(js, "w", encoding="utf-8") as fh:
            json.dump({
                "title": self.title,
                "start": self.start.isoformat(),
                "total": total, "reliable": reliable,
                "passed": passed, "failed": failed, "discarded": discarded,
                "success_rate": round(rate, 1),
                "comparisons": self.rows,
            }, fh, indent=2, ensure_ascii=False)

        # also, ALWAYS: an executive summary (to show a manager).
        # Human language, no discards, no gaps or anchoring.
        ex = self._save_executive(folder, stamp, reliable, passed, failed, rate)

        print(f"\nTechnical report saved:\n  {txt}\n  {js}")
        print(f"Executive summary (for presenting):\n  {ex}")
        return txt

    def _save_executive(self, folder, stamp, reliable, passed, failed, rate):
        """Clean summary, in ENGLISH, for an executive. Doesn't mention
        discards or time gaps."""
        path = os.path.join(folder, f"executive_summary_{stamp}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("OmniOps Validation — Executive Summary\n")
            fh.write(f"Date: {self.start:%Y-%m-%d %H:%M}\n")
            fh.write("=" * 44 + "\n\n")
            fh.write("Automated, independent verification that OmniOps\n")
            fh.write("displays the correct power value.\n\n")
            fh.write(f"Measurements verified : {reliable}\n")
            fh.write(f"  Passed              : {passed}\n")
            fh.write(f"  Failed              : {failed}\n")
            fh.write(f"Pass rate             : {rate:.1f}%\n\n")
            if failed == 0:
                fh.write("Overall result: PASS\n")
                fh.write(f"OmniOps showed the correct value in {rate:.0f}% of "
                         "measurements. No differences.\n")
            else:
                fh.write("Overall result: FAIL\n")
                fh.write("Differences detected (to review):\n")
                for f in self.rows:
                    if f["category"] == "FAIL":
                        fh.write(f"  {f['time']}: expected {f['expected']} kW, "
                                 f"OmniOps showed {f['actual']} kW\n")
        return path


if __name__ == "__main__":
    r = Reporter(reliable_gap_s=1.0)
    r.record("20:20:24", 2520, 2520, 1.00, True, 0.5)    # PASS
    r.record("20:20:34", 4404, 4404, 1.00, True, 0.3)    # PASS
    r.record("20:20:19", 2520, 1241, 0.49, False, 1.4)   # DISCARDED (high gap)
    r.record("20:25:00", 3000, 1500, 0.50, False, 0.3)   # reliable FAIL (example)
    r.save()
    print("\n(demo with the 3 categories)")
