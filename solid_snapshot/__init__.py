bl_info = {
    "name": "Solid Snapshot",
    "author": "Matteo Fontana",
    "version": (1, 0, 0),
    "blender": (3, 2, 0),
    "location": "3D Viewport > Sidebar (N) > Snapshot",
    "description": "Viewport snapshot with temporary Standard color management, "
                   "optional camera bookmark, saved next to the .blend",
    "category": "3D View",
}

import os
import re

import bpy
from bpy.props import BoolProperty, PointerProperty, StringProperty
from mathutils import Matrix


CAMERA_COLLECTION = "CAMERAS"
# Blender's viewport behaves like a camera with a 72 mm sensor at the
# viewport focal length (36 mm sensor * internal zoom factor 2).
VIEWPORT_SENSOR = 72.0


# ---------------------------------------------------------------------------
# Color management
# ---------------------------------------------------------------------------

def store_color_management(owner):
    vs = owner.view_settings
    return {
        "display_device": owner.display_settings.display_device,
        "view_transform": vs.view_transform,
        "look": vs.look,
        "exposure": vs.exposure,
        "gamma": vs.gamma,
        "use_curve_mapping": vs.use_curve_mapping,
    }


def _safe_set(owner, attr, value):
    try:
        setattr(owner, attr, value)
    except (TypeError, ValueError, AttributeError):
        pass


def set_standard_color_management(scene, neutral):
    vs = scene.view_settings
    vs.view_transform = "Standard"
    _safe_set(vs, "look", "None")
    if neutral:
        vs.exposure = 0.0
        vs.gamma = 1.0
        vs.use_curve_mapping = False


def restore_color_management(owner, saved):
    vs = owner.view_settings
    _safe_set(owner.display_settings, "display_device", saved["display_device"])
    # The view transform must come before the look (looks depend on it).
    _safe_set(vs, "view_transform", saved["view_transform"])
    _safe_set(vs, "look", saved["look"])
    vs.exposure = saved["exposure"]
    vs.gamma = saved["gamma"]
    vs.use_curve_mapping = saved["use_curve_mapping"]


# ---------------------------------------------------------------------------
# Render / output settings that are touched temporarily
# ---------------------------------------------------------------------------

def store_render_settings(scene):
    r = scene.render
    im = r.image_settings
    return {
        "resolution_x": r.resolution_x,
        "resolution_y": r.resolution_y,
        "resolution_percentage": r.resolution_percentage,
        "film_transparent": r.film_transparent,
        "file_format": im.file_format,
        "color_mode": im.color_mode,
        "color_depth": im.color_depth,
        "color_management": im.color_management,
        "output_cm": store_color_management(im),
    }


def restore_render_settings(scene, saved):
    r = scene.render
    im = r.image_settings
    r.resolution_x = saved["resolution_x"]
    r.resolution_y = saved["resolution_y"]
    r.resolution_percentage = saved["resolution_percentage"]
    r.film_transparent = saved["film_transparent"]
    # Format first: valid color modes/depths depend on it.
    _safe_set(im, "file_format", saved["file_format"])
    _safe_set(im, "color_mode", saved["color_mode"])
    _safe_set(im, "color_depth", saved["color_depth"])
    im.color_management = saved["color_management"]
    # Switching back to OVERRIDE copies the scene settings into the output
    # settings, so put the user's own override values back afterwards.
    restore_color_management(im, saved["output_cm"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_window_region(area):
    regions = [r for r in area.regions if r.type == "WINDOW"]
    if not regions:
        return None
    # Quad view has several WINDOW regions; the last one is the main
    # (user-perspective) view, which matches space.region_3d.
    return regions[-1]


def next_snapshot_name(base, folder, prefix):
    """Return the next free 'Base_001' style name.

    A number counts as taken if an object with that name exists or a
    snapshot image with that number is already in the folder.
    """
    obj_pat = re.compile(r"^%s_(\d+)$" % re.escape(base))
    file_pat = re.compile(r"^%s_%s_(\d+)\.png$" % (re.escape(prefix), re.escape(base)),
                          re.IGNORECASE)
    used = 0
    for obj in bpy.data.objects:
        m = obj_pat.match(obj.name)
        if m:
            used = max(used, int(m.group(1)))
    if os.path.isdir(folder):
        for fname in os.listdir(folder):
            m = file_pat.match(fname)
            if m:
                used = max(used, int(m.group(1)))
    return "%s_%03d" % (base, used + 1)


def marker_camera_on_frame(scene):
    """Camera bound to a marker on the current frame, if any."""
    frame = scene.frame_current
    for m in scene.timeline_markers:
        if m.frame == frame and m.camera is not None and m.camera.type == "CAMERA":
            return m.camera
    return None


def update_camera_from_view(context, cam, region):
    """Move an existing camera to the current view, keeping its name."""
    tmp = camera_from_view(context, cam.name + "_tmp", region)
    old_data = cam.data
    cam.matrix_world = tmp.matrix_world.copy()
    cam.data = tmp.data
    bpy.data.objects.remove(tmp)
    if old_data.users == 0:
        bpy.data.cameras.remove(old_data)
    cam.data.name = cam.name


def bind_marker(scene, cam, name):
    """Put a timeline marker on the current frame and bind the camera to it.

    If a marker already sits on this frame it is reused, so the same frame
    never ends up with two competing camera markers.
    """
    frame = scene.frame_current
    marker = next((m for m in scene.timeline_markers if m.frame == frame), None)
    if marker is None:
        marker = scene.timeline_markers.new(name, frame=frame)
    else:
        marker.name = name
    marker.camera = cam
    return marker


def get_camera_collection(scene):
    coll = bpy.data.collections.get(CAMERA_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(CAMERA_COLLECTION)
    if coll not in scene.collection.children_recursive:
        scene.collection.children.link(coll)
    return coll


def camera_from_view(context, name, region):
    """Create a camera object matching the current viewport view."""
    scene = context.scene
    space = context.space_data
    rv3d = space.region_3d

    # Already looking through a camera: just duplicate it.
    if rv3d.view_perspective == "CAMERA" and scene.camera is not None:
        src = scene.camera
        cam_data = src.data.copy()
        cam_data.name = name
        obj = bpy.data.objects.new(name, cam_data)
        obj.matrix_world = src.matrix_world.copy()
        return obj

    cam_data = bpy.data.cameras.new(name)
    cam_data.sensor_fit = "AUTO"
    cam_data.sensor_width = VIEWPORT_SENSOR
    cam_data.lens = space.lens
    cam_data.clip_start = space.clip_start
    cam_data.clip_end = space.clip_end

    if rv3d.view_perspective == "ORTHO":
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = rv3d.view_distance * VIEWPORT_SENSOR / space.lens
        # Ortho viewports clip symmetrically around the view center;
        # move the camera back so nothing in front gets cut.
        cam_data.clip_start = 0.0
        cam_data.clip_end = space.clip_end * 2.0

    obj = bpy.data.objects.new(name, cam_data)
    # Built from the view's own values rather than rv3d.view_matrix, which is
    # only refreshed on redraw.
    mat = (Matrix.Translation(rv3d.view_location)
           @ rv3d.view_rotation.to_matrix().to_4x4()
           @ Matrix.Translation((0.0, 0.0, rv3d.view_distance)))
    if rv3d.view_perspective == "ORTHO":
        mat = mat @ Matrix.Translation((0.0, 0.0, space.clip_end))
    obj.matrix_world = mat
    return obj


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class SOLIDSNAP_Settings(bpy.types.PropertyGroup):
    folder_name: StringProperty(
        name="Folder",
        description="Sub-folder next to the .blend file where snapshots are saved",
        default="snapshots",
    )
    prefix: StringProperty(
        name="Prefix",
        description="File name prefix (empty = .blend file name)",
        default="",
    )
    force_standard: BoolProperty(
        name="Use Standard View Transform",
        description="Temporarily switch color management to Standard for the snapshot",
        default=True,
    )
    neutral_exposure: BoolProperty(
        name="Neutral Exposure/Gamma",
        description="Also reset exposure to 0, gamma to 1 and disable curves during the snapshot",
        default=True,
    )
    base_name: StringProperty(
        name="Name",
        description="Base name for cameras and images, numbered automatically "
                    "(Snap_001, Snap_002, ...)",
        default="Snap",
    )
    save_camera: BoolProperty(
        name="Save Camera",
        description="Store the current view as a camera in the CAMERAS collection",
        default=True,
    )
    add_marker: BoolProperty(
        name="Add Timeline Marker",
        description="Add a marker on the current frame and bind the new camera to it "
                    "(reuses a marker already on that frame)",
        default=False,
    )
    override_existing: BoolProperty(
        name="Override Camera on Frame",
        description="If a marker on the current frame already has a camera, move that "
                    "camera to the current view and overwrite its image instead of "
                    "creating a new one",
        default=False,
    )
    match_viewport: BoolProperty(
        name="Match Viewport Size",
        description="Render at the viewport's pixel size and framing instead of the "
                    "scene resolution (ignored when looking through a camera)",
        default=True,
    )
    show_overlays: BoolProperty(
        name="Include Overlays",
        description="Keep grid, gizmos, outlines etc. in the snapshot",
        default=True,
    )
    transparent: BoolProperty(
        name="Transparent Background",
        description="Render the background transparent (PNG with alpha)",
        default=False,
    )


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class SOLIDSNAP_OT_snapshot(bpy.types.Operator):
    bl_idname = "view3d.solid_snapshot"
    bl_label = "Take Snapshot"
    bl_description = ("Render the viewport with Standard color management, save it "
                      "to the snapshots folder and optionally store the view as a camera")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        scene = context.scene
        settings = scene.solid_snapshot

        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the .blend file first: snapshots go next to it")
            return {"CANCELLED"}

        area = context.area
        region = find_window_region(area)
        if region is None:
            self.report({"ERROR"}, "No 3D viewport region found")
            return {"CANCELLED"}

        folder = bpy.path.abspath("//" + (settings.folder_name.strip() or "snapshots"))
        os.makedirs(folder, exist_ok=True)
        prefix = settings.prefix.strip() or bpy.path.display_name_from_filepath(bpy.data.filepath)
        # Override mode: reuse the camera bound to a marker on this frame,
        # keeping its name and overwriting its image.
        target = None
        if settings.save_camera and settings.add_marker and settings.override_existing:
            target = marker_camera_on_frame(scene)

        if target is not None:
            snap_name = target.name
            old_file = target.get("snapshot_file", "")
            if isinstance(old_file, str) and old_file.lower().endswith(".png"):
                filepath = bpy.path.abspath(old_file)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
            else:
                filepath = os.path.join(folder, "%s_%s.png" % (prefix, snap_name))
        else:
            base = bpy.path.clean_name(settings.base_name.strip() or "Snap")
            snap_name = next_snapshot_name(base, folder, prefix)
            filepath = os.path.join(folder, "%s_%s.png" % (prefix, snap_name))

        rv3d = context.space_data.region_3d
        in_camera = rv3d.view_perspective == "CAMERA" and scene.camera is not None

        saved_cm = store_color_management(scene)
        saved_render = store_render_settings(scene)
        overlay = context.space_data.overlay
        saved_overlays = overlay.show_overlays
        try:
            overlay.show_overlays = saved_overlays and settings.show_overlays
            if settings.force_standard:
                set_standard_color_management(scene, settings.neutral_exposure)

            r = scene.render
            if settings.match_viewport and not in_camera:
                r.resolution_x = region.width
                r.resolution_y = region.height
                r.resolution_percentage = 100
            r.film_transparent = settings.transparent
            im = r.image_settings
            im.file_format = "PNG"
            im.color_mode = "RGBA" if settings.transparent else "RGB"
            im.color_depth = "8"
            # An output color override (Render Properties > Output) would
            # otherwise replace the scene settings when the image is saved.
            im.color_management = "FOLLOW_SCENE"

            with context.temp_override(area=area, region=region):
                bpy.ops.render.opengl(write_still=False, view_context=True)

            result = next((img for img in bpy.data.images if img.type == "RENDER_RESULT"), None)
            if result is None:
                self.report({"ERROR"}, "Viewport render produced no image")
                return {"CANCELLED"}
            # save_render applies the scene's (now Standard) color management.
            result.save_render(filepath, scene=scene)
        except Exception as ex:  # keep the user's settings safe no matter what
            self.report({"ERROR"}, "Snapshot failed: %s" % ex)
            return {"CANCELLED"}
        finally:
            overlay.show_overlays = saved_overlays
            restore_render_settings(scene, saved_render)
            restore_color_management(scene, saved_cm)

        msg = "Snapshot saved: %s" % filepath
        if settings.save_camera:
            if target is not None:
                update_camera_from_view(context, target, region)
                cam = target
                msg += "  |  camera overridden: %s" % cam.name
            else:
                cam = camera_from_view(context, snap_name, region)
                get_camera_collection(scene).objects.link(cam)
                msg += "  |  camera: %s" % cam.name
            cam["snapshot_file"] = bpy.path.relpath(filepath)
            if settings.add_marker:
                marker = bind_marker(scene, cam, snap_name)
                msg += "  |  marker on frame %d" % marker.frame

        self.report({"INFO"}, msg)
        return {"FINISHED"}


class SOLIDSNAP_OT_open_folder(bpy.types.Operator):
    bl_idname = "view3d.solid_snapshot_open_folder"
    bl_label = "Open Snapshots Folder"
    bl_description = "Open the snapshots folder in the file browser"

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def execute(self, context):
        settings = context.scene.solid_snapshot
        folder = bpy.path.abspath("//" + (settings.folder_name.strip() or "snapshots"))
        os.makedirs(folder, exist_ok=True)
        bpy.ops.wm.path_open(filepath=folder)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class SOLIDSNAP_PT_panel(bpy.types.Panel):
    bl_label = "Snapshot"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Snapshot"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.solid_snapshot

        layout.operator(SOLIDSNAP_OT_snapshot.bl_idname, icon="RENDER_STILL")

        # Same toggle as Sidebar > View > View Lock > "Camera to View",
        # so the camera can be framed without switching tabs.
        space = context.space_data
        row = layout.row(align=True)
        row.prop(space, "lock_camera", text="Camera to View", icon="LOCKVIEW_ON" if space.lock_camera else "LOCKVIEW_OFF", toggle=True)
        row.operator("view3d.view_camera", text="", icon="VIEW_CAMERA")

        col = layout.column(heading="Color")
        col.prop(settings, "force_standard")
        sub = col.column()
        sub.active = settings.force_standard
        sub.prop(settings, "neutral_exposure")

        col = layout.column(heading="Camera")
        col.prop(settings, "save_camera")
        sub = col.column()
        sub.active = settings.save_camera
        sub.prop(settings, "add_marker")
        sub2 = sub.column()
        sub2.active = settings.save_camera and settings.add_marker
        sub2.prop(settings, "override_existing")

        col = layout.column(heading="Options")
        col.prop(settings, "match_viewport")
        col.prop(settings, "show_overlays")
        col.prop(settings, "transparent")

        col = layout.column()
        col.prop(settings, "base_name")
        col.prop(settings, "folder_name")
        col.prop(settings, "prefix")
        col.operator(SOLIDSNAP_OT_open_folder.bl_idname, icon="FILE_FOLDER")

        if not bpy.data.filepath:
            layout.label(text="Save the .blend file first", icon="ERROR")


def menu_func(self, context):
    self.layout.separator()
    self.layout.operator(SOLIDSNAP_OT_snapshot.bl_idname, icon="RENDER_STILL")


classes = (
    SOLIDSNAP_Settings,
    SOLIDSNAP_OT_snapshot,
    SOLIDSNAP_OT_open_folder,
    SOLIDSNAP_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.solid_snapshot = PointerProperty(type=SOLIDSNAP_Settings)
    bpy.types.VIEW3D_MT_view.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_view.remove(menu_func)
    del bpy.types.Scene.solid_snapshot
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
