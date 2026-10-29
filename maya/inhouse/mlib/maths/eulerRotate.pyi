# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""om2.MEulerRotation を継承した、回転順序を持つラジアンのオイラー回転値。"""

import math
import operator
import maya.api.OpenMaya as om2
from ..util import _checked_index, _copy_state, _foreign_comparison, _rethrow_init_error
from .quaternion import Quaternion
from .vector import _reduce_value
from typing import Any, Iterable, Iterator
from mlib.maths.matrix import Matrix
from mlib.maths.vector import Vector
from typing_extensions import Self
import types

_MEuler: Any
_MQuaternion: Any
_NEW: Any
_INIT: Any
_GET: Any
_SET: Any
_NUMBER: tuple
ORDER_NAMES: tuple
_ORDER_INDEX: dict

def orderIndex(order: str | int) -> int:
    """回転順序の名前または番号を om2 の番号(0〜5)へ変換する。

    Args:
        order (str | int): ``"xyz"`` などの名前(大文字小文字を問わない)、または
            om2 の ``MEulerRotation.kXYZ``〜``kZYX`` (Maya の rotateOrder と同じ番号)。

    Returns:
        int: om2 の回転順序の番号。

    Raises:
        ValueError: 未対応の名前・番号、または bool などの不正な型の場合。
    """
    ...

def _euler_keywords(x: float = ..., y: float = ..., z: float = ..., order: str | int | None = ...) -> tuple:
    """キーワード引数付きの EulerRotate の生成引数を (x, y, z, order) へまとめる。

    Args:
        x (float): X 回転(ラジアン)。
        y (float): Y 回転(ラジアン)。
        z (float): Z 回転(ラジアン)。
        order (str | int | None): 回転順序。None は xyz。

    Returns:
        tuple: (x, y, z, order)。
    """
    ...


class EulerRotate(om2.MEulerRotation):
    """om2.MEulerRotationを継承した、radのXYZ成分と回転順序を持つ可変値。

    Vectorの派生ではなく、OpenMaya APIへそのまま渡せる。
    生成形式は :meth:`__init__` に従い、MEulerRotation入力は順序を含めてコピーする。
    コンストラクタのorder指定は成分を並べ替えない。姿勢を保った順序変更には ``reorder()`` を使う。
    orderはMayaのrotateOrderと同じ0〜5。コンストラクタは順序名も受理し、
    :attr:`orderName` でも名前を取得・設定できる。

    演算はOM2に従い、結果はEulerRotateを返す。
    ``+`` / ``-`` は同順序なら成分ごと、異なる順序なら右辺を左辺の順序へ変換する。
    ``*`` は数値なら成分のスケール、EulerRotate/Quaternionなら回転合成。
    ``数値 * e`` と ``e / 数値`` はmlibの拡張。``+=`` / ``-=`` / ``*=`` / ``/=`` は自身更新。
    数学値を返す継承メソッドも対応するmlib型を返し、コピー操作とIt付きの自身更新を区別する。

    ハッシュ不可。番号は-3〜2、範囲外はIndexError。スライスは成分tuple、反復はXYZ順。
    ``==`` は順序を含む成分の完全一致。異種型との比較は :class:`~mlib.maths.vector.Vector` と同じ扱い。
    表示は度、内部値はrad。
    """
    __slots__: tuple
    __hash__: None
    def __new__(cls, *args, **kwargs) -> Self:
        """基底初期化でC++実体を確保し、clsの0回転(xyz順)を作る。

        ``__init__`` を省略・失敗しても実体へアクセスできるよう、先に確保する。
        詳細は :meth:`mlib.maths.vector.Vector.__new__` を参照。

        Args:
            *args: ここでは使わない生成引数。
            **kwargs: ここでは使わないキーワード引数。

        Returns:
            EulerRotate: clsの0回転。
        """
        ...
    def __init__(self, *args, **kwargs) -> None:
        """成分と回転順序を設定する。

        引数をすべて検証してから書き込むため、例外時に値は変わらない。

        Args:
            *args: ``()``、``(x, y, z)``、``(x, y, z, order)``、``(values)``、
                ``(values, order)``、または ``(MEulerRotation)``。角度はラジアン。
            **kwargs: ``order``、または ``x`` / ``y`` / ``z`` / ``order`` のキーワード引数。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 引数の数や型が不正な場合、または同じ引数を二重に指定した場合。
            ValueError: 未対応の回転順序、または成分が数値でない場合。
        """
        ...
    def __getitem__(self, index: int | slice) -> float | tuple[float, ...]:
        """回転成分を取得する。

        Args:
            index (int | slice): -3〜2 の番号(X、Y、Z の順)、またはスライス。

        Returns:
            float | tuple[float, ...]: 指定成分(ラジアン)。スライスでは成分の tuple。

        Raises:
            TypeError: 番号が整数・スライス以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        ...
    def __setitem__(self, index: int, value: float) -> None:
        """回転成分を設定する。

        Args:
            index (int): -3〜2 の番号。
            value (float): 設定する値(ラジアン)。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 番号が整数以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        ...
    def __iter__(self) -> Iterator[float]:
        """X、Y、Z の順に回転成分を反復する。

        Returns:
            Iterator[float]: 3成分(ラジアン)のイテレータ。
        """
        ...
    def __reduce__(self) -> tuple:
        """copy / pickle 用に、コンストラクタを通さずに再構築する情報を返す。

        Returns:
            tuple: ``(_rebuild, (type(self), (x, y, z, order))[, state])``。
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
    def __copy__(self) -> EulerRotate:
        """同じ型・同じ成分と順序の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートも浅く写す。

        Returns:
            EulerRotate: 自身と同じクラスの新しいインスタンス。
        """
        ...
    def __deepcopy__(self, memo: dict) -> EulerRotate:
        """同じ型・同じ成分と順序の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートは深く複製する。

        Args:
            memo (dict): copy.deepcopy の memo。

        Returns:
            EulerRotate: 自身と同じクラスの新しいインスタンス。
        """
        ...
    def __repr__(self) -> str:
        """度数法の回転成分と回転順序名を含むデバッグ表現を返す。

        Returns:
            str: ``EulerRotate(degrees=(90, 0, -45), order='xyz')`` の形式の文字列。
            内部値はラジアンのまま。
        """
        ...
    __str__: Any
    def __eq__(self, other: object) -> bool | types.NotImplementedType:
        """MEulerRotation 系との比較を om2 と同じ規則(順序を含む完全一致)で行う。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MEulerRotation 系なら om2 の比較結果。
            その他の om2 の型は False。それ以外の型は NotImplemented(相手の比較に委ね、
            どちらも判断しなければ False になる)。
        """
        ...
    def __ne__(self, other: object) -> bool | types.NotImplementedType:
        """``__eq__`` の否定を返す。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MEulerRotation 系なら om2 の比較結果。
            その他の om2 の型は True。それ以外の型は NotImplemented。
        """
        ...
    def __add__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """om2 の ``+`` の結果を EulerRotate で返す。

        Args:
            other (object): MEulerRotation 系。順序が違えば自身の順序へ変換して加算する。

        Returns:
            EulerRotate | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        ...
    def __radd__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """左辺の MEulerRotation 系との和を返す。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        ...
    def __iadd__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """MEulerRotation 系を自身へ加算する。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        ...
    def __sub__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """om2 の ``-`` の結果を EulerRotate で返す。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        ...
    def __rsub__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """左辺の MEulerRotation 系から自身を引いた値を返す。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        ...
    def __isub__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """MEulerRotation 系を自身から減算する。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        ...
    def __mul__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """om2 の ``*`` の結果を EulerRotate で返す。

        Args:
            other (object): 数値(成分のスケール)、または MEulerRotation 系 /
                MQuaternion 系(自身を先に適用する回転の合成)。

        Returns:
            EulerRotate | types.NotImplementedType: 結果。対応しない型は NotImplemented。
        """
        ...
    def __rmul__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """左辺からの乗算を om2 の意味論で行う。

        Args:
            other (object): 数値、または左辺の MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 結果。対応しない型は NotImplemented。
        """
        ...
    def __imul__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """数値倍、または回転の合成を自身へ適用する。

        Args:
            other (object): 数値、MEulerRotation 系、または MQuaternion 系。

        Returns:
            EulerRotate | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        ...
    def __truediv__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """数値による成分ごとの除算を返す(om2 には無い mlib の拡張)。

        順序は保持し、各成分を other で割る。

        Args:
            other (object): 除数の int または float。

        Returns:
            EulerRotate | types.NotImplementedType: 新しい回転値。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合。
        """
        ...
    def __itruediv__(self, other: object) -> EulerRotate | types.NotImplementedType:
        """数値で自身の各成分を除算する(mlib の拡張。順序は変えない)。

        Args:
            other (object): 除数の int または float。

        Returns:
            EulerRotate | types.NotImplementedType: 自身。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合。
        """
        ...
    def __neg__(self) -> EulerRotate:
        """om2 の単項 ``-`` (逆回転の成分)を EulerRotate で返す。

        Returns:
            EulerRotate: 新しい回転値。
        """
        ...
    @classmethod
    def fromIterable(cls, values: Iterable[float], order: str | int = ...) -> EulerRotate:
        """3要素の反復可能オブジェクトから生成する。

        Args:
            values (Iterable[float]): ラジアンの3成分。
            order (str | int): 回転順序。既定は ``"xyz"``。

        Returns:
            EulerRotate: 呼び出したクラスの新しいインスタンス。

        Raises:
            ValueError: 要素数が3でない場合、または未対応の回転順序の場合。
        """
        ...
    @classmethod
    def fromDegrees(cls, x: float, y: float, z: float, order: str | int = ...) -> EulerRotate:
        """度数法の3成分から生成する。

        Args:
            x (float): X 回転角度(度)。
            y (float): Y 回転角度(度)。
            z (float): Z 回転角度(度)。
            order (str | int): 回転順序。既定は ``"xyz"``。

        Returns:
            EulerRotate: ラジアンに変換した回転値。

        Raises:
            ValueError: 未対応の回転順序の場合。
        """
        ...
    @staticmethod
    def computeAlternateSolution(*args) -> EulerRotate:
        """同じ向きを表す、単純な一周加算とは異なるオイラー回転を計算する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 回転rotを1個指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    @staticmethod
    def computeBound(*args) -> EulerRotate:
        """各角度を±πの範囲へ収めた、等価なオイラー回転を計算する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 回転rotを1個指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    @staticmethod
    def computeClosestCut(*args) -> EulerRotate:
        """各軸へ一周の整数倍を加え、基準に近い等価な回転を計算する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 元の回転srcと基準targetを指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    @staticmethod
    def computeClosestSolution(*args) -> EulerRotate:
        """基準に最も近い、等価なオイラー回転を計算する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 元の回転srcと基準targetを指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    @staticmethod
    def decompose(*args) -> EulerRotate:
        """マトリクスと回転順序からオイラー回転を分解する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: MMatrix系のmatrixとOpenMayaの回転順序定数orderを指定する。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    @property
    def orderName(self) -> str:
        """回転順序の名前(``"xyz"`` など)を取得または設定する。

        設定時は名前(大文字小文字を問わない)と om2 の番号のどちらも受け付け、
        成分は並べ替えない。未対応の値は ValueError。

        Returns:
            str: 小文字の回転順序名。
        """
        ...
    def asDegrees(self) -> tuple[float, float, float]:
        """保持するXYZのEuler角を、radから度へ換算したtupleで取得する。

        現在のMaya UI角度単位は参照しない。回転順序は変更せず、
        等価な別解や一定の角度範囲へ正規化する処理も行わない。

        Returns:
            tuple[float, float, float]: XYZ角度の独立した値列(度)。自身は変化しない。
        """
        ...
    def asQuaternion(self) -> Quaternion:
        """保持するEuler角と回転順序から、独立したQuaternionを作る。

        自身は変更しない。Quaternionは回転の向きを表し、元のEuler角の回転周期や
        回転順序番号、利用者の追加Python状態を保存する容器ではない。

        Returns:
            Quaternion: 新しい単位Quaternion。
        """
        ...
    def mirror(self, axis: str | int = ...) -> EulerRotate:
        """Matrixと同じ規約で向きをビヘイビアミラーした複製を返す。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または0/1/2。

        Returns:
            EulerRotate: 同型の新しい回転。Eulerの回転順序は維持する。
        """
        ...
    def mirrorIt(self, axis: str | int = ...) -> EulerRotate:
        """自身の向きをビヘイビアミラーする。

        Args:
            axis (str | int): mirrorと同じ反転軸。

        Returns:
            EulerRotate: 更新した自身。
        """
        ...
    def asMatrix(self) -> Matrix:
        """回転順序を反映した回転マトリクスを返す。

        Returns:
            Matrix: 回転だけを持つ4行4列のマトリクス。
        """
        ...
    def isEquivalent(self, other: om2.MEulerRotation | Iterable[float], tolerance: float = ...) -> bool:
        """許容誤差付きでほぼ等しいか判定する。

        om2 の ``isEquivalent`` に委譲するため、回転順序が一致し、各成分の差が
        tolerance 以内のときだけ True になる。

        Args:
            other (om2.MEulerRotation | Iterable[float]): 比較対象。列は xyz 順序の
                ラジアンとして扱う。
            tolerance (float): 各成分の許容誤差。

        Returns:
            bool: ほぼ等しければ True。
        """
        ...
    def alternateSolution(self, *args) -> EulerRotate:
        """同じ向き・回転順序を持つ、別解のオイラー回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    def bound(self, *args) -> EulerRotate:
        """各角度を±πの範囲へ収めた、等価な回転の複製を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    def closestCut(self, *args) -> EulerRotate:
        """各軸へ一周の整数倍を加え、基準に近い等価な回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 基準となる回転targetを指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    def closestSolution(self, *args) -> EulerRotate:
        """基準に最も近い、等価なオイラー回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 基準となる回転targetを指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    def inverse(self, *args) -> EulerRotate:
        """逆回転を表す新しいオイラー回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    def reorder(self, *args) -> EulerRotate:
        """指定した回転順序で同じ向きを表す、新しい回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの回転順序定数orderを指定する。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        ...
    def asVector(self, *args) -> Vector:
        """回転順序を除いたXYZ角度成分を、radのVectorとして返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Vector: 演算結果を保持する新しいmlib値。
        """
        ...
    @classmethod
    def _wrap(cls, value: om2.MEulerRotation | om2.MQuaternion | om2.MMatrix) -> EulerRotate:
        """om2 の値を複製した cls のインスタンスを返す。

        Python の ``__new__`` / ``__init__`` を通さず(利用者の派生クラスの ``__init__`` も
        呼ばない)、基底の ``__init__`` で C++ の実体を確保する。

        Args:
            value (om2.MEulerRotation | om2.MQuaternion | om2.MMatrix): 複製元。
                ``setValue`` が受け付ける値。MEulerRotation なら順序も写す。

        Returns:
            EulerRotate: cls の新しいインスタンス。
        """
        ...
    x: Any
    y: Any
    z: Any
    order: Any
