"""In-Blender test suite for the Solid Snapshot add-on.

Do not run this file directly: ``tests/run_tests.py`` starts a separate
Blender instance (factory settings, scratch profile, fixed window size) with
this script and the arguments after ``--``:

    --addon PATH   add-on to test: the package folder or a single .py file
    --work DIR     scratch folder for .blend files and snapshots
    --out FILE     JSON file the results are written to

The viewport render needs a real window, so Blender runs with its UI. Each
test runs in its own timer tick after a fresh factory scene was loaded in the
previous tick, so the viewport has been drawn before the test uses it.
"""

import array
import ast
import hashlib
import importlib.util
import json
import os
import sys
import time
import traceback

import bpy
from mathutils import Euler, Matrix

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _arg(name):
    return ARGS[ARGS.index(name) + 1]


ADDON = _arg("--addon")
WORK = _arg("--work")
OUT = _arg("--out")

TESTS = []
mod = None  # the loaded add-on module


def test(fn):
    TESTS.append(fn)
    return fn


class Fail(AssertionError):
    pass


def check(cond, msg):
    if not cond:
        raise Fail(msg)


# ---------------------------------------------------------------------------
# Harness helpers
# ---------------------------------------------------------------------------

def load_addon(path):
    """Import and register the add-on from a package folder or a .py file."""
    if os.path.isdir(path):
        spec = importlib.util.spec_from_file_location(
            "solid_snapshot", os.path.join(path, "__init__.py"),
            submodule_search_locations=[path])
    else:
        spec = importlib.util.spec_from_file_location("solid_snapshot", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["solid_snapshot"] = m
    spec.loader.exec_module(m)
    m.register()
    return m


def view3d():
    """Largest 3D viewport of the first window: (window, area, ui_region, window_region)."""
    win = bpy.context.window_manager.windows[0]
    area = max((a for a in win.screen.areas if a.type == "VIEW_3D"),
               key=lambda a: a.width * a.height)
    ui = next(r for r in area.regions if r.type == "UI")
    wr = next(r for r in area.regions if r.type == "WINDOW")
    return win, area, ui, wr


def set_view(persp="PERSP", rot=(1.1, 0.0, 0.8), dist=12.0):
    _, area, _, _ = view3d()
    sp = area.spaces.active
    rv = sp.region_3d
    rv.view_perspective = persp
    rv.view_location = (0.0, 0.0, 0.0)
    rv.view_rotation = Euler(rot).to_quaternion()
    rv.view_distance = dist
    sp.lens = 50.0
    sp.clip_start = 0.01
    sp.clip_end = 1000.0
    redraw()
    return sp, rv


def redraw():
    """Draw the window once so rv3d.view_matrix reflects the view just set."""
    win, area, _, wr = view3d()
    with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=wr):
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)


def save_blend(name="t"):
    folder = os.path.join(WORK, "case_%s_%d" % (name, int(time.time() * 1000)))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return folder


def snap(**settings):
    """Apply panel settings and run the snapshot operator like the panel button does."""
    st = bpy.context.scene.solid_snapshot
    for k, v in settings.items():
        setattr(st, k, v)
    win, area, ui, _ = view3d()
    with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=ui):
        return bpy.ops.view3d.solid_snapshot()


def pngs(folder):
    return sorted(f for f in os.listdir(folder) if f.lower().endswith(".png")) if os.path.isdir(folder) else []


def image_info(path):
    """(width, height, depth, pixel-hash, min alpha, pixels) of an image file."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = array.array("f", [0.0]) * (w * h * 4)
        img.pixels.foreach_get(px)
        q = bytes(int(round(v * 255)) & 0xFF for v in px)
        alpha = min(px[3::4]) if px else 1.0
        return w, h, img.depth, hashlib.sha1(q).hexdigest(), alpha, px
    finally:
        bpy.data.images.remove(img)


def mean_abs_diff(a, b):
    check(len(a) == len(b), "image sizes differ")
    return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))


def cm_state(scene):
    vs = scene.view_settings
    return (scene.display_settings.display_device, vs.view_transform, vs.look,
            round(vs.exposure, 5), round(vs.gamma, 5), vs.use_curve_mapping)


def render_state(scene):
    r = scene.render
    im = r.image_settings
    return (r.resolution_x, r.resolution_y, r.resolution_percentage, r.film_transparent,
            im.file_format, im.color_mode, im.color_depth, im.color_management)


def enum_ids(owner, prop):
    """Current items of a dynamic enum (view transforms, looks).

    bl_rna only lists a static placeholder for these, but assigning an
    invalid value makes Blender name the valid ones in the error message.
    """
    try:
        setattr(owner, prop, "__no_such_item__")
    except TypeError as ex:
        msg = str(ex)
        items = ast.literal_eval(msg[msg.index(" in (") + 4:])
        return [items] if isinstance(items, str) else list(items)
    raise Fail("could not list items of %s" % prop)


def set_transform(scene, name, look_index=-1, exposure=0.0, gamma=1.0, curves=False):
    vs = scene.view_settings
    vs.view_transform = name
    looks = enum_ids(vs, "look")
    vs.look = looks[look_index] if looks else "None"
    vs.exposure = exposure
    vs.gamma = gamma
    vs.use_curve_mapping = curves


def mat_close(a, b, eps=1e-4):
    return all(abs(a[i][j] - b[i][j]) < eps for i in range(4) for j in range(4))


def snapshot_folder(folder):
    return os.path.join(folder, "snapshots")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@test
def unsaved_file_is_refused():
    set_view()
    before = cm_state(bpy.context.scene)
    try:
        snap()
        raise Fail("operator ran on an unsaved file")
    except RuntimeError as ex:
        check("Save the .blend" in str(ex), "unexpected error: %s" % ex)
    check(cm_state(bpy.context.scene) == before, "color management touched")


@test
def basic_snapshot_output():
    set_view()
    folder = save_blend("basic")
    _, _, _, wr = view3d()
    check(snap() == {"FINISHED"}, "operator did not finish")
    files = pngs(snapshot_folder(folder))
    check(files == ["basic_Snap_001.png"], "files: %s" % files)
    w, h, depth, _, _, _ = image_info(os.path.join(snapshot_folder(folder), files[0]))
    check((w, h) == (wr.width, wr.height), "size %sx%s != viewport %sx%s" % (w, h, wr.width, wr.height))
    check(depth == 24, "expected RGB (24 bit), got %s" % depth)
    coll = bpy.data.collections.get("CAMERAS")
    check(coll is not None and [o.name for o in coll.objects] == ["Snap_001"], "camera missing")
    check(coll in bpy.context.scene.collection.children_recursive, "CAMERAS not linked to scene")
    cam = coll.objects[0]
    check(cam["snapshot_file"].replace("\\", "/") == "//snapshots/basic_Snap_001.png",
          "snapshot_file = %r" % cam["snapshot_file"])


@test
def color_management_restored_for_every_transform():
    scene = bpy.context.scene
    set_view()
    save_blend("cm")
    tried = []
    for vt in enum_ids(scene.view_settings, "view_transform"):
        set_transform(scene, vt, exposure=0.7, gamma=1.3, curves=True)
        before = cm_state(scene)
        check(snap(save_camera=False, match_viewport=False) == {"FINISHED"}, "failed for %s" % vt)
        check(cm_state(scene) == before, "%s: %s != %s" % (vt, cm_state(scene), before))
        tried.append(vt)
    check(len(tried) >= 3, "too few view transforms: %s" % tried)


@test
def standard_transform_is_applied():
    scene = bpy.context.scene
    set_view()
    folder = save_blend("std")
    sf = snapshot_folder(folder)
    scene.render.resolution_x, scene.render.resolution_y = 320, 180
    common = dict(save_camera=False, match_viewport=False)

    set_transform(scene, "Standard", look_index=0)
    snap(force_standard=False, **common)
    ref = image_info(os.path.join(sf, pngs(sf)[-1]))

    set_transform(scene, "AgX", exposure=1.5, gamma=0.6, curves=True)
    snap(force_standard=True, neutral_exposure=True, **common)
    forced = image_info(os.path.join(sf, pngs(sf)[-1]))
    snap(force_standard=False, **common)
    unforced = image_info(os.path.join(sf, pngs(sf)[-1]))

    d_forced = mean_abs_diff(ref[5], forced[5])
    d_unforced = mean_abs_diff(ref[5], unforced[5])
    check(d_forced < 1.0 / 255, "forced Standard differs from real Standard: %.5f" % d_forced)
    m_unforced = max(abs(x - y) for x, y in zip(ref[5], unforced[5]))
    # The flat background barely changes between transforms, so use the
    # largest pixel difference (the shaded cube) rather than the mean.
    check(m_unforced > 0.1, "AgX not visibly different from Standard: mean %.5f max %.5f" % (d_unforced, m_unforced))


@test
def neutral_off_keeps_exposure():
    scene = bpy.context.scene
    set_view()
    folder = save_blend("neutral")
    sf = snapshot_folder(folder)
    scene.render.resolution_x, scene.render.resolution_y = 320, 180
    common = dict(save_camera=False, match_viewport=False)

    set_transform(scene, "Standard", look_index=0, exposure=1.0)
    snap(force_standard=False, **common)
    ref = image_info(os.path.join(sf, pngs(sf)[-1]))

    set_transform(scene, "AgX", exposure=1.0)
    snap(force_standard=True, neutral_exposure=False, **common)
    kept = image_info(os.path.join(sf, pngs(sf)[-1]))
    d = mean_abs_diff(ref[5], kept[5])
    check(d < 1.0 / 255, "Standard+exposure 1 mismatch: %.5f" % d)


@test
def output_color_override_does_not_leak_into_snapshot():
    # Regression: with Output > Color Management set to Override, the image
    # used to be saved with the override (e.g. AgX) instead of Standard.
    scene = bpy.context.scene
    set_view()
    folder = save_blend("outoverride")
    sf = snapshot_folder(folder)
    scene.render.resolution_x, scene.render.resolution_y = 320, 180
    common = dict(save_camera=False, match_viewport=False, force_standard=True)
    set_transform(scene, "Standard", look_index=0)
    snap(**common)
    ref = image_info(os.path.join(sf, pngs(sf)[-1]))
    im = scene.render.image_settings
    im.color_management = "OVERRIDE"
    im.view_settings.view_transform = "AgX"
    im.view_settings.exposure = 1.5
    set_transform(scene, "Filmic")
    snap(**common)
    got = image_info(os.path.join(sf, pngs(sf)[-1]))
    d = max(abs(a - b) for a, b in zip(ref[5], got[5]))
    check(d < 2.0 / 255, "output override leaked into the snapshot: max diff %.4f" % d)
    check((im.color_management, im.view_settings.view_transform, round(im.view_settings.exposure, 3))
          == ("OVERRIDE", "AgX", 1.5), "output override settings not restored: %s %s %s"
          % (im.color_management, im.view_settings.view_transform, im.view_settings.exposure))


@test
def render_settings_restored():
    scene = bpy.context.scene
    set_view()
    save_blend("render")
    r = scene.render
    for fmt, mode, depth in (("JPEG", "RGB", "8"), ("OPEN_EXR", "RGBA", "32"), ("PNG", "BW", "16")):
        r.resolution_x, r.resolution_y, r.resolution_percentage = 1234, 567, 60
        r.film_transparent = True
        r.image_settings.file_format = fmt
        r.image_settings.color_mode = mode
        r.image_settings.color_depth = depth
        before = render_state(scene)
        snap(save_camera=False, transparent=False)
        check(render_state(scene) == before, "%s: %s != %s" % (fmt, render_state(scene), before))


@test
def scene_resolution_when_not_matching_viewport():
    scene = bpy.context.scene
    set_view()
    folder = save_blend("res")
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 640, 360, 50
    snap(save_camera=False, match_viewport=False)
    w, h, _, _, _, _ = image_info(os.path.join(snapshot_folder(folder), pngs(snapshot_folder(folder))[-1]))
    check((w, h) == (320, 180), "size %sx%s" % (w, h))


@test
def camera_view_uses_scene_resolution_and_duplicates_camera():
    scene = bpy.context.scene
    set_view(persp="CAMERA")
    folder = save_blend("camview")
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 400, 300, 100
    src = scene.camera
    check(src is not None, "factory scene has no camera")
    snap(match_viewport=True)
    w, h, _, _, _, _ = image_info(os.path.join(snapshot_folder(folder), pngs(snapshot_folder(folder))[-1]))
    check((w, h) == (400, 300), "size %sx%s" % (w, h))
    cam = bpy.data.objects["Snap_001"]
    check(cam.data != src.data, "camera data shared with scene camera")
    check(mat_close(cam.matrix_world, src.matrix_world), "matrix differs from scene camera")
    check(abs(cam.data.lens - src.data.lens) < 1e-5, "lens differs")


@test
def perspective_camera_matches_viewport():
    set_view()
    save_blend("persp")
    sp, rv = set_view()  # same values; view_matrix was refreshed by the redraw tick
    expected = rv.view_matrix.inverted()
    snap()
    cam = bpy.data.objects["Snap_001"]
    check(cam.data.type == "PERSP", "type %s" % cam.data.type)
    check(mat_close(cam.matrix_world, expected), "camera matrix does not match the viewport")
    check(abs(cam.data.lens - 50.0) < 1e-5 and abs(cam.data.sensor_width - 72.0) < 1e-5, "lens/sensor")
    check(cam.data.sensor_fit == "AUTO", "sensor fit %s" % cam.data.sensor_fit)
    check(abs(cam.data.clip_start - 0.01) < 1e-6 and abs(cam.data.clip_end - 1000.0) < 1e-3, "clipping")


@test
def saved_camera_reproduces_viewport_framing():
    # Proves the 72 mm sensor equivalence: looking through the saved camera
    # at the viewport's resolution must give the same picture.
    scene = bpy.context.scene
    set_view()
    folder = save_blend("framing")
    sf = snapshot_folder(folder)
    _, area, _, wr = view3d()
    area.spaces.active.overlay.show_overlays = False
    snap(save_camera=True, match_viewport=True, show_overlays=False)
    first = image_info(os.path.join(sf, pngs(sf)[-1]))
    cam = bpy.data.objects["Snap_001"]
    cam.hide_viewport = True  # keep the camera itself out of the picture
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = wr.width, wr.height
    scene.render.resolution_percentage = 100
    set_view(persp="CAMERA")
    area.spaces.active.overlay.show_overlays = False
    snap(save_camera=False, match_viewport=False, show_overlays=False)
    second = image_info(os.path.join(sf, pngs(sf)[-1]))
    check(first[:2] == second[:2], "sizes differ: %s vs %s" % (first[:2], second[:2]))
    d = mean_abs_diff(first[5], second[5])
    check(d < 2.0 / 255, "camera framing differs from the viewport: mean diff %.4f" % d)


@test
def ortho_camera_matches_viewport():
    set_view(persp="ORTHO", dist=8.0)
    save_blend("ortho")
    sp, rv = set_view(persp="ORTHO", dist=8.0)
    expected = rv.view_matrix.inverted() @ Matrix.Translation((0, 0, 1000.0))
    snap()
    cam = bpy.data.objects["Snap_001"]
    check(cam.data.type == "ORTHO", "type %s" % cam.data.type)
    check(abs(cam.data.ortho_scale - 8.0 * 72.0 / 50.0) < 1e-4, "ortho scale %s" % cam.data.ortho_scale)
    # Framing of an ortho camera depends on orientation and scale, not on the
    # distance along the view axis, so check those plus the clip range.
    rot_cam = cam.matrix_world.to_3x3().normalized()
    rot_view = expected.to_3x3().normalized()
    check(all(abs(rot_cam[i][j] - rot_view[i][j]) < 1e-4 for i in range(3) for j in range(3)),
          "ortho camera orientation differs from the view")
    offset = cam.matrix_world.translation - rv.view_location
    axis = rot_view.col[2]
    check((offset - axis * offset.dot(axis)).length < 1e-3, "camera is not on the view axis")
    check(cam.data.clip_start <= offset.length <= cam.data.clip_end, "view centre outside clip range")
    # The add-on asks for clip_start 0; Blender clamps it to its tiny minimum.
    check(cam.data.clip_start < 1e-3 and abs(cam.data.clip_end - 2000.0) < 1e-3,
          "ortho clipping %s..%s" % (cam.data.clip_start, cam.data.clip_end))


@test
def save_camera_off_adds_nothing():
    set_view()
    folder = save_blend("nocam")
    n_obj = len(bpy.data.objects)
    snap(save_camera=False, add_marker=True)
    check(len(bpy.data.objects) == n_obj, "objects were added")
    check(len(bpy.context.scene.timeline_markers) == 0, "marker added without a camera")
    check(len(pngs(snapshot_folder(folder))) == 1, "image missing")


@test
def naming_sequence_and_custom_names():
    set_view()
    folder = save_blend("names")
    for _ in range(3):
        snap(match_viewport=False)
    check(pngs(snapshot_folder(folder)) == ["names_Snap_001.png", "names_Snap_002.png", "names_Snap_003.png"],
          "sequence: %s" % pngs(snapshot_folder(folder)))
    other = os.path.join(folder, "imgs")
    os.makedirs(other)
    open(os.path.join(other, "X_Shot_007.png"), "wb").close()
    snap(base_name="Shot", prefix="X", folder_name="imgs", match_viewport=False)
    check("X_Shot_008.png" in pngs(other), "existing file not respected: %s" % pngs(other))
    bpy.data.objects.new("Shot_010", None)
    snap(match_viewport=False)
    check("X_Shot_011.png" in pngs(other), "existing object not respected: %s" % pngs(other))
    check({"Shot_008", "Shot_011"} <= set(bpy.data.objects.keys()), "cameras not named after images")


@test
def markers_created_and_reused():
    scene = bpy.context.scene
    set_view()
    save_blend("markers")
    scene.frame_set(5)
    snap(add_marker=True, match_viewport=False)
    scene.frame_set(5)
    snap(add_marker=True, override_existing=False, match_viewport=False)
    scene.frame_set(9)
    snap(add_marker=True, match_viewport=False)
    got = sorted((m.frame, m.name, m.camera.name) for m in scene.timeline_markers)
    check(got == [(5, "Snap_002", "Snap_002"), (9, "Snap_003", "Snap_003")], "markers: %s" % got)
    check(len(bpy.data.collections["CAMERAS"].objects) == 3, "expected 3 cameras")


@test
def override_moves_existing_camera():
    scene = bpy.context.scene
    set_view()
    folder = save_blend("override")
    scene.frame_set(3)
    snap(add_marker=True, override_existing=True, match_viewport=False)
    cam = bpy.data.objects["Snap_001"]
    old_matrix = cam.matrix_world.copy()
    path = os.path.join(snapshot_folder(folder), "override_Snap_001.png")
    old_hash = image_info(path)[3]
    n_cams = len(bpy.data.cameras)
    sp, rv = set_view(rot=(0.6, 0.0, 2.0), dist=6.0)
    snap(add_marker=True, override_existing=True, match_viewport=False)
    check(len(bpy.data.collections["CAMERAS"].objects) == 1, "a new camera was created")
    check(len(bpy.data.cameras) == n_cams, "camera data leaked: %d -> %d" % (n_cams, len(bpy.data.cameras)))
    check(cam.data.name == "Snap_001", "camera data name %s" % cam.data.name)
    check(not mat_close(cam.matrix_world, old_matrix), "camera did not move")
    expected = (Matrix.Translation(rv.view_location) @ rv.view_rotation.to_matrix().to_4x4()
                @ Matrix.Translation((0, 0, rv.view_distance)))
    check(mat_close(cam.matrix_world, expected), "camera not at the new view")
    check(pngs(snapshot_folder(folder)) == ["override_Snap_001.png"], "files: %s" % pngs(snapshot_folder(folder)))
    check(image_info(path)[3] != old_hash, "image was not overwritten")
    check([(m.frame, m.camera.name) for m in scene.timeline_markers] == [(3, "Snap_001")], "markers")


@test
def override_without_marker_creates_new_camera():
    scene = bpy.context.scene
    set_view()
    save_blend("override_new")
    scene.frame_set(1)
    snap(add_marker=True, override_existing=True, match_viewport=False)
    scene.frame_set(2)
    snap(add_marker=True, override_existing=True, match_viewport=False)
    check(sorted(bpy.data.collections["CAMERAS"].objects.keys()) == ["Snap_001", "Snap_002"], "cameras")
    check(len(scene.timeline_markers) == 2, "markers")


@test
def overlays_option():
    scene = bpy.context.scene
    set_view()
    folder = save_blend("overlays")
    sf = snapshot_folder(folder)
    scene.render.resolution_x, scene.render.resolution_y = 320, 180
    _, area, _, _ = view3d()
    ov = area.spaces.active.overlay
    ov.show_overlays = True
    snap(show_overlays=True, save_camera=False, match_viewport=False)
    with_ov = image_info(os.path.join(sf, pngs(sf)[-1]))
    check(ov.show_overlays, "overlays not restored")
    snap(show_overlays=False, save_camera=False, match_viewport=False)
    without = image_info(os.path.join(sf, pngs(sf)[-1]))
    check(ov.show_overlays, "overlays not restored after hiding")
    check(with_ov[3] != without[3], "overlay option had no effect")
    ov.show_overlays = False
    snap(show_overlays=True, save_camera=False, match_viewport=False)
    check(not ov.show_overlays, "overlays were switched on")


@test
def transparent_background():
    scene = bpy.context.scene
    set_view()
    folder = save_blend("alpha")
    sf = snapshot_folder(folder)
    scene.render.resolution_x, scene.render.resolution_y = 320, 180
    snap(transparent=True, save_camera=False, match_viewport=False)
    w, h, depth, _, alpha, _ = image_info(os.path.join(sf, pngs(sf)[-1]))
    check(depth == 32 and alpha < 0.01, "not transparent: depth %s, min alpha %s" % (depth, alpha))
    snap(transparent=False, save_camera=False, match_viewport=False)
    w, h, depth, _, alpha, _ = image_info(os.path.join(sf, pngs(sf)[-1]))
    check(depth == 24 and alpha == 1.0, "unexpected alpha: depth %s, min alpha %s" % (depth, alpha))


@test
def camera_collection_linking():
    scene = bpy.context.scene
    set_view()
    save_blend("coll")
    coll = bpy.data.collections.new("CAMERAS")  # exists but not linked
    snap(match_viewport=False)
    check(coll in scene.collection.children_recursive, "existing CAMERAS not linked")
    parent = bpy.data.collections.new("Parent")
    scene.collection.children.link(parent)
    scene.collection.children.unlink(coll)
    parent.children.link(coll)  # nested: must not be linked a second time
    snap(match_viewport=False)
    check(coll.name not in scene.collection.children, "nested CAMERAS linked again at the top")
    check(len(coll.objects) == 2, "cameras: %d" % len(coll.objects))


@test
def failure_restores_everything():
    scene = bpy.context.scene
    set_view()
    save_blend("fail")
    set_transform(scene, "AgX", exposure=0.4)
    scene.render.resolution_x = 999
    _, area, _, _ = view3d()
    area.spaces.active.overlay.show_overlays = True
    cm_before, r_before = cm_state(scene), render_state(scene)
    orig = mod.set_standard_color_management

    def broken(sc, neutral):
        orig(sc, neutral)
        raise ValueError("simulated failure")

    mod.set_standard_color_management = broken
    try:
        snap(show_overlays=False)
        raise Fail("failure was not reported")
    except RuntimeError as ex:
        check("simulated failure" in str(ex), "unexpected error: %s" % ex)
    finally:
        mod.set_standard_color_management = orig
    check(cm_state(scene) == cm_before, "color management not restored")
    check(render_state(scene) == r_before, "render settings not restored")
    check(area.spaces.active.overlay.show_overlays, "overlays not restored")
    check("CAMERAS" not in bpy.data.collections, "camera created despite failure")


@test
def open_folder_poll():
    check(not bpy.ops.view3d.solid_snapshot_open_folder.poll(), "poll true on unsaved file")
    save_blend("poll")
    check(bpy.ops.view3d.solid_snapshot_open_folder.poll(), "poll false on saved file")


@test
def ui_registration():
    check(hasattr(bpy.types, "SOLIDSNAP_PT_panel"), "panel not registered")
    check(bpy.types.SOLIDSNAP_PT_panel.bl_category == "Snapshot", "panel tab")
    funcs = bpy.types.VIEW3D_MT_view._dyn_ui_initialize()
    check(any(getattr(f, "__module__", "") == "solid_snapshot" for f in funcs), "View menu entry missing")

    class FakeLayout:
        active = True

        def __getattr__(self, name):
            return lambda *a, **k: self

    class FakePanel:
        layout = FakeLayout()

    win, area, ui, _ = view3d()
    for saved in (False, True):
        if saved:
            save_blend("ui")
        with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=ui):
            mod.SOLIDSNAP_PT_panel.draw(FakePanel(), bpy.context)


@test
def unregister_and_register_again():
    mod.unregister()
    check(not hasattr(bpy.types.Scene, "solid_snapshot"), "scene property left behind")
    check(not hasattr(bpy.types, "SOLIDSNAP_PT_panel"), "panel left registered")
    mod.register()
    check(hasattr(bpy.context.scene, "solid_snapshot"), "not registered again")


# ---------------------------------------------------------------------------
# Runner: one timer tick loads a fresh scene, the next tick runs a test.
# ---------------------------------------------------------------------------

results = []
state = {"i": 0, "phase": "reset", "t0": time.time()}


def finish():
    passed = sum(r["ok"] for r in results)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"blender": bpy.app.version_string, "addon": ADDON,
                   "passed": passed, "failed": len(results) - passed,
                   "seconds": round(time.time() - state["t0"], 1), "results": results}, f, indent=1)
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()


def tick():
    try:
        if state["i"] >= len(TESTS):
            finish()
            return None
        if state["phase"] == "reset":
            bpy.ops.wm.read_homefile(use_factory_startup=True)
            set_view()
            state["phase"] = "run"
            return 0.2
        fn = TESTS[state["i"]]
        t = time.time()
        try:
            fn()
            results.append({"name": fn.__name__, "ok": True, "seconds": round(time.time() - t, 2)})
        except Exception as ex:
            results.append({"name": fn.__name__, "ok": False, "error": "%s: %s" % (type(ex).__name__, ex),
                            "trace": traceback.format_exc()})
        print("[%s] %s" % ("PASS" if results[-1]["ok"] else "FAIL", fn.__name__), flush=True)
        state["i"] += 1
        state["phase"] = "reset"
        return 0.05
    except Exception:
        results.append({"name": "<harness>", "ok": False, "error": traceback.format_exc()})
        finish()
        return None


mod = load_addon(ADDON)
# persistent: the timer must survive the file loads between tests
bpy.app.timers.register(tick, first_interval=1.0, persistent=True)
