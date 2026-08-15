"""Blender-side half of blender-mcp: opens a local port so the MCP server can drive this session."""

from __future__ import annotations

import bpy

from . import tcp_server


def _preferences():
    return bpy.context.preferences.addons[__package__].preferences


class BlenderMCPPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    host: bpy.props.StringProperty(
        name="Host",
        default="127.0.0.1",
        description="Interface to listen on. Keep this on loopback unless you know why not",
    )
    port: bpy.props.IntProperty(
        name="Port",
        default=9876,
        min=1024,
        max=65535,
        description="Must match BLENDER_MCP_PORT in the MCP server's environment",
    )
    request_timeout: bpy.props.IntProperty(
        name="Request timeout",
        default=600,
        min=5,
        max=7200,
        subtype="TIME_ABSOLUTE",
        description="How long a single request may run before the caller is told it timed out",
    )
    autostart: bpy.props.BoolProperty(
        name="Start listening on launch",
        default=False,
        description="Open the port automatically whenever Blender starts",
    )

    def draw(self, context):
        layout = self.layout
        column = layout.column()
        column.prop(self, "host")
        column.prop(self, "port")
        column.prop(self, "request_timeout")
        column.prop(self, "autostart")


class BLENDERMCP_OT_start(bpy.types.Operator):
    bl_idname = "blender_mcp.start"
    bl_label = "Start MCP Bridge"
    bl_description = "Begin accepting requests from the blender-mcp server"

    @classmethod
    def poll(cls, context):
        return not tcp_server.is_running()

    def execute(self, context):
        prefs = _preferences()
        try:
            tcp_server.start(prefs.host, prefs.port, float(prefs.request_timeout))
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"MCP bridge listening on {prefs.host}:{prefs.port}")
        return {"FINISHED"}


class BLENDERMCP_OT_stop(bpy.types.Operator):
    bl_idname = "blender_mcp.stop"
    bl_label = "Stop MCP Bridge"
    bl_description = "Stop accepting requests and close the port"

    @classmethod
    def poll(cls, context):
        return tcp_server.is_running()

    def execute(self, context):
        tcp_server.stop()
        self.report({"INFO"}, "MCP bridge stopped")
        return {"FINISHED"}


class BLENDERMCP_PT_panel(bpy.types.Panel):
    bl_label = "MCP Bridge"
    bl_idname = "BLENDERMCP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP"

    def draw(self, context):
        layout = self.layout
        prefs = _preferences()
        status = tcp_server.status

        if status["running"]:
            box = layout.box()
            box.label(text=f"Listening on {status['host']}:{status['port']}", icon="LINKED")
            box.label(text=f"Open connections: {status['connections']}")
            box.label(text=f"Requests handled: {status['handled']}")
            layout.operator(BLENDERMCP_OT_stop.bl_idname, icon="PAUSE")
        else:
            layout.label(text="Not listening", icon="UNLINKED")
            layout.operator(BLENDERMCP_OT_start.bl_idname, icon="PLAY")

        column = layout.column(align=True)
        column.prop(prefs, "host")
        column.prop(prefs, "port")

        if status["last_error"]:
            layout.box().label(text="Last error - see System Console", icon="ERROR")


_CLASSES = (
    BlenderMCPPreferences,
    BLENDERMCP_OT_start,
    BLENDERMCP_OT_stop,
    BLENDERMCP_PT_panel,
)


def _autostart_once():
    """Deferred so that add-on preferences are fully available before we read them."""
    prefs = _preferences()
    if prefs.autostart and not tcp_server.is_running():
        try:
            tcp_server.start(prefs.host, prefs.port, float(prefs.request_timeout))
        except RuntimeError as exc:
            print(f"[blender-mcp] autostart failed: {exc}")
    return


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(_autostart_once, first_interval=0.5)


def unregister():
    if tcp_server.is_running():
        tcp_server.stop()
    if bpy.app.timers.is_registered(_autostart_once):
        bpy.app.timers.unregister(_autostart_once)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
