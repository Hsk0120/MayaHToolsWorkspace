"""Independent Maya command-port startup; no HTools dependencies."""
import maya.cmds as cmds
import maya.utils as maya_utils

PORT_SETTINGS = ((":7001", "mel"), (":7002", "python"))
_scheduled = False


def open_ports():
    """Open missing ports, preserving the existing HTools configuration."""
    for port_name, source_type in PORT_SETTINGS:
        try:
            if cmds.commandPort(port_name, q=True):
                print("[MayaCommandPorts] {} already open".format(port_name))
                continue
            cmds.commandPort(name=port_name, sourceType=source_type, echoOutput=False)
            print("[MayaCommandPorts] {} ({}) opened".format(port_name, source_type))
        except Exception as error:
            cmds.warning("[MayaCommandPorts] Failed to open {} ({}): {}".format(
                port_name, source_type, error))


def _open_deferred():
    global _scheduled
    try:
        open_ports()
    finally:
        _scheduled = False


def initialize():
    """Schedule once while pending; skip batch/standalone sessions."""
    global _scheduled
    if _scheduled or cmds.about(batch=True):
        return
    _scheduled = True
    try:
        maya_utils.executeDeferred(_open_deferred)
    except Exception:
        _scheduled = False
        raise
