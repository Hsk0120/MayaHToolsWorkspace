"""Mayaシーン内の単一対象を表す共通基底と取得入口。"""

import maya.api.OpenMaya as om2


class _ObjectType(type):
    """Objectへの入力だけを振り分け、派生クラスの構築は通常通り行う。"""

    def __call__(cls, *args, **kwargs):
        """解決済み参照への二重初期化を避けて適切な型を返す。

        Args:
            *args: 呼出し先またはUIシグナルから渡される位置引数。
            **kwargs: 呼出し先へ渡すキーワード引数。
        """
        if cls is Object:
            return cls._resolve_input(*args, **kwargs)
        return super().__call__(*args, **kwargs)


class Object(metaclass=_ObjectType):
    """Node・Plug・単数Componentの共通基底。既存対象を参照し、新規作成しない。

    Object(value)は対象に対応した具象ラッパーを返す。
    等価比較・ハッシュ・寿命の判定は各参照型が担当する。
    コレクション・数学値・保存データ・UI参照はこの基底に含めない。
    """

    @staticmethod
    def _resolve_input(value):
        """入力を一意なNode・Plug・Componentへ解決する。

        Args:
            value (str | Object | MObject | MDagPath | MPlug | tuple):
                単一対象。コンポーネントのAPI入力は(MDagPath, MObject)。
        Returns:
            Object: 既存ラッパーはそのまま、その他は対応する具体型。
        Raises:
            TypeError: 未対応の型・コンポーネント種類の場合。
            ValueError: 空入力または複数要素を指定した場合。
            RuntimeError: 名前が存在しない、または一意に解決できない場合。
        """
        from .nodes.node import Node
        from .plugs.plug import Plug
        from .components.component import Component
        if isinstance(value, Object):
            return value
        if isinstance(value, om2.MPlug):
            return Plug._resolve_input(value)
        if isinstance(value, (om2.MObject, om2.MDagPath)):
            return Node._resolve_input(value)
        if isinstance(value, tuple):
            return Component._resolve_input(value)
        if not isinstance(value, str):
            raise TypeError("Expected a scene object reference or name")
        if not value:
            raise ValueError("Expected a non-empty object name")
        selection = om2.MSelectionList()
        selection.add(value)
        if selection.length() != 1:
            raise RuntimeError("Object requires one unambiguous target")
        try:
            selection.getPlug(0)
        except (RuntimeError, TypeError):
            pass
        else:
            return Plug._resolve_input(value)
        try:
            path, component = selection.getComponent(0)
        except (RuntimeError, TypeError):
            return Node._resolve_input(value)
        if not component.isNull():
            return Component._resolve_input((path, component))
        return Node._resolve_input(value)

    @staticmethod
    def _classes():
        """循環 import を避けるため、判定に使う hlib クラスを呼び出し時に取得する。

        Returns:
            tuple[type, type, type, type]: Node、Plug、Component、Components。
        """
        from .components.component import Component, Components
        from .nodes.node import Node
        from .plugs.plug import Plug

        return Node, Plug, Component, Components

    @staticmethod
    def _unsupported(value):
        """対応しない入力型の TypeError を作る。

        Args:
            value (object): 入力値。

        Returns:
            TypeError: 送出する例外。
        """
        return TypeError(
            f"対応していない型です: {type(value).__name__}"
            "(str / Node / Plug / Component / om2.MObject / om2.MDagPath / om2.MPlug を指定してください)"
        )

    @staticmethod
    def _name(value, node_class, plug_class, component_class):
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
        from .nodes.node import Node as _InputNode
        from .plugs.plug import Plug as _InputPlug
        if isinstance(value, str):
            name = value
        elif isinstance(value, node_class):
            name = value.fullName()
            if not name:
                raise ValueError("無効な(削除済みの)ノードは指定できません")
        elif isinstance(value, plug_class):
            name = value.fullName()
            if not name:
                raise ValueError("無効な(所有ノードまたはアトリビュートが削除済みの)Plug は指定できません")
        elif isinstance(value, component_class):
            try:
                name = value.fullName()
            except (RuntimeError, IndexError) as error:
                raise ValueError(f"無効なコンポーネントは指定できません: {error}") from error
        elif isinstance(value, om2.MPlug):
            name = _InputPlug._mplug_name(value)
        elif isinstance(value, om2.MDagPath):
            if not value.isValid() or not om2.MObjectHandle(value.node()).isValid():
                raise ValueError("無効な(削除済みの)MDagPath は指定できません")
            name = value.fullPathName()
        elif isinstance(value, om2.MObject):
            name = _InputNode._mobject_name(value)
        else:
            raise Object._unsupported(value)
        if not name:
            raise ValueError("空でない名前を指定してください")
        return name

    @staticmethod
    def _input_name(value):
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
        node_class, plug_class, component_class, _ = Object._classes()
        return Object._name(value, node_class, plug_class, component_class)

    @staticmethod
    def _flatten_inputs(values):
        """対象列を一度だけ展開する。型別の混在規則は呼出し側が検証する。

        Args:
            values (object): 単数参照または入れ子の反復可能な対象列。
        Returns:
            list: 順序を保持した対象。Componentsは範囲圧縮のため展開しない。
        Raises:
            TypeError: 未対応型の場合。
        """
        singles = (str,) + Object._classes() + (om2.MObject, om2.MDagPath, om2.MPlug)
        result = []

        def collect(value):
            """単数参照を保持し、容器だけを展開する。"""
            if isinstance(value, singles):
                result.append(value)
                return
            try:
                iterator = iter(value)
            except TypeError:
                raise Object._unsupported(value) from None
            for item in iterator:
                collect(item)

        collect(values)
        return result

    @staticmethod
    def _input_names(values, allow_plugs=True):
        """単一の対象・コレクション・反復可能オブジェクトを名前のリストへ正規化する。

        単一の対象(Object._input_name が受け付ける型)は1要素のリストになる。``Components``・
        ``Selection``・``Joints`` などのコレクションと、list/tuple/set/ジェネレーター
        などの反復可能オブジェクトは、入れ子も含めて保持順に展開する。
        ``ArrayPlug`` は要素へ展開せず、配列アトリビュートそのものの名前として扱う。
        ``Components`` は全番号をまとめて1回だけ検証し、保持順で連続する番号を
        ``|cube|cubeShape.vtx[0:9]`` のような範囲指定の名前にまとめる(要素数が多くても
        maya.cmds へ渡す名前が増えない)。

        Args:
            values (object): 変換対象。単一の対象、または対象を要素に持つ反復可能オブジェクト。
            allow_plugs (bool): False の場合、Plug(``ArrayPlug`` を含む)と ``om2.MPlug`` を
                TypeError にする(アトリビュートを渡しても maya.cmds が何もしないコマンド用。文字列は
                解決しないため対象外)。

        Returns:
            list[str]: 正規化した名前のリスト。空の反復可能オブジェクトは空リスト。

        Raises:
            TypeError: いずれかの要素が対応しない型の場合。allow_plugs が False で、
                Plug・MPlug が含まれる場合。同じ対象列に文字列とNodeが混在する場合。
            ValueError: いずれかの要素が空文字列、または無効な対象の場合。
        """
        from .nodes.node import Nodes as _InputNodes
        node_class, plug_class, component_class, components_class = Object._classes()
        singles = (str, node_class, plug_class, component_class, om2.MObject, om2.MDagPath, om2.MPlug)
        names = []

        def collect(value):
            if not allow_plugs and isinstance(value, (plug_class, om2.MPlug)):
                raise TypeError(
                    f"アトリビュート(Plug・MPlug)は指定できません: {type(value).__name__}"
                    "(所有ノードを対象にする場合は plug.node を指定してください)"
                )
            if isinstance(value, singles):
                names.append(Object._name(value, node_class, plug_class, component_class))
                return
            if isinstance(value, components_class):
                try:
                    # 全番号の検証はコレクションごとに1回だけ行い、連続する番号は範囲指定にまとめる。
                    names.extend(value.compactNames())
                except (RuntimeError, IndexError) as error:
                    raise ValueError(f"無効なコンポーネントは指定できません: {error}") from error
                return
            try:
                iterator = iter(value)
            except TypeError:
                raise Object._unsupported(value) from None
            for item in iterator:
                collect(item)

        items = Object._flatten_inputs(values)
        _InputNodes._validate_inputs(items)
        collect(items)
        return names
