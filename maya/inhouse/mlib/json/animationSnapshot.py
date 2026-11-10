"""ノードのアニメーション(時間入力のアニメカーブとアニメーションレイヤー)を保存・復元する。"""

import math

import maya.cmds as cmds

from ..decorator import _require_bool
from ..nodes.node import Node
from ._animCurveData import (_check_curve, _is_time_input, _merge_keys, _output_kind, _read_curve, _transform_keys,
                             _write_curve)
from .plugRef import PlugRef
from .snapshot import Snapshot

#: 適用時の既存キーの扱い。
_MODES = ("replace", "insert", "merge")
#: レイヤーの設定のうち、animLayerコマンドで読み書きするもの。
_LAYER_FLAGS = ("weight", "mute", "solo", "override", "passthrough")
#: レイヤーの設定のうち、enumのアトリビュートとして名前で読み書きするもの。
_LAYER_ENUMS = ("rotationAccumulationMode", "scaleAccumulationMode")


class AnimationSnapshot(Snapshot):
    """ノードのアトリビュートにつながる時間入力のアニメカーブを、アニメーションレイヤーごとに保持する。

    カーブはキーの時刻・値、接線の型・角度・ウェイト、接線とウェイトのロック、ブレークダウン、
    ウェイト付き接線、前後のインフィニティまで保存し、同じ形に作り直す。値はmlibの既定の単位
    (角度は度、距離はcm)、時刻は保存時のUI時間単位のフレームで保存するため、適用時のUI単位に左右されない。
    アニメーションレイヤーに入ったアトリビュートは、ベースレイヤーと各レイヤーのカーブを別々に保存し、
    レイヤーの設定(ウェイト・ミュート・ソロ・ロック・オーバーライド・パススルー・回転と
    スケールの累積モード・親レイヤー)も保存する。ドリブンキー(単位なし入力のカーブ)は
    :class:`~mlib.json.drivenKeysSnapshot.DrivenKeysSnapshot` で扱う。

    データの形::

        {"timeRange": [1.0, 24.0] or None, "rootLayer": "BaseAnimation" or None,
         "layers": [{"name": "L1", "parent": None, "weight": 1.0, "mute": False, "solo": False, "lock": False,
                     "override": False, "passthrough": True, "rotationAccumulationMode": "...",
                     "scaleAccumulationMode": "..."}, ...],
         "curves": [{"plug": {<PlugRef>}, "layer": None or "L1", "curve": {<カーブ>}}, ...]}

    ``layer`` がNoneのカーブはベースレイヤー(レイヤーが無ければアトリビュートへ直接つながるカーブ)。
    カーブの辞書の形は ``mlib/json/_animCurveData.py`` の説明を参照する。

    Examples:
        >>> anim = AnimationSnapshot.capture(mlib.ls(type="joint"), time=(1, 24))
        >>> anim.save("walk.json")
        >>> AnimationSnapshot.load("walk.json").apply(namespaceMap={"chrA": "chrB"}, mode="insert", timeOffset=100)
    """

    FORMAT = "mlib.animation"
    VERSION = 1

    @classmethod
    def capture(cls, nodes, *, time=None):
        """ノードのアトリビュートにつながる時間入力のアニメカーブとアニメーションレイヤーを取得する。

        アトリビュートへ直接つながるカーブと、アニメーションレイヤーに入ったアトリビュートの
        ベースレイヤー・各レイヤーのカーブを対象にする。キーが1つも無い(範囲内に無い)カーブは保存しない。
        保存したレイヤーの親レイヤーも、ルート(BaseAnimation)を除いて保存する。

        Args:
            nodes (Iterable[Node | str]): 対象のノード。1つのNode・名前も受け付ける。
            time (tuple[float, float] | None): 両端を含む時刻の範囲(現在のUI時間単位のフレーム)。
                範囲内のキーだけを保存する。Noneは全キー。

        Returns:
            AnimationSnapshot: 取得したカーブを持つ新しいインスタンス。

        Raises:
            TypeError: nodesがノードまたはその並びでない、またはtimeが2つの数値の並びでない場合。
            ValueError: timeが有限でない、または開始が終了より大きい場合。
            RuntimeError: ノードが存在しない場合。
        """
        time_range = _require_time_range(time)
        targets = _require_nodes(nodes)
        layer_plugs = _layer_members()
        root = cmds.animLayer(query=True, root=True) if layer_plugs else None
        curves, used_layers = [], []
        seen = set()
        for node in targets:
            full = node.getFullName()
            if full in seen:
                continue
            seen.add(full)
            for attribute, layer, curve in _node_curves(full, layer_plugs.get(full, []), root):
                data = _read_curve(curve, input_range=time_range)
                if not data["keys"]:
                    continue
                curves.append({"plug": PlugRef.capture(full + "." + attribute).toData(), "layer": layer,
                               "curve": data})
                if layer is not None and layer not in used_layers:
                    used_layers.append(layer)
        layers = _capture_layers(used_layers, root)
        return cls({"timeRange": list(time_range) if time_range else None,
                    "rootLayer": root if layers else None, "layers": layers, "curves": curves})

    def apply(self, *, nameMap=None, replace=None, namespaceMap=None, mode="replace", timeOffset=0.0,
              timing="frame", createLayers=True, fast=False):
        """保存したカーブを、対応付けたノードのアトリビュートへ書き戻す。

        カーブが無いアトリビュートには新しく作る。通常は1回のUndoにまとめ、途中で失敗したら巻き戻す。
        見つからないノード・アトリビュートは ``missing``、ロックされたアトリビュート、アニメカーブ・
        アニメーションレイヤー以外(コンストレイント・ドリブンキー等)が入力につながったアトリビュート、
        出力の種類(角度・距離等)が違うカーブ、見つからない・ロックされたレイヤーのカーブは
        ``skipped`` に記録して飛ばし、まとめて警告する。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。レイヤー名には当てない。
            mode (str): 既存のキーの扱い。``"replace"`` (既定)はカーブごと入れ替える(ウェイト付き接線・
                インフィニティも保存した値にする)。``"insert"`` は保存した範囲(``capture`` の ``time``、
                省略時はカーブごとの最初と最後のキー。timeOffset後)のキーだけを置き換え、範囲外のキーを残す。
                ``"merge"`` は同じ時刻のキーだけを上書きし、ほかの既存のキーを残す。insert・mergeでは既存の
                カーブのウェイト付き接線・インフィニティを保つ。
            timeOffset (float): キーの時刻へ足す量(現在のUI時間単位のフレーム)。
            timing (str): 保存時とfpsが違う場合の扱い。``"frame"`` (既定)はフレーム番号を保ち、
                ``"second"`` は秒を保つように時刻と接線を換算する。
            createLayers (bool): Trueは見つからないレイヤーを保存した設定で作る(既定)。同じ名前の
                レイヤーがあれば設定を変えずに使う。Falseは見つからないレイヤーのカーブを飛ばす。
            fast (bool): TrueはUndoに記録せず、キーをOpenMayaで書く(通常の約4倍速い)。既定False。
                途中で失敗しても巻き戻さない。

        Returns:
            ValidationReport: 適用の結果。

        Raises:
            TypeError: timeOffsetが数値でない、またはcreateLayers・fastがbool以外の場合。
            ValueError: modeが対応外、timeOffsetが有限でない、またはtimingが ``"frame"``・``"second"``
                以外の場合。
        """
        if mode not in _MODES:
            raise ValueError(f"mode must be one of {_MODES}, got {mode!r}")
        if isinstance(timeOffset, bool) or not isinstance(timeOffset, (int, float)):
            raise TypeError("timeOffset must be a number")
        if not math.isfinite(timeOffset):
            raise ValueError("timeOffset must be finite")
        _require_bool(createLayers, "createLayers")
        self._convert_time(0.0, timing)
        return self._run_apply({"nameMap": nameMap, "replace": replace, "namespaceMap": namespaceMap},
                               {"mode": mode, "timeOffset": float(timeOffset), "timing": timing,
                                "createLayers": createLayers}, fast=fast)

    def _check_data(self, data):
        """``curves``・``layers`` の形を確かめる。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が違う場合。
        """
        time_range = data.get("timeRange")
        if time_range is not None:
            try:
                _require_time_range(time_range)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid timeRange in animation data: {time_range!r}") from error
        root = data.get("rootLayer")
        if root is not None and not isinstance(root, str):
            raise ValueError(f"Invalid rootLayer in animation data: {root!r}")
        layers = data.get("layers")
        curves = data.get("curves")
        if not isinstance(layers, list) or not isinstance(curves, list):
            raise ValueError("animation data must have 'layers' and 'curves' lists")
        names = []
        for layer in layers:
            _check_layer(layer, names)
            names.append(layer["name"])
        for entry in curves:
            if not isinstance(entry, dict) or set(entry) != {"plug", "layer", "curve"}:
                raise ValueError(f"Invalid animation curve entry: {entry!r}")
            PlugRef.fromData(entry["plug"])
            if entry["layer"] is not None and entry["layer"] not in names:
                raise ValueError(f"Animation curve refers to an unknown layer: {entry['layer']!r}")
            _check_curve(entry["curve"])
            if not _is_time_input(entry["curve"]["curveType"]):
                raise ValueError(f"Animation curves must have time input: {entry['curve']['curveType']!r}")

    def _validate(self, mapping, report, options):
        """見つからないノード・アトリビュートを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
        """
        for entry in self._data["curves"]:
            _resolve_plug(entry, mapping, report)

    def _apply(self, mapping, report, options, fast):
        """カーブを書き込む。fastではcmdsの部分(カーブ・レイヤーの作成)もUndoに記録しない。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): mode・timeOffset・timing・createLayers。
            fast (bool): TrueはUndoなしでOpenMayaを使う。
        """
        if not fast:
            self._apply_curves(mapping, report, options, fast)
            return
        state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            self._apply_curves(mapping, report, options, fast)
        finally:
            cmds.undoInfo(stateWithoutFlush=state)

    def _apply_curves(self, mapping, report, options, fast):
        """保存したカーブを順に書き込み、作ったレイヤーのロックを最後に戻す。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): mode・timeOffset・timing・createLayers。
            fast (bool): TrueはキーをOpenMayaで書く。
        """
        mode, offset = options["mode"], options["timeOffset"]
        scale = self._convert_time(1.0, options["timing"])
        time_range = self._data["timeRange"]
        if time_range is not None:
            time_range = (time_range[0] * scale + offset, time_range[1] * scale + offset)
        layers = _LayerResolver(self._data["layers"], options["createLayers"])
        for entry in self._data["curves"]:
            plug = _resolve_plug(entry, mapping, report)
            if plug is None:
                continue
            name = str(plug)
            saved = entry["curve"]
            kind = _output_kind(saved["curveType"])
            keys = _transform_keys(saved["keys"], scale, offset, scale if kind == "T" else 1.0)
            if cmds.getAttr(name, lock=True):
                report.addSkipped(name, "locked")
                continue
            layer = None
            if entry["layer"] is not None:
                layer, reason = layers.resolve(entry["layer"])
                if layer is None:
                    report.addSkipped(name, reason)
                    continue
            curve, reason, created = _target_curve(name, layer, keys)
            if curve is None:
                if reason:
                    report.addSkipped(name, reason)
                continue
            curve_type = cmds.nodeType(curve)
            if _output_kind(curve_type) != kind or not _is_time_input(curve_type):
                report.addSkipped(name, f"curve type {curve_type} does not match {saved['curveType']}")
                continue
            settings = saved
            existing = []
            if mode != "replace" and not created:
                current = _read_curve(curve)
                existing = current["keys"]
                if existing:
                    settings = current
            _write_curve(curve, settings, _merge_keys(existing, keys, mode, time_range),
                                  fast=fast)
        layers.restoreLocks()


class _LayerResolver:
    """保存したレイヤー名を、シーンのアニメーションレイヤーへ対応付ける(必要なら作る)。"""

    def __init__(self, layers, create):
        """保存したレイヤーの設定を保持する。

        Args:
            layers (list[dict]): 保存したレイヤーの設定(親が先)。
            create (bool): 見つからないレイヤーを作るか。
        """
        self._settings = {layer["name"]: layer for layer in layers}
        self._create = create
        self._resolved = {}
        self._locks = []

    def resolve(self, name):
        """レイヤー名に対応するシーンのレイヤーを返す。

        Args:
            name (str): 保存したレイヤー名。

        Returns:
            tuple[str | None, str]: レイヤー名と、使えない場合の理由。
        """
        if name not in self._resolved:
            self._resolved[name] = self._find_or_create(name)
        return self._resolved[name]

    def restoreLocks(self):
        """作ったレイヤーのうち、保存時にロックされていたものをロックする。"""
        for layer in self._locks:
            cmds.animLayer(layer, edit=True, lock=True)

    def _find_or_create(self, name):
        """既存のレイヤーを使うか、保存した設定で作る。

        Args:
            name (str): 保存したレイヤー名。

        Returns:
            tuple[str | None, str]: レイヤー名と、使えない場合の理由。
        """
        if cmds.objExists(name) and cmds.nodeType(name) == "animLayer":
            if cmds.animLayer(name, query=True, lock=True):
                return None, f"animation layer {name} is locked"
            return name, ""
        if not self._create:
            return None, f"animation layer {name} not found"
        settings = self._settings[name]
        flags = {}
        if settings["parent"] is not None:
            parent, reason = self.resolve(settings["parent"])
            if parent is None:
                return None, reason
            flags["parent"] = parent
        layer = cmds.animLayer(name, override=settings["override"], passthrough=settings["passthrough"],
                               weight=settings["weight"], **flags)
        for flag in ("mute", "solo"):
            if settings[flag]:
                cmds.animLayer(layer, edit=True, **{flag: True})
        for attribute in _LAYER_ENUMS:
            names = cmds.attributeQuery(attribute, node=layer, listEnum=True)[0].split(":")
            if settings[attribute] in names:
                cmds.setAttr(layer + "." + attribute, names.index(settings[attribute]))
        if settings["lock"]:
            self._locks.append(layer)
        return layer, ""


def _require_nodes(nodes):
    """ノード・名前・その並びを、Nodeのlistにする。

    Args:
        nodes (object): 対象のノード。

    Returns:
        list[Node]: 対象のノード。

    Raises:
        TypeError: ノード・名前・その並びでない場合。
        RuntimeError: ノードが存在しない場合。
    """
    if isinstance(nodes, (str, Node)):
        nodes = [nodes]
    try:
        items = list(nodes)
    except TypeError as error:
        raise TypeError("nodes must be a node, a node name, or an iterable of them") from error
    result = []
    for item in items:
        if not isinstance(item, (str, Node)):
            raise TypeError(f"nodes must contain nodes or node names, got {type(item).__name__}")
        if isinstance(item, str) and not cmds.objExists(item):
            raise RuntimeError(f"Node does not exist: {item}")
        result.append(item if isinstance(item, Node) else Node(item))
    return result


def _require_time_range(time):
    """時刻の範囲を検証する。

    Args:
        time (object): Noneまたは ``(start, end)``。

    Returns:
        tuple[float, float] | None: 範囲。

    Raises:
        TypeError: 2つの数値の並びでない場合。
        ValueError: 有限でない、または開始が終了より大きい場合。
    """
    if time is None:
        return None
    if not isinstance(time, (list, tuple)) or len(time) != 2 or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) for value in time):
        raise TypeError("time must be None or a (start, end) pair of numbers")
    start, end = float(time[0]), float(time[1])
    if not (math.isfinite(start) and math.isfinite(end)):
        raise ValueError("time must be finite")
    if start > end:
        raise ValueError(f"time range start must not be greater than end: {time!r}")
    return start, end


def _check_layer(layer, names):
    """保存したレイヤーの設定の形を確かめる。

    Args:
        layer (object): レイヤーの設定。
        names (list[str]): それより前に出たレイヤー名(親は先に出る)。

    Raises:
        ValueError: 形・型が違う場合。
    """
    expected = {"name", "parent", "lock"} | set(_LAYER_FLAGS) | set(_LAYER_ENUMS)
    if not isinstance(layer, dict) or set(layer) != expected:
        raise ValueError(f"Invalid animation layer data: {layer!r}")
    if not isinstance(layer["name"], str) or not layer["name"] or layer["name"] in names:
        raise ValueError(f"Invalid animation layer name: {layer['name']!r}")
    if layer["parent"] is not None and layer["parent"] not in names:
        raise ValueError(f"Animation layer parent must come before the layer: {layer['parent']!r}")
    weight = layer["weight"]
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
        raise ValueError(f"Invalid animation layer weight: {weight!r}")
    for flag in ("lock", "mute", "solo", "override", "passthrough"):
        if not isinstance(layer[flag], bool):
            raise ValueError(f"Animation layer {flag} must be a bool: {layer[flag]!r}")
    for attribute in _LAYER_ENUMS:
        if not isinstance(layer[attribute], str):
            raise ValueError(f"Animation layer {attribute} must be a string: {layer[attribute]!r}")


def _layer_members():
    """アニメーションレイヤーに入ったアトリビュートを、ノードの完全パスごとに集める。

    Returns:
        dict[str, list[str]]: ノードの完全パスと、アトリビュートのパスの並び(重複なし)。
            レイヤーが無ければ空の辞書。
    """
    members = {}
    for layer in cmds.ls(type="animLayer") or []:
        for plug in cmds.animLayer(layer, query=True, attribute=True) or []:
            node, _, attribute = plug.partition(".")
            full = (cmds.ls(node, long=True) or [node])[0]
            attributes = members.setdefault(full, [])
            if attribute not in attributes:
                attributes.append(attribute)
    return members


def _node_curves(full, layered, root):
    """ノードのアトリビュートにつながる時間入力のカーブを集める。

    Args:
        full (str): ノードの完全パス。
        layered (list[str]): アニメーションレイヤーに入ったアトリビュートのパス。
        root (str | None): ルートレイヤー名。

    Returns:
        list[tuple[str, str | None, str]]: (アトリビュートのパス, レイヤー名(ベースはNone), カーブ名)。
    """
    result = []
    pairs = cmds.listConnections(full, source=True, destination=False, connections=True, plugs=True,
                                 skipConversionNodes=True) or []
    for destination, source in zip(pairs[::2], pairs[1::2]):
        attribute = destination.partition(".")[2]
        if attribute in layered:
            continue
        curve = source.partition(".")[0]
        if cmds.nodeType(curve).startswith("animCurveT"):
            result.append((attribute, None, curve))
    for attribute in layered:
        plug = full + "." + attribute
        affected = cmds.animLayer([plug], query=True, affectedLayers=True) or []
        # affectedLayersは上のレイヤーから返すため、ベース→下のレイヤーの順にする。
        for layer in reversed(affected):
            for curve in cmds.animLayer(layer, query=True, findCurveForPlug=plug) or []:
                if cmds.nodeType(curve).startswith("animCurveT"):
                    result.append((attribute, None if layer == root else layer, curve))
                    break
    return result


def _capture_layers(used, root):
    """使ったレイヤーとその親(ルートを除く)の設定を、親が先の順で返す。

    Args:
        used (list[str]): カーブを保存したレイヤー名。
        root (str | None): ルートレイヤー名。

    Returns:
        list[dict]: レイヤーの設定。
    """
    needed = set()
    for layer in used:
        while layer and layer != root and layer not in needed:
            needed.add(layer)
            layer = cmds.animLayer(layer, query=True, parent=True)
    result = []
    pending = list(cmds.animLayer(root, query=True, children=True) or []) if root else []
    while pending:
        layer = pending.pop(0)
        children = cmds.animLayer(layer, query=True, children=True) or []
        pending = list(children) + pending
        if layer not in needed:
            continue
        parent = cmds.animLayer(layer, query=True, parent=True)
        settings = {"name": layer, "parent": None if parent in (None, root) else parent,
                    "lock": bool(cmds.animLayer(layer, query=True, lock=True))}
        for flag in _LAYER_FLAGS:
            value = cmds.animLayer(layer, query=True, **{flag: True})
            settings[flag] = float(value) if flag == "weight" else bool(value)
        for attribute in _LAYER_ENUMS:
            settings[attribute] = cmds.getAttr(layer + "." + attribute, asString=True)
        result.append(settings)
    return result


def _resolve_plug(entry, mapping, report):
    """カーブを書くPlugを探し、見つからなければreportへ記録する。

    Args:
        entry (dict): カーブの項目。
        mapping (NameMapping): 名前の対応付け。
        report (ValidationReport): 記録先。

    Returns:
        Plug | None: 見つかったPlug。
    """
    ref = PlugRef.fromData(entry["plug"])
    plug = ref.resolve(mapping)
    if plug is None:
        node_missing = ref.node.resolve(mapping) is None
        report.addMissing(ref.node.mappedName(mapping) if node_missing else ref.mappedName(mapping))
    return plug


def _target_curve(plug, layer, keys):
    """Plug(とレイヤー)のカーブを探し、無ければMayaのキー設定で作る。

    Args:
        plug (str): 書き込むPlugの名前。
        layer (str | None): レイヤー名。Noneはベース(レイヤーに入っていなければ直接つながるカーブ)。
        keys (list[dict]): 書くキー。空でカーブが無ければ何もしない。

    Returns:
        tuple[str | None, str, bool]: カーブ名、使えない場合の理由(何もしない場合は空文字列)、
            このとき作ったカーブならTrue。
    """
    sources = cmds.listConnections(plug, source=True, destination=False, skipConversionNodes=True) or []
    source_type = cmds.nodeType(sources[0]) if sources else None
    if source_type is not None and not source_type.startswith(("animCurveT", "animBlendNode")):
        return None, f"connected to {source_type}", False
    if layer is None and source_type is not None and source_type.startswith("animCurveT"):
        return sources[0], "", False
    if layer is None and source_type is not None:
        # レイヤーに入ったアトリビュートのベースは、ルートレイヤーのカーブ。
        layer = cmds.animLayer(query=True, root=True)
    if layer is not None:
        if layer not in (cmds.animLayer([plug], query=True, affectedLayers=True) or []):
            cmds.animLayer(layer, edit=True, attribute=plug)
        curves = cmds.animLayer(layer, query=True, findCurveForPlug=plug) or []
        if curves:
            return curves[0], "", False
    if not keys:
        return None, "", False
    flags = {"animLayer": layer} if layer is not None else {}
    cmds.setKeyframe(plug, time=keys[0]["input"], **flags)
    if layer is not None:
        curves = cmds.animLayer(layer, query=True, findCurveForPlug=plug) or []
    else:
        curves = cmds.listConnections(plug, source=True, destination=False, skipConversionNodes=True,
                                      type="animCurve") or []
    if not curves:
        return None, "Maya did not create an animation curve", False
    return curves[0], "", True
