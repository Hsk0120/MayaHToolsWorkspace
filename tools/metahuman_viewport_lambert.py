"""Convert assigned MetaHuman materials to Lambert for Viewport 2.0.

Run this file in the Maya Script Editor (Python) to convert the scene.
Call convert(dry_run=True) to list the changes without editing the scene.
"""

from maya import cmds


_CHUNK = "Convert MetaHuman Materials to Lambert"
_LEGACY_TYPES = {"blinn", "phong", "phongE"}
_LAMBERT_INPUTS = ("color", "transparency", "diffuse", "ambientColor", "incandescence", "normalCamera")


def _source(plug):
    """Return the source plug of a directly connected destination."""
    if cmds.connectionInfo(plug, isExactDestination=True):
        return cmds.connectionInfo(plug, sourceFromDestination=True)
    return ""


def _copy_input(old, new, attr):
    """Copy a value and any connection on the compound or its children."""
    old_plug = f"{old}.{attr}"
    new_plug = f"{new}.{attr}"
    source = _source(old_plug)
    if source:
        cmds.connectAttr(source, new_plug)
        return

    if attr == "normalCamera":
        # Unconnected normals are computed by Maya at shading time.
        return

    children = cmds.attributeQuery(attr, node=old, listChildren=True) or []
    if not children:
        cmds.setAttr(new_plug, cmds.getAttr(old_plug))
        return
    for child in children:
        source = _source(f"{old}.{child}")
        if source:
            cmds.connectAttr(source, f"{new}.{child}")
        else:
            cmds.setAttr(f"{new}.{child}", cmds.getAttr(f"{old}.{child}"))


def _configure_dx(old, new, texture):
    """Use the DX material's base texture or constant diffuse color."""
    if texture:
        cmds.connectAttr(texture, f"{new}.color")
    elif cmds.objExists(f"{old}.DiffuseColor"):
        cmds.setAttr(f"{new}.color", *cmds.getAttr(f"{old}.DiffuseColor")[0], type="double3")

    if cmds.objExists(f"{old}.Opacity"):
        transparency = 1.0 - cmds.getAttr(f"{old}.Opacity")
        cmds.setAttr(f"{new}.transparency", *([transparency] * 3), type="double3")


def convert(*, dry_run=False):
    """Replace assigned surface shaders, preserving shading group membership.

    Args:
        dry_run: Report the planned connections without modifying Maya.

    Returns:
        Mapping from original materials to new Lambert materials. Empty in preview mode.
    """
    plan = []
    for group in cmds.ls(type="shadingEngine") or []:
        if not cmds.sets(group, query=True):
            continue
        destination = f"{group}.surfaceShader"
        source = _source(destination)
        if not source:
            continue
        material = source.split(".", 1)[0]
        kind = cmds.nodeType(material)
        if kind == "lambert":
            continue
        if kind not in _LEGACY_TYPES and kind != "dx11Shader":
            raise RuntimeError(f"Unsupported assigned surface material: {material} ({kind})")
        if cmds.getAttr(destination, lock=True) or cmds.lockNode(group, query=True, lock=True)[0]:
            raise RuntimeError(f"Locked shading group: {group}")

        texture = ""
        if kind == "dx11Shader":
            for flag in ("UseOpacityMaskTexture", "UseDiffuseTextureAlpha"):
                if cmds.objExists(f"{material}.{flag}") and cmds.getAttr(f"{material}.{flag}"):
                    raise RuntimeError(f"Unsupported DX transparency input: {material}.{flag}")
            toggle = f"{material}.UseDiffuseTexture"
            if cmds.objExists(f"{material}.DiffuseTexture") and (
                not cmds.objExists(toggle) or cmds.getAttr(toggle)
            ):
                texture = _source(f"{material}.DiffuseTexture")
        plan.append((material, kind, destination, texture))

    if dry_run:
        for material, kind, destination, texture in plan:
            print(f"{material} ({kind}) -> {destination}" + (f" [color: {texture}]" if texture else ""))
        print(f"{len(plan)} shading group(s) to convert.")
        return {}
    if not plan:
        print("No assigned materials to convert.")
        return {}
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Enable Maya Undo before converting materials.")

    replacements = {}
    cmds.undoInfo(openChunk=True, chunkName=_CHUNK)
    try:
        try:
            for material, kind, destination, texture in plan:
                if material not in replacements:
                    name = material.rsplit(":", 1)[-1]
                    new = cmds.shadingNode("lambert", asShader=True, name=f":{name}_viewportLambert")
                    replacements[material] = new
                    if kind == "dx11Shader":
                        _configure_dx(material, new, texture)
                    else:
                        for attr in _LAMBERT_INPUTS:
                            _copy_input(material, new, attr)
                cmds.connectAttr(f"{replacements[material]}.outColor", destination, force=True)
        finally:
            cmds.undoInfo(closeChunk=True)
    except Exception:
        if replacements and cmds.undoInfo(query=True, undoName=True) == _CHUNK:
            cmds.undo()
        raise
    print(f"Converted {len(replacements)} material(s) across {len(plan)} shading group(s).")
    return replacements


if __name__ == "__main__":
    convert()
