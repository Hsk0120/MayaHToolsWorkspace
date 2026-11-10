# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""名前で指定したアトリビュートの値を、型を問わず保存・復元する。"""

from .. import logger
from .codec import encode
from .plugRef import PlugRef
from .poseSnapshot import _block_reason, _require_nodes, _write_plug
from .snapshot import Snapshot, ValidationReport
from typing import Any, Iterable
from mlib.json.nameMapping import NameMapping
from mlib.nodes.node import Node
from mlib.plugs.plug import Plug

_UNSUPPORTED: Any


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
    FORMAT: str
    VERSION: int
    @classmethod
    def capture(cls, nodes: Iterable[Node | Plug | str], attributes: Iterable[str] | None = ...) -> AttributesSnapshot:
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
        ...
    def apply(self, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ...) -> ValidationReport:
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
        ...
    def _check_data(self, data: dict):
        """``plugs`` の各項目がPlug参照と値を持つか確かめる。

        Args:
            data (dict): 保持する前のデータ。

        Raises:
            ValueError: データの形が違う、または値がJSONで書けない場合。
        """
        ...
    def _validate(self, mapping: NameMapping, report: ValidationReport, options: dict):
        """ノードの対応と、書けないアトリビュートを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
        """
        ...
    def _apply(self, mapping: NameMapping, report: ValidationReport, options: dict, fast: bool):
        """書けるアトリビュートへ値を書き込む。

        飛ばすものは :meth:`_validate` で記録済みのため、ここでは書込みに失敗したものだけを記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。
            options (dict): 使わない。
            fast (bool): 使わない(常にcmdsで書く)。
        """
        ...
    def _plan(self, mapping: NameMapping, report: ValidationReport) -> list[tuple[Plug, object]]:
        """書き込む (Plug, 値) を集め、見つからないもの・書けないものをreportへ記録する。

        Args:
            mapping (NameMapping): 名前の対応付け。
            report (ValidationReport): 記録先。

        Returns:
            list[tuple[Plug, object]]: 書き込める組。
        """
        ...

def _require_attribute_names(attributes: Iterable[str] | str | None) -> list[str]:
    """アトリビュート名の指定を確かめてlistにする。

    Args:
        attributes (Iterable[str] | str | None): アトリビュート名。

    Returns:
        list[str]: 名前。Noneは空list。

    Raises:
        TypeError: 文字列以外を含む場合。
        ValueError: 空の名前を含む場合。
    """
    ...

def _collect_plugs(nodes: Iterable[Node | Plug | str] | Node | Plug | str, names: list[str]) -> list[Plug]:
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
    ...

def _capture_value(plug: Plug) -> Any:
    """Plugの値を、保存できる形で取得する。

    Args:
        plug (Plug): 対象のPlug。

    Returns:
        object: 値(角度は度、距離はcm)。保存できないものは ``_UNSUPPORTED``。
    """
    ...
