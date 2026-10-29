# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaシーン内の単一対象を表す共通基底と、選択リストによる対象の判別補助。"""

import maya.api.OpenMaya as om2
from typing import Any, Iterator
from mlib.components.component import Component
from mlib.nodes.node import Node
from mlib.plugs.plug import Plug


def _exists(name: str) -> bool:
    """名前がシーンの対象に解決できるか、選択リストへの追加で調べる。

    一意な完全名に対しては ``cmds.objExists`` と同じ結果になる(範囲外のコンポーネント番号や
    マルチアトリビュートの未作成要素も True)。

    Args:
        name (str): 調べる完全名。

    Returns:
        bool: 選択リストへ追加できた場合 True。
    """
    ...

def _selection_plug(selection: om2.MSelectionList, index: int) -> om2.MPlug | None:
    """選択リストの要素がアトリビュートなら、そのMPlugを取得する。

    ``MSelectionList.getPlug`` はノード・コンポーネントの要素で RuntimeError または
    TypeError(Mayaの版で異なる)になるため、両方をNoneに読み替える。

    Args:
        selection (om2.MSelectionList): 選択リスト。
        index (int): 要素の番号。

    Returns:
        om2.MPlug | None: アトリビュートの要素ならMPlug。それ以外、またはnullのMPlugならNone。
    """
    ...

def _selection_component(selection: om2.MSelectionList, index: int) -> tuple[om2.MDagPath, om2.MObject] | None:
    """選択リストの要素がコンポーネントなら、所有DAGパスとコンポーネントを取得する。

    ``MSelectionList.getComponent`` はDGノードの要素で RuntimeError または TypeError になり、
    DAGノード単体ではnullのコンポーネントを返すため、どちらもNoneに読み替える。

    Args:
        selection (om2.MSelectionList): 選択リスト。
        index (int): 要素の番号。

    Returns:
        tuple[om2.MDagPath, om2.MObject] | None: コンポーネントの要素なら(所有DAGパス, コンポーネント)。
            DGノード・DAGノード単体ならNone。
    """
    ...


class _ObjectType(type):
    """Objectへの入力だけを振り分け、派生クラスの構築は通常通り行う。"""


class Object(metaclass=_ObjectType):
    """Node・Plug・単数Componentの共通基底。

    対象の検索には :func:`~mlib.ls` を使う。
    入力した単一対象の種類を保って解決し、所有ノードへの変換は行わない。
    既存のObjectは削除済みでも同じインスタンスを返す。
    複数対象は受け付けず、ノード作成・複製・選択変更は行わない。
    """
    def asString(self) -> str:
        """現在の対象名を文字列へ変換する。

        Node・Plug・Componentそれぞれの ``str()`` と同じ名前を返す。
        名前変更や親子付け替えに追従し、名前をキャッシュしない。
        無効な参照の扱いも各型の ``str()`` に従う。

        Returns:
            str: Mayaコマンドへ渡す対象名。

        Raises:
            RuntimeError: 各型の文字列変換が無効な参照を拒否する場合。
        """
        ...
    @staticmethod
    def _resolve_input(value: str | Object | om2.MObject | om2.MDagPath | om2.MPlug | tuple) -> Object:
        """単一対象をNode・Plug・Componentへ解決する。

        Args:
            value (str | Object | om2.MObject | om2.MDagPath | om2.MPlug | tuple):
                名前・既存ラッパー・API参照。APIコンポーネントは ``(MDagPath, MObject)`` の組。

        Returns:
            Object: 既存ラッパーなら無効でも同じインスタンス。それ以外は種類に応じた新しい参照。

        Raises:
            TypeError: 入力型・MObjectの種類・APIコンポーネントの組や種類が未対応の場合。
            ValueError: 空文字列・空MPlug、またはコンポーネントが単一要素でない場合。
            IndexError: APIコンポーネントの番号がシェイプの範囲外の場合。
            RuntimeError: 名前が存在しない・一意でない、またはAPI参照が無効の場合。
        """
        ...
    @staticmethod
    def _classes() -> tuple[type, type, type, type]:
        """循環 import を避けるため、判定に使う mlib クラスを呼び出し時に取得する。

        Returns:
            tuple[type, type, type, type]: Node、Plug、Component、Components。
        """
        ...
    @staticmethod
    def _unsupported(value: object) -> TypeError:
        """対応しない入力型の TypeError を作る。

        Args:
            value (object): 入力値。

        Returns:
            TypeError: 送出する例外。
        """
        ...
    @staticmethod
    def _name(value: object, node_class: type, plug_class: type, component_class: type) -> str:
        """単一の対象を名前へ変換する(Object._input_name の本体)。

        Args:
            value (object): 変換対象。
            node_class (type): Node クラス。
            plug_class (type): Plug クラス。
            component_class (type): Component クラス。

        Returns:
            str: maya.cmds へ渡せる名前。

        Raises:
            TypeError: 対応しない型の場合。
            ValueError: 空文字列、または無効な対象の場合。
        """
        ...
    @staticmethod
    def _input_name(value: str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug) -> str:
        """単一の対象を maya.cmds へ渡せる一意な名前へ変換する。

        文字列は解決せず(Maya へ問い合わせず)そのまま返す。解決済みの Node が
        必要な場合は Node._resolve_input を使う。変換規則はモジュールの説明を参照。

        Args:
            value (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                変換対象。

        Returns:
            str: maya.cmds で解決できる名前。

        Raises:
            TypeError: 対応しない型、依存ノード以外を指す MObject、または
                Components などの複数の対象を渡した場合(Object._input_names を使う)。
            ValueError: 空文字列、または無効な(削除済み・範囲外の)対象の場合。
        """
        ...
    @staticmethod
    def _flatten_inputs(values: object) -> list:
        """対象列を一度だけ展開する。型別の混在規則は呼出し側が検証する。

        Args:
            values (object): 単数参照または入れ子の反復可能な対象列。

        Returns:
            list: 順序を保持した対象。Componentsは範囲圧縮のため展開しない。

        Raises:
            TypeError: 未対応型の場合。
        """
        ...
    @staticmethod
    def _input_names(values: object, allow_plugs: bool = ...) -> list[str]:
        """単一の対象・コレクション・反復可能オブジェクトを名前のリストへ正規化する。

        単一の対象(Object._input_name が受け付ける型)は1要素のリストになる。``Components``・
        ``Selection``・``Joints`` などのコレクションと、list/tuple/set/ジェネレーター
        などの反復可能オブジェクトは、入れ子も含めて保持順に展開する。
        ``MultiPlug`` は要素へ展開せず、マルチアトリビュートそのものの名前として扱う。
        ``Components`` は全番号をまとめて1回だけ検証し、保持順で連続する番号を
        ``|cube|cubeShape.vtx[0:9]`` のような範囲指定の名前にまとめる(要素数が多くても
        maya.cmds へ渡す名前が増えない)。

        Args:
            values (object): 変換対象。単一の対象、または対象を要素に持つ反復可能オブジェクト。
            allow_plugs (bool): False の場合、Plug(``MultiPlug`` を含む)と ``om2.MPlug`` を
                TypeError にする(アトリビュートを渡しても maya.cmds が何もしないコマンド用。文字列は
                解決しないため対象外)。

        Returns:
            list[str]: 正規化した名前のリスト。空の反復可能オブジェクトは空リスト。

        Raises:
            TypeError: いずれかの要素が対応しない型の場合。allow_plugs が False で、
                Plug・MPlug が含まれる場合。同じ対象列に文字列とNodeが混在する場合。
            ValueError: いずれかの要素が空文字列、または無効な対象の場合。
        """
        ...
    def __getattr__(self, name: str) -> Any: ...
