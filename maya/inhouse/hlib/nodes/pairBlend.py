"""移動・回転をブレンドする。Euler/Quaternion補間を選択できる。"""
from .._core.registry import node_wrapper
from .._core.coerce import to_plug
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ._calculation import _Calculation
from .node import Node


@node_wrapper("pairBlend")
class PairBlend(Node):
    """移動・回転をブレンドする。Euler/Quaternion補間を選択できる。"""

    def weight_plug(self):
        """ブレンドウェイトのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("weight")

    def get_weight(self):
        """ブレンドウェイトの評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.weight_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_weight(self, value, *, fast=False):
        """ブレンドウェイトへ定数値を設定する。

        Args:
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.scalar(value)
        self.weight_plug().set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_weight(self, source, force=False):
        """ブレンドウェイトへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        to_plug(source).connect(self.weight_plug(), force=force)
        return self

    def get_rotation_interpolation(self):
        """現在のモード名を取得する。
        Returns:
            str: euler, quaternion。
        """
        return _Calculation.enum_name(self.plug("rotInterpolation"), ('euler', 'quaternion'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_rotation_interpolation(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): euler, quaternion、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enum_value(mode, ('euler', 'quaternion'))
        self.plug("rotInterpolation").set(value)
        return self

    def get_rotate_order(self):
        """現在のモード名を取得する。
        Returns:
            str: xyz, yzx, zxy, xzy, yxz, zyx。
        """
        return _Calculation.enum_name(self.plug("rotateOrder"), ('xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_rotate_order(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): xyz, yzx, zxy, xzy, yxz, zyx、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enum_value(mode, ('xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx'))
        self.plug("rotateOrder").set(value)
        return self

    def translate_plug(self, index):
        """translate入力（移動はUI距離単位、回転は度）のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug(f"inTranslate{_Calculation.index(index, (1, 2))}")

    def get_translate(self, index):
        """translate入力（移動はUI距離単位、回転は度）の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.translate_plug(index).get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_translate(self, index, value, *, fast=False):
        """translate入力（移動はUI距離単位、回転は度）へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.vector(value)
        self.translate_plug(index).set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_translate(self, index, source, force=False):
        """translate入力（移動はUI距離単位、回転は度）へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        to_plug(source).connect(self.translate_plug(index), force=force)
        return self

    def rotate_plug(self, index):
        """rotate入力（移動はUI距離単位、回転は度）のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug(f"inRotate{_Calculation.index(index, (1, 2))}")

    def get_rotate(self, index):
        """rotate入力（移動はUI距離単位、回転は度）の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.rotate_plug(index).get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_rotate(self, index, value, *, fast=False):
        """rotate入力（移動はUI距離単位、回転は度）へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.vector(value)
        self.rotate_plug(index).set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_rotate(self, index, source, force=False):
        """rotate入力（移動はUI距離単位、回転は度）へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        to_plug(source).connect(self.rotate_plug(index), force=force)
        return self

    def output_plug(self, kind="translate"):
        """移動または回転の出力を取得する。

        Args:
            kind (str): translate/rotate。
        Returns:
            Plug: 出力参照。
        """
        if kind not in ("translate", "rotate"):
            raise ValueError("kind must be translate or rotate")
        return self.plug("out" + kind.title())

    def result(self, kind="translate"):
        """移動または回転の評価値を取得する。

        Args:
            kind (str): translate/rotate。
        Returns:
            tuple[float, float, float]: 移動はUI距離単位、回転は度。
        """
        return tuple(self.output_plug(kind).get())
