# Solid Snapshot

[![Blender](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmttfntn%2Fsnapshot-blender%2Fmain%2Fsolid_snapshot%2Fblender_manifest.toml&query=%24.blender_version_min&label=Blender&color=E87D0D&logo=blender&logoColor=white)](https://www.blender.org/download/)
[![Release](https://img.shields.io/github/v/release/mttfntn/snapshot-blender)](https://github.com/mttfntn/snapshot-blender/releases/latest)
[![tests](https://github.com/mttfntn/snapshot-blender/actions/workflows/tests.yml/badge.svg)](https://github.com/mttfntn/snapshot-blender/actions/workflows/tests.yml)
[![License](https://img.shields.io/github/license/mttfntn/snapshot-blender)](LICENSE)
[![Language](https://img.shields.io/github/languages/top/mttfntn/snapshot-blender)](https://github.com/mttfntn/snapshot-blender)

A Blender add-on that saves a picture of the 3D viewport in **Standard** colors,
even when your scene uses AgX, Filmic or another view transform, and then puts
all your settings back. Optionally it bookmarks the view as a camera and binds
it to a timeline marker.

## What one click does

1. Remembers your color management (view transform, look, exposure, gamma,
   curves) and the render/output settings it needs to touch.
2. Switches to Standard, renders the viewport, and saves a PNG to
   `snapshots/` next to your `.blend` file, named `<blend>_Snap_001.png`,
   `<blend>_Snap_002.png`, ...
3. Restores every setting, even if something fails.
4. Optionally adds a camera `Snap_001` (matching the view) to a **CAMERAS**
   collection, and a timeline marker bound to that camera.

## Install

Requires **Blender 5.3**.

1. Download `solid_snapshot-X.Y.Z.zip` from the
   [Releases](https://github.com/mttfntn/snapshot-blender/releases) page.
2. In Blender: **Edit > Preferences > Add-ons**, open the drop-down menu at the
   top right, choose **Install from Disk...** and pick the zip
   (or drag the zip onto the Blender window).

## Use

Save your `.blend` file first (snapshots go next to it). Then open the 3D
viewport sidebar (**N**) > **Snapshot** tab and click **Take Snapshot**. The
same command is at the bottom of the viewport's **View** menu.

| Option | What it does |
| --- | --- |
| Camera to View | Same lock as Sidebar > View: move the camera by navigating. The camera button next to it looks through the active camera. |
| Use Standard View Transform | Switch to Standard for the snapshot (default on). |
| Neutral Exposure/Gamma | Also use exposure 0, gamma 1, no curves (default on). |
| Save Camera | Add a camera matching the view to the CAMERAS collection (default on). |
| Add Timeline Marker | Put a marker on the current frame bound to the new camera. A marker already on that frame is reused. |
| Override Camera on Frame | If the marker on this frame already has a camera, move that camera and overwrite its image instead of making a new one. |
| Collection > Check | Which cameras must be in CAMERAS: *Snapshot Cameras* (made by this add-on, default) or *All Cameras*. The line below says how many are outside. |
| Collect Cameras | Move those cameras into CAMERAS and out of this scene's other collections. Cameras in a sub-collection of CAMERAS already count as inside. |
| Match Viewport Size | Image size = viewport size; off = scene resolution. Looking through a camera always uses the scene resolution. |
| Include Overlays | Keep grid, outlines, gizmos in the image. |
| Transparent Background | PNG with alpha. |
| Name / Folder / Prefix | `Snap` / `snapshots` / the .blend name by default. |

The saved camera reproduces the viewport framing when the render resolution
has the same aspect ratio as the viewport.

## For maintainers

- [HANDOVER.md](HANDOVER.md): how the project works, how to change, test and release it.
- [AGENTS.md](AGENTS.md): the same, compact, for AI coding assistants.

These files are not part of the installable package.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). Copyright 2026 Matteo Fontana.
