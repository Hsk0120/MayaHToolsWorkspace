"""指定した軸をターゲットへ向けるマトリクスを作る。"""

from . import _calculation
from .node import Node

#: 主軸の向け方の名前(Mayaの ``primaryMode`` の番号順)。
_PRIMARY_MODES = ("lockAxis", "aim", "align")
#: 副軸の向け方の名前(Mayaの ``secondaryMode`` の番号順)。
_SECONDARY_MODES = ("none", "aim", "align")


class AimMatrix(Node):
    """入力マトリクスの主軸・副軸を、ターゲットのマトリクスまたはベクトルへ向けたマトリクスを出力する。"""

    def setInput(self, inputMatrix=None, primaryInputAxis=None, primaryTargetMatrix=None,
        primaryTargetVector=None, secondaryInputAxis=None, secondaryTargetMatrix=None,
        secondaryTargetVector=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            inputMatrix (Matrix | Iterable[float] | Plug | str | None): 向きを変える元のマトリクス。
            primaryInputAxis (Iterable[float] | Plug | str | None): 主軸(入力マトリクスの空間)。
            primaryTargetMatrix (Matrix | Iterable[float] | Plug | str | None): 主軸のターゲットのマトリクス。
            primaryTargetVector (Iterable[float] | Plug | str | None): 主軸のターゲットのベクトル。
            secondaryInputAxis (Iterable[float] | Plug | str | None): 副軸(入力マトリクスの空間)。
            secondaryTargetMatrix (Matrix | Iterable[float] | Plug | str | None): 副軸のターゲットのマトリクス。
            secondaryTargetVector (Iterable[float] | Plug | str | None): 副軸のターゲットのベクトル。

        Returns:
            AimMatrix: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "inputMatrix": inputMatrix,
            "primaryInputAxis": primaryInputAxis,
            "primaryTargetMatrix": primaryTargetMatrix,
            "primaryTargetVector": primaryTargetVector,
            "secondaryInputAxis": secondaryInputAxis,
            "secondaryTargetMatrix": secondaryTargetMatrix,
            "secondaryTargetVector": secondaryTargetVector,
        })

    def getPrimaryMode(self):
        """主軸の向け方を名前で取得する(``primaryMode``)。

        Returns:
            str: ``"lockAxis"``・``"aim"``・``"align"`` のいずれか。
        """
        return _calculation.get_enum(self, "primaryMode", _PRIMARY_MODES)

    def setPrimaryMode(self, mode):
        """主軸の向け方を名前または番号で設定する(``primaryMode``)。1回のUndoで戻せる。

        Args:
            mode (str | int): ``"lockAxis"``・``"aim"``・``"align"`` のいずれか、またはMayaの番号(0から)。

        Returns:
            AimMatrix: 自身。

        Raises:
            TypeError: modeが文字列・int以外の場合。
            ValueError: 未対応の名前・範囲外の番号の場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込みを拒否した場合。
        """
        return _calculation.set_enum(self, "setPrimaryMode", "primaryMode", mode, _PRIMARY_MODES, "mode")

    def getSecondaryMode(self):
        """副軸の向け方を名前で取得する(``secondaryMode``)。

        Returns:
            str: ``"none"``・``"aim"``・``"align"`` のいずれか。
        """
        return _calculation.get_enum(self, "secondaryMode", _SECONDARY_MODES)

    def setSecondaryMode(self, mode):
        """副軸の向け方を名前または番号で設定する(``secondaryMode``)。1回のUndoで戻せる。

        Args:
            mode (str | int): ``"none"``・``"aim"``・``"align"`` のいずれか、またはMayaの番号(0から)。

        Returns:
            AimMatrix: 自身。

        Raises:
            TypeError: modeが文字列・int以外の場合。
            ValueError: 未対応の名前・範囲外の番号の場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込みを拒否した場合。
        """
        return _calculation.set_enum(self, "setSecondaryMode", "secondaryMode", mode, _SECONDARY_MODES, "mode")

    def getResult(self):
        """出力 ``outputMatrix`` の現在の値を取得する。

        Returns:
            Matrix: 向きを変えたマトリクス。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``outputMatrix`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("outputMatrix")
