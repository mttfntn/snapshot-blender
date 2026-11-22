# Handover: Solid Snapshot

## What it is

A Blender add-on (packaged as a Blender **extension**) that saves a snapshot
of the 3D viewport in Standard colors, without permanently changing the
scene's color management, and can bookmark the view as a camera bound to a
timeline marker. User-facing description: [README.md](README.md).

It is an original project, not a fork: there is no upstream to merge from.

## What you need

| Need | Version / note |
| --- | --- |
| Blender | **5.3.x** (the only supported and tested version) |
| Python | 3.9+ on your PATH, only to run the test/build scripts (the add-on itself uses Blender's Python) |
| git | any recent version |
| GitHub | push access to `mttfntn/snapshot-blender` (public) |

No third-party Python packages are used anywhere.

## How the code is organized

| Path | Purpose |
| --- | --- |
| `solid_snapshot/__init__.py` | The whole add-on: helpers, settings, operators, panel, registration |
| `solid_snapshot/blender_manifest.toml` | Extension metadata: id, version, supported Blender range, license |
| `tests/run_tests.py` | Starts an isolated Blender and runs the test suite; exit code 0 = pass |
| `tests/blender_tests.py` | The tests themselves (run inside Blender) |
| `tests/compare.py` | Compares the behaviour of an old git revision with the current code |
| `tests/behaviour_record.py` | Records 180 option combinations inside Blender for `compare.py` |
| `tools/build.py` | Builds `dist/solid_snapshot-X.Y.Z.zip` with Blender's own extension builder |
| `tools/ci/download_blender.sh` | CI: downloads Blender with retries, mirrors and checksum check |
| `.github/workflows/tests.yml` | CI: tests + build on every push to `main` and on pull requests |
| `.github/workflows/release.yml` | CI: on a `vX.Y.Z` tag, tests, builds and publishes a GitHub release |
| `LICENSE` | GPL-3.0-or-later; copied into the package at build time |
| `README.md`, `HANDOVER.md`, `AGENTS.md` | Docs (not shipped in the package) |

## How the main feature works

Everything happens in `SOLIDSNAP_OT_snapshot.execute()`:

1. **Refuse unsaved files.** Images are saved relative to the `.blend`.
2. **Pick names.** `next_snapshot_name()` returns the next free `Snap_NNN`
   (checking both existing objects and files already in the folder). In
   override mode, `marker_camera_on_frame()` finds the camera bound to a
   marker on the current frame and reuses its name and image path.
3. **Store settings**: `store_color_management(scene)` and
   `store_render_settings(scene)` (resolution, transparency, file format,
   the output color override and the override's own values), plus the
   viewport overlay toggle.
4. **Change settings temporarily** inside `try`: Standard view transform,
   overlays, viewport-sized resolution, PNG, output color set to
   *Follow Scene*.
5. **Render and save**: `bpy.ops.render.opengl(view_context=True)` with a
   context override pointing at the viewport's main region, then
   `Render Result.save_render()`, which applies the scene's (now Standard)
   color management.
6. **Restore everything** in `finally`, so a failure never leaves the
   user's settings changed.
7. **Camera / marker** (after the image is saved): `camera_from_view()`
   builds a camera from the view's location, rotation and distance, with a
   72 mm sensor at the viewport lens (Blender's viewport equivalence);
   `bind_marker()` binds it to a marker on the current frame;
   `update_camera_from_view()` moves an existing camera in override mode.

Panel settings are a `PropertyGroup` on the scene (`scene.solid_snapshot`),
so they are saved per `.blend`.

## How to make a change

1. Edit `solid_snapshot/__init__.py`.
2. If behaviour changes, add or adjust a test in `tests/blender_tests.py`
   (one function decorated with `@test`; each test gets a fresh factory scene).
3. Run the tests (below). For refactors, also run the behaviour comparison
   against the previous commit and make sure it reports no differences:
   `python tests/compare.py --old-rev HEAD`.
4. To try it by hand, build the zip and install it in Blender (see Release),
   or point Blender at the folder.

## How to run the tests

```
python tests/run_tests.py
```

Options: `--blender PATH` (or set `BLENDER`), `--addon PATH` to test another
copy, `--keep` to keep the scratch folder, `--json FILE` to save results.

The runner starts a **separate** Blender with `--factory-startup`, a scratch
user profile (`BLENDER_USER_RESOURCES`) and a fixed 1280x720 window, so a
Blender you have open and your real preferences are never touched. A window
appears for about 15 seconds: the viewport render needs a real window.

Behaviour comparison between two versions:

```
python tests/compare.py --old-rev <git revision>
```

## How to make a release

1. Update `version` in `solid_snapshot/blender_manifest.toml` (e.g. `1.1.0`).
2. Nothing to change in `README.md`: its release, license and language badges read GitHub, and the Blender badge reads the manifest.
3. Commit and push to `main`; wait for the **tests** workflow to pass.
4. Create an **annotated** tag whose message is the release notes, and push it:
   ```
   git tag -a v1.1.0 -m "Solid Snapshot 1.1.0

   - what changed"
   git push origin v1.1.0
   ```
   The message is rendered as Markdown on GitHub: text in angle brackets
   such as `<blend>` disappears (read as HTML), so write `[blend]` or put it
   in backticks.
5. The **release** workflow re-runs the tests, builds the zip and publishes a
   GitHub release with the zip attached and the tag message as notes. It
   refuses lightweight tags and tags that don't match the manifest version.

Local build without releasing: `python tools/build.py` writes `dist/*.zip`.

## Bringing in updates from an original project

There is none: this project was written from scratch, not forked. If you
ever base it on another add-on, add it as a remote (`git remote add upstream
URL`), merge with `git fetch upstream && git merge upstream/main`, run the
tests and the comparison, and credit the original authors in README and
LICENSE.

## Things to know

- **The viewport matrix is stale until a redraw.** `rv3d.view_matrix` only
  updates when Blender draws; cameras are built from `view_location`,
  `view_rotation` and `view_distance` instead.
- **Output color override.** With Render Properties > Output > Color
  Management set to *Override*, saved images use the override, not the scene.
  The add-on sets *Follow Scene* while saving. Switching back to *Override*
  makes Blender copy the scene settings into the override, so the override's
  own values are stored and restored too.
- **View transforms and looks are dynamic enums.** Their real items are not
  listed in `bl_rna`; the tests read them from the error message of an
  invalid assignment.
- **Errors from operators.** An operator that reports `{'ERROR'}` makes a
  Python `bpy.ops` call raise `RuntimeError`; tests rely on that.
- **Class docstrings are user-visible** on Blender classes (tooltips), so
  operators, panels and the property group use `#` comments instead.
- **A failing `--python` script leaves Blender open**; the test runner passes
  `--python-exit-code 2` and has a timeout.
- **Timers vanish on file load** unless registered with `persistent=True`.
- **PNG files contain a date**, so compare pixels, not file bytes.
- **Ortho cameras** are placed `view_distance + clip_end` behind the view
  centre with clipping `~0..2*clip_end`; this does not change framing.
  Blender clamps `clip_start = 0` to its tiny minimum.
- CI runs Blender on Linux under `xvfb` with software OpenGL (Mesa).
- CI uploads **no Actions artifacts**. Artifact storage is one quota for the
  whole GitHub account, and other repos had filled it (the first CI run failed
  on that). Test results are in the job log; the release job builds its own
  zip and attaches it to the release, which doesn't count against that quota.
  Blender itself is kept in the Actions cache (a separate limit).

## Known limits

- Only Blender 5.3 is supported and tested (CI: Linux; locally: Windows).
- The saved camera frames exactly like the viewport only when the render
  resolution has the viewport's aspect ratio (sensor fit is Auto).
- "Add Timeline Marker" reuses and renames a marker already on that frame.
- Override mode overwrites the image at the camera's stored path.
- Undo removes the camera/marker but not the image file on disk.
- Settings that Blender rejects while restoring (e.g. a look that no longer
  exists) are skipped silently by `_safe_set()`.
- The repo is public: all README badges are live (release and license from
  GitHub, the Blender version from the manifest).

## How the current state was verified (November 2026)

- Test suite: 24 tests, all passing on Blender 5.3.0 (Windows, isolated).
- Behaviour comparison against the original code (`c75ff43`): 180 option
  combinations, zero run-to-run noise; the only differences are the images
  saved with an output color override, which now match the same shots
  without override (the bug fix).
- The built zip was installed into a scratch Blender profile with
  `blender --command extension install-file` and the test suite was run
  against the installed copy.
