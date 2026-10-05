"""既存シーンの状態を保存し、事前検証後に明示適用する。"""

import hashlib
import math
from dataclasses import dataclass, field

from .references import NodeRef, PlugRef, ComponentRef


def _units():
    """現在の Maya の距離・角度・時間の単位名を辞書で返す。"""
    from maya import cmds
    return {key: cmds.currentUnit(query=True, **{key: True}) for key in ("linear", "angle", "time")}


def _node(value):
    """既存の Node をそのまま返し、それ以外は Node として解決する。

    Args:
        value (object): ノード入力。

    Returns:
        Node: 解決したノード。
    """
    from ..nodes.node import Node
    return value if isinstance(value, Node) else Node(value)


def _items(value):
    """単数入力を一要素のリストにし、その他の列をリストにする。

    Args:
        value (object): 文字列、fullName を持つ参照、または反復可能な列。

    Returns:
        list: 入力の列。
    """
    if isinstance(value, str) or hasattr(value, "fullName"):
        return [value]
    return list(value)


def _signature(shape):
    """位置に依存しないトポロジー情報。頂点番号対応を検証する。"""
    from maya.api import OpenMaya as om
    path = om.MDagPath(_node(shape).mpath())
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
    """保存形式とUI単位を保ち、保持参照からアトリビュートを取得する。"""
    plug = _node(node).plug(name)
    kind = plug.dataType()
    supported = {"bool", "byte", "char", "short", "long", "enum", "float", "double", "doubleAngle", "doubleLinear", "time", "string", "matrix", "double2", "double3", "float2", "float3", "long2", "long3", "short2", "short3"}
    if kind not in supported or plug.mplug().isArray:
        raise ValueError("Unsupported attribute type: " + plug.fullName())
    return {"name": name, "type": kind, "value": _attribute_value(plug.mplug())}


def _attribute_value(plug):
    """cmds.getAttrと同じ保存用の値形式・UI単位でMPlugを読む。

    Args:
        plug (MPlug): 対応型を検証済みの保存対象。

    Returns:
        object: 複合値は一要素のlist、行列は16要素のlist。未初期化文字列はNone。
    """
    import maya.api.OpenMaya as om2
    from .._core.attributeType import value_reader, typed_data
    attribute = plug.attribute()
    if plug.isCompound:
        return [tuple(_attribute_value(plug.child(i)) for i in range(plug.numChildren()))]
    if attribute.hasFn(om2.MFn.kUnitAttribute):
        from .._core.unitValue import convert
        return convert(plug, value_reader(attribute)(plug), to_ui=True)
    if attribute.hasFn(om2.MFn.kMatrixAttribute):
        data = typed_data(plug)
        return None if data.isNull() else list(om2.MFnMatrixData(data).matrix())
    if attribute.hasFn(om2.MFn.kTypedAttribute):
        kind = om2.MFnTypedAttribute(attribute).attrType()
        if kind == om2.MFnData.kMatrix:
            data = typed_data(plug)
            return None if data.isNull() else list(om2.MFnMatrixData(data).matrix())
        if kind == om2.MFnData.kString:
            if typed_data(plug).isNull():
                return None
    reader = value_reader(attribute)
    if reader is not False:
        return reader(plug)
    # charなどcmds固有の返却形式がある型は既存の仕様を維持する。
    from maya import cmds
    return cmds.getAttr(plug.name())


def _set_attribute(node, attr):
    """保存した型と値を cmds.setAttr へ渡して復元する。

    Args:
        node (str): 対象ノード名。
        attr (dict): name、type、value を持つ保存データ。単位の変換は行わない。
    """
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

    @classmethod
    def fromData(cls, data):
        """既知の用途・版だけを読み込む。

        Args:
            data (dict): kind、version、records、units を持つ保存データ。

        Returns:
            Snapshot: kind に対応するスナップショット。
        """
        if type(data.get("version")) is not int or data["version"] != 1 or data.get("kind") not in set(_KINDS) | {"editor"}:
            raise ValueError("Unsupported snapshot kind/version")
        if not isinstance(data.get("records"), list) or not isinstance(data.get("units"), dict):
            raise ValueError("Invalid snapshot data")
        if data["kind"] == "editor":
            from .editors import EditorSnapshot
            return EditorSnapshot(**data)
        return _KINDS[data["kind"]](**data)

    def toData(self):
        """保存用データを返す。"""
        return {"kind": self.kind, "records": self.records, "units": self.units, "version": self.version}

    def plan(self, mapping=None, namespace_map=None):
        """シーンを変更せず、変更候補と検証エラーを収集する。

        選択スナップショット以外は保存時との Maya 単位の不一致をエラーに記録する。
        単位は自動変換しない。選択スナップショットでは単位を比較しない。

        Args:
            mapping (dict | None): 保存ノードパスから移行先への対応。
            namespace_map (dict | None): 保存名前空間から移行先への対応。

        Returns:
            ApplyPlan: 変更前後の候補と検証エラー。
        """
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
                    names = [ref.resolve(**options).fullName() for ref in record["items"]]
                    plan.changes.append({"target": "selection", "before": cmds.ls(selection=True, long=True) or [], "after": names})
                    continue
                node = record["node"].resolve(**options)
                name = node.fullName()
                if name in seen:
                    raise ValueError("Multiple records map to the same target: " + name)
                seen.add(name)
                if cmds.lockNode(name, query=True, lock=True)[0] or cmds.referenceQuery(name, isNodeReferenced=True):
                    raise ValueError("Locked or referenced target: " + name)
                before = _KINDS[self.kind]._validate_record(node, record, options)
                plan.changes.append({"target": name, "before": before, "after": record})
            except (ValueError, TypeError, RuntimeError, KeyError, IndexError, AttributeError, OverflowError) as error:
                plan.errors.append(str(error))
        return plan

    def validate(self, **kwargs):
        """適用候補の検証エラーを返す。シーンは変更しない。

        Args:
            **kwargs: plan() に渡す mapping、namespace_map。

        Returns:
            ValidationReport: 適用候補の検証エラー。
        """
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
        from ..decorators.undo import undoChunk
        plan = self.plan(mapping, namespace_map)
        if plan.errors:
            raise ValueError("\n".join(plan.errors))
        if not cmds.undoInfo(query=True, state=True):
            raise RuntimeError("Snapshot.apply requires Undo enabled")
        options = {"mapping": plan.mapping, "namespace_map": plan.namespace_map}
        with undoChunk("hlibJsonApply"):
            for record in self.records:
                if self.kind == "selection":
                    names = [ref.resolve(**options).fullName() for ref in record["items"]]
                    cmds.select(names, replace=True) if names else cmds.select(clear=True)
                else:
                    _KINDS[self.kind]._apply_record(record["node"].resolve(**options), record, options)
        return plan

    @classmethod
    def _validate_record(cls, node, record, options):
        """共通アトリビュート・キー・接続を検証し、形状検証を委譲する。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            options (dict): 対象名と名前空間の解決設定。

        Returns:
            dict: 変更前の値。
        """
        from maya import cmds
        name = node.fullName()
        before = {}
        for attr in record.get("attributes", []):
            _check_attribute_value(attr)
            plug = name + "." + attr["name"]
            current = _attribute(node, attr["name"])
            if current["type"] != attr["type"]:
                raise ValueError("Attribute type mismatch: " + plug)
            if not cmds.getAttr(plug, settable=True) or cmds.listConnections(plug, source=True, destination=False):
                raise ValueError("Attribute locked or connected: " + plug)
            before[attr["name"]] = current["value"]
        cls._validate_geometry(node, record, options, before)
        if "inputs" in record:
            AnimationSnapshot._validate_keys(node, record, before)
        if "connections" in record:
            DrivenKeysSnapshot._validate_connections(node, record, options)
        from .codec import encode
        encode(record)
        return before

    @classmethod
    def _apply_record(cls, node, record, options):
        """アトリビュート・形状・キーを既存の順序で適用する。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            options (dict): 対象名と名前空間の解決設定。
        """
        from maya import cmds
        name = node.fullName()
        for attr in record.get("attributes", []):
            _set_attribute(name, attr)
        cls._apply_geometry(node, record, options)
        if "inputs" in record:
            # 全キーを先にcutするとMayaがカーブ本体を削除するため、保存キーを先に設定する。
            AnimationSnapshot._apply_keys(node, record)

    @staticmethod
    def _validate_geometry(node, record, options, before):
        """形状を持たない種類では追加検証を行わない。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            options (dict): 対象名と名前空間の解決設定。
            before (dict): 変更前の値を追記する辞書。
        """

    @staticmethod
    def _apply_geometry(node, record, options):
        """形状を持たない種類では追加更新を行わない。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            options (dict): 対象名と名前空間の解決設定。
        """


class SelectionSnapshot(Snapshot):
    """ノード・Plug・コンポーネントの順序付き選択。"""


class AttributesSnapshot(Snapshot):
    """明示指定したアトリビュートの型と値。入力接続・ロックは変更しない。"""

    @staticmethod
    def _capture_record(node, attributes=None):
        """指定アトリビュートの型と値を保存する。

        Args:
            node (Node): 対象の既存ノード。
            attributes (Iterable[str] | None): 取得するアトリビュート名。用途により固定項目を使う。

        Returns:
            dict: 保存用のレコード。
        """
        record = {"node": NodeRef.capture(node)}
        attrs = attributes
        if not attrs or isinstance(attrs, str):
            raise ValueError("attributes must be a non-empty list")
        record["attributes"] = [_attribute(node, attr) for attr in attrs]
        return record


class PoseSnapshot(Snapshot):
    """ローカルTRS・shear・回転順序・pivot・jointOrient等のポーズ。"""

    @staticmethod
    def _capture_record(node, attributes=None):
        """Transform固有のポーズ項目を選び、アトリビュート取得を共有する。

        Args:
            node (Node): 対象の既存ノード。
            attributes (Iterable[str] | None): 取得するアトリビュート名。用途により固定項目を使う。

        Returns:
            dict: 保存用のレコード。
        """
        from maya import cmds
        name = node.fullName()
        if not cmds.objectType(name, isAType="transform"):
            raise ValueError("Pose requires Transform")
        attrs = [p + axis for p in ("translate", "rotate", "scale", "rotatePivot", "scalePivot", "rotatePivotTranslate", "scalePivotTranslate", "rotateAxis") for axis in "XYZ"]
        attrs = ["rotateOrder"] + attrs + ["shearXY", "shearXZ", "shearYZ"]
        if cmds.objExists(name + ".offsetParentMatrix"):
            attrs.append("offsetParentMatrix")
        if node.type() == "joint":
            attrs += ["jointOrient" + a for a in "XYZ"] + ["segmentScaleCompensate"]
        return AttributesSnapshot._capture_record(node, attrs)


globals().pop("CurveSnapshot", None)


class NurbsCurveSnapshot(Snapshot):
    """既存カーブのCV位置と表示色。同じ次数・ノット・ウェイトのみ適用可能。"""

    @staticmethod
    def _capture_record(node, attributes=None):
        """カーブのトポロジー・CV・表示情報を保存する。

        Args:
            node (Node): 対象の既存ノード。
            attributes (Iterable[str] | None): 取得するアトリビュート名。用途により固定項目を使う。

        Returns:
            dict: 保存用のレコード。
        """
        from maya import cmds
        record = {"node": NodeRef.capture(node)}
        name = node.fullName()
        record["topology"] = _signature(node)
        record["positions"] = [cmds.xform(cv.fullName(), query=True, translation=True, objectSpace=True) for cv in node.cvs()]
        record["attributes"] = [_attribute(node, attr) for attr in ("overrideEnabled", "overrideRGBColors", "overrideColor", "overrideColorRGB", "lineWidth")]
        return record

    @staticmethod
    def _validate_geometry(node, record, options, before):
        """形状固有の一致条件を検証し、変更前の値を追記する。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            options (dict): 対象名と名前空間の解決設定。
            before (dict): 変更前の値を追記する辞書。
        """
        from maya import cmds
        name = node.fullName()
        shape = name
        if _signature(shape) != record["topology"]:
            raise ValueError("Topology differs: " + shape)
        if cmds.listConnections(name + ".create", source=True, destination=False):
            raise ValueError("Curve has construction history: " + name)
        if len(record["positions"]) != record["topology"]["vertices"] or any(len(p) != 3 for p in record["positions"]):
            raise ValueError("Invalid CV positions")
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) for p in record["positions"] for v in p):
            raise ValueError("CV coordinates must be finite numbers")
        for i in range(len(record["positions"])):
            if not cmds.getAttr(name + ".controlPoints[{}]".format(i), settable=True):
                raise ValueError("CV is locked or connected")
        before["positions"] = [cmds.xform(cv.fullName(), query=True, translation=True, objectSpace=True) for cv in node.cvs()]

    @staticmethod
    def _apply_geometry(node, record, options):
        """検証済みの形状データを既存の順序で更新する。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            options (dict): 対象名と名前空間の解決設定。
        """
        from maya import cmds
        name = node.fullName()
        for i, pos in enumerate(record["positions"]):
            cmds.xform(name + ".cv[{}]".format(i), objectSpace=True, translation=pos)


class SkinWeightsSnapshot(Snapshot):
    """既存mesh skinClusterの疎ウェイト・blendWeights・方式。"""

    @staticmethod
    def _capture_record(node, attributes=None):
        """スキンの対象・influence・疎ウェイトを保存する。

        Args:
            node (Node): 対象の既存ノード。
            attributes (Iterable[str] | None): 取得するアトリビュート名。用途により固定項目を使う。

        Returns:
            dict: 保存用のレコード。
        """
        from maya import cmds
        from maya import cmds
        record = {"node": NodeRef.capture(node)}
        name = node.fullName()
        if node.type() != "skinCluster":
            raise ValueError("Expected skinCluster")
        influences = node.influences()
        weights = list(node.getWeights(influences))
        record.update(geometry=NodeRef.capture(node.mesh_path.fullPathName()), topology=_signature(node.mesh_path.fullPathName()),
                      influences=[NodeRef.capture(x) for x in influences], weights=[[i, v] for i, v in enumerate(weights) if v != 0.0])
        count = record["topology"]["vertices"]
        record["blend_weights"] = [cmds.getAttr(name + ".blendWeights[{}]".format(i)) for i in range(count)]
        record["attributes"] = [_attribute(node, attr) for attr in ("skinningMethod", "normalizeWeights", "maintainMaxInfluences", "maxInfluences")]
        return record

    @staticmethod
    def _validate_geometry(node, record, options, before):
        """形状固有の一致条件を検証し、変更前の値を追記する。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            options (dict): 対象名と名前空間の解決設定。
            before (dict): 変更前の値を追記する辞書。
        """
        from maya import cmds
        name = node.fullName()
        shape = node.mesh_path.fullPathName()
        if _signature(shape) != record["topology"]:
            raise ValueError("Topology differs: " + shape)
        geometry = record["geometry"].resolve(**options).fullName()
        if geometry != node.mesh_path.fullPathName():
            raise ValueError("Skin geometry mapping differs")
        names = [r.resolve(**options).fullName() for r in record["influences"]]
        current = [NodeRef.capture(x).resolve().fullName() for x in node.influences()]
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
        before["weights"] = list(node.getWeights(names))

    @staticmethod
    def _apply_geometry(node, record, options):
        """検証済みの形状データを既存の順序で更新する。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            options (dict): 対象名と名前空間の解決設定。
        """
        from maya import cmds
        name = node.fullName()
        names = [r.resolve(**options).fullName() for r in record["influences"]]
        weights = [0.0] * (record["topology"]["vertices"] * len(names))
        for index, value in record["weights"]:
            weights[index] = value
        node.setWeights(names, weights)
        for i, value in enumerate(record["blend_weights"]):
            cmds.setAttr(name + ".blendWeights[{}]".format(i), value)


class AnimationSnapshot(Snapshot):
    """既存AnimCurveの全キー・接線・Infinity。キーは全置換する。"""

    @staticmethod
    def _capture_record(node, attributes=None):
        """既存AnimCurveのキー・接線・Infinityを保存する。

        Args:
            node (Node): 対象の既存ノード。
            attributes (Iterable[str] | None): 取得するアトリビュート名。用途により固定項目を使う。

        Returns:
            dict: 保存用のレコード。
        """
        record = {"node": NodeRef.capture(node)}
        if not node.type().startswith("animCurve"):
            raise ValueError("Expected animation curve")
        from ..utils.units import angleToUi
        tangents = [node.getTangent(i) for i in range(node.keyCount())]
        for tangent in tangents:
            for flag in ("inAngle", "outAngle"):
                tangent[flag] = angleToUi(tangent[flag])
        record.update(inputs=[node._unit_value(v) for v in node.keyInputs()],
                      values=[node._unit_value(v, output=True) for v in node.keyValues()],
                      tangents=tangents, infinity=node.getInfinity())
        return record

    @staticmethod
    def _validate_keys(node, record, before):
        """キーの値・順序・更新可能性を検証する。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            before (dict): 変更前の値を追記する辞書。
        """
        from maya import cmds
        name = node.fullName()
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in record["inputs"] + record["values"]):
            raise ValueError("Animation keys must be finite numbers")
        if not record["inputs"] and node.keyCount():
            raise ValueError("Cannot clear the last animation key while preserving the existing node")
        if len(record["inputs"]) != len(record["values"]) or len(record["inputs"]) != len(record["tangents"]):
            raise ValueError("Invalid key counts")
        if any(a >= b for a, b in zip(record["inputs"], record["inputs"][1:])):
            raise ValueError("Key inputs must be strictly increasing")
        for attr in ("ktv", "preInfinity", "postInfinity"):
            if cmds.getAttr(name + "." + attr, lock=True):
                raise ValueError("Animation attribute locked: " + attr)
        before.update(inputs=[node._unit_value(v) for v in node.keyInputs()],
                      values=[node._unit_value(v, output=True) for v in node.keyValues()])

    @staticmethod
    def _apply_keys(node, record):
        """既存カーブを維持し、キー・接線・Infinityを復元する。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
        """
        from maya import cmds
        name = node.fullName()
        # 全キーの先行削除はカーブ本体も消すため、保存キーを先に設定する。
        for x, y in zip(record["inputs"], record["values"]):
            node.setKey(node._unit_value(x, to_ui=False), node._unit_value(y, output=True, to_ui=False))
        wanted = set(node._unit_value(v, to_ui=False) for v in record["inputs"])
        for i, x in reversed(list(enumerate(node.keyInputs()))):
            if x not in wanted:
                cmds.cutKey(name, clear=True, animation="objects", index=(i, i))
        for i, tangent in enumerate(record["tangents"]):
            node.setTangent(i, weightedTangents=tangent["weightedTangents"])
            node.setTangent(i, lock=False)
            if tangent["weightedTangents"]:
                node.setTangent(i, weightLock=False)
            node.setTangent(i, inTangentType=tangent["inTangentType"], outTangentType=tangent["outTangentType"])
            fixed = {}
            for prefix in ("in", "out"):
                if tangent[prefix + "TangentType"] == "fixed":
                    from ..utils.units import angleFromUi
                    fixed[prefix + "Angle"] = angleFromUi(tangent[prefix + "Angle"])
                    if tangent["weightedTangents"]:
                        fixed[prefix + "Weight"] = tangent[prefix + "Weight"]
            if fixed:
                node.setTangent(i, **fixed)
            node.setTangent(i, lock=tangent["lock"])
            if tangent["weightedTangents"]:
                node.setTangent(i, weightLock=tangent["weightLock"])
        node.setInfinity(**record["infinity"])


class DrivenKeysSnapshot(Snapshot):
    """既存SDKグラフのカーブ・blendWeighted値。接続構成は照合し、再作成しない。"""

    @staticmethod
    def _capture_record(node, attributes=None):
        """SDK部品の値と既存の接続構成を保存する。

        Args:
            node (Node): 対象の既存ノード。
            attributes (Iterable[str] | None): 取得するアトリビュート名。用途により固定項目を使う。

        Returns:
            dict: 保存用のレコード。
        """
        from maya import cmds
        name = node.fullName()
        if node.type().startswith("animCurve"):
            record = AnimationSnapshot._capture_record(node, attributes)
        elif node.type() in ("blendWeighted", "unitConversion"):
            record = {"node": NodeRef.capture(node)}
            attrs = ["conversionFactor"] if node.type() == "unitConversion" else ["weight[{}]".format(i) for i in cmds.getAttr(name + ".weight", multiIndices=True) or []]
            record["attributes"] = [_attribute(node, attr) for attr in attrs]
        else:
            raise ValueError("Expected animation curve")
        record["connections"] = _connections(name)
        return record

    @staticmethod
    def _validate_connections(node, record, options):
        """保存時のSDK接続が維持されているか検証する。

        Args:
            node (Node): 対象の既存ノード。
            record (dict): 保存した一件分のデータ。
            options (dict): 対象名と名前空間の解決設定。
        """
        name = node.fullName()
        expected = {tuple(p.resolve(**options).fullName() for p in pair) for pair in record["connections"]}
        actual = {tuple(p.resolve().fullName() for p in pair) for pair in _connections(name)}
        if expected != actual:
            raise ValueError("Driven-key connections differ: " + name)


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
    from ..scene.selection import Selection
    from ..components import Component
    from ..plugs.plug import Plug
    if kind == "editor":
        from .editors import captureEditors
        return captureEditors(targets)
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
                children = cmds.listRelatives(node.fullName(), shapes=True, noIntermediate=True, fullPath=True, type="nurbsCurve") or []
                if not children:
                    raise ValueError("Target has no nurbsCurve shapes: " + node.fullName())
                shapes.extend(_node(x) for x in children)
        nodes = shapes
    if kind == "driven_keys":
        nodes = _sdk_nodes(nodes)
    unique = {n.fullName(): n for n in nodes}
    records = [_KINDS[kind]._capture_record(node, attributes) for node in unique.values()]
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
    pending = [n.fullName() for n in nodes]
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
    """指定対象の接続を PlugRef の組として取得する。

    Args:
        name (str): listConnections に渡す対象名。

    Returns:
        list[tuple[PlugRef, PlugRef]]: 対象側、接続相手側の順の組。
            接続元、接続先の順へ並べ替える処理は行わない。
    """
    from maya import cmds
    pairs = cmds.listConnections(name, source=True, destination=True, connections=True, plugs=True) or []
    return [(PlugRef.capture(pairs[i]), PlugRef.capture(pairs[i + 1])) for i in range(0, len(pairs), 2)]
