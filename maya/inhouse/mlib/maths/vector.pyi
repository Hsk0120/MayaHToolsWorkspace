# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""om2.MVector を継承した3成分ベクトルと基本演算。"""

import math
import maya.api.OpenMaya as om2
from ..util import _checked_index, _copy_state, _foreign_comparison, _instance_state, _rethrow_init_error
from typing import Any, Iterable, Iterator, Sequence
from mlib.maths.quaternion import Quaternion
from typing_extensions import Self
import types

_MVector: Any
_MPoint: Any
_MMatrix: Any
_MQuaternion: Any
_MEuler: Any
_NEW: Any
_INIT: Any
_GET: Any
_SET: Any
_NUMBER: tuple
_OM2_POINT_TYPES: tuple

def _resolve_mvector(value: om2.MVector | om2.MPoint | Iterable[float]) -> om2.MVector:
    """値を om2.MVector として扱える形へ変換する。

    MVector 系(mlib の Vector 派生を含む)はそのまま返す。MPoint などの om2 の
    3成分型は MVector へ変換し(MPoint の w では割らない)、それ以外は
    3要素の反復可能オブジェクトとして展開する。

    Args:
        value (om2.MVector | om2.MPoint | Iterable[float]): 変換元。

    Returns:
        om2.MVector: value 自身、または新しい MVector。

    Raises:
        TypeError: 反復できない値の場合。
        ValueError: 反復可能オブジェクトの要素数が3でない場合。
    """
    ...

def _zero(cls) -> Vector:
    """Python の ``__new__`` / ``__init__`` を通さずに cls のゼロベクトルを作る。

    om2 の型は C++ の実体を基底の ``__init__`` で確保するため、``__new__`` の直後に
    必ず基底の ``__init__`` を呼ぶ。演算結果の生成など内部の高速な経路で使う。

    Args:
        cls (type): 生成する Vector 系のクラス。

    Returns:
        Vector: cls のゼロベクトル。
    """
    ...

def _vector_of(cls, value: om2.MVector | Sequence[float]) -> Vector:
    """om2 の MVector または3要素の列から cls のインスタンスを作る。

    引数付きコンストラクタは om2 の多重定義の解決が遅いため、引数なしで確保した
    インスタンスへ成分を代入する。

    Args:
        cls (type): 生成する Vector 系のクラス。
        value (om2.MVector | Sequence[float]): 値の取得元。

    Returns:
        Vector: cls の新しいインスタンス。
    """
    ...

def _vector_keywords(x: float = ..., y: float = ..., z: float = ...) -> tuple:
    """キーワード引数付きの Vector の生成引数を (x, y, z) へまとめる。

    Args:
        x (float): X 成分。
        y (float): Y 成分。
        z (float): Z 成分。

    Returns:
        tuple: (x, y, z)。
    """
    ...

def _rebuild(cls, values: tuple) -> Any:
    """copy / pickle の再構築関数。cls の ``__init__`` を呼ばずに値を復元する。

    om2 の型は C++ の実体を基底の ``__init__`` で確保するため、基底の ``__new__`` と
    ``__init__`` で確保してから成分を設定する。利用者の派生クラスが独自の引数の
    ``__init__`` を持っていても呼ばない。追加のアトリビュート(``__dict__`` / ``__slots__``)は
    pickle の標準の手順(``__reduce__`` の3番目の要素)で後から復元される。

    Args:
        cls (type): 復元するクラス。om2.MVector / MQuaternion / MEulerRotation /
            MMatrix のいずれかの派生。
        values (tuple): 成分。MVector 系は (x, y, z)、MQuaternion 系は (x, y, z, w)、
            MEulerRotation 系は (x, y, z, order)、MMatrix 系は行優先の16要素。

    Returns:
        object: 復元した cls のインスタンス。

    Raises:
        TypeError: cls が対応する om2 の型の派生でない場合。
        ValueError: values の要素数が型と合わない場合。
    """
    ...

def _reduce_value(value: object, values: tuple) -> tuple:
    """copy / pickle 用に、:func:`_rebuild` で再構築する情報を返す。

    利用者の派生クラスが持つ追加のアトリビュートは、pickle の標準形式の state(``__dict__`` の
    辞書、``__slots__`` もあれば ``(辞書, slots の辞書)``)として3番目の要素に置く。
    インスタンスの生成後に設定されるため、自身を参照するアトリビュートも復元できる。

    Args:
        value (object): 複製・保存する mlib の値。
        values (tuple): :func:`_rebuild` へ渡す成分。

    Returns:
        tuple: ``(_rebuild, (type(value), values))``、または state を加えた3要素の tuple。
    """
    ...


class Vector(om2.MVector):
    """om2.MVectorを継承した、可変・ハッシュ不可のXYZベクトル値。

    OpenMaya APIへそのまま渡せる。生成時は成分をコピーし、引数形式は :meth:`__init__` に従う。
    MPointからもwで割らずXYZを写す。

    演算はOM2に従い、ベクトル結果は派生型によらず基底Vectorを返す。
    ``om2.MVector`` が左辺の ``+`` / ``-`` / ``^`` もVectorになる。

    * ``+`` / ``-`` はMVector系の成分ごとの加減算。
    * ``v * 数値`` / ``数値 * v`` / ``v / 数値`` はスカラー演算。0除算はZeroDivisionError。
    * ``v * w`` は内積(float)、``v ^ w`` は外積。
    * ``v * m`` は平行移動を含まない行ベクトルの方向変換。
      ``m * v`` は列ベクトルの積(``v * mᵀ``)。

    ``+=`` / ``-=`` / ``*=`` / ``/=`` / ``^=`` は自身を更新し派生型を保つ。
    ただし ``v *= w`` は内積のfloatへ束ね直す。コピーを返す操作と自身更新を区別し、
    数学値を返す継承メソッドも対応するmlib型を使う。OpenMayaの共有クラス定数は変更しない。

    成分・番号へ代入可能。番号は-3〜2、範囲外はIndexError。スライスは代入不可のtuple、反復はXYZ順。
    ``==`` はMVector系の成分の完全一致で、派生型が違っても等しくなり得る。
    それ以外はOM2型ならFalse、他は相手の比較へ委ね、未判定ならFalse。
    OM2型が左辺の比較はOM2側でTypeErrorになり得る。
    """
    __slots__: tuple
    __hash__: None
    def __new__(cls, *args, **kwargs) -> Self:
        """基底初期化でC++実体を確保し、clsのゼロベクトルを作る。

        ``__init__`` を省略・失敗した派生クラスでも未確保実体へアクセスしないため、ここで確保する。
        mlibの ``__init__`` は成分だけを設定する。基底初期化の再実行はMaya 2022で実体をリークする。

        Args:
            *args: ここでは使わない生成引数。
            **kwargs: ここでは使わないキーワード引数。

        Returns:
            Vector: clsのゼロベクトル。
        """
        ...
    def __init__(self, *args, **kwargs) -> None:
        """成分を設定する。

        Args:
            *args: ``()``、``(x, y, z)``、``(x, y)``、``(values)``、または
                ``(MVector | MPoint | MFloatVector | MFloatPoint)`` など om2 の
                MVector のコンストラクタが受け付ける引数。
            **kwargs: ``x``、``y``、``z``。位置引数と合わせて使える。省略した成分は 0。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 未知のキーワード引数、または同じ成分を二重に指定した場合。
            ValueError: om2 のコンストラクタが受け付けない引数(文字列の成分など)の場合。
        """
        ...
    def __getitem__(self, index: int | slice) -> float | tuple[float, ...]:
        """成分を取得する。

        Args:
            index (int | slice): -3〜2 の番号、またはスライス。

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
            index (int): -3〜2 の番号。
            value (float): 設定する値。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 番号が整数以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        ...
    def __iter__(self) -> Iterator[float]:
        """X、Y、Z の順に成分を反復する。

        Returns:
            Iterator[float]: 3成分のイテレータ。
        """
        ...
    def __reduce__(self) -> tuple:
        """copy / pickle 用に、コンストラクタを通さずに再構築する情報を返す。

        om2 の型は C++ の実体を基底の ``__init__`` で確保するため、再構築関数で
        確保してから成分を設定する。利用者の派生クラスの ``__init__`` は呼ばず、
        ``__dict__`` と ``__slots__`` のアトリビュートは再構築時に復元する。

        Returns:
            tuple: ``(_rebuild, (type(self), (x, y, z))[, state])``。
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
    def __copy__(self) -> Vector:
        """同じ型・同じ成分の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートも浅く写す。

        Returns:
            Vector: 自身と同じクラスの新しいインスタンス。
        """
        ...
    def __deepcopy__(self, memo: dict) -> Vector:
        """同じ型・同じ成分の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートは深く複製する。

        Args:
            memo (dict): copy.deepcopy の memo。

        Returns:
            Vector: 自身と同じクラスの新しいインスタンス。
        """
        ...
    def __repr__(self) -> str:
        """クラス名と3成分を含むデバッグ表現を返す。

        Returns:
            str: ``Translate(1.0, 2.0, 3.0)`` の形式の文字列。
        """
        ...
    __str__: Any
    def __eq__(self, other: object) -> bool | types.NotImplementedType:
        """MVector 系との成分の完全一致を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MVector 系なら om2 と同じ成分比較の結果。
            その他の om2 の型は False。それ以外の型は NotImplemented(相手の比較に委ね、
            どちらも判断しなければ False になる)。
        """
        ...
    def __ne__(self, other: object) -> bool | types.NotImplementedType:
        """``__eq__`` の否定を返す。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MVector 系なら om2 と同じ比較の結果。
            その他の om2 の型は True。それ以外の型は NotImplemented。
        """
        ...
    def __add__(self, other: object) -> Vector | types.NotImplementedType:
        """MVector 系との成分ごとの加算を返す。

        Args:
            other (object): 加算する MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        ...
    def __radd__(self, other: object) -> Vector | types.NotImplementedType:
        """左辺の MVector 系との成分ごとの加算を返す。

        Args:
            other (object): 左辺の MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        ...
    def __iadd__(self, other: object) -> Vector | types.NotImplementedType:
        """MVector 系を自身へ加算する。

        om2 の MVector を継承した型では、対応しない型との ``+=`` が例外にならず
        NotImplemented が代入されてしまうため、型を検査してから委譲する。

        Args:
            other (object): 加算する MVector 系。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented(TypeError になる)。
        """
        ...
    def __sub__(self, other: object) -> Vector | types.NotImplementedType:
        """MVector 系との成分ごとの減算を返す。

        Args:
            other (object): 減算する MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        ...
    def __rsub__(self, other: object) -> Vector | types.NotImplementedType:
        """左辺の MVector 系から自身を引いた値を返す。

        Args:
            other (object): 左辺の MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        ...
    def __isub__(self, other: object) -> Vector | types.NotImplementedType:
        """MVector 系を自身から減算する。

        Args:
            other (object): 減算する MVector 系。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        ...
    def __mul__(self, other: object) -> Vector | float | types.NotImplementedType:
        """om2 の意味論で乗算する。

        Args:
            other (object): 数値、MVector 系、または MMatrix 系。

        Returns:
            Vector | float | types.NotImplementedType: 数値ならスカラー倍の Vector、
            MVector 系なら内積の float、MMatrix 系なら行ベクトル規約で方向変換した
            Vector(平行移動を含まない)。対応しない型は NotImplemented。
        """
        ...
    def __rmul__(self, other: object) -> Vector | types.NotImplementedType:
        """左辺からの乗算を om2 の意味論で行う。

        ``m * v`` (m は MMatrix 系)は om2 と同じく列ベクトルとしての積
        (``v * mᵀ``)になる。位置をマトリクスで変換する場合は
        :meth:`mlib.maths.matrix.Matrix.transformPoint`、方向は ``v * m`` を使う。

        Args:
            other (object): 数値または MMatrix 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        ...
    def __imul__(self, other: object) -> Vector | types.NotImplementedType:
        """数値倍、または MMatrix 系による行ベクトル規約の方向変換を自身へ適用する。

        Args:
            other (object): 数値または MMatrix 系。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented
            (MVector 系を渡した場合は om2 と同じく内積へ戻り、名前が float に再束縛される)。
        """
        ...
    def __truediv__(self, other: object) -> Vector | types.NotImplementedType:
        """数値による成分ごとの除算を返す。

        Args:
            other (object): 除数の int または float。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合(Maya のバージョンにかかわらない)。
        """
        ...
    def __itruediv__(self, other: object) -> Vector | types.NotImplementedType:
        """数値で自身を除算する。

        Args:
            other (object): 除数の int または float。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合。
        """
        ...
    def __xor__(self, other: object) -> Vector | types.NotImplementedType:
        """MVector 系との外積を返す(om2 の ``^``)。

        Args:
            other (object): 外積の相手となる MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        ...
    def __rxor__(self, other: object) -> Vector | types.NotImplementedType:
        """左辺の MVector 系と自身の外積 ``other ^ self`` を返す。

        Vector は om2.MVector の派生なので、``om2.MVector ^ Vector`` では Python が
        このメソッドを先に呼ぶ(定義しないと om2 の結果の ``om2.MVector`` になる)。

        Args:
            other (object): 左辺の MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        ...
    def __ixor__(self, other: object) -> Vector | types.NotImplementedType:
        """MVector 系との外積で自身を書き換える(om2 の MVector には無い in-place 版)。

        Args:
            other (object): 外積の相手となる MVector 系。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        ...
    def __neg__(self) -> Vector:
        """各成分の符号を反転した値を返す。

        Returns:
            Vector: 新しい Vector。派生クラスの型は保持しない。
        """
        ...
    @classmethod
    def fromIterable(cls, values: Iterable[float]) -> Vector:
        """3要素の反復可能オブジェクトから生成する。

        Args:
            values (Iterable[float]): 3要素の反復可能オブジェクト。

        Returns:
            Vector: 呼び出したクラスの新しいインスタンス。

        Raises:
            ValueError: 要素数が3でない場合。
        """
        ...
    def mirror(self, axis: str | int = ..., pivot: Iterable[float] = ...) -> Vector:
        """指定中心から成分を反転した同型の複製を返す。

        Translate・Scale・Shearでも数値反転として使用できる。
        Scale・Shearのマトリクスとしての鏡映にはMatrix.mirrorを使う。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または0/1/2。
            pivot (Iterable[float]): 値と同じ単位の中心。方向には原点を使う。

        Returns:
            Vector: 同型の新しい値。
        """
        ...
    def mirrorIt(self, axis: str | int = ..., pivot: Iterable[float] = ...) -> Vector:
        """自身の3成分を反転する。

        Args:
            axis (str | int): mirrorと同じ反転軸。
            pivot (Iterable[float]): 値と同じ単位の中心。

        Returns:
            Vector: 更新した自身。
        """
        ...
    def dot(self, other: om2.MVector | om2.MPoint | Iterable[float]) -> float:
        """内積を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 内積の相手。

        Returns:
            float: 内積。
        """
        ...
    def cross(self, other: om2.MVector | om2.MPoint | Iterable[float]) -> Vector:
        """外積を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 外積の相手。

        Returns:
            Vector: 外積。派生クラスの型は保持しない。
        """
        ...
    def lengthSq(self) -> float:
        """長さの2乗(自身との内積)を返す。

        平方根を計算しないため、長さの比較だけが目的なら length() より速い。

        Returns:
            float: 長さの2乗。
        """
        ...
    def normal(self, *args) -> Vector:
        """OpenMayaの規則で正規化したVectorの複製を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Vector: 演算結果を保持する新しいmlib値。
        """
        ...
    def rotateBy(self, *args) -> Vector:
        """OpenMayaの回転規則でXYZベクトルを回し、独立したVectorを返す。

        MVector.rotateBy()へ引数をそのまま渡し、自身や回転引数は変更しない。
        Quaternionの事前正規化やゼロ拒否を独自に加えないため、
        Quaternion.rotateVector()の正規化コピーによる回転とは入力条件が異なる。

        Args:
            *args: Quaternion/EulerRotateなどの回転、またはOpenMayaの軸定数とrad角度。
                多重定義の受理型はMVector.rotateBy()に従う。

        Returns:
            Vector: 基底Vectorの新しい値。派生型や追加Python状態は引き継がない。
        """
        ...
    def rotateTo(self, *args) -> Quaternion:
        """自身の方向から指定した方向へ向けるQuaternionを返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 目標方向となるMVector系のtargetを指定する。

        Returns:
            Quaternion: 演算結果を保持する新しいmlib値。
        """
        ...
    def transformAsNormal(self, *args) -> Vector:
        """マトリクスの逆転置で法線変換し、正規化したVectorの複製を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 変換に使うMMatrix系のmatrixを指定する。

        Returns:
            Vector: 演算結果を保持する新しいmlib値。
        """
        ...
    def unitIt(self) -> Vector:
        """ゼロ値を拒否して自身を正規化する。

        Returns:
            Vector: 更新した自身。

        Raises:
            ValueError: ゼロ値の場合。自身は変更しない。
        """
        ...
    def unit(self) -> Vector:
        """正規化した新しいベクトルを返す。

        om2 の ``normal()`` はゼロベクトルでも例外にならず ``om2.MVector`` を返すが、
        このメソッドは mlib の Vector を返し、ゼロベクトルを拒否する。

        Returns:
            Vector: 長さ 1 のベクトル。派生クラスの型は保持しない。

        Raises:
            ValueError: ゼロベクトルの場合。
        """
        ...
    def distanceTo(self, other: om2.MVector | om2.MPoint | Iterable[float]) -> float:
        """2点間のユークリッド距離を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 距離を測る相手。

        Returns:
            float: 距離。
        """
        ...
    def angleTo(self, other: om2.MVector | om2.MPoint | Iterable[float]) -> float:
        """別のベクトルとの成す角度をラジアンで返す。

        ``atan2(|a × b|, a · b)`` で計算するため、ほぼ平行・反平行な場合も精度を
        保つ(om2 の ``angle()`` は約 1e-5 rad 未満の角度を 0 として返す)。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 角度を測る相手。

        Returns:
            float: 0 から pi の範囲のラジアン角度。

        Raises:
            ValueError: 自身または other がゼロベクトルの場合。
        """
        ...
    def isEquivalent(self, other: om2.MVector | om2.MPoint | Iterable[float], tolerance: float = ...) -> bool:
        """許容誤差付きでほぼ等しいか判定する。

        om2 の ``isEquivalent`` に委譲するため、2点間のユークリッド距離が
        tolerance 以下かどうかで判定する。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 比較対象。
            tolerance (float): 距離の許容誤差。

        Returns:
            bool: ほぼ等しければ True。
        """
        ...
    def lerp(self, other: om2.MVector | om2.MPoint | Iterable[float], t: float) -> Vector:
        """別のベクトルとの線形補間 ``self + (other - self) * t`` を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 補間先。
            t (float): 補間係数。0 で自身、1 で other。範囲外は外挿になる。

        Returns:
            Vector: 補間結果。派生クラスの型は保持しない。
        """
        ...
    @classmethod
    def _wrap(cls, value: om2.MVector) -> Vector:
        """3成分の値を複製した cls のインスタンスを返す(追加のアトリビュートは写さない)。

        Python の ``__new__`` / ``__init__`` を通さない(利用者の派生クラスの
        ``__init__`` も呼ばない)。

        Args:
            value (om2.MVector): 複製元。x・y・zを持つ値。

        Returns:
            Vector: cls の新しいインスタンス。
        """
        ...
    x: Any
    y: Any
    z: Any
