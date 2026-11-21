"""Run the Solid Snapshot test suite in an isolated Blender instance.

Usage:
    python tests/run_tests.py [--blender PATH] [--addon PATH] [--keep]

Blender is found from --blender, the BLENDER environment variable, or the
usual install locations. --addon defaults to the package folder of this repo.

Isolation: every run uses a new temporary folder that serves as the user
profile (BLENDER_USER_RESOURCES) and the work folder, plus --factory-startup,
so neither a running Blender nor your real preferences are touched.

Exit code 0 means all tests passed. The run also fails if Blender printed a
Python traceback outside the tests (for example from a panel draw).
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WINDOW = ["--window-geometry", "0", "0", "1280", "720"]


def find_blender(explicit=None):
    candidates = [explicit, os.environ.get("BLENDER")]
    candidates += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender 5.3*\blender.exe"), reverse=True)
    candidates += ["/Applications/Blender.app/Contents/MacOS/Blender", shutil.which("blender")]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    sys.exit("Blender not found: pass --blender or set BLENDER")


def run_blender(blender, script, script_args, timeout=300, extra_env=None):
    """Start Blender with the UI on a scratch profile and run a script in it.

    Returns (exit code, combined output, scratch folder).
    """
    scratch = tempfile.mkdtemp(prefix="solid_snapshot_test_")
    env = dict(os.environ)
    env["BLENDER_USER_RESOURCES"] = os.path.join(scratch, "profile")
    env.update(extra_env or {})
    cmd = [blender, "--factory-startup", "--no-window-focus", *WINDOW]
    if sys.platform.startswith("linux"):
        cmd += ["--gpu-backend", "opengl"]
    # --python-exit-code: if the script itself fails (e.g. a syntax error)
    # Blender exits instead of staying open until the timeout.
    cmd += ["--python-exit-code", "2", "--python", script, "--", *script_args(scratch)]
    try:
        proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as ex:  # Blender is killed by subprocess.run
        out = ex.output.decode("utf-8", "replace") if isinstance(ex.output, bytes) else (ex.output or "")
        return "timeout after %ss" % timeout, out, scratch
    return proc.returncode, proc.stdout, scratch


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blender")
    ap.add_argument("--addon", default=os.path.join(REPO, "solid_snapshot"))
    ap.add_argument("--json", help="also copy the result JSON here")
    ap.add_argument("--keep", action="store_true", help="keep the scratch folder")
    args = ap.parse_args()

    blender = find_blender(args.blender)
    addon = os.path.abspath(args.addon)
    if not os.path.exists(addon):
        sys.exit("add-on not found: %s" % addon)

    def script_args(scratch):
        work = os.path.join(scratch, "work")
        os.makedirs(work)
        return ["--addon", addon, "--work", work, "--out", os.path.join(scratch, "result.json")]

    print("Blender: %s\nAdd-on:  %s" % (blender, addon), flush=True)
    code, output, scratch = run_blender(blender, os.path.join(HERE, "blender_tests.py"), script_args)
    result_path = os.path.join(scratch, "result.json")
    ok = True
    if not os.path.isfile(result_path):
        print(output)
        print("No result file: Blender exited with %s before finishing" % code)
        ok = False
    else:
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
        if args.json:
            shutil.copyfile(result_path, args.json)
        print("Blender version: %s" % result["blender"])
        for r in result["results"]:
            print("  %s  %s%s" % ("PASS" if r["ok"] else "FAIL", r["name"],
                                  "" if r["ok"] else "\n        " + r["error"]))
        print("%d passed, %d failed in %ss" % (result["passed"], result["failed"], result["seconds"]))
        ok = result["failed"] == 0 and result["passed"] > 0
        # Errors raised outside the test functions (e.g. in a panel draw callback)
        # are only printed by Blender, so scan the output for them.
        stray = [line for line in output.splitlines() if line.startswith("Traceback")]
        expected = sum(not r["ok"] for r in result["results"])
        if len(stray) > expected:
            print(output)
            print("Blender printed %d unexpected traceback(s)" % (len(stray) - expected))
            ok = False
    if args.keep:
        print("Scratch folder kept: %s" % scratch)
    else:
        shutil.rmtree(scratch, ignore_errors=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
