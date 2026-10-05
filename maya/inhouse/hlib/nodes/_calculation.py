"""計算ノードの入力検証と参照解決をまとめる。"""

import math


class _Calculation:
    """Mayaノード継承を変更せず共有する内部操作。"""

    @staticmethod
    def set_value(value, validator, target, *indices):
        """値を検証してから対象Plugを解決し、設定する。

        Args:
            value (object): 入力値。
            validator (callable): 値の検証・型変換。例外はそのまま伝播する。
            target (callable): ノード固有のPlug取得メソッド。
            *indices: Plug取得に渡す番号。

        Note:
            値の検証を先に行い、不正値による対象解決を避ける。
            Undoとfastの範囲は呼出元の公開メソッドで管理する。
        """
        value = validator(value)
        target(*indices).set(value)

    @staticmethod
    def connect(source, target, *indices, force=False):
        """接続元を解決してから対象Plugを取得し、接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            target (callable): ノード固有のPlug取得メソッド。
            *indices: Plug取得に渡す番号。
            force (bool): 既存接続を置き換えるか。

        Note:
            接続方向とロック処理はPlug.connectへ集約する。
            接続元の解決失敗時には接続先を取得しない。
        """
        from ..plugs.plug import Plug as _InputPlug
        source = _InputPlug._resolve_input(source)
        source.connectTo(target(*indices), force=force)

    @staticmethod
    def index(value, allowed=None):
        """論理番号または列挙番号を検証する。

        Args:
            value (int): 検証する番号。
            allowed (Iterable[int] | None): 指定時は許可値に限定する。
        Returns:
            int: 有効な番号。
        Raises:
            ValueError: bool・範囲外・非整数の場合。
        """
        from ..plugs.arrayPlug import ArrayPlug
        try:
            ArrayPlug._validate_index(value)
        except (TypeError, IndexError):
            raise ValueError("Expected an integer index in 0..2147483647") from None
        if allowed is not None and value not in allowed:
            raise ValueError("Index is outside the allowed values")
        return value

    @staticmethod
    def scalar(value):
        """有限な数値を検証する。

        Args:
            value (float): 入力値。
        Returns:
            float: 有限値。
        Raises:
            ValueError: 非有限値の場合。
        """
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Expected a finite value")
        return value

    @staticmethod
    def vector(value, size=3):
        """固定長の有限値列を検証する。

        Args:
            value (Iterable[float]): 成分列。
            size (int): 必要な要素数。
        Returns:
            tuple[float]: 有限な成分列。
        Raises:
            ValueError: 長さまたは数値が不正な場合。
        """
        values = tuple(_Calculation.scalar(v) for v in value)
        if len(values) != size:
            raise ValueError("Expected %d components" % size)
        return values

    @staticmethod
    def boolean(value):
        """boolを検証する。

        Args:
            value (bool): 入力値。
        Returns:
            bool: 入力値。
        Raises:
            TypeError: bool以外の場合。
        """
        if type(value) is not bool:
            raise TypeError("Expected bool")
        return value

    @staticmethod
    def enumValue(value, names):
        """モード名または番号をMayaの番号へ変換する。

        Args:
            value (str | int): モード。
            names (tuple[str]): 番号順の名前。
        Returns:
            int: 列挙値。
        Raises:
            ValueError: 未対応のモードの場合。
        """
        if isinstance(value, str):
            return names.index(value.lower())
        return _Calculation.index(value, range(len(names)))

    @staticmethod
    def enumName(plug, names):
        """Mayaの列挙値を公開名へ変換する。

        Args:
            plug (Plug): enum参照。
            names (tuple[str]): 番号順の名前。
        Returns:
            str: 現在のモード。
        """
        return names[_Calculation.index(plug.get(), range(len(names)))]

    @staticmethod
    def geometryOutput(value, node_type, world_space):
        """カーブ/サーフェスの入力元Plugを解決する。

        Args:
            value (Node | str | MObject | MDagPath): シェイプまたは単一シェイプのTransform。
            node_type (str): 対応するMayaシェイプ型。
            world_space (bool): worldSpaceを使用するか。
        Returns:
            Plug: localまたはインスタンスに対応するworldSpace。
        Raises:
            TypeError: シェイプ型が異なる場合。
            ValueError: Transformの対象シェイプが一意でない場合。
        """
        from ..nodes.node import Node as _InputNode
        from .transform import Transform
        _Calculation.boolean(world_space)
        node = _InputNode._resolve_input(value)
        if isinstance(node, Transform):
            shapes = [s for s in node.shapes() if s.isType(node_type)]
            if len(shapes) != 1:
                raise ValueError("Expected exactly one matching shape")
            node = shapes[0]
        if not node.isType(node_type):
            raise TypeError("Expected a " + node_type)
        if world_space:
            # 接続時に実体化する。参照の取得では未評価worldSpace要素を作成しない。
            return node.plug("worldSpace")._element_reference(node.mpath().instanceNumber())
        return node.plug("local")
