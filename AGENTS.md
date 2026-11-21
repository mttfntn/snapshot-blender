# AGENTS.md: Solid Snapshot

Blender 5.3 extension (add-on). One module, no dependencies. Human-oriented
version with more context: HANDOVER.md.

## Commands

```
python tests/run_tests.py                      # full suite, isolated Blender; exit 0 = pass (~15 s)
python tests/run_tests.py --addon PATH         # test another copy (folder or single .py)
python tests/compare.py --old-rev HEAD         # behaviour diff vs a git revision; exit 0 = identical
python tools/build.py                          # dist/solid_snapshot-X.Y.Z.zip (validate + build)
```
Blender path: `--blender PATH` or env `BLENDER`; default
`C:\Program Files\Blender Foundation\Blender 5.3\blender.exe`.
Linux/CI needs a display: `xvfb-run -a -s "-screen 0 1920x1080x24" python3 tests/run_tests.py`.

## Architecture

- `solid_snapshot/__init__.py`: everything. Sections: color management
  store/restore -> render settings store/restore -> helpers (naming, markers,
  cameras) -> `SOLIDSNAP_Settings` (PropertyGroup on `Scene.solid_snapshot`)
  -> `SOLIDSNAP_OT_snapshot` (`view3d.solid_snapshot`) ->
  `SOLIDSNAP_OT_open_folder` -> `SOLIDSNAP_PT_panel` (sidebar tab "Snapshot")
  -> View menu entry -> register/unregister.
- `solid_snapshot/blender_manifest.toml`: version + supported range
  (5.3.0 <= Blender < 5.4.0). bl_info is intentionally absent.
- Tests: `tests/blender_tests.py` (`@test` functions, fresh factory scene per
  test, run by timer ticks), driven by `tests/run_tests.py`.

## Data flow of execute()

unsaved -> error | pick name (`next_snapshot_name` / override target via
`marker_camera_on_frame`) -> store CM + render + overlay state -> try:
Standard, overlays, resolution = WINDOW region size (not in camera view),
PNG 8-bit, output CM = FOLLOW_SCENE -> `render.opengl(view_context=True)`
with override to the WINDOW region -> `Render Result.save_render(path)` ->
finally: restore all -> camera (`camera_from_view` / `update_camera_from_view`)
-> `snapshot_file` custom prop -> marker (`bind_marker`).

## Rules

- Never change behaviour silently: run `run_tests.py`; for refactors also
  `compare.py --old-rev HEAD` must report 0 differing keys.
- Anything changed temporarily must be stored before the `try` and restored
  in `finally`.
- Blender classes: `#` comments, not docstrings (they become tooltips).
- Keep `blender_version_min/max`, the CI `BLENDER_VERSION` and README badge
  in sync.
- Tests must stay isolated: factory startup + scratch `BLENDER_USER_RESOURCES`;
  never drive the user's running Blender.
- Line endings LF (`.gitattributes`).

## Pitfalls found in this project

- `rv3d.view_matrix` is stale until redraw: build matrices from
  `view_location`/`view_rotation`/`view_distance`; in tests call
  `wm.redraw_timer` (with a window context override) before reading it.
- `image_settings.color_management = "OVERRIDE"` copies scene CM into the
  override: store/restore the override values after switching back.
- `view_transform`/`look` are dynamic enums; `bl_rna...enum_items` shows only
  a placeholder.
- Operator `report({'ERROR'})` -> `RuntimeError` in Python `bpy.ops` calls.
- `bpy.app.timers.register(..., persistent=True)` or it dies on file load.
- Blender stays open if the `--python` script fails: use `--python-exit-code`.
- Viewport == camera with 72 mm sensor at the viewport lens (proven by test
  `saved_camera_reproduces_viewport_framing`).
- Camera `clip_start` 0 is clamped by Blender to ~1e-6.
- PNGs carry a date in metadata: compare pixels, not bytes.

## How changes were verified (Nov 2026)

24/24 tests on Blender 5.3.0; compare vs original `c75ff43`: 0 noise, only
differences = images with output color override (bug fix, now identical to
no-override shots); built zip installed in a scratch profile and tested.

## Release checklist

1. Bump `version` in `solid_snapshot/blender_manifest.toml`.
2. Bump the static release badge in README.md.
3. Commit, push `main`, wait for green `tests` workflow.
4. `git tag -a vX.Y.Z -m "notes"` (annotated; message = release notes, rendered as
   Markdown: no bare `<word>`, GitHub drops it as HTML).
5. `git push origin vX.Y.Z` -> `release` workflow tests, builds, publishes.
6. Check the release page has `solid_snapshot-X.Y.Z.zip`.

## Git

- Remote `origin` = https://github.com/mttfntn/snapshot-blender.git (private).
- Default branch `main`; small commits; commit messages end with a
  Co-Authored-By line when an AI wrote them.
- Ignored: `*.blend*`, `snapshots/`, `dist/`, `__pycache__/`.
- CI uploads no artifacts (account-wide storage quota was full); release job builds its own zip.
