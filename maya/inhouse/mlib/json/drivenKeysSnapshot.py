"""ドリブンキー(ドライバーのアトリビュートを入力とするアニメカーブと、その間のノード)を保存・復元する。"""

import math

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..cmds import getPlug
from ..common.drivenKey import DrivenKey
from ..core.attributeType import _from_seconds
from ._animCurveData import _check_curve, _is_time_input, _output_kind, _read_curve, _write_curve
from .animationSnapshot import _require_nodes
from .plugRef import PlugRef
from .snapshot import Snapshot


class DrivenKeysSnapshot(Snapshot):
    """駆動されるアトリビュートごとに、ドライバーのPlug・カーブ・blendWeightedの重みを保持する。

    カーブは :class:`~mlib.json.animationSnapshot.AnimationSnapshot` と同じく完全に保存する。カーブの入力
    (ドライバーの値)は、ドライバーのアトリビュートのmlibの単位(角度は度、距離はcm、時間はフレーム)へ
    直して保存する。Mayaがドライバーとカーブの間に挟むunitConversionの係数は保存時のUI単位で決まるため、
    適用時に作り直された係数に合わせて入力を換算する。値はカーブの出力の単位(角度は度、距離はcm、
    その他は無次元)。複数のドライバーを合計するblendWeightedは、Mayaのドリブンキー設定
    (``setDrivenKeyframe``)で作り直し、各入力の重み(weight)を戻す。

    データの形::

        {"items": [{"driven": {<PlugRef>}, "blendWeighted": False,
                    "drivers": [{"driver": {<PlugRef>}, "weight": 1.0, "curve": {<カーブ>}}, ...]}, ...]}

    Examples:
        >>> keys = DrivenKeysSnapshot.capture(mlib.ls("*_corrective_jnt"))
        >>> keys.save("drivenKeys.json")
        >>> DrivenKeysSnapshot.load("drivenKeys.json").apply(replace=[("_L_", "_R_")])
    """

    FORMAT = "mlib.drivenKeys"
    VERSION = 1

    @classmethod
    def capture(cls, nodes):
        """駆動されるノードのアトリビュートから、ドリブンキーを取得する。

        アトリビュートの入力につながる単位なし入力のカーブ(animCurveU*)と、blendWeightedを経由する
        カーブを対象にする。ドライバーにつながっていないカーブと、blendWeightedのカーブ以外の入力は保存しない。

        Args:
            nodes (Iterable[Node | str]): 駆動されるノード。1つのNode・名前も受け付ける。

        Returns:
            DrivenKeysSnapshot: 取得したドリブンキーを持つ新しいインスタンス。

        Raises:
            TypeError: nodesがノードまたはその並びでない場合。
            RuntimeError: ノードが存在しない場合。
        """
        items = []
        seen = set()
        for node in _require_nodes(nodes):
            full = node.getFullName()
            if full in seen:
                continue
            seen.add(full)
            pairs = cmds.listConnections(full, source=True, destination=False, connections=True, plugs=True,
                                         skipConversionNodes=True) or []
            for destination, source in zip(pairs[::2], pairs[1::2]):
                source_node = source.partition(".")[0]
                source_type = cmds.nodeType(source_node)
                if source_type == "blendWeighted":
                    curves = _blend_curves(source_node)
                elif source_type.startswith("animCurveU"):
                    curves = [(source_node, None)]
                else:
                    continue
                drivers = []
                for curve, index in curves:
                    driver = _driver(curve)
                    if driver is None:
                        continue
                    weight = 1.0 if index is None else cmds.getAttr(f"{source_node}.weight[{index}]")
                    data = _read_curve(curve, input_scale=_input_scale(curve, driver))
                    drivers.append({"driver": PlugRef.capture(driver).toData(), "weight": float(weight),
                                    "curve": data})
                if drivers:
                    driven = full + "." + destination.partition(".")[2]
                    items.append({"driven": PlugRef.capture(driven).toData(),
                                  "blendWeighted": source_type == "blendWeighted", "drivers": drivers})
        return cls({"items": items})

    def apply(self, *, nameMap=None, replace=None, namespaceMap=None):
        """保存したドリブンキーを、対応付けたドライバー・駆動先で作り直す。

        ドライバーと駆動先の組ごとに、既存のカーブがあれば全キーを置き換え、無ければMayaのドリブンキー設定
        (``setDrivenKeyframe``。必要ならblendWeighted・unitConversionも作られる)でカーブを作ってから書く。
        保存していない別のドライバーのカーブは変えない。1回のUndoにまとめ、途中で失敗したら巻き戻す。
        見つからないドライバー・駆動先は ``missing``、ロックされた駆動先、ドリブンキー以外
        (コンストレイント・時間入力のカーブ等)が入力につながった駆動先、出力の種類が違うカーブは
        ``skipped`` に記録して飛ばし、まとめて警告する。fast引数は持たない(ドリブンキーのキー数は少なく、
        作成はcmdsで行うため速くならない)。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。ドライバー・駆動先の両方に当てる。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。

        Returns:
            ValidationReport: 適用の結果。
        """
        return self._run_apply({"nameMap": nameMap, "replace": replace, "namespaceMap": namespaceMap}, {})

    def _check_data(self, data):
        """``items`` の形を確かめる。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が違う場合。
        """
        items = data.get("items")
        if not isinstance(items, list):
            raise ValueError("driven key data must have an 'items' list")
        for item in items:
            if not isinstance(item, dict) or set(item) != {"driven", "blendWeighted", "drivers"} \
                    or not isinstance(item["blendWeighted"], bool) or not isinstance(item["drivers"], list):
                raise ValueError(f"Invalid driven key entry: {item!r}")
            PlugRef.fromData(item["driven"])
            for driver in item["drivers"]:
                if not isinstance(driver, dict) or set(driver) != {"driver", "weight", "curve"}:
                    raise ValueError(f"Invalid driven key driver: {driver!r}")
                PlugRef.fromData(driver["driver"])
                weight = driver["weight"]
                if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
                    raise ValueError(f"Invalid driven key weight: {weight!r}")
                _check_curve(driver["curve"])
                if _is_time_input(driver["curve"]["curveType"]):
                    raise ValueError(f"Driven key curves must have unitless input: {driver['curve']['curveType']!r}")

    def _validate(self, mapping, report, options):
        """見つからないドライバー・駆動先を記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
        """
        for item in self._data["items"]:
            _resolve(item["driven"], mapping, report)
            for driver in item["drivers"]:
                _resolve(driver["driver"], mapping, report)

    def _apply(self, mapping, report, options, fast):
        """ドライバーと駆動先の組ごとにカーブを用意し、キーを書き込む。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
            fast (bool): 使わない(常にcmdsで書く)。
        """
        for item in self._data["items"]:
            driven = _resolve(item["driven"], mapping, report)
            if driven is None:
                continue
            name = str(driven)
            if cmds.getAttr(name, lock=True):
                report.addSkipped(name, "locked")
                continue
            sources = cmds.listConnections(name, source=True, destination=False, skipConversionNodes=True) or []
            source_type = cmds.nodeType(sources[0]) if sources else None
            if source_type is not None and source_type != "blendWeighted" \
                    and not source_type.startswith("animCurveU"):
                report.addSkipped(name, f"connected to {source_type}")
                continue
            for saved in item["drivers"]:
                driver = _resolve(saved["driver"], mapping, report)
                if driver is not None:
                    _apply_driver(driver, driven, saved, report)


def _apply_driver(driver, driven, saved, report):
    """ドライバーと駆動先の組のカーブを用意し、保存したキーで書き直す。

    Args:
        driver (Plug): ドライバー。
        driven (Plug): 駆動先。
        saved (dict): 保存したドライバーの項目。
        report (ValidationReport): 記録先。
    """
    label = f"{driver} -> {driven}"
    data = saved["curve"]
    try:
        relation = DrivenKey(driver, driven)
    except (TypeError, ValueError) as error:
        report.addSkipped(label, str(error))
        return
    curves = relation.getCurves()
    if not curves:
        if not data["keys"]:
            return
        first = data["keys"][0]
        # ドリブンキーの作成(カーブ・blendWeighted・unitConversionと接続)はMayaに任せ、キーは後で書き直す。
        relation.setKey(first["input"], first["value"])
        curves = relation.getCurves()
    if len(curves) != 1:
        report.addSkipped(label, "multiple driven key curves")
        return
    curve = curves[0].getFullName()
    curve_type = cmds.nodeType(curve)
    if _output_kind(curve_type) != _output_kind(data["curveType"]):
        report.addSkipped(label, f"curve type {curve_type} does not match {data['curveType']}")
        return
    _write_curve(curve, data, data["keys"], input_scale=_input_scale(curve, str(driver)))
    for destination in cmds.listConnections(curve + ".output", source=False, destination=True, plugs=True,
                                            skipConversionNodes=True) or []:
        node, _, attribute = destination.partition(".")
        if cmds.nodeType(node) == "blendWeighted" and attribute.startswith("input["):
            weight = f"{node}.weight[{attribute[6:-1]}]"
            if saved["weight"] != 1.0 or cmds.getAttr(weight) != saved["weight"]:
                cmds.setAttr(weight, saved["weight"])


def _resolve(data, mapping, report):
    """PlugRefの辞書からPlugを探し、見つからなければreportへ記録する。

    Args:
        data (dict): PlugRefの辞書。
        mapping (NameMapping): 名前の対応付け。
        report (ValidationReport): 記録先。

    Returns:
        Plug | None: 見つかったPlug。
    """
    ref = PlugRef.fromData(data)
    plug = ref.resolve(mapping)
    if plug is None:
        node_missing = ref.node.resolve(mapping) is None
        report.addMissing(ref.node.mappedName(mapping) if node_missing else ref.mappedName(mapping))
    return plug


def _blend_curves(blend):
    """blendWeightedの各入力につながるドリブンキーのカーブを集める。

    Args:
        blend (str): blendWeightedノードの名前。

    Returns:
        list[tuple[str, int]]: カーブ名と、blendWeightedの入力の番号。
    """
    result = []
    for index in cmds.getAttr(blend + ".input", multiIndices=True) or []:
        sources = cmds.listConnections(f"{blend}.input[{index}]", source=True, destination=False,
                                       skipConversionNodes=True) or []
        if sources and cmds.nodeType(sources[0]).startswith("animCurveU"):
            result.append((sources[0], index))
    return result


def _driver(curve):
    """カーブの入力につながるドライバーのPlug名を返す。

    Args:
        curve (str): カーブ名。

    Returns:
        str | None: ドライバーのPlug名。つながっていなければNone。
    """
    sources = cmds.listConnections(curve + ".input", source=True, destination=False, plugs=True,
                                   skipConversionNodes=True) or []
    return sources[0] if sources else None


def _input_scale(curve, driver):
    """カーブの入力値に掛けると、ドライバーのmlibの単位の値になる倍率を返す。

    カーブの入力は、ドライバーの内部単位(rad・cm・秒)の値にunitConversionの係数を掛けた値になる。

    Args:
        curve (str): カーブ名。
        driver (str): ドライバーのPlug名。

    Returns:
        float: 倍率。
    """
    factor = 1.0
    sources = cmds.listConnections(curve + ".input", source=True, destination=False) or []
    if sources and cmds.nodeType(sources[0]) == "unitConversion":
        factor = cmds.getAttr(sources[0] + ".conversionFactor")
    attribute = getPlug(driver).mplug().attribute()
    scale = 1.0
    if attribute.hasFn(om2.MFn.kUnitAttribute):
        unit_type = om2.MFnUnitAttribute(attribute).unitType()
        if unit_type == om2.MFnUnitAttribute.kAngle:
            scale = math.degrees(1.0)
        elif unit_type == om2.MFnUnitAttribute.kTime:
            scale = _from_seconds(1.0, "frame")
    return scale / factor
