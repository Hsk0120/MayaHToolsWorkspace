# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""サーフェス上の点の位置・法線・接線を取得する。"""

from . import _calculation
from .node import Node
from mlib.maths.vector import Vector
from mlib.nodes.nurbsSurface import NurbsSurface
from mlib.nodes.transform import Transform
from mlib.plugs.plug import Plug

_OUTPUTS: dict
_GEOMETRY: dict


class PointOnSurfaceInfo(Node):
    """サーフェス上のUVパラメーターの点の位置・法線・接線を出力する。"""
    def setInput(self, inputSurface: NurbsSurface | Transform | Plug | str | None = ..., parameterU: float | Plug | str | None = ..., parameterV: float | Plug | str | None = ..., turnOnPercentage: bool | Plug | str | None = ...) -> PointOnSurfaceInfo:
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            inputSurface (NurbsSurface | Transform | Plug | str | None): 対象のサーフェス。シェイプ(またはそれを1つだけ持つTransform)はworldSpaceを接続する。
            parameterU (float | Plug | str | None): Uパラメーター。
            parameterV (float | Plug | str | None): Vパラメーター。
            turnOnPercentage (bool | Plug | str | None): Trueはパラメーターを割合(0〜1)として扱う。

        Returns:
            PointOnSurfaceInfo: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            ValueError: ジオメトリの入力のTransformに、対応するシェイプが1つだけでない場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        ...
    def getResult(self, kind: str = ...) -> Vector:
        """出力の現在の値を取得する。

        Args:
            kind (str): 出力の種類。``"position"`` は ``position``、``"normal"`` は ``normal``、
                ``"normalizedNormal"`` は ``normalizedNormal``、``"tangentU"`` は ``tangentU``、
                ``"normalizedTangentU"`` は ``normalizedTangentU``、``"tangentV"`` は ``tangentV``、
                ``"normalizedTangentV"`` は ``normalizedTangentV``。

        Returns:
            Vector: 計算した値。

        Raises:
            ValueError: kindが未対応の名前の場合。
        """
        ...
    def getOutputPlug(self, kind: str = ...) -> Plug:
        """出力のアトリビュートを取得する(接続元に使う)。

        Args:
            kind (str): 出力の種類。:meth:`getResult` と同じ。

        Returns:
            Plug: 出力のアトリビュート。

        Raises:
            ValueError: kindが未対応の名前の場合。
        """
        ...
