"""Build the installable extension zip into dist/.

Usage:
    python tools/build.py [--blender PATH]

Copies solid_snapshot/ plus the repo's LICENSE into a temporary staging
folder (so the license ships in the package without a second copy in git),
then runs Blender's own `extension validate` and `extension build`.
Prints the path of the built zip on the last line.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tests"))
from run_tests import find_blender  # noqa: E402  (same lookup as the tests)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blender")
    ap.add_argument("--output-dir", default=os.path.join(REPO, "dist"))
    args = ap.parse_args()
    blender = find_blender(args.blender)

    staging = tempfile.mkdtemp(prefix="solid_snapshot_build_")
    try:
        pkg = os.path.join(staging, "solid_snapshot")
        shutil.copytree(os.path.join(REPO, "solid_snapshot"), pkg,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copyfile(os.path.join(REPO, "LICENSE"), os.path.join(pkg, "LICENSE"))
        os.makedirs(args.output_dir, exist_ok=True)
        env = dict(os.environ, BLENDER_USER_RESOURCES=os.path.join(staging, "profile"))
        for cmd in (["extension", "validate", pkg],
                    ["extension", "build", "--source-dir", pkg, "--output-dir", args.output_dir]):
            print("$ blender --command " + " ".join(cmd), flush=True)
            subprocess.run([blender, "--factory-startup", "--command", *cmd], env=env, check=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    zips = sorted((os.path.join(args.output_dir, f) for f in os.listdir(args.output_dir) if f.endswith(".zip")),
                  key=os.path.getmtime)
    print(zips[-1])


if __name__ == "__main__":
    main()
