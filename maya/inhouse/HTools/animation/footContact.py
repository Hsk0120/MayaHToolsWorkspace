"""接地区間の滑りと床面との距離、ループ端の姿勢差を計測する。"""

import math

import maya.api.OpenMaya as om
import maya.cmds as cmds


def inspectContact(node, start, end, contactStart, contactEnd, floor=0.0, step=1.0, floorNormal=None, floorMesh=None):
    """ワールド平面に対する足の接地と、両端の位置・回転差を計測する。

    floorMesh指定時は現在時刻の静的な床と鉛直線の最近交点を使い、滑りは水平距離で測る。
    時刻はシーンのフレーム単位、距離はcm、回転は度。接地点に置いたTransformを指定する。
    """
    if not all(math.isfinite(x) for x in (start, end, contactStart, contactEnd, floor, step)):
        raise ValueError("Enter finite frame values and floor height.")
    if not start <= contactStart <= contactEnd <= end or step <= 0:
        raise ValueError("Contact frames must lie inside the loop and step must be positive.")
    up = 1 if cmds.upAxis(query=True, axis=True) == "y" else 2
    up_vector = om.MVector.kYaxisVector if up == 1 else om.MVector.kZaxisVector
    normal = up_vector if floorNormal is None else om.MVector(floorNormal)
    if not all(math.isfinite(component) for component in normal) or normal * up_vector <= 0:
        raise ValueError("Floor normal must be finite and point upwards.")
    normal = normal.normal()
    ground = None
    if floorMesh:
        ground_selection = om.MSelectionList()
        ground_selection.add(floorMesh)
        ground_path = ground_selection.getDagPath(0)
        if not ground_path.node().hasFn(om.MFn.kMesh):
            raise ValueError("Choose a static floor mesh shape.")
        ground = om.MFnMesh(ground_path)
        # 現在時刻の床を固定し、足先だけを各時刻で評価する。
        normal = up_vector
    selection = om.MSelectionList()
    selection.add(node)
    path = selection.getDagPath(0)
    matrix_plug = om.MFnDependencyNode(path.node()).findPlug("worldMatrix", False).elementByLogicalIndex(path.instanceNumber())

    def sample(frame):
        context = om.MDGContext(om.MTime(frame, om.MTime.uiUnit()))
        transform = om.MTransformationMatrix(om.MFnMatrixData(matrix_plug.asMObject(context)).matrix())
        return transform.translation(om.MSpace.kWorld), transform.rotation(asQuaternion=True)

    initial, q0 = sample(start)
    final, q1 = sample(end)
    anchor, _ = sample(contactStart)
    count = int(math.ceil((contactEnd - contactStart) / step))
    slide = clearance = penetration = 0.0
    for index in range(count + 1):
        position, _ = sample(min(contactEnd, contactStart + step * index))
        delta = position - anchor
        slip = (delta - normal * (delta * normal)).length()
        height = (position - up_vector * floor) * normal
        if ground is not None:
            hits = ground.allIntersections(om.MFloatPoint(position), om.MFloatVector(up_vector),
                                           om.MSpace.kWorld, 1e20, True)
            if not hits or not len(hits[0]):
                raise ValueError(f"No floor intersection at frame {min(contactEnd, contactStart + step * index):g}.")
            height = -min(hits[1], key=abs)
        slide = max(slide, slip)
        clearance = max(clearance, height)
        penetration = max(penetration, -height)
    dot = abs(q0.x*q1.x + q0.y*q1.y + q0.z*q1.z + q0.w*q1.w)
    return dict(slide=slide, clearance=clearance, penetration=penetration,
                loopDistance=(final-initial).length(), loopDegrees=math.degrees(2*math.acos(min(1, dot))))


def run():
    """選択した足先を同じ接地区間で検査する画面を開く。"""
    window = "HToolsFootContact"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Foot Contact and Loop")
    cmds.columnLayout(adjustableColumn=True)
    first = cmds.playbackOptions(query=True, minTime=True)
    last = cmds.playbackOptions(query=True, maxTime=True)
    loop = cmds.floatFieldGrp(label="Loop frames", numberOfFields=2, value1=first, value2=last)
    contact = cmds.floatFieldGrp(label="Contact frames", numberOfFields=2, value1=first, value2=last)
    floor = cmds.floatFieldGrp(label="Floor height (cm)")
    normal = cmds.floatFieldGrp(label="Floor normal (XYZ)", numberOfFields=3,
                                value2=float(cmds.upAxis(query=True, axis=True) == "y"),
                                value3=float(cmds.upAxis(query=True, axis=True) == "z"))
    mesh_field = cmds.textFieldGrp(label="Static floor mesh (optional DAG path)")
    step = cmds.floatFieldGrp(label="Sample step (frames)", value1=1)
    report = cmds.scrollField(editable=False, height=170)

    def inspect(*_):
        nodes = cmds.ls(selection=True, long=True, transforms=True) or []
        lines = []
        for node in nodes:
            result = inspectContact(node, *cmds.floatFieldGrp(loop, query=True, value=True)[:2],
                                    *cmds.floatFieldGrp(contact, query=True, value=True)[:2],
                                    floor=cmds.floatFieldGrp(floor, query=True, value1=True),
                                    step=cmds.floatFieldGrp(step, query=True, value1=True),
                                    floorNormal=cmds.floatFieldGrp(normal, query=True, value=True)[:3],
                                    floorMesh=cmds.textFieldGrp(mesh_field, query=True, text=True))
            lines.append(node + "\n" + ", ".join("{}={:.4f}".format(k, v) for k, v in result.items()))
        cmds.scrollField(report, edit=True, text="\n".join(lines) or "Select one or more foot contact transforms.")

    cmds.button(label="Inspect selected feet", command=inspect)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
