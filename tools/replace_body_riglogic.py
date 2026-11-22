"""このbody.dnaの四肢24ジョイントをMaya標準の回転ネットワークに置き換える。"""
from maya import cmds as c


def install():
    """現在のbody_rl4Embeddedの出力を検査し、1回のUndoで戻せる単位で置換する。"""
    c.loadPlugin("matrixNodes", quiet=True)
    solver = "body_rl4Embedded"
    # 実測したDNAの出力順とblendWeight。NoneはDNAのウェイト列に要素がない出力。
    rows = []
    for side in ("l", "r"):
        for limb, end, weights in (
            ("upperarm", "upperarm", (0.2, 0.8)),
            ("thigh", "thigh", (0.0, 0.5)),
            ("lowerarm", "hand", (None, 0.5) if side == "l" else (0.2, 0.8)),
            ("calf", "foot", (0.0, 0.5)),
        ):
            base = limb + "_" + side
            driver = end + "_" + side
            for index, weight in enumerate(weights, 1):
                rows.append((driver, f"{limb}_twist_0{index}_{side}", "inverse" if driver == base else "twist", weight))
            weight = 0.0 if base == "lowerarm_l" else 0.5
            rows.append((base, limb + "_correctiveRoot_" + side, "swing", weight))

    c.loadPlugin("quatNodes", quiet=True)
    original = c.objExists(solver)
    if not c.undoInfo(q=True, state=True):
        raise RuntimeError("MayaのUndoを有効にしてください。")
    expected = set()
    old = set()
    for driver, target, mode, weight in rows:
        for axis in "XYZ":
            dest = target + ".rotate" + axis
            expected.add(dest)
            src = c.connectionInfo(dest, sourceFromDestination=True)
            valid = src.startswith(solver + ".") if original else src == target + "_local.outputRotate" + axis
            if not valid:
                raise RuntimeError(f"対象の接続が異なります: {dest} <- {src}")
        if not original:
            # 旧版の生成名と実際の上流履歴が一致するものだけを回収する。
            names = {target + suffix for suffix in ("_local", "_fraction", "_fractionMatrix", "_parts",
                     "_correctiveMatrix", "_inverseInput", "_inverseSwing")}
            names.update(driver + suffix for suffix in ("_rotationParts", "_rotationMatrix", "_inverseTwist",
                         "_twistMatrix", "_normalizeXW", "_twistLength", "_twistFallback"))
            old.update(names.intersection(c.listHistory(target + "_local") or []))
            old.add(target + "_local")
    if original:
        for dst in c.listConnections(solver, s=False, d=True, p=True) or []:
            if c.nodeType(dst.split(".")[0]) == "joint" and c.attributeName(dst, long=True) in ("rotateX", "rotateY", "rotateZ") and dst.split(".")[0] + "." + c.attributeName(dst, long=True) in expected:
                continue
            if dst not in expected and not (dst.endswith((".dependNode", ".dn")) and
                    (dst.split(".")[0] == "MayaNodeEditorSavedTabsInfo" or c.nodeType(dst.split(".")[0]) == "nodeGraphEditorInfo") and
                    dst in (c.listConnections(solver + ".message", s=False, d=True, p=True) or [])):
                raise RuntimeError(f"対象外の接続があります: {dst}")

    made = []
    def make(kind, name):
        node = c.createNode(kind, name=name, skipSelect=True)
        made.append(node)
        return node

    parts = {}
    conversions = {}
    link = c.connectAttr
    c.undoInfo(openChunk=True, chunkName="SimpleBodyRotations")
    try:
        try:
            for driver, target, mode, weight in rows:
                if driver not in parts:
                    if not original:
                        parts[driver] = driver + "_rotationParts"
                        old.discard(parts[driver])
                        old.discard(driver + "_rotationMatrix")
                    else:
                        parts[driver] = make("decomposeMatrix", driver + "_rotationParts")
                        matrix = make("composeMatrix", driver + "_rotationMatrix")
                        link(driver + ".rotate", matrix + ".inputRotate")
                        link(driver + ".rotateOrder", matrix + ".inputRotateOrder")
                        link(matrix + ".outputMatrix", parts[driver] + ".inputMatrix")

                # 同じ入力・モード・回転順なら2本のtwistが変換を共有できる。
                order = c.getAttr(target + ".rotateOrder")
                key = (driver, mode, order)
                if key not in conversions:
                    quat = parts[driver] + ".outputQuat"
                    if mode != "twist":
                        inv = make("quatConjugate", driver + "_" + mode + "Conjugate")
                        link(quat, inv + ".inputQuat")
                        quat = inv + ".outputQuat"
                    euler = make("quatToEuler", driver + "_" + mode + "Euler")
                    c.setAttr(euler + ".inputRotateOrder", order)
                    for axis in ("XYZW" if mode == "swing" else "XW"):
                        link(quat + axis, euler + ".inputQuat" + axis)
                    conversions[key] = euler

                pb = make("pairBlend", target + "_blend")
                c.setAttr(pb + ".rotInterpolation", 1)
                c.setAttr(pb + ".rotateOrder", order)
                c.setAttr(pb + ".weight", 0 if weight is None else 1 - weight)
                link(conversions[key] + ".outputRotate", pb + ".inRotate2")
                for axis in "XYZ":
                    dest = target + ".rotate" + axis
                    c.disconnectAttr(c.connectionInfo(dest, sourceFromDestination=True), dest)
                link(pb + ".outRotate", target + ".rotate")
            if original:
                c.delete(solver)
            # 他の用途にも接続されている旧ノードと、その入力元を保持する。
            while old:
                retained = {n for n in old if set(c.listConnections(n, s=False, d=True) or []) - old}
                if not retained:
                    c.delete(list(old))
                    break
                old -= retained
        finally:
            c.undoInfo(closeChunk=True)
    except Exception:
        if made and c.undoInfo(q=True, undoName=True) == "SimpleBodyRotations":
            c.undo()
        raise
    return len(rows)


if __name__ == "__main__":
    print(install())
