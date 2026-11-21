"""Record what the add-on does for a broad matrix of options (runs in Blender).

Started by tests/compare.py with: -- --addon PATH --work DIR --out FILE

For every view mode x scene color setup x output color setup x option set it
takes a snapshot and records everything observable afterwards: operator
result, files written, image size/depth/pixel hash, cameras, markers, and
the scene/render/output/overlay settings. Two versions of the add-on are
compared by diffing these records.
"""

import array
import hashlib
import importlib.util
import json
import os
import sys
import traceback

import bpy
from mathutils import Euler

ARGS = sys.argv[sys.argv.index("--") + 1:]
ADDON = ARGS[ARGS.index("--addon") + 1]
WORK = ARGS[ARGS.index("--work") + 1]
OUT = ARGS[ARGS.index("--out") + 1]

VIEWS = ["PERSP", "ORTHO", "CAMERA"]
SCENE_CM = {
    "standard": dict(view_transform="Standard", look="None", exposure=0.0, gamma=1.0, curves=False),
    "agx_punchy": dict(view_transform="AgX", look="AgX - Punchy", exposure=0.8, gamma=1.2, curves=False),
    "filmic_curves": dict(view_transform="Filmic", look="Medium High Contrast", exposure=-0.5, gamma=0.9, curves=True),
}
OUTPUT_CM = ["follow", "override_agx"]
OPTIONS = [
    ("defaults", {}),
    ("no_standard", dict(force_standard=False)),
    ("no_neutral", dict(neutral_exposure=False)),
    ("no_camera", dict(save_camera=False)),
    ("marker", dict(add_marker=True)),
    ("override_twice", dict(add_marker=True, override_existing=True)),
    ("scene_res", dict(match_viewport=False)),
    ("no_overlays", dict(show_overlays=False)),
    ("transparent", dict(transparent=True)),
    ("custom_names", dict(base_name="Shot", prefix="P", folder_name="imgs")),
]
DEFAULTS = dict(force_standard=True, neutral_exposure=True, save_camera=True, add_marker=False,
                override_existing=False, match_viewport=True, show_overlays=True, transparent=False,
                base_name="Snap", prefix="", folder_name="snapshots")


def load_addon(path):
    if os.path.isdir(path):
        spec = importlib.util.spec_from_file_location("solid_snapshot", os.path.join(path, "__init__.py"),
                                                      submodule_search_locations=[path])
    else:
        spec = importlib.util.spec_from_file_location("solid_snapshot", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["solid_snapshot"] = m
    spec.loader.exec_module(m)
    m.register()
    return m


def view3d():
    win = bpy.context.window_manager.windows[0]
    area = max((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.width * a.height)
    return win, area


def r5(v):
    return round(float(v), 4)


def all_files():
    """{relative path: modification time} of every PNG under WORK."""
    out = {}
    for root, _, files in os.walk(WORK):
        for f in files:
            if f.lower().endswith(".png"):
                full = os.path.join(root, f)
                out[os.path.relpath(full, WORK).replace("\\", "/")] = os.stat(full).st_mtime_ns
    return out


def image_record(path):
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = array.array("f", [0.0]) * (w * h * 4)
        img.pixels.foreach_get(px)
        return {"size": [w, h], "depth": img.depth, "pixels_sha1": hashlib.sha1(px.tobytes()).hexdigest()}
    finally:
        bpy.data.images.remove(img)


def cm_record(owner):
    vs = owner.view_settings
    return [owner.display_settings.display_device, vs.view_transform, vs.look,
            r5(vs.exposure), r5(vs.gamma), vs.use_curve_mapping]


def state_record():
    s = bpy.context.scene
    r = s.render
    im = r.image_settings
    _, area = view3d()
    cams = []
    coll = bpy.data.collections.get("CAMERAS")
    for o in sorted(coll.objects if coll else [], key=lambda o: o.name):
        d = o.data
        cams.append({"name": o.name, "data": d.name, "type": d.type, "lens": r5(d.lens),
                     "sensor": r5(d.sensor_width), "fit": d.sensor_fit, "ortho": r5(d.ortho_scale),
                     "clip": [r5(d.clip_start), r5(d.clip_end)],
                     "matrix": [[r5(v) for v in row] for row in o.matrix_world],
                     "file": str(o.get("snapshot_file", "")).replace("\\", "/")})
    return {
        "scene_cm": cm_record(s),
        "render": [r.resolution_x, r.resolution_y, r.resolution_percentage, r.film_transparent,
                   im.file_format, im.color_mode, im.color_depth, im.color_management],
        "output_cm": cm_record(im),
        "overlays": area.spaces.active.overlay.show_overlays,
        "cameras": cams,
        "markers": sorted([m.frame, m.name, m.camera.name if m.camera else None] for m in s.timeline_markers),
        "camera_data_blocks": len(bpy.data.cameras),
    }


def setup_scene(view, cm_name, out_cm, case_dir):
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    s = bpy.context.scene
    _, area = view3d()
    sp = area.spaces.active
    rv = sp.region_3d
    rv.view_perspective = view
    rv.view_location = (0.0, 0.0, 0.0)
    rv.view_rotation = Euler((1.1, 0.0, 0.8)).to_quaternion()
    rv.view_distance = 12.0
    sp.lens = 50.0
    r = s.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = 480, 270, 100
    c = SCENE_CM[cm_name]
    vs = s.view_settings
    vs.view_transform = c["view_transform"]
    vs.look = c["look"]
    vs.exposure, vs.gamma, vs.use_curve_mapping = c["exposure"], c["gamma"], c["curves"]
    if out_cm == "override_agx":
        im = r.image_settings
        im.color_management = "OVERRIDE"
        im.view_settings.view_transform = "AgX"
        im.view_settings.exposure = 1.5
    os.makedirs(case_dir, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(case_dir, "scene.blend"))
    s.frame_set(7)


def run_case(name, opts):
    st = bpy.context.scene.solid_snapshot
    for k, v in dict(DEFAULTS, **opts).items():
        setattr(st, k, v)
    win, area = view3d()
    ui = next(r for r in area.regions if r.type == "UI")
    before = all_files()
    with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=ui):
        try:
            result = sorted(bpy.ops.view3d.solid_snapshot())
        except RuntimeError as ex:
            result = ["ERROR: %s" % str(ex).strip().splitlines()[-1]]
    # written = new files and overwritten ones (override mode reuses a file)
    written = sorted(f for f, t in all_files().items() if before.get(f) != t)
    return {"result": result, "written_files": written, "state": state_record()}


def add_images(rec):
    """Hash each written image right away, before a later shot overwrites it."""
    rec["images"] = {f: image_record(os.path.join(WORK, f)) for f in rec["written_files"]}


records = {}
cases = [(v, c, o) for v in VIEWS for c in SCENE_CM for o in OUTPUT_CM]
progress = {"i": 0}


def tick():
    try:
        if progress["i"] >= len(cases):
            json.dump({"blender": bpy.app.version_string, "records": records}, open(OUT, "w"), indent=1, sort_keys=True)
            bpy.ops.wm.quit_blender()
            return None
        view, cm_name, out_cm = cases[progress["i"]]
        progress["i"] += 1
        case_dir = os.path.join(WORK, "%s_%s_%s" % (view, cm_name, out_cm))
        setup_scene(view, cm_name, out_cm, case_dir)
        for opt_name, opts in OPTIONS:
            key = "%s|%s|%s|%s" % (view, cm_name, out_cm, opt_name)
            rec = run_case(opt_name, opts)
            add_images(rec)
            if opt_name == "override_twice":  # second shot on the same frame from another angle
                _, area = view3d()
                area.spaces.active.region_3d.view_rotation = Euler((0.7, 0.0, 2.2)).to_quaternion()
                second = run_case(opt_name, opts)
                add_images(second)
                rec = {"first": rec, "second": second}
            records[key] = rec
        print("recorded", view, cm_name, out_cm, flush=True)
        return 0.05
    except Exception:
        records["<error>"] = traceback.format_exc()
        json.dump({"records": records}, open(OUT, "w"), indent=1)
        bpy.ops.wm.quit_blender()
        return None


load_addon(ADDON)
bpy.app.timers.register(tick, first_interval=1.0, persistent=True)
