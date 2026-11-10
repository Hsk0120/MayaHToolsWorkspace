"""名前で指定したアトリビュートの値を、型を問わず保存・復元する。"""

from .. import logger
from .codec import encode
from .plugRef import PlugRef
from .poseSnapshot import _block_reason, _require_nodes, _write_plug
from .snapshot import Snapshot, ValidationReport

#: 保存しない値の目印。
_UNSUPPORTED = object()


class AttributesSnapshot(Snapshot):
    """指定したアトリビュートの値を、キー可能かどうか・型を問わず保持する。

    数値・bool・enumの番号・文字列・マトリクス・double3等のコンパウンドアトリビュート・型付き配列を扱う。
    角度は度、距離はcmで保存する(:meth:`Plug.get` の既定)。ユーザー定義アトリビュートの定義(addAttr)は
    保存しないため、適用先に無いアトリビュートは飛ばす。マルチアトリビュート全体・message・値の無いものは保存しない。

    データの形::

        {"plugs": [{"plug": {<PlugRef>}, "value": <値>}, ...]}

    Examples:
        >>> snap = AttributesSnapshot.capture(mlib.ls(type="joint"), ["radius", "visibility"])
        >>> snap.save("attrs.json")
        >>> AttributesSnapshot.load("attrs.json").apply()
    """

    FORMAT = "mlib.attributes"
    VERSION = 1

    @classmethod
    def capture(cls, nodes, attributes=None):
        """指定したアトリビュートの現在値を取得する。

        ``nodes`` の各ノードについて ``attributes`` の各名前を探し、ノードに無い名前は飛ばす。
        ``nodes`` にPlug(または ``"node.attr"`` の文字列)を含めると、そのPlugだけを記録する。
        同じPlugは最初の1回だけ記録する。

        Args:
            nodes (Iterable[Node | Plug | str]): 対象のノードまたはPlug。1つの指定も受け付ける。
            attributes (Iterable[str] | None): 各ノードで記録するアトリビュートの名前・パス。
                NoneはPlugだけを記録する。

        Returns:
            AttributesSnapshot: 取得した値を持つ新しいインスタンス。

        Raises:
            TypeError: nodes・attributesの型が違う場合。
            ValueError: attributesを指定せずにノードを渡した場合。
            RuntimeError: ノードが存在しない場合。
            MissingAttributeError: 指定したPlugが存在しない場合。
        """
        names = _require_attribute_names(attributes)
        entries = []
        seen = set()
        for plug in _collect_plugs(nodes, names):
            key = PlugRef.capture(plug)
            identity = (plug.getNode().getFullName(), key.attribute)
            if identity in seen:
                continue
            seen.add(identity)
            value = _capture_value(plug)
            if value is not _UNSUPPORTED:
                entries.append({"plug": key.toData(), "value": value})
        return cls({"plugs": entries})

    def apply(self, *, nameMap=None, replace=None, namespaceMap=None):
        """保存した値を、対応付けたノードのアトリビュートへ書き戻す。

        1回のUndoにまとめる。見つからないノードは ``missing``、ロック・入力接続・対象に無いアトリビュートは
        ``skipped`` に記録して飛ばし、まとめて警告する。

        Args:
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。

        Returns:
            ValidationReport: 適用の結果。
        """
        return self._run_apply({"nameMap": nameMap, "replace": replace, "namespaceMap": namespaceMap}, {})

    def _check_data(self, data):
        """``plugs`` の各項目がPlug参照と値を持つか確かめる。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が違う、または値がJSONで書けない場合。
        """
        entries = data.get("plugs")
        if not isinstance(entries, list):
            raise ValueError("attributes data must have a 'plugs' list")
        for entry in entries:
            if not isinstance(entry, dict) or "value" not in entry:
                raise ValueError(f"Invalid attributes entry: {entry!r}")
            PlugRef.fromData(entry.get("plug"))
            try:
                encode(entry["value"])
            except TypeError as error:
                raise ValueError(f"Invalid attribute value in JSON: {entry['value']!r}") from error

    def _validate(self, mapping, report, options):
        """ノードの対応と、書けないアトリビュートを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
        """
        self._plan(mapping, report)

    def _apply(self, mapping, report, options, fast):
        """書けるアトリビュートへ値を書き込む。

        飛ばすものは :meth:`_validate` で記録済みのため、ここでは書込みに失敗したものだけを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
            fast (bool): 使わない(常にcmdsで書く)。
        """
        for plug, value in self._plan(mapping, ValidationReport()):
            _write_plug(plug, value, report)

    def _plan(self, mapping, report):
        """書き込む (Plug, 値) を集め、見つからないもの・書けないものをreportへ記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。

        Returns:
            list[tuple[Plug, object]]: 書き込める組。
        """
        writes = []
        for entry in self._data["plugs"]:
            ref = PlugRef.fromData(entry["plug"])
            node = ref.node.resolve(mapping)
            if node is None:
                report.addMissing(ref.node.mappedName(mapping))
                continue
            label = node.getName() + "." + ref.attribute
            plug = ref.resolve(mapping)
            if plug is None:
                report.addSkipped(label, "missing attribute")
                continue
            reason = _block_reason(plug.mplug())
            if reason:
                report.addSkipped(label, reason)
                continue
            if entry["value"] is None:
                report.addSkipped(label, "no value")
                continue
            writes.append((plug, entry["value"]))
        return writes


def _require_attribute_names(attributes):
    """アトリビュート名の指定を確かめてlistにする。

    Args:
        attributes (Iterable[str] | str | None): アトリビュート名。

    Returns:
        list[str]: 名前。Noneは空list。

    Raises:
        TypeError: 文字列以外を含む場合。
        ValueError: 空の名前を含む場合。
    """
    if attributes is None:
        return []
    if isinstance(attributes, str):
        attributes = [attributes]
    try:
        names = list(attributes)
    except TypeError:
        raise TypeError("attributes must be an iterable of attribute names") from None
    for name in names:
        if not isinstance(name, str):
            raise TypeError("attribute names must be strings")
        if not name:
            raise ValueError("attribute names must not be empty")
    return names


def _collect_plugs(nodes, names):
    """ノード・Plugの指定から、記録するPlugを指定順に集める。

    Args:
        nodes (Iterable[Node | Plug | str] | Node | Plug | str): 対象。
        names (list[str]): 各ノードで探すアトリビュート名。

    Returns:
        list[Plug]: 記録するPlug。ノードに無い名前は含めない。

    Raises:
        TypeError: nodesの型が違う場合。
        ValueError: namesが空でノードを渡した場合。
        RuntimeError: ノード・Plugが存在しない場合。
    """
    # 循環参照の回避: plugs・cmdsはノードのメソッドからmlib.jsonを使う。
    from ..cmds import getPlug
    from ..nodes.node import Node
    from ..plugs.plug import Plug
    if isinstance(nodes, (str, Node, Plug)):
        nodes = [nodes]
    try:
        nodes = list(nodes)
    except TypeError:
        raise TypeError("nodes must be a node, a plug or an iterable of them") from None
    result = []
    for item in nodes:
        if isinstance(item, Plug):
            result.append(item)
            continue
        if isinstance(item, str) and "." in item:
            result.append(getPlug(item))
            continue
        if not names:
            raise ValueError("attributes are required when nodes are given")
        node = _require_nodes(item)[0]
        for name in names:
            try:
                result.append(node.getPlug(name))
            except (AttributeError, RuntimeError, ValueError):
                continue
    return result


def _capture_value(plug):
    """Plugの値を、保存できる形で取得する。

    Args:
        plug (Plug): 対象のPlug。

    Returns:
        object: 値(角度は度、距離はcm)。保存できないものは ``_UNSUPPORTED``。
    """
    name = plug.getName()
    if plug.mplug().isArray:
        logger.warning("AttributesSnapshot: skipped multi attribute %s (capture its elements instead)", name)
        return _UNSUPPORTED
    if plug.getType() == "message":
        logger.warning("AttributesSnapshot: skipped message attribute %s", name)
        return _UNSUPPORTED
    try:
        value = plug.get()
        encode(value)
    except (RuntimeError, TypeError, ValueError) as error:
        logger.warning("AttributesSnapshot: skipped %s (%s)", name, error)
        return _UNSUPPORTED
    if value is None:
        logger.warning("AttributesSnapshot: skipped %s (no value)", name)
        return _UNSUPPORTED
    return value
