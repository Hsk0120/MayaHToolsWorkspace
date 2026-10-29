# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaの型名と明示したラッパークラスの対応を管理し、未登録型のクラスを生成する。"""

import weakref
import maya.cmds as cmds
from typing import Any, Mapping

__all__ = ['NodeRegistry']
_INHERITED_TYPES_CACHE: dict
_GENERATING_REGISTRIES: Any

def _inherited_node_types(node_type: str) -> tuple[str, ...]:
    """指定ノードタイプの継承チェーンを取得する。

    ``cmds.nodeType(node_type, isTypeName=True, inherited=True)`` は
    ノードの実体を必要とせず型名だけで継承関係を照会できる一方、都度
    Maya に問い合わせるとやや低速なため、認識済みの型名だけ結果をキャッシュする。
    未知型は後からプラグインが導入される可能性があるため、負結果を保存しない。
    Maya API 2.0 に同等の照会手段が無いため cmds を使用する。

    Args:
        node_type (str): Maya の nodeType 名。

    Returns:
        tuple[str, ...]: node_type 自身を先頭に、直接の親から基底型へ
            向かう順の継承チェーン。Maya が認識しない型名の場合は
            node_type 自身のみを含む1要素の tuple。
    """
    ...

def _node_type_exists(node_type: str) -> bool:
    """Mayaが型名として認識するnodeTypeか判定する。

    :func:`_inherited_node_types` と同じ照会とキャッシュを使う。認識済みの型だけを
    キャッシュし、未知型は後からプラグインが導入される可能性があるため毎回問い合わせる。
    ``om2.MNodeClass(未知型)`` は例外にならず typeId 0 を返すだけなので、存在判定は
    この cmds 照会に統一する。

    Args:
        node_type (str): Maya の nodeType 名。

    Returns:
        bool: ``cmds.nodeType(node_type, isTypeName=True)`` が型名として認識する場合は True。
    """
    ...

def _clear_type_hierarchy_cache() -> None:
    """型継承キャッシュと、動的クラスを生成する全登録表の生成済みクラスを消去する。

    プラグインのロード/アンロードの後に呼び、次の型選択で継承を再照会して
    クラスを作り直す。消去前に保持していた生成クラスの参照は、以後の
    ラッパーに対して ``isinstance`` が偽になる。

    Returns:
        None: 値を返さない。
    """
    ...

def _generated_class_name(node_type: str) -> str:
    """Maya の nodeType 名から生成クラスの名前を決める。

    先頭の1文字を大文字にする(``pointLight`` → ``PointLight``)。先頭が既に大文字の
    型名(``AISEnvFacade`` 等)はそのまま使う。

    Args:
        node_type (str): Maya の nodeType 名。

    Returns:
        str: 生成クラスの名前。
    """
    ...


class NodeRegistry:
    """ノード型・アトリビュート型などの文字列キーとラッパークラスを対応付ける登録表。

    ``generate_classes=True`` の表は、Maya が認識する未登録の nodeType に対して
    クラスを生成して返す(cymel の nodetypes と同じ考え方)。生成クラスの親は
    Maya の継承チェーン(``cmds.nodeType(inherited=True)``)上で最も近い登録済み
    クラスで、登録クラスと生成対象の間にある抽象型(geometryFilter・containerBase・
    entity など)のクラスは生成しない。したがって生成クラス同士の ``isinstance`` は
    Maya の継承を表さず、継承の判定には ``Node.isType()`` を使う。
    """
    def __init__(self, fallback_class: type, resolve_inherited_types: bool = ..., generate_classes: bool = ...) -> None:
        """フォールバッククラスと空のノード型対応表を初期化する。

        Args:
            fallback_class (type): 未登録キーに対して使用するクラス。Maya が認識しない
                型名はクラスを生成せず、このクラスを返す。
            resolve_inherited_types (bool): ``True`` の場合、完全一致が
                無いキーに対して Maya のノードタイプ継承チェーンを辿り、
                最も近い登録済み祖先型のクラスを返す(Plug のアトリビュート型など、
                Mayaのノードタイプ継承と無関係なキー体系では使わない)。
                ``generate_classes=True`` ではこの設定に関わらず継承チェーンを使う。
            generate_classes (bool): ``True`` の場合、完全一致が無い Maya 認識済みの型に
                対して、最寄りの登録済み祖先型(無ければ fallback_class)を親とする
                クラスを生成してキャッシュする。祖先型のクラスをそのまま返す
                フォールバックは行わない。

        Returns:
            None: 値を返さない。
        """
        ...
    def register(self, node_type: str, wrapper_class: type) -> None:
        """文字列キーへラッパークラスを登録する。同じキーは上書きする。

        NodeのnodeTypeやPlugのアトリビュート型で共通に使い、非空strとclassの対応形式を検証する。
        生成済みクラスは親の候補が変わるため全て廃棄する。

        Args:
            node_type (str): 空でない登録キー。
            wrapper_class (type): 対応するクラス。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: キーが文字列以外、またはwrapper_classがクラス以外の場合。
            ValueError: キーが空文字列の場合。
        """
        ...
    def clear(self):
        """この表の登録対応と生成済みクラスを空にする。フォールバック型と継承検索の設定は保持する。"""
        ...
    def replace(self, wrappers: Mapping[str, type]) -> None:
        """全キーと値の対応形式を検証してから、この表を置き換える。

        検査は非空strとclassの対応形式に限り、検証失敗時は現在の登録と生成済みクラスを保つ。

        Args:
            wrappers (Mapping[str, type]): 登録キーとクラスの対応。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: キーが文字列以外、または値がクラス以外の場合。
            ValueError: キーが空文字列の場合。
        """
        ...
    def wrapper_class(self, node_type: str) -> type:
        """キーのクラスを返す。未登録なら設定に応じて生成・祖先型・フォールバックを使う。

        解決の順序は「完全一致の登録 → 生成済みクラス → 生成(generate_classes=True) →
        最寄りの登録祖先型(resolve_inherited_types=True) → フォールバック」。
        Maya が認識しない型名は生成せずフォールバックを返す(未知型は後からプラグインが
        導入される可能性があるため、負結果は保存しない)。

        Args:
            node_type (str): 登録キー。継承検索・生成を使う表ではMayaのnodeType名。

        Returns:
            type: 完全一致、生成クラス、最寄りの登録祖先型、またはフォールバックのクラス。
        """
        ...
    def lookup(self, key: str) -> type | None:
        """登録済みクラスを返す。未登録なら ``None``。

        フォールバックを伴わずに「完全一致する登録があるか」だけを知りたい場合に使う
        (例: Plug のアトリビュート型 dispatch)。生成クラスは登録ではないので返さない。

        Args:
            key (str): 登録キー(nodeType またはアトリビュート型など)。

        Returns:
            type | None: 登録済みクラス。
        """
        ...
    def _generate_class(self, node_type: str) -> type:
        """Maya が認識する未登録の型に対応するクラスを生成し、キャッシュして返す。

        親は継承チェーン上で最も近い登録済みクラス。チェーンに登録が無ければ
        フォールバッククラスを親にする。中間の抽象型は生成しない。

        Args:
            node_type (str): Maya が認識する nodeType 名。

        Returns:
            type: 生成したクラス。``_generated_node_type`` に型名、``_generated`` に True を持つ。
        """
        ...
    def _invalidate_generated(self) -> None:
        """生成済みクラスのキャッシュを空にする。次の照会で作り直す。

        Returns:
            None: 値を返さない。
        """
        ...
    def _registered_types(self, base: type | None = ...) -> list[str]:
        """登録済みの型名を返す。生成クラスは含まない。

        Args:
            base (type | None): 指定した場合、このクラスの派生(自身を含む)が登録された
                型名だけを返す。

        Returns:
            list[str]: 名前順の登録キー。
        """
        ...
    @staticmethod
    def _require_entry(node_type: str, wrapper_class: type) -> None:
        """汎用登録の型名とクラスを検証する。既存キーの上書きは拒否しない。

        Args:
            node_type (str): 登録する型名。
            wrapper_class (type): 対応するクラス。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 型名が文字列以外、またはwrapper_classがクラスではない場合。
            ValueError: 型名が空文字列の場合。
        """
        ...
    def _snapshot(self) -> dict[str, type]:
        """拡張の登録開始前に、現在の型対応を独立したコピーで保持する。

        Returns:
            dict[str, type]: この登録表だけが復元に使う内部状態。
        """
        ...
    def _restore(self, snapshot: dict[str, type]) -> None:
        """登録中の障害で、検証済みの保存状態を再登録せずに復元する。生成済みクラスは廃棄する。

        Args:
            snapshot (dict[str, type]): _snapshotで取得した内部状態。

        Returns:
            None: 値を返さない。
        """
        ...
