"""計算ノードの入力検証と参照解決をまとめる。"""
import math
from .._core.coerce import to_node


class _Calculation:
    """Mayaノード継承を変更せず共有する内部操作。"""

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
        if type(value) is not int or not 0 <= value <= 2147483647:
            raise ValueError("Expected an integer index in 0..2147483647")
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
    def enum_value(value, names):
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
    def enum_name(plug, names):
        """Mayaの列挙値を公開名へ変換する。

        Args:
            plug (Plug): enum参照。
            names (tuple[str]): 番号順の名前。
        Returns:
            str: 現在のモード。
        """
        return names[_Calculation.index(plug.get(), range(len(names)))]

    @staticmethod
    def geometry_output(value, node_type, world_space):
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
        from .transform import Transform
        _Calculation.boolean(world_space)
        node = to_node(value)
        if isinstance(node, Transform):
            shapes = [s for s in node.shapes() if s.is_type(node_type)]
            if len(shapes) != 1:
                raise ValueError("Expected exactly one matching shape")
            node = shapes[0]
        if not node.is_type(node_type):
            raise TypeError("Expected a " + node_type)
        if world_space:
            # 接続作成操作の内部だけで呼ぶ。未評価worldSpace要素の作成を明示する。
            return node.plug("worldSpace").element(node.dag_path().instanceNumber(), create=True)
        return node.plug("local")
