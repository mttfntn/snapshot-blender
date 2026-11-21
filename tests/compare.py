"""Compare the behaviour of two versions of the add-on.

Usage:
    python tests/compare.py --old-rev REV [--new PATH] [--blender PATH]
    python tests/compare.py --old PATH   [--new PATH]

--old-rev extracts the add-on from a git revision (single-file or package
layout). Each version runs tests/behaviour_record.py in its own isolated
Blender (factory settings, scratch profile). The new version runs twice so
run-to-run noise is measured first: a difference that also appears between
two runs of the same code is noise, not a behaviour change.

Prints every differing record key with the differing fields, and exits 1
if old and new differ anywhere outside the noise.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from run_tests import find_blender, run_blender  # noqa: E402


def extract_rev(rev, dest):
    """Write the add-on as it was at `rev` into dest; return its path."""
    names = subprocess.run(["git", "-C", REPO, "ls-tree", "-r", "--name-only", rev],
                           capture_output=True, text=True, check=True).stdout.split()
    if "solid_snapshot/__init__.py" in names:
        files = [n for n in names if n.startswith("solid_snapshot/")]
        target = os.path.join(dest, "solid_snapshot")
    else:
        files = ["solid_snapshot.py"]
        target = os.path.join(dest, "solid_snapshot.py")
    for n in files:
        data = subprocess.run(["git", "-C", REPO, "show", "%s:%s" % (rev, n)], capture_output=True, check=True).stdout
        out = os.path.join(dest, n)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
    return target


def record(blender, addon, label):
    out_holder = {}

    def script_args(scratch):
        work = os.path.join(scratch, "work")
        os.makedirs(work)
        out_holder["out"] = os.path.join(scratch, "record.json")
        return ["--addon", addon, "--work", work, "--out", out_holder["out"]]

    print("recording %s: %s" % (label, addon), flush=True)
    code, output, scratch = run_blender(blender, os.path.join(HERE, "behaviour_record.py"), script_args, timeout=1200)
    try:
        with open(out_holder["out"], encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        print(output)
        sys.exit("%s: no record (Blender exit %s)" % (label, code))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if "<error>" in data["records"]:
        sys.exit("%s: recorder failed\n%s" % (label, data["records"]["<error>"]))
    return data["records"]


def diff(a, b, path=""):
    """List of (path, a_value, b_value) where two JSON values differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += diff(a.get(k, "<missing>"), b.get(k, "<missing>"), "%s/%s" % (path, k))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, "%s[%d]" % (path, i))
        return out
    return [] if a == b else [(path, a, b)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old")
    ap.add_argument("--old-rev")
    ap.add_argument("--new", default=os.path.join(REPO, "solid_snapshot"))
    ap.add_argument("--blender")
    ap.add_argument("--save", help="write all three records to this JSON file")
    args = ap.parse_args()
    if not (args.old or args.old_rev):
        ap.error("give --old or --old-rev")
    blender = find_blender(args.blender)

    tmp = tempfile.mkdtemp(prefix="solid_snapshot_compare_")
    try:
        old = args.old or extract_rev(args.old_rev, tmp)
        new_a = record(blender, os.path.abspath(args.new), "new (run 1)")
        new_b = record(blender, os.path.abspath(args.new), "new (run 2)")
        old_r = record(blender, os.path.abspath(old), "old")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump({"old": old_r, "new_1": new_a, "new_2": new_b}, f, indent=1, sort_keys=True)

    noise = {k: diff(new_a[k], new_b[k]) for k in new_a}
    noise = {k: v for k, v in noise.items() if v}
    print("\nrecords: %d  | noise between two runs of the new version: %d keys" % (len(new_a), len(noise)))
    for k, v in noise.items():
        print("  NOISE %s: %s" % (k, [p for p, _, _ in v]))

    changed = {}
    for k in sorted(set(old_r) | set(new_a)):
        d = diff(old_r.get(k, "<missing>"), new_a.get(k, "<missing>"))
        noisy_paths = {p for p, _, _ in noise.get(k, [])}
        d = [x for x in d if x[0] not in noisy_paths]
        if d:
            changed[k] = d
    print("old vs new: %d of %d keys differ" % (len(changed), len(new_a)))
    for k, d in changed.items():
        print("  DIFF %s" % k)
        for p, a, b in d[:12]:
            print("      %s\n          old: %s\n          new: %s" % (p, json.dumps(a)[:160], json.dumps(b)[:160]))
        if len(d) > 12:
            print("      ... %d more" % (len(d) - 12))
    sys.exit(1 if changed else 0)


if __name__ == "__main__":
    main()
