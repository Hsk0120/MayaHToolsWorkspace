# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""om2.MQuaternion を継承したクォータニオンと、回転の補間・分解。"""

import math
import maya.api.OpenMaya as om2
from ..util import _angle_unit, _checked_index, _copy_state, _foreign_comparison, _rethrow_init_error, _to_radians
from .vector import Vector, _reduce_value, _resolve_mvector, _zero
from typing import Any, Iterable, Iterator
from mlib.maths.eulerRotate import EulerRotate
from mlib.maths.matrix import Matrix
from typing_extensions import Self
import types

_MQuaternion: Any
_MVector: Any
_NEW: Any
_INIT: Any
_GET: Any
_SET: Any
_NUMBER: tuple

def _quaternion_keywords(x: float = ..., y: float = ..., z: float = ..., w: float = ...) -> tuple:
    """キーワード引数付きの Quaternion の生成引数を (x, y, z, w) へまとめる。

    Args:
        x (float): X 成分。
        y (float): Y 成分。
        z (float): Z 成分。
        w (float): W 成分。

    Returns:
        tuple: (x, y, z, w)。
    """
    ...

def _unit_copy(value: om2.MQuaternion) -> Quaternion:
    """MQuaternion 系を正規化した新しい Quaternion を返す。

    Args:
        value (om2.MQuaternion): 正規化元。mlib の Quaternion 以外の MQuaternion も受け付ける。

    Returns:
        Quaternion: 長さ 1 の新しいクォータニオン。

    Raises:
        ValueError: ゼロクォータニオンの場合。
    """
    ...


class Quaternion(om2.MQuaternion):
    """om2.MQuaternionを継承した、可変・ハッシュ不可のXYZWクォータニオン。

    OpenMaya APIへそのまま渡せる。生成形式は :meth:`__init__` に従い、入力から独立した値を作る。
    軸角の角度はrad。生成時と積の計算時に正規化しない。

    ``q1 * q2`` はq1、q2の順に適用する回転で、マトリクスの積の順序と同じ(Hamilton積の ``q2 ⊗ q1``)。
    加減算・単項の ``-`` は成分ごとの演算。``数値 * q`` は4成分のスカラー倍で、
    ``q * 数値`` と除算は未対応。演算結果はQuaternionで、左辺が ``om2.MQuaternion`` でも同じ。
    ただし ``om2.MEulerRotation * q`` はOM2型を返し、``EulerRotate * q`` はEulerRotateを返す。
    ``*=`` / ``+=`` / ``-=`` は自身更新で、OM2にない ``+=`` / ``-=`` も同じオブジェクトを更新する。
    数学値を返す継承メソッドも対応するmlib型を返し、コピー操作とIt付きの自身更新を区別する。

    成分へ代入できる。lenは4、番号は-4〜3、範囲外はIndexError。スライスは成分tuple、反復はXYZW順。
    ``==`` は成分の完全一致で、同じ回転でもqと-qは等しくない。
    異種型との比較は :class:`~mlib.maths.vector.Vector` と同じ扱い。
    """
    __slots__: tuple
    __hash__: None
    def __new__(cls, *args, **kwargs) -> Self:
        """基底初期化でC++実体を確保し、clsの単位クォータニオンを作る。

        ``__init__`` を省略しても実体へアクセスできるよう、先に確保する。
        詳細は :meth:`mlib.maths.vector.Vector.__new__` を参照。

        Args:
            *args: ここでは使わない生成引数。
            **kwargs: ここでは使わないキーワード引数。

        Returns:
            Quaternion: clsの単位クォータニオン。
        """
        ...
    def __init__(self, *args, **kwargs) -> None:
        """成分を設定する。

        Args:
            *args: ``()``、``(x, y, z, w)``、``(values)``、``(MQuaternion)``、
                ``(angle, axis)``、``(a, b[, factor])`` など om2 の MQuaternion の
                コンストラクタが受け付ける引数。加えて ``(EulerRotate | om2.MEulerRotation)`` は
                ``asQuaternion()`` と同じ回転、``(Matrix | om2.MMatrix)`` は
                ``om2.MTransformationMatrix`` で分解した回転成分(スケール・シアー・平行移動を除く)。
            **kwargs: ``x``、``y``、``z``、``w``。位置引数と合わせて使える。
                省略した成分は (0, 0, 0, 1) の値。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 未知のキーワード引数、または同じ成分を二重に指定した場合。
            ValueError: om2 のコンストラクタが受け付けない引数の場合。
        """
        ...
    def __getitem__(self, index: int | slice) -> float | tuple[float, ...]:
        """成分を取得する。

        Args:
            index (int | slice): -4〜3 の番号(X、Y、Z、W の順)、またはスライス。

        Returns:
            float | tuple[float, ...]: 指定成分。スライスでは成分の tuple。

        Raises:
            TypeError: 番号が整数・スライス以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        ...
    def __setitem__(self, index: int, value: float) -> None:
        """成分を設定する。

        Args:
            index (int): -4〜3 の番号。
            value (float): 設定する値。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 番号が整数以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        ...
    def __iter__(self) -> Iterator[float]:
        """X、Y、Z、W の順に成分を反復する。

        Returns:
            Iterator[float]: 4成分のイテレータ。
        """
        ...
    def __reduce__(self) -> tuple:
        """copy / pickle 用に、コンストラクタを通さずに再構築する情報を返す。

        Returns:
            tuple: ``(_rebuild, (type(self), (x, y, z, w))[, state])``。
            利用者の派生クラスの ``__init__`` は呼ばず、``__dict__`` と ``__slots__`` の
            アトリビュートは再構築時に復元する。
        """
        ...
    def __reduce_ex__(self, protocol: int) -> tuple:
        """pickle のプロトコルにかかわらず __reduce__ と同じ情報を返す。

        Args:
            protocol (int): pickle のプロトコル番号。使用しない。

        Returns:
            tuple: ``__reduce__()`` の結果。
        """
        ...
    def __copy__(self) -> Quaternion:
        """同じ型・同じ成分の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートも浅く写す。

        Returns:
            Quaternion: 自身と同じクラスの新しいインスタンス。
        """
        ...
    def __deepcopy__(self, memo: dict) -> Quaternion:
        """同じ型・同じ成分の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートは深く複製する。

        Args:
            memo (dict): copy.deepcopy の memo。

        Returns:
            Quaternion: 自身と同じクラスの新しいインスタンス。
        """
        ...
    def __repr__(self) -> str:
        """クラス名と4成分を含むデバッグ表現を返す。

        Returns:
            str: ``Quaternion(x, y, z, w)`` の形式の文字列。
        """
        ...
    __str__: Any
    def __eq__(self, other: object) -> bool | types.NotImplementedType:
        """MQuaternion 系との成分の完全一致を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MQuaternion 系なら om2 と同じ比較の結果。
            その他の om2 の型は False。それ以外の型は NotImplemented(相手の比較に委ね、
            どちらも判断しなければ False になる)。
        """
        ...
    def __ne__(self, other: object) -> bool | types.NotImplementedType:
        """``__eq__`` の否定を返す。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MQuaternion 系なら om2 と同じ比較の結果。
            その他の om2 の型は True。それ以外の型は NotImplemented。
        """
        ...
    def __mul__(self, other: object) -> Quaternion | types.NotImplementedType:
        """om2 の順序でクォータニオンの積を返す(自身を先に適用する回転)。

        Args:
            other (object): 右側の MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 積。正規化しない。対応しない型は NotImplemented。
        """
        ...
    def __rmul__(self, other: object) -> Quaternion | types.NotImplementedType:
        """左辺の MQuaternion 系との積を om2 の順序で返す。数値なら成分をスケールする。

        ``数値 * q`` は om2 と同じく4成分それぞれのスカラー倍(正規化しない)。
        ``q * 数値`` は om2 と同じく対応しない。

        Args:
            other (object): 左側の MQuaternion 系、または int / float。

        Returns:
            Quaternion | types.NotImplementedType: 積。対応しない型は NotImplemented。
        """
        ...
    def __imul__(self, other: object) -> Quaternion | types.NotImplementedType:
        """自身へ右から MQuaternion 系を掛ける(``self = self * other``)。

        Args:
            other (object): 右側の MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        ...
    def __add__(self, other: object) -> Quaternion | types.NotImplementedType:
        """成分ごとの和を返す(om2 の ``+``)。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        ...
    def __radd__(self, other: object) -> Quaternion | types.NotImplementedType:
        """左辺の MQuaternion 系との成分ごとの和を返す。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        ...
    def __iadd__(self, other: object) -> Quaternion | types.NotImplementedType:
        """MQuaternion 系を成分ごとに自身へ加算する(om2 の MQuaternion には無い in-place 版)。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        ...
    def __sub__(self, other: object) -> Quaternion | types.NotImplementedType:
        """成分ごとの差を返す(om2 の ``-``)。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        ...
    def __rsub__(self, other: object) -> Quaternion | types.NotImplementedType:
        """左辺の MQuaternion 系から自身を引いた成分ごとの差を返す。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        ...
    def __isub__(self, other: object) -> Quaternion | types.NotImplementedType:
        """MQuaternion 系を成分ごとに自身から減算する(om2 の MQuaternion には無い in-place 版)。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        ...
    def __neg__(self) -> Quaternion:
        """全成分の符号を反転したクォータニオンを返す(同じ回転を表す)。

        Returns:
            Quaternion: 新しいクォータニオン。
        """
        ...
    @classmethod
    def fromAxisAngle(cls, axis: om2.MVector | Iterable[float], angle: float, *, unit: str = ...) -> Quaternion:
        """軸と角度から回転クォータニオンを生成する。

        Args:
            axis (om2.MVector | Iterable[float]): 回転軸。内部で正規化する。
            angle (float): 回転角度。単位はunitに従う。
            unit (str): angleの単位。既定 ``"rad"`` はラジアン(om2と同じ)、``"deg"`` は度
                (``"degree"`` / ``"radians"`` 等の別名も可)。

        Returns:
            Quaternion: axis を中心に angle だけ回転する単位クォータニオン。

        Raises:
            TypeError: unitが文字列以外の場合。
            ValueError: axis がゼロベクトルの場合(om2 は単位クォータニオンを返す)、またはunitが未対応の場合。
        """
        ...
    @staticmethod
    def squad(*args) -> Quaternion:
        """クォータニオン空間の三次曲線上で補間したQuaternionを返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 両端p/q、中間制御点a/b、補間値tをp, a, b, q, tの順で指定する。
                任意のspinは一周する回数。

        Returns:
            Quaternion: 演算結果を保持する新しいmlib値。
        """
        ...
    @staticmethod
    def squadPt(*args) -> Quaternion:
        """squadで滑らかにつながる曲線の中間制御回転を計算する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 隣接する3個のクォータニオンq0, q1, q2を指定する。

        Returns:
            Quaternion: 演算結果を保持する新しいmlib値。
        """
        ...
    def dot(self, other: om2.MQuaternion) -> float:
        """4成分の内積を返す。

        Args:
            other (om2.MQuaternion): 内積の相手。x、y、z、w を持つ値。

        Returns:
            float: 内積。
        """
        ...
    def length(self) -> float:
        """クォータニオンの長さ(ノルム)を返す。

        Returns:
            float: 長さ。
        """
        ...
    def unitIt(self) -> Quaternion:
        """ゼロ値を拒否して自身を正規化する。

        Returns:
            Quaternion: 更新した自身。

        Raises:
            ValueError: ゼロ値の場合。自身は変更しない。
        """
        ...
    def unit(self) -> Quaternion:
        """正規化した新しいクォータニオンを返す。

        om2 の ``normal()`` はゼロクォータニオンに単位クォータニオンを返すが、このメソッドは拒否する。

        Returns:
            Quaternion: 長さ 1 のクォータニオン。

        Raises:
            ValueError: ゼロクォータニオンの場合。
        """
        ...
    def conjugate(self) -> Quaternion:
        """共役クォータニオンを返す(om2 の同名メソッドを mlib の型で返すよう上書き)。

        Returns:
            Quaternion: XYZ 成分の符号を反転した新しいクォータニオン。
        """
        ...
    def inverse(self) -> Quaternion:
        """逆クォータニオン(共役を長さの2乗で割った値)を返す。

        om2 の同名メソッドを上書きし、mlib の型で返す。om2 はゼロクォータニオンに NaN を
        返すが、このメソッドは拒否する。単位クォータニオンなら conjugate() と同じ。

        Returns:
            Quaternion: 逆クォータニオン。

        Raises:
            ValueError: ゼロクォータニオンの場合。
        """
        ...
    def rotateVector(self, vector: om2.MVector | Iterable[float]) -> Vector:
        """Quaternionの正規化したコピーで、XYZベクトルを回転する。

        正規化は独立したコピー上で行い、自身と入力ベクトルは変更しない。
        非単位QuaternionをMVector.rotateBy()へ直接渡す場合と異なり、
        Quaternionの長さを使ってベクトルを拡縮するものではない。位置の平行移動は含まない。

        Args:
            vector (om2.MVector | Iterable[float]): 回転するXYZ。MPoint入力ではwを無視する。

        Returns:
            Vector: 新しい回転結果。入力の派生型や追加Python状態は引き継がない。

        Raises:
            ValueError: 自身がゼロQuaternionの場合。
        """
        ...
    def angleTo(self, other: om2.MQuaternion) -> float:
        """別のクォータニオンが表す回転との角度差をラジアンで返す。

        両方を正規化し、二重被覆(q と -q が同じ回転)を考慮する。acos を使わず
        ``4 * atan2(|p - q|, |p + q|)`` で計算するため、角度差が 0 や pi に近くても
        精度を保つ。

        Args:
            other (om2.MQuaternion): 角度差を測る相手の回転。

        Returns:
            float: 0 から pi の範囲のラジアン角度。

        Raises:
            ValueError: 自身または other がゼロクォータニオンの場合。
        """
        ...
    def slerp(self, other: om2.MQuaternion, t: float, spin: int = ...) -> Quaternion:
        """別のクォータニオンとの球面線形補間を返す。

        om2 の静的メソッド ``MQuaternion.slerp(p, q, t, spin=0)`` を上書きする。
        インスタンスメソッドとして ``p.slerp(q, t)`` と呼べるほか、
        ``Quaternion.slerp(p, q, t)`` の静的呼び出しの形でも使える。入力を正規化
        してからom2のslerpへ渡す。spin=0では最短経路を補間する。

        Args:
            other (om2.MQuaternion): 補間先の回転。
            t (float): 補間係数。0 で自身、1 で other。
            spin (int): om2 の slerp に渡す追加回転数。既定は 0。

        Returns:
            Quaternion: 補間結果。

        Raises:
            ValueError: 自身または other がゼロクォータニオンの場合。
        """
        ...
    def asCanonicalAxisAngle(self) -> tuple[Vector, float]:
        """軸と角度の組へ分解する。

        om2 の ``asAxisAngle`` と異なり、w が負なら符号を反転して角度を 0 から pi の
        範囲に収め、回転が無い場合の軸は (1, 0, 0) とする。角度は
        ``2 * atan2(|xyz|, w)`` で求めるため、微小な回転でも精度を保つ。

        Returns:
            tuple[Vector, float]: 正規化した回転軸と、ラジアンの回転角度(0 から pi)。

        Raises:
            ValueError: 自身がゼロクォータニオンの場合。
        """
        ...
    def asSwingTwist(self, axis: om2.MVector | Iterable[float] = ...) -> tuple[Quaternion, Quaternion]:
        """指定軸まわりの捻り(twist)と、それ以外の曲げ(swing)へ分解する。

        ``twist`` は axis 周りだけの回転、``swing`` は axis の向きを変える残りの
        回転。om2 の積の順序で ``twist * swing`` が自身と同じ回転になる
        (twist を先に適用し、続けて swing を適用する)。

        Args:
            axis (om2.MVector | Iterable[float]): 捻り軸。内部で正規化する。

        Returns:
            tuple[Quaternion, Quaternion]: (swing, twist)。どちらも正規化済み。

        Raises:
            ValueError: axis がゼロベクトルの場合、または自身がゼロクォータニオンの場合。
        """
        ...
    def asDecomposedEulerRotate(self, order: str | int = ...) -> EulerRotate:
        """EulerRotate へ変換する。

        正規化した回転マトリクスを ``om2.MEulerRotation.decompose`` で分解するため、
        ``Matrix.euler`` と同じ規約の角度になる。中間軸が 90 度を超える等価な角度を
        返すことがある。

        Args:
            order (str | int): 回転順序。``"xyz"``/``"yzx"``/``"zxy"``/``"xzy"``/
                ``"yxz"``/``"zyx"``、または om2 の番号 0〜5。

        Returns:
            EulerRotate: ラジアンの Euler 回転値。

        Raises:
            ValueError: order が未対応の場合、またはゼロクォータニオンの場合。
        """
        ...
    def mirror(self, axis: str | int = ...) -> Quaternion:
        """Matrixと同じ規約で向きをビヘイビアミラーした複製を返す。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または0/1/2。

        Returns:
            Quaternion: 同型の新しい回転。
        """
        ...
    def mirrorIt(self, axis: str | int = ...) -> Quaternion:
        """自身の向きをビヘイビアミラーする。

        Args:
            axis (str | int): mirrorと同じ反転軸。

        Returns:
            Quaternion: 更新した自身。
        """
        ...
    def asUnitMatrix(self) -> Matrix:
        """Quaternionの正規化したコピーから、独立した回転Matrixを作る。

        自身を正規化する操作ではない。元のQuaternionやその成分参照は変更しない。
        OpenMayaへそのまま委譲するasMatrix()とは別に、コピーの正規化とゼロ拒否を行う。

        Returns:
            Matrix: 回転だけを持つ新しい4行4列のマトリクス。追加Python状態は引き継がない。

        Raises:
            ValueError: 自身がゼロQuaternionの場合。
        """
        ...
    def normal(self, *args) -> Quaternion:
        """OpenMayaの規則で正規化したQuaternionの複製を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Quaternion: 演算結果を保持する新しいmlib値。
        """
        ...
    def exp(self, *args) -> Quaternion:
        """クォータニオンの指数を、新しいQuaternionとして返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Quaternion: 演算結果を保持する新しいmlib値。
        """
        ...
    def log(self, *args) -> Quaternion:
        """クォータニオンの自然対数を、新しいQuaternionとして返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Quaternion: 演算結果を保持する新しいmlib値。
        """
        ...
    def asMatrix(self, *args) -> Matrix:
        """保持する回転を、等価な回転マトリクスへ変換する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Matrix: 演算結果を保持する新しいmlib値。
        """
        ...
    def asEulerRotation(self, *args) -> EulerRotate:
        """保持する回転を、等価なEulerRotateへ変換する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    def asEulerRotate(self, *args) -> EulerRotate:
        """標準のasEulerRotationへ委譲し、EulerRotateの新しい値を返す。

        Args:
            *args: OpenMayaの標準メソッドへ渡す位置引数。

        Returns:
            EulerRotate: ラジアンのEuler回転値。元の標準メソッドと同じ演算結果。

        Note:
            OpenMaya標準のasEulerRotationも引き続き使用できる。
            引数・例外・自身を変更しない動作は標準メソッドと同じ。
        """
        ...
    def asAxisAngle(self) -> tuple[Vector, float]:
        """OpenMayaの軸角表現をmlibの軸ベクトルで返す。

        Returns:
            tuple[Vector, float]: 軸とラジアン角度。角度範囲はOpenMayaに従う。
        """
        ...
    @classmethod
    def _wrap(cls, value: om2.MQuaternion | om2.MEulerRotation | om2.MMatrix) -> Quaternion:
        """om2 の値を複製した cls のインスタンスを返す。

        Python の ``__new__`` / ``__init__`` を通さない(利用者の派生クラスの
        ``__init__`` も呼ばない)。

        Args:
            value (om2.MQuaternion | om2.MEulerRotation | om2.MMatrix): 複製元。
                ``setValue`` が受け付ける値。

        Returns:
            Quaternion: cls の新しいインスタンス。
        """
        ...
    x: Any
    y: Any
    z: Any
    w: Any
