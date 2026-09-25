"""既存シーンの状態を保存し、事前検証後に明示適用する。"""
from dataclasses import dataclass, field
import hashlib
import math
from .references import NodeRef, PlugRef, ComponentRef


def _units():
    from maya import cmds
    return {key: cmds.currentUnit(query=True, **{key: True}) for key in ("linear", "angle", "time")}


def _node(value):
    from ..nodes.node import Node
    return value if isinstance(value, Node) else Node(value)


def _items(value):
    if isinstance(value, str) or hasattr(value, "full_name"):
        return [value]
    return list(value)


def _signature(shape):
    """位置に依存しないトポロジー情報。頂点番号対応を検証する。"""
    from maya.api import OpenMaya as om
    selection = om.MSelectionList()
    selection.add(shape)
    path = selection.getDagPath(0)
    if path.node().hasFn(om.MFn.kTransform):
        path.extendToShape()
    if path.node().hasFn(om.MFn.kMesh):
        fn = om.MFnMesh(path)
        counts, indices = fn.getVertices()
        return {"vertices": fn.numVertices, "connectivity": hashlib.sha256(repr((list(counts), list(indices))).encode("ascii")).hexdigest()}
    fn = om.MFnNurbsCurve(path)
    return {"degree": fn.degree, "form": fn.form, "knots": list(fn.knots()),
            "weights": [p.w for p in fn.cvPositions()], "vertices": fn.numCVs}


def _attribute(node, name):
    from maya import cmds
    plug = node + "." + name
    kind = cmds.getAttr(plug, type=True)
    supported = {"bool", "byte", "char", "short", "long", "enum", "float", "double", "doubleAngle", "doubleLinear", "time", "string", "matrix", "double2", "double3", "float2", "float3", "long2", "long3", "short2", "short3"}
    if kind not in supported or cmds.attributeQuery(name.split("[")[0].split(".")[-1], node=node, multi=True):
        # 配列の明示要素は許可するが、配列全体を暗黙展開しない。
        if kind not in supported or "[" not in name:
            raise ValueError("Unsupported attribute type: " + plug)
    return {"name": name, "type": kind, "value": cmds.getAttr(plug)}


def _set_attribute(node, attr):
    from maya import cmds
    name, kind, value = node + "." + attr["name"], attr["type"], attr["value"]
    if kind == "string":
        cmds.setAttr(name, value or "", type="string")
    elif kind == "matrix":
        cmds.setAttr(name, *value, type="matrix")
    elif kind.endswith(("2", "3")):
        cmds.setAttr(name, *value[0], type=kind)
    else:
        cmds.setAttr(name, value)


def _check_attribute_value(attr):
    """編集されたJSONも、値の形と数値を変更前に検証する。"""
    kind, value = attr["type"], attr["value"]
    if kind == "string":
        if value is not None and not isinstance(value, str):
            raise ValueError("String attribute requires string")
        return
    if kind == "matrix":
        values = value
        if not isinstance(values, (list, tuple)) or len(values) != 16:
            raise ValueError("Matrix attribute requires 16 values")
    elif kind.endswith(("2", "3")):
        if not isinstance(value, (list, tuple)) or len(value) != 1 or not isinstance(value[0], (list, tuple)) or len(value[0]) != int(kind[-1]):
            raise ValueError("Invalid compound attribute value")
        values = value[0]
    else:
        values = [value]
    if any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in values):
        raise ValueError("Attribute values must be finite numbers")


@dataclass
class ValidationReport:
    """適用計画のエラー一覧。空ならvalid=True。"""
    errors: list = field(default_factory=list)

    @property
    def valid(self):
        """bool: エラーがないか。"""
        return not self.errors


@dataclass
class ApplyPlan:
    """対象対応と変更前後を保持する。apply時には最新状態で再検証する。"""
    snapshot: object
    mapping: dict = field(default_factory=dict)
    namespace_map: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def apply(self):
        """再検証後に適用する。失敗は例外で通知し、部分適用を成功扱いにしない。"""
        return self.snapshot.apply(mapping=self.mapping, namespace_map=self.namespace_map)


@dataclass
class Snapshot:
    """用途、レコード、取得時単位を持つデータ。取得後はシーンへ追従しない。"""
    kind: str
    records: list
    units: dict
    version: int = 1

    def to_data(self):
        """保存用データを返す。"""
        return {"kind": self.kind, "records": self.records, "units": self.units, "version": self.version}

    @classmethod
    def from_data(cls, data):
        """既知の用途・版だけを読み込む。"""
        if type(data.get("version")) is not int or data["version"] != 1 or data.get("kind") not in set(_KINDS) | {"editor"}:
            raise ValueError("Unsupported snapshot kind/version")
        if not isinstance(data.get("records"), list) or not isinstance(data.get("units"), dict):
            raise ValueError("Invalid snapshot data")
        if data["kind"] == "editor":
            from .editors import EditorSnapshot
            return EditorSnapshot(**data)
        return _KINDS[data["kind"]](**data)

    def plan(self, mapping=None, namespace_map=None):
        """変更候補とエラーを収集する。単位不一致は自動変換せず拒否する。"""
        from maya import cmds
        plan = ApplyPlan(self, dict(mapping or {}), dict(namespace_map or {}))
        options = {"mapping": plan.mapping, "namespace_map": plan.namespace_map}
        if self.kind not in _KINDS or type(self.version) is not int or self.version != 1:
            plan.errors.append("Unsupported snapshot kind/version")
            return plan
        if self.kind != "selection" and self.units != _units():
            plan.errors.append("Maya units differ from the snapshot; restore the captured units before applying")
        seen = set()
        for record in self.records:
            try:
                if self.kind == "selection":
                    names = [ref.resolve(**options).full_name() for ref in record["items"]]
                    plan.changes.append({"target": "selection", "before": cmds.ls(selection=True, long=True) or [], "after": names})
                    continue
                node = record["node"].resolve(**options)
                name = node.full_name()
                if name in seen:
                    raise ValueError("Multiple records map to the same target: " + name)
                seen.add(name)
                if cmds.lockNode(name, query=True, lock=True)[0] or cmds.referenceQuery(name, isNodeReferenced=True):
                    raise ValueError("Locked or referenced target: " + name)
                before = _validate_record(self.kind, node, record, options)
                plan.changes.append({"target": name, "before": before, "after": record})
            except (ValueError, TypeError, RuntimeError, KeyError, IndexError, AttributeError, OverflowError) as error:
                plan.errors.append(str(error))
        return plan

    def validate(self, **kwargs):
        """ValidationReport: planのエラーを返す。シーンは変更しない。"""
        return ValidationReport(self.plan(**kwargs).errors)

    def apply(self, mapping=None, namespace_map=None):
        """全件検証後、Undo可能なMayaコマンドで既存対象へ適用する。

        Args:
            mapping (dict | None): 保存時の絶対名から適用対象への明示対応。
            namespace_map (dict | None): 完全な名前空間から新しい名前空間への対応。
        Returns:
            ApplyPlan: 実行直前の変更計画。
        Raises:
            ValueError: 検証不一致。変更前に停止する。
            RuntimeError: Undo無効または実行中のMayaエラー。途中変更は一回のUndoで戻せるが自動rollbackはしない。
        """
        from maya import cmds
        from ..decorators.undo import undo_chunk
        plan = self.plan(mapping, namespace_map)
        if plan.errors:
            raise ValueError("\n".join(plan.errors))
        if not cmds.undoInfo(query=True, state=True):
            raise RuntimeError("Snapshot.apply requires Undo enabled")
        options = {"mapping": plan.mapping, "namespace_map": plan.namespace_map}
        with undo_chunk("hlibJsonApply"):
            for record in self.records:
                if self.kind == "selection":
                    names = [ref.resolve(**options).full_name() for ref in record["items"]]
                    cmds.select(names, replace=True) if names else cmds.select(clear=True)
                else:
                    _apply_record(self.kind, record["node"].resolve(**options), record, options)
        return plan


class SelectionSnapshot(Snapshot):
    """ノード・Plug・コンポーネントの順序付き選択。"""


class AttributesSnapshot(Snapshot):
    """明示指定した属性の型と値。入力接続・ロックは変更しない。"""


class PoseSnapshot(Snapshot):
    """ローカルTRS・shear・回転順序・pivot・jointOrient等のポーズ。"""


globals().pop("CurveSnapshot", None)


class NurbsCurveSnapshot(Snapshot):
    """既存カーブのCV位置と表示色。同じ次数・ノット・ウェイトのみ適用可能。"""


class SkinWeightsSnapshot(Snapshot):
    """既存mesh skinClusterの疎ウェイト・blendWeights・方式。"""


class AnimationSnapshot(Snapshot):
    """既存AnimCurveの全キー・接線・Infinity。キーは全置換する。"""


class DrivenKeysSnapshot(Snapshot):
    """既存SDKグラフのカーブ・blendWeighted値。接続構成は照合し、再作成しない。"""


_KINDS = {"selection": SelectionSnapshot, "attributes": AttributesSnapshot, "pose": PoseSnapshot,
          "curve": NurbsCurveSnapshot, "skin_weights": SkinWeightsSnapshot, "animation": AnimationSnapshot,
          "driven_keys": DrivenKeysSnapshot}


def capture(targets=None, kind="pose", attributes=None):
    """Mayaの状態を取得する。取得だけでは選択・時刻・シーンを変更しない。

    Args:
        targets: 対象Node/名前またはその列。selectionのみ省略で現在選択。
        kind (str): selection/attributes/pose/curve/skin_weights/animation/driven_keys/editor。
        attributes (list[str] | None): attributesで必須。配列は要素を明示する。
    Returns:
        Snapshot: 未解決参照と値を持つ用途別Snapshot。
    """
    from maya import cmds
    from ..selection import Selection
    from ..components import Component
    from ..plugs.plug import Plug
    if kind == "editor":
        from .editors import capture_editors
        return capture_editors(targets)
    if kind not in _KINDS:
        raise ValueError("Unknown snapshot kind: " + kind)
    if kind == "selection":
        items = Selection.capture() if targets is None else Selection(targets)
        refs = [ComponentRef.capture(x) if isinstance(x, Component) else PlugRef.capture(x) if isinstance(x, Plug) else NodeRef.capture(x) for x in items]
        return SelectionSnapshot(kind, [{"items": refs}], _units())
    if targets is None:
        raise ValueError("Explicit targets are required")
    nodes = [_node(x) for x in _items(targets)]
    if kind == "curve":
        shapes = []
        for node in nodes:
            if node.type() == "nurbsCurve":
                shapes.append(node)
            else:
                children = cmds.listRelatives(node.full_name(), shapes=True, noIntermediate=True, fullPath=True, type="nurbsCurve") or []
                if not children:
                    raise ValueError("Target has no nurbsCurve shapes: " + node.full_name())
                shapes.extend(_node(x) for x in children)
        nodes = shapes
    if kind == "driven_keys":
        nodes = _sdk_nodes(nodes)
    unique = {n.full_name(): n for n in nodes}
    records = [_capture_record(kind, node, attributes) for node in unique.values()]
    if not records:
        raise ValueError("No supported targets")
    result = _KINDS[kind](kind, records, _units())
    # 保存前にも型・非有限値を検証する。
    from .codec import encode
    encode(result)
    return result


def _sdk_nodes(nodes):
    """AnimCurve・blendWeighted・unitConversionを上流に辿る。"""
    from maya import cmds
    result, visited = [], set()
    pending = [n.full_name() for n in nodes]
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        typ = cmds.nodeType(name)
        if typ.startswith("animCurveT"):
            raise ValueError("Time animation is not a driven-key graph")
        if typ.startswith("animCurveU") or typ in ("blendWeighted", "unitConversion"):
            result.append(_node(name))
        sources = cmds.listConnections(name, source=True, destination=False) or []
        pending.extend(x for x in sources if cmds.nodeType(x).startswith("animCurveU") or cmds.nodeType(x) in ("blendWeighted", "unitConversion"))
    return result


def _connections(name):
    from maya import cmds
    pairs = cmds.listConnections(name, source=True, destination=True, connections=True, plugs=True) or []
    return [(PlugRef.capture(pairs[i]), PlugRef.capture(pairs[i + 1])) for i in range(0, len(pairs), 2)]


def _capture_record(kind, node, attributes=None):
    from maya import cmds
    record = {"node": NodeRef.capture(node)}
    name = node.full_name()
    if kind in ("pose", "attributes"):
        attrs = attributes
        if kind == "pose":
            if not cmds.objectType(name, isAType="transform"):
                raise ValueError("Pose requires Transform")
            attrs = [p + axis for p in ("translate", "rotate", "scale", "rotatePivot", "scalePivot", "rotatePivotTranslate", "scalePivotTranslate", "rotateAxis") for axis in "XYZ"]
            attrs = ["rotateOrder"] + attrs + ["shearXY", "shearXZ", "shearYZ"]
            if cmds.objExists(name + ".offsetParentMatrix"):
                attrs.append("offsetParentMatrix")
            if node.type() == "joint":
                attrs += ["jointOrient" + a for a in "XYZ"] + ["segmentScaleCompensate"]
        if not attrs or isinstance(attrs, str):
            raise ValueError("attributes must be a non-empty list")
        record["attributes"] = [_attribute(name, attr) for attr in attrs]
    elif kind == "curve":
        record["topology"] = _signature(name)
        record["positions"] = [cmds.xform(name + ".cv[{}]".format(i), query=True, objectSpace=True, translation=True) for i in range(record["topology"]["vertices"])]
        record["attributes"] = [_attribute(name, attr) for attr in ("overrideEnabled", "overrideRGBColors", "overrideColor", "overrideColorRGB", "lineWidth")]
    elif kind == "skin_weights":
        if node.type() != "skinCluster":
            raise ValueError("Expected skinCluster")
        influences = node.influences()
        weights = list(node.get_weights(influences))
        record.update(geometry=NodeRef.capture(node.mesh_path.fullPathName()), topology=_signature(node.mesh_path.fullPathName()),
                      influences=[NodeRef.capture(x) for x in influences], weights=[[i, v] for i, v in enumerate(weights) if v != 0.0])
        count = record["topology"]["vertices"]
        record["blend_weights"] = [cmds.getAttr(name + ".blendWeights[{}]".format(i)) for i in range(count)]
        record["attributes"] = [_attribute(name, attr) for attr in ("skinningMethod", "normalizeWeights", "maintainMaxInfluences", "maxInfluences")]
    elif kind in ("animation", "driven_keys"):
        if node.type().startswith("animCurve"):
            record.update(inputs=node.key_inputs(), values=node.values(), tangents=[node.tangent(i) for i in range(node.key_count())], infinity=node.infinity())
        elif kind == "driven_keys" and node.type() in ("blendWeighted", "unitConversion"):
            attrs = ["conversionFactor"] if node.type() == "unitConversion" else ["weight[{}]".format(i) for i in cmds.getAttr(name + ".weight", multiIndices=True) or []]
            record["attributes"] = [_attribute(name, attr) for attr in attrs]
        else:
            raise ValueError("Expected animation curve")
        if kind == "driven_keys":
            record["connections"] = _connections(name)
    return record


def _validate_record(kind, node, record, options):
    from maya import cmds
    name = node.full_name()
    before = {}
    for attr in record.get("attributes", []):
        _check_attribute_value(attr)
        plug = name + "." + attr["name"]
        current = _attribute(name, attr["name"])
        if current["type"] != attr["type"]:
            raise ValueError("Attribute type mismatch: " + plug)
        if not cmds.getAttr(plug, settable=True) or cmds.listConnections(plug, source=True, destination=False):
            raise ValueError("Attribute locked or connected: " + plug)
        before[attr["name"]] = current["value"]
    if kind in ("curve", "skin_weights"):
        shape = name if kind == "curve" else node.mesh_path.fullPathName()
        if _signature(shape) != record["topology"]:
            raise ValueError("Topology differs: " + shape)
        if kind == "curve":
            if cmds.listConnections(name + ".create", source=True, destination=False):
                raise ValueError("Curve has construction history: " + name)
            if len(record["positions"]) != record["topology"]["vertices"] or any(len(p) != 3 for p in record["positions"]):
                raise ValueError("Invalid CV positions")
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) for p in record["positions"] for v in p):
                raise ValueError("CV coordinates must be finite numbers")
            for i in range(len(record["positions"])):
                if not cmds.getAttr(name + ".controlPoints[{}]".format(i), settable=True):
                    raise ValueError("CV is locked or connected")
            before["positions"] = [cmds.xform(name + ".cv[{}]".format(i), query=True, translation=True, objectSpace=True) for i in range(len(record["positions"]))]
        else:
            geometry = record["geometry"].resolve(**options).full_name()
            if geometry != node.mesh_path.fullPathName():
                raise ValueError("Skin geometry mapping differs")
            names = [r.resolve(**options).full_name() for r in record["influences"]]
            current = [NodeRef.capture(x).resolve().full_name() for x in node.influences()]
            if len(names) != len(set(names)) or set(names) != set(current):
                raise ValueError("Influence membership differs")
            size = record["topology"]["vertices"] * len(names)
            indices = [p[0] for p in record["weights"]]
            if len(set(indices)) != len(indices) or any(type(i) is not int or not 0 <= i < size for i in indices):
                raise ValueError("Invalid sparse weight indices")
            if len(record["blend_weights"]) != record["topology"]["vertices"]:
                raise ValueError("Invalid blendWeights count")
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for _, v in record["weights"]):
                raise ValueError("Weights must be non-negative finite numbers")
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in record["blend_weights"]):
                raise ValueError("blendWeights must be between zero and one")
            for attr in ("weightList", "blendWeights"):
                if cmds.getAttr(name + "." + attr, lock=True) or cmds.listConnections(name + "." + attr, source=True, destination=False):
                    raise ValueError("Weight attributes locked or connected")
            for influence in names:
                if cmds.objExists(influence + ".lockInfluenceWeights") and cmds.getAttr(influence + ".lockInfluenceWeights"):
                    raise ValueError("Influence weights locked: " + influence)
            for attr in cmds.listAttr(name + ".weightList", multi=True) or []:
                if cmds.getAttr(name + "." + attr, lock=True):
                    raise ValueError("Weight element locked: " + attr)
            for i in range(record["topology"]["vertices"]):
                if not cmds.getAttr(name + ".blendWeights[{}]".format(i), settable=True):
                    raise ValueError("Blend weight locked or connected")
            before["weights"] = list(node.get_weights(names))
    if "inputs" in record:
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in record["inputs"] + record["values"]):
            raise ValueError("Animation keys must be finite numbers")
        if not record["inputs"] and node.key_count():
            raise ValueError("Cannot clear the last animation key while preserving the existing node")
        if len(record["inputs"]) != len(record["values"]) or len(record["inputs"]) != len(record["tangents"]):
            raise ValueError("Invalid key counts")
        if any(a >= b for a, b in zip(record["inputs"], record["inputs"][1:])):
            raise ValueError("Key inputs must be strictly increasing")
        for attr in ("ktv", "preInfinity", "postInfinity"):
            if cmds.getAttr(name + "." + attr, lock=True):
                raise ValueError("Animation attribute locked: " + attr)
        before.update(inputs=node.key_inputs(), values=node.values())
    if "connections" in record:
        expected = {tuple(p.resolve(**options).full_name() for p in pair) for pair in record["connections"]}
        actual = {tuple(p.resolve().full_name() for p in pair) for pair in _connections(name)}
        if expected != actual:
            raise ValueError("Driven-key connections differ: " + name)
    from .codec import encode
    encode(record)
    return before


def _apply_record(kind, node, record, options):
    from maya import cmds
    name = node.full_name()
    for attr in record.get("attributes", []):
        _set_attribute(name, attr)
    if kind == "curve":
        for i, pos in enumerate(record["positions"]):
            cmds.xform(name + ".cv[{}]".format(i), objectSpace=True, translation=pos)
    elif kind == "skin_weights":
        names = [r.resolve(**options).full_name() for r in record["influences"]]
        weights = [0.0] * (record["topology"]["vertices"] * len(names))
        for index, value in record["weights"]:
            weights[index] = value
        node.set_weights(names, weights)
        for i, value in enumerate(record["blend_weights"]):
            cmds.setAttr(name + ".blendWeights[{}]".format(i), value)
    if "inputs" in record:
        # 全キーを先にcutするとMayaがカーブ本体を削除するため、保存キーを先に設定する。
        for x, y in zip(record["inputs"], record["values"]):
            node.set_key(x, y)
        wanted = set(record["inputs"])
        for i, x in reversed(list(enumerate(node.key_inputs()))):
            if x not in wanted:
                cmds.cutKey(name, clear=True, animation="objects", index=(i, i))
        for i, tangent in enumerate(record["tangents"]):
            node.set_tangent(i, weightedTangents=tangent["weightedTangents"])
            node.set_tangent(i, lock=False)
            if tangent["weightedTangents"]:
                node.set_tangent(i, weightLock=False)
            node.set_tangent(i, inTangentType=tangent["inTangentType"], outTangentType=tangent["outTangentType"])
            fixed = {}
            for prefix in ("in", "out"):
                if tangent[prefix + "TangentType"] == "fixed":
                    fixed[prefix + "Angle"] = tangent[prefix + "Angle"]
                    if tangent["weightedTangents"]:
                        fixed[prefix + "Weight"] = tangent[prefix + "Weight"]
            if fixed:
                node.set_tangent(i, **fixed)
            node.set_tangent(i, lock=tangent["lock"])
            if tangent["weightedTangents"]:
                node.set_tangent(i, weightLock=tangent["weightLock"])
        node.set_infinity(**record["infinity"])
