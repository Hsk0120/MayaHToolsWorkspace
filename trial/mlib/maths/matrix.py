"""om2.MMatrix を継承した、Maya の行ベクトル規約の4行4列のマトリクス。"""

from operator import index as _as_index

import maya.api.OpenMaya as om2

from ..util import _checked_index, _copy_state, _foreign_comparison
from .eulerRotate import EulerRotate
from .quaternion import Quaternion
from .scale import Scale
from .shear import Shear
from .translate import Translate
from .vector import (
    Vector,
    _reduce_value,
    _vector_of,
    _zero,
)

_MMatrix = om2.MMatrix
_MVector = om2.MVector
_MPoint = om2.MPoint
_MQuaternion = om2.MQuaternion
_MEuler = om2.MEulerRotation
_MTransformationMatrix = om2.MTransformationMatrix
_K_TRANSFORM = om2.MSpace.kTransform
_GET = _MMatrix.__getitem__
_SET = _MMatrix.__setitem__
#: om2 のスカラー倍。結果は素の om2.MMatrix で、1.0 倍は符号付きゼロ・inf・NaN を含めて
#: 値を変えない。mlib の ``__getitem__`` (Python)を経由せず、om2 の C 実装の添字で
#: 16要素を読むために使う(:attr:`Matrix.values` など)。
_SCALED = _MMatrix.__mul__
#: ``m * v`` で Vector を作る om2 の関数(Python の ``__new__`` / ``__init__`` を通さない)。
_VECTOR_NEW = _MVector.__new__
_VECTOR_INIT = _MVector.__init__
_VECTOR_IADD = _MVector.__iadd__
#: om2 の列ベクトルとしての積 ``m * v`` (``_VECTOR_RMUL(v, m)``)。
_VECTOR_RMUL = _MVector.__rmul__
_NUMBER = (int, float)
#: 添字の型の判定用(組み込み名より速く引けるモジュールの名前)。
_INT = int
#: ``m[行, 列]`` の (行, 列)(それぞれ -4〜3)から平坦な添字(0〜15)への表。
_CELL_INDEX = {(row, column): (row % 4) * 4 + column % 4 for row in range(-4, 4) for column in range(-4, 4)}
_POINT_TYPES = (_MVector, om2.MPoint, om2.MFloatVector, om2.MFloatPoint)
_MATRIX_SOURCES = (_MMatrix, om2.MFloatMatrix)
_MATRIX_ERROR = "Matrix expects an MMatrix, 4x4 rows, or 16 values"


def _reinit_is_safe():
    """om2 の ``MMatrix.__init__`` を確保済みのインスタンスへ再適用してよい版か判定する。

    Maya 2022 の om2 は ``__init__`` を再び呼ぶたびに確保済みの C++ の実体をリークする
    (計測で約150バイト/回)。Maya 2024〜2027 ではリークせず、受け付けない引数で失敗した
    場合も値は変わらないことを確認している(2023 は未検証のためリークする版として扱う)。

    Returns:
        bool: API バージョンが 2024 以降なら True。
    """
    try:
        return om2.MGlobal.apiVersion() >= 20240000
    except Exception:  # noqa: BLE001 - 判定できない環境はリークする版として安全側に倒す。
        return False


#: 列(16要素・4行4列)からの設定で、om2 のコンストラクタを自身へ再適用するか。
#: Matrix(16要素の list) の計測では、再適用できない 2022 は一時的な MMatrix を作って写す経路
#: (要素ごとの書き込み 2.29µs → 1.44µs)、2024 以降は再適用の方が写す経路より約1割速い
#: (2027 で 2.39µs → 1.51µs)。どちらも om2 が要素を検査し、受け付けない値では失敗する。
_REINIT = _reinit_is_safe()


def _set_sequence(target, values):
    """om2 のコンストラクタが受け付ける列を target へ書き込む。

    Args:
        target (om2.MMatrix): 書き込み先。
        values (list | tuple): 16要素、または4要素の行を4つ並べた列。

    Returns:
        bool: 書き込めたら True。om2 が受け付けない形(文字列の要素など)なら False で、
        target は変わらない。
    """
    try:
        if _REINIT:
            _MMatrix.__init__(target, values)
        else:
            _assign(target, _MMatrix(values))
    except (TypeError, ValueError):
        return False
    return True


def _xyz(value):
    """3成分の値を (x, y, z) の tuple として取り出す。

    Args:
        value (om2.MVector | om2.MPoint | Iterable[float]): 取り出し元。MPoint の w は無視する。

    Returns:
        tuple: (x, y, z)。

    Raises:
        ValueError: 反復可能オブジェクトの要素数が3でない場合。
    """
    if isinstance(value, _POINT_TYPES):
        return value.x, value.y, value.z
    x, y, z = value
    return x, y, z


def _new(cls):
    """Python の ``__new__`` / ``__init__`` を通さずに cls の単位マトリクスを作る。

    om2 の型は C++ の実体を基底の ``__init__`` で確保するため、``__new__`` の直後に
    必ず基底の ``__init__`` を呼ぶ。

    Args:
        cls (type): 生成する Matrix 系のクラス。

    Returns:
        Matrix: cls の単位マトリクス。
    """
    result = _MMatrix.__new__(cls)
    _MMatrix.__init__(result)
    return result


def _assign(target, source):
    """source の16要素を target へそのまま写す(C++ の実体は確保し直さない)。

    単位マトリクスを -0.0 倍した「すべて -0.0」のマトリクスへ source を加算する。-0.0 は加算の
    単位元なので、符号付きゼロ・inf・NaN を含めて source と同じ値になる(0.0 を
    使うと -0.0 が 0.0 になる)。

    Args:
        target (om2.MMatrix): 書き込み先。
        source (om2.MMatrix): 複製元。

    Returns:
        om2.MMatrix: target。
    """
    target.setToIdentity()
    _MMatrix.__imul__(target, -0.0)
    _MMatrix.__iadd__(target, source)
    return target


def _number(value):
    """マトリクスの要素を float へ変換する。

    om2 のコンストラクタと同じく数値だけを受け付け、文字列は拒否する
    (``float("1")`` のような文字列からの変換はしない)。

    Args:
        value (object): 要素。

    Returns:
        float: 変換した値。

    Raises:
        TypeError: 文字列など数値でない場合。
    """
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError("Matrix values must be numbers")
    return float(value)


def _flat_values(values):
    """om2 が直接受け付けない入力を、float の16要素リストへ変換する。

    Args:
        values (Sequence): 16要素、または4要素の行を4つ並べた列。要素は数値。

    Returns:
        list[float]: 行優先順の16要素。

    Raises:
        ValueError: 16要素の数値として解釈できない場合(文字列の要素を含む)。
    """
    try:
        if len(values) == 16:
            return [_number(value) for value in values]
        if len(values) == 4:
            rows = [tuple(row) for row in values]
            if all(len(row) == 4 for row in rows):
                return [_number(value) for row in rows for value in row]
    except (TypeError, ValueError):
        pass
    raise ValueError(_MATRIX_ERROR)


def _rotate_matrix(rotate):
    """回転の指定を回転だけの om2.MMatrix へ変換する。

    Args:
        rotate (Iterable[float] | om2.MEulerRotation | om2.MQuaternion): XYZ 順の
            ラジアン3成分、回転順序を持つ Euler 回転、またはクォータニオン(正規化して使う)。

    Returns:
        om2.MMatrix: 回転マトリクス。

    Raises:
        ValueError: ゼロクォータニオン、または3成分として解釈できない場合。
    """
    if isinstance(rotate, _MQuaternion):
        if rotate.x * rotate.x + rotate.y * rotate.y + rotate.z * rotate.z + rotate.w * rotate.w == 0.0:
            raise ValueError("Cannot normalize a zero quaternion")
        # mlibの派生クラスで包み直さないよう、om2の関数を直接呼ぶ(値は rotate.normal().asMatrix() と同じ)。
        return _MQuaternion.asMatrix(_MQuaternion.normal(rotate))
    if isinstance(rotate, _MEuler):
        return rotate.asMatrix()
    x, y, z = rotate
    euler = _MEuler()
    euler.x = x
    euler.y = y
    euler.z = z
    return euler.asMatrix()


def _compose_into(target, translate, rotation, scale, shear):
    """S * Sh * R に平行移動を置いた値を、単位マトリクスの target へ書き込む。

    ``MTransformationMatrix.setScale`` は絶対値が 1e-12 未満のスケールを 1e-12 に
    丸めるため使わず、要素を直接書き込む。

    Args:
        target (om2.MMatrix): 単位マトリクスで初期化済みの書き込み先。
        translate (tuple[float, float, float] | None): 平行移動。None は 0。
        rotation (om2.MMatrix | None): 回転マトリクス。None は回転なし。
        scale (tuple[float, float, float] | None): スケール。None は 1。
        shear (tuple[float, float, float] | None): XY、XZ、YZ のシアー。None は 0。

    Returns:
        om2.MMatrix: target。
    """
    if scale is not None or shear is not None:
        sx, sy, sz = (1.0, 1.0, 1.0) if scale is None else scale
        xy, xz, yz = (0.0, 0.0, 0.0) if shear is None else shear
        _SET(target, 0, sx)
        _SET(target, 4, sy * xy)
        _SET(target, 5, sy)
        _SET(target, 8, sz * xz)
        _SET(target, 9, sz * yz)
        _SET(target, 10, sz)
    if rotation is not None:
        _MMatrix.__imul__(target, rotation)
    if translate is not None:
        _SET(target, 12, translate[0])
        _SET(target, 13, translate[1])
        _SET(target, 14, translate[2])
    return target


def _components(translate, rotate, scale, shear):
    """合成用の引数を検証し、_compose_into へ渡す形へ変換する。

    Args:
        translate (Iterable[float] | None): 平行移動。
        rotate (Iterable[float] | om2.MEulerRotation | om2.MQuaternion | None): 回転。
        scale (Iterable[float] | None): スケール。
        shear (Iterable[float] | None): シアー。

    Returns:
        tuple: (translate, rotation_matrix, scale, shear)。未指定は None のまま。

    Raises:
        ValueError: 3成分として解釈できない値、またはゼロクォータニオンの場合。
    """
    return (
        None if translate is None else _xyz(translate),
        None if rotate is None else _rotate_matrix(rotate),
        None if scale is None else _xyz(scale),
        None if shear is None else _xyz(shear),
    )


class Matrix(om2.MMatrix):
    """om2.MMatrixを継承した、Mayaの行ベクトル規約の可変な4行4列のマトリクス。

    OpenMaya APIへそのまま渡せる。入力はコピーし、16要素は行優先、平行移動は番号12〜14。
    Mayaへ渡す平行移動はcmで、UI単位へ換算しない。
    合成・分解はアフィン変換を想定する。分解はMTransformationMatrixの規約で、
    負の行列式ではZスケールを負にして180度の補償回転を入れる(cmds.xform/decomposeMatrixと同じ)。

    * ``a * b`` / ``a @ b`` はaを先に適用するマトリクスの積。結果は ``type(a)``。
      ``om2.MMatrix * Matrix`` もMatrixを返す。
    * 数値倍・加減算はOM2の成分ごとの演算。
    * ``Vector * m`` は平行移動を含まない方向変換。
      左辺が ``om2.MVector`` / ``om2.MPoint`` ならOM2側で処理しOM2型を返す。
    * ``m * v`` はMVector系との列ベクトルの積(``v * mᵀ``)をVectorで返す。
      ``m * om2.MPoint`` も列ベクトルの積のXYZをVectorで返し、結果のwは捨ててwで割らない。
    * ``m @ v`` はTypeError。位置の変換は :meth:`transformPoint` または ``om2.MPoint(p) * m`` を使う。

    ``*=`` / ``@=`` / ``+=`` / ``-=`` は自身を更新する。数学値を返す継承メソッドもmlib型を返し、
    コピー操作は独立値、It付き操作は自身更新となる。成分プロパティの取得値も独立した複製で、編集してもマトリクスは変わらない。

    ハッシュ不可。``m[i]`` は-16〜15、``m[行, 列]`` は各-4〜3で代入でき、範囲外はIndexError。
    ``==`` はMMatrix系の完全一致。異種型との比較は :class:`~mlib.maths.vector.Vector` と同じ扱い。
    """

    __slots__ = ()
    __hash__ = None

    def __new__(cls, *args, **kwargs):
        """基底初期化でC++実体を確保し、clsの単位マトリクスを作る。

        ``__init__`` を省略・失敗しても実体へアクセスできるよう、先に確保する。
        詳細は :meth:`mlib.maths.vector.Vector.__new__` を参照。

        Args:
            *args: ここでは使わない生成引数。
            **kwargs: ここでは使わないキーワード引数。

        Returns:
            Matrix: clsの単位マトリクス。
        """
        self = _MMatrix.__new__(cls)
        _MMatrix.__init__(self)
        return self

    def __init__(self, values=None, *, translate=None, rotate=None, scale=None, shear=None):
        """入力マトリクス、または TRS / shear 成分から値を設定する。

        入力をすべて検証してから書き込むため、例外時に値は変わらない。

        Args:
            values (om2.MMatrix | om2.MFloatMatrix | Iterable[float] | Iterable[Iterable[float]] | None):
                16要素または4行4列のマトリクス。指定時は他の変換引数をすべて無視する。
            translate (Iterable[float] | None): XYZ の平行移動成分。None は 0。
            rotate (Iterable[float] | EulerRotate | Quaternion | None): XYZ 順の
                ラジアン3成分、回転順序を反映する EulerRotate(om2.MEulerRotation)、
                またはクォータニオン(正規化して使う)。None は回転なし。
            scale (Iterable[float] | None): XYZ のスケール成分。None は 1。0 や
                微小値もそのまま書き込む。
            shear (Iterable[float] | None): XY、XZ、YZ のシアー成分。None は 0。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: マトリクス入力が16要素として解釈できない場合、成分が3要素でない場合、
                または回転クォータニオンがゼロの場合。
        """
        if values is not None:
            kind = values.__class__
            if kind is not list and kind is not tuple:
                if isinstance(values, _MMatrix):
                    _assign(self, values)
                    return
                if isinstance(values, om2.MFloatMatrix):
                    _assign(self, _MMatrix(values))
                    return
                try:
                    values = list(values)
                except TypeError:
                    raise ValueError(_MATRIX_ERROR) from None
            # om2 が受け付けない形(数値以外の要素や行の列以外)は検証してから書き込む。
            # om2 は失敗時に値を変えないため、例外時も自身は変わらない。
            if not _set_sequence(self, values):
                _set_sequence(self, _flat_values(values))
            return
        if translate is None and rotate is None and scale is None and shear is None:
            self.setToIdentity()
            return
        parts = _components(translate, rotate, scale, shear)
        self.setToIdentity()
        _compose_into(self, *parts)

    def __getitem__(self, index):
        """マトリクスの要素を取得する。

        Args:
            index (int | slice | tuple[int, int]): 平坦な番号(負の番号も可)、スライス、
                または (行, 列)。行・列はそれぞれ -4〜3。

        Returns:
            float | tuple[float, ...]: 指定要素。スライスでは tuple。

        Raises:
            TypeError: 番号が整数・スライス・tuple 以外の場合。
            IndexError: 番号が範囲外の場合(平坦な番号は -16〜15)。
        """
        if index.__class__ is _INT:
            if -16 <= index < 16:
                # -16〜15 の範囲では ``index & 15`` が負の添字を 0〜15 へ正規化する。
                return _GET(self, index & 15)
        elif index.__class__ is tuple:
            # よく使う m[行, 列](-4〜3 の int)は表を引いて _flat_index を通さない。表は
            # 1.0 や True とも一致するため、行・列が int そのものか確かめてから使う。
            try:
                flat = _CELL_INDEX.get(index)
            except TypeError:  # ハッシュできない要素は _flat_index で TypeError にする。
                flat = None
            if flat is not None and index[0].__class__ is _INT is index[1].__class__:
                return _GET(self, flat)
        if isinstance(index, tuple):
            return _GET(self, _flat_index(index))
        if isinstance(index, slice):
            return tuple(_SCALED(self, 1.0))[index]
        return _GET(self, _checked_index(index, 16, "Matrix"))

    def __setitem__(self, index, value):
        """マトリクスの要素を設定する。

        Args:
            index (int | tuple[int, int]): 平坦な番号(-16〜15)、または (行, 列)。
            value (float): 設定する値。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 番号が整数・tuple 以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        if index.__class__ is _INT:
            if -16 <= index < 16:
                _SET(self, index & 15, value)
                return
        elif index.__class__ is tuple:
            # __getitem__ と同じく、m[行, 列](-4〜3 の int)は表を引く。
            try:
                flat = _CELL_INDEX.get(index)
            except TypeError:
                flat = None
            if flat is not None and index[0].__class__ is _INT is index[1].__class__:
                _SET(self, flat, value)
                return
        if isinstance(index, tuple):
            index = _flat_index(index)
        else:
            index = _checked_index(index, 16, "Matrix")
        _SET(self, index, value)

    def __iter__(self):
        """行優先順の16要素を反復する。

        要素は反復を始めた時点の値(素の om2.MMatrix へ写した値)を返す。

        Returns:
            Iterator[float]: 16要素のイテレータ。
        """
        return iter(_SCALED(self, 1.0))

    def __reduce__(self):
        """copy / pickle 用に、コンストラクタを通さずに再構築する情報を返す。

        Returns:
            tuple: ``(_rebuild, (type(self), 16要素の tuple)[, state])``。
            利用者の派生クラスの ``__init__`` は呼ばず、``__dict__`` と ``__slots__`` の
            アトリビュートは再構築時に復元する。
        """
        return _reduce_value(self, tuple(_SCALED(self, 1.0)))

    def __reduce_ex__(self, protocol):
        """pickle のプロトコルにかかわらず __reduce__ と同じ情報を返す。

        Args:
            protocol (int): pickle のプロトコル番号。使用しない。

        Returns:
            tuple: ``__reduce__()`` の結果。
        """
        return self.__reduce__()

    def __copy__(self):
        """同じ型・同じ値の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートも浅く写す。

        Returns:
            Matrix: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self))

    def __deepcopy__(self, memo):
        """同じ型・同じ値の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートは深く複製する。

        Args:
            memo (dict): copy.deepcopy の memo。

        Returns:
            Matrix: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self), memo)

    def __repr__(self):
        """4行の値を含むデバッグ表現を返す。

        Returns:
            str: 型名と現在の成分を含む文字列表現。
        """
        return "{}({!r})".format(type(self).__name__, self.rows)

    __str__ = __repr__

    def __eq__(self, other):
        """MMatrix 系との全要素の完全一致を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MMatrix 系なら om2 と同じ比較の結果。
            その他の om2 の型は False。それ以外の型は NotImplemented(相手の比較に委ね、
            どちらも判断しなければ False になる)。
        """
        if isinstance(other, _MMatrix):
            return _MMatrix.__eq__(self, other)
        return _foreign_comparison(other, False)

    def __ne__(self, other):
        """``__eq__`` の否定を返す。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MMatrix 系なら om2 と同じ比較の結果。
            その他の om2 の型は True。それ以外の型は NotImplemented。
        """
        if isinstance(other, _MMatrix):
            return _MMatrix.__ne__(self, other)
        return _foreign_comparison(other, True)

    def __mul__(self, other):
        """マトリクスの積、スカラー倍、またはベクトル・点との列ベクトルとしての積を返す。

        ベクトルと点は om2 と同じ列ベクトルとしての積(``v * mᵀ``)を計算し、
        om2 の型(``om2.MVector`` / ``om2.MPoint``)が右辺でも mlib の Vector で返す。

        Args:
            other (object): 右側の MMatrix 系、数値、MVector 系、または om2.MPoint。

        Returns:
            Matrix | Vector | types.NotImplementedType: マトリクス・数値なら ``type(self)`` の
            新しいマトリクス。MVector 系なら om2 の列ベクトルとしての積の Vector。om2.MPoint なら
            om2 の列ベクトルとしての積(同次座標の4成分)の x、y、z を持つ Vector(w は捨て、
            w で割らない)。対応しない型は NotImplemented。
        """
        if isinstance(other, _MMatrix):
            result = _new(type(self))
            result.setToProduct(self, other)
            return result
        if isinstance(other, _NUMBER):
            return type(self)._wrap(_MMatrix.__mul__(self, other))
        if isinstance(other, _MVector):
            result = _VECTOR_NEW(Vector)
            _VECTOR_INIT(result)
            _VECTOR_IADD(result, _VECTOR_RMUL(other, self))
            return result
        if isinstance(other, _MPoint):
            value = _MPoint.__rmul__(other, self)
            result = _VECTOR_NEW(Vector)
            _VECTOR_INIT(result)
            result.x = value.x
            result.y = value.y
            result.z = value.z
            return result
        return NotImplemented

    def __rmul__(self, other):
        """左辺の MMatrix 系とのマトリクスの積、またはスカラー倍を返す。

        Args:
            other (object): 左側の MMatrix 系、または数値。

        Returns:
            Matrix | types.NotImplementedType: ``type(self)`` の新しいマトリクス。
            対応しない型は NotImplemented。
        """
        if isinstance(other, _MMatrix):
            result = _new(type(self))
            result.setToProduct(other, self)
            return result
        if isinstance(other, _NUMBER):
            return type(self)._wrap(_MMatrix.__mul__(self, other))
        return NotImplemented

    def __imul__(self, other):
        """自身へ右からマトリクスを掛ける、またはスカラー倍する。

        Args:
            other (object): MMatrix 系または数値。

        Returns:
            Matrix | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, (int, float, _MMatrix)):
            return NotImplemented
        return _MMatrix.__imul__(self, other)

    def __matmul__(self, other):
        """``@`` 演算子によるマトリクスの積(``*`` と同じ)。

        Args:
            other (object): 右側の MMatrix 系。

        Returns:
            Matrix | types.NotImplementedType: マトリクスの積。マトリクス以外は NotImplemented(TypeError)。
        """
        if isinstance(other, _MMatrix):
            return self.__mul__(other)
        return NotImplemented

    def __rmatmul__(self, other):
        """左辺の MMatrix 系との ``@`` によるマトリクスの積。

        Args:
            other (object): 左側の MMatrix 系。

        Returns:
            Matrix | types.NotImplementedType: マトリクスの積。マトリクス以外は NotImplemented。
        """
        if isinstance(other, _MMatrix):
            return self.__rmul__(other)
        return NotImplemented

    def __imatmul__(self, other):
        """``@=`` で自身へ右からマトリクスを掛ける(``*=`` と同じ in-place のマトリクスの積)。

        Args:
            other (object): MMatrix 系。

        Returns:
            Matrix | types.NotImplementedType: 自身。マトリクス以外は NotImplemented(TypeError)。
        """
        if not isinstance(other, _MMatrix):
            return NotImplemented
        return _MMatrix.__imul__(self, other)

    def __add__(self, other):
        """成分ごとの和を返す。

        Args:
            other (object): MMatrix 系。

        Returns:
            Matrix | types.NotImplementedType: ``type(self)`` の新しいマトリクス。
        """
        if not isinstance(other, _MMatrix):
            return NotImplemented
        return type(self)._wrap(_MMatrix.__add__(self, other))

    def __radd__(self, other):
        """左辺の MMatrix 系との成分ごとの和を返す。

        Args:
            other (object): MMatrix 系。

        Returns:
            Matrix | types.NotImplementedType: ``type(self)`` の新しいマトリクス。
        """
        if not isinstance(other, _MMatrix):
            return NotImplemented
        return type(self)._wrap(_MMatrix.__add__(other, self))

    def __iadd__(self, other):
        """MMatrix 系を成分ごとに自身へ加算する。

        Args:
            other (object): MMatrix 系。

        Returns:
            Matrix | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MMatrix):
            return NotImplemented
        return _MMatrix.__iadd__(self, other)

    def __sub__(self, other):
        """成分ごとの差を返す。

        Args:
            other (object): MMatrix 系。

        Returns:
            Matrix | types.NotImplementedType: ``type(self)`` の新しいマトリクス。
        """
        if not isinstance(other, _MMatrix):
            return NotImplemented
        return type(self)._wrap(_MMatrix.__sub__(self, other))

    def __rsub__(self, other):
        """左辺の MMatrix 系から自身を引いた成分ごとの差を返す。

        Args:
            other (object): MMatrix 系。

        Returns:
            Matrix | types.NotImplementedType: ``type(self)`` の新しいマトリクス。
        """
        if not isinstance(other, _MMatrix):
            return NotImplemented
        return type(self)._wrap(_MMatrix.__sub__(other, self))

    def __isub__(self, other):
        """MMatrix 系を成分ごとに自身から減算する。

        Args:
            other (object): MMatrix 系。

        Returns:
            Matrix | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MMatrix):
            return NotImplemented
        return _MMatrix.__isub__(self, other)

    @classmethod
    def identity(cls):
        """単位マトリクスを生成する。

        引数なしの ``Matrix()`` と同じ結果だが、意図を明示できる。

        Returns:
            Matrix: 呼び出したクラスの単位マトリクス。
        """
        return _new(cls)

    @classmethod
    def compose(cls, translate=(0.0, 0.0, 0.0), rotate=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), shear=(0.0, 0.0, 0.0)):
        """TRS / shear 成分から Matrix を合成する。

        Args:
            translate (Iterable[float]): XYZ の平行移動成分。
            rotate (Iterable[float] | EulerRotate | Quaternion): XYZ 順のラジアン
                3成分、回転順序を反映する EulerRotate、またはクォータニオン。
            scale (Iterable[float]): XYZ のスケール成分。
            shear (Iterable[float]): XY、XZ、YZ のシアー成分。

        Returns:
            Matrix: 呼び出したクラスの新しいマトリクス。

        Raises:
            ValueError: 成分が3要素でない場合、または回転クォータニオンがゼロの場合。
        """
        return cls(translate=translate, rotate=rotate, scale=scale, shear=shear)

    @classmethod
    def fromMMatrix(cls, matrix):
        """Maya API 2.0 のマトリクスから、複製した mlib のマトリクスを作る。

        Matrix はそれ自体が om2.MMatrix なので、om2 へ渡すための変換は不要。

        Args:
            matrix (om2.MMatrix | om2.MFloatMatrix): 複製元のマトリクス。

        Returns:
            Matrix: 呼び出したクラスの新しいマトリクス。
        """
        if isinstance(matrix, _MATRIX_SOURCES):
            return cls._wrap(matrix)
        return cls(matrix)

    @classmethod
    def fromTransformation(cls, transformation):
        """Maya API 2.0の変換情報からマトリクスを生成する。

        Args:
            transformation (om2.MTransformationMatrix): 合成する変換情報。

        Returns:
            Matrix: 呼び出したクラスの新しいマトリクス。
        """
        return cls._wrap(transformation.asMatrix())

    @property
    def values(self):
        """マトリクスの16成分を行優先順の独立したtupleとして取得する。

        Mayaの行ベクトル規約で、平行移動は番号12・13・14にある。
        要素は数値のスナップショットで、マトリクスを後から変更してもこのtupleは変わらない。

        Returns:
            tuple[float, ...]: 16要素。4行の入れ子形式はrowsを使う。
        """
        return tuple(_SCALED(self, 1.0))

    @property
    def rows(self):
        """マトリクスの16成分を、行ごとに区切った4行4列のtupleとして取得する。

        各行もtupleであり、元のマトリクスへの可変参照ではない。
        配列形の変更だけを行い、転置や座標空間・UI単位の変換は行わない。

        Returns:
            tuple[tuple[float, float, float, float], ...]: 行優先の4行。
        """
        values = tuple(_SCALED(self, 1.0))
        return (values[0:4], values[4:8], values[8:12], values[12:16])

    @property
    def translate(self):
        """Translate 成分(番号12〜14)を取得または設定する。

        取得値は複製。設定時は3成分を受け取り、マトリクスを分解せずに番号12〜14へ直接
        書き込むため、ゼロスケールなど分解できないマトリクスにも使える。
        ``matrix.translate.x = value`` は複製だけを変更する。マトリクスの更新には
        ``matrix.translate = value`` を使う。

        Returns:
            Translate: マトリクスの平行移動成分。
        """
        return self._translate()

    @translate.setter
    def translate(self, value):
        """番号12〜14へ平行移動を直接書き込む。

        Args:
            value (Iterable[float]): 新しい平行移動。3成分。

        Returns:
            None: 値を返さない。
        """
        x, y, z = _xyz(value)
        _SET(self, 12, x)
        _SET(self, 13, y)
        _SET(self, 14, z)

    @property
    def scale(self):
        """Scale 成分を取得または設定する。

        om2.MTransformationMatrix と同じ規約で分解する(行列式が負なら Z が負)。
        設定時は XYZ の3成分を受け取り、回転・シアー・平行移動を保って再合成する。
        取得・設定とも、分解できない場合は ValueError。

        Returns:
            Scale: 分解したスケール成分。
        """
        return _vector_of(Scale, self._checked_transformation().scale(_K_TRANSFORM))

    @scale.setter
    def scale(self, value):
        """スケール成分を置き換えて再合成する。

        Args:
            value (Iterable[float]): 新しいスケール。3成分。

        Returns:
            None: 値を返さない。
        """
        self._recompose(scale=value)

    @property
    def shear(self):
        """Shear 成分(XY、XZ、YZ)を取得または設定する。

        設定時は3成分を受け取り、回転・スケール・平行移動を保って再合成する。
        取得・設定とも、分解できない場合は ValueError。

        Returns:
            Shear: 分解したシアー成分。
        """
        return _vector_of(Shear, self._checked_transformation().shear(_K_TRANSFORM))

    @shear.setter
    def shear(self, value):
        """シアー成分を置き換えて再合成する。

        Args:
            value (Iterable[float]): 新しいシアー。3成分。

        Returns:
            None: 値を返さない。
        """
        self._recompose(shear=value)

    @property
    def quaternion(self):
        """回転成分を Quaternion として取得する。

        Returns:
            Quaternion: 分解した回転値。

        Raises:
            ValueError: 分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        return Quaternion._wrap(self._checked_transformation().rotation(asQuaternion=True))

    @property
    def euler(self):
        """回転成分を XYZ 順序の EulerRotate として取得する。

        om2.MTransformationMatrix.rotation() と同じ角度(中間軸が 90 度を超える
        等価な解になることがある)。

        Returns:
            EulerRotate: 分解した回転値(ラジアン)。

        Raises:
            ValueError: 分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        return EulerRotate._wrap(self._checked_transformation().rotation())

    @property
    def rotate(self):
        """回転成分を XYZ 順序の EulerRotate として取得または設定する。

        設定時は XYZ 順のラジアン3成分、回転順序を
        反映する EulerRotate、または Quaternion を受け取り、スケール・シアー・
        平行移動を保って再合成する。取得・設定とも、分解できない場合は ValueError。
        取得したEulerRotateの編集は元のマトリクスへ反映しない。更新時はrotateへ代入する。

        Returns:
            EulerRotate: 分解した回転値(ラジアン)。
        """
        return EulerRotate._wrap(self._checked_transformation().rotation())

    @rotate.setter
    def rotate(self, value):
        """回転成分を置き換えて再合成する。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 新しい回転。

        Returns:
            None: 値を返さない。
        """
        self._recompose(rotate=value)

    def decompose(self):
        """Mayaの規約でマトリクスを分解し、独立したTRS・シアー値を取得する。

        一つのMTransformationMatrixで回転・スケール・シアーを分解し、平行移動は
        元Matrixの番号12〜14から取得する。戻り値は独立した数学値として作る。
        元のピボットやEulerの回転周期・元の負スケール軸を復元する操作ではない。
        分解規約はOpenMayaに従い、UI単位への換算は行わない。

        Returns:
            dict[str, object]: translate(Translate)、euler(EulerRotate、XYZ順序・rad)、
                quaternion(Quaternion)、scale(Scale)、shear(Shear)を持つ新しい辞書。
                各値を自身更新しても元のMatrixは変化しない。

        Raises:
            ValueError: ゼロのスケール軸など、実装の分解前検査で拒否した場合。
        """
        tm = self._checked_transformation()
        euler = tm.rotation()
        return {
            "translate": self._translate(),
            "quaternion": Quaternion._wrap(tm.rotation(asQuaternion=True)),
            "euler": EulerRotate._wrap(euler),
            "scale": _vector_of(Scale, tm.scale(_K_TRANSFORM)),
            "shear": _vector_of(Shear, tm.shear(_K_TRANSFORM)),
        }

    def isEquivalent(self, other, tolerance=1e-10):
        """許容誤差付きでほぼ等しいか判定する。

        ``==`` は完全一致なので、浮動小数点誤差を許容した比較にはこちらを使う。

        Args:
            other (om2.MMatrix | Iterable[float]): 比較対象。16要素や4行4列も受け付ける。
            tolerance (float): 各成分の差の許容誤差。

        Returns:
            bool: 全16成分の差が tolerance 以内なら True。
        """
        if not isinstance(other, _MMatrix):
            other = Matrix(other)
        return _MMatrix.isEquivalent(self, other, tolerance)

    def inverse(self):
        """OpenMayaの特異性判定を通過したマトリクスから、独立した逆マトリクスを作る。

        isSingular()で検査してからMMatrix.inverse()を呼ぶ。
        独自の厳密な行列式ゼロ比較や、UI単位に応じた閾値変更は行わない。
        自身は変更せず、ノードの親子関係やシーンの逆変換を編集するものではない。

        Returns:
            Matrix: 自身と同じクラスの新しい逆マトリクス。追加Python状態はコピーしない。

        Raises:
            ValueError: OpenMayaのisSingular()がTrueと判定した場合。
        """
        if self.isSingular():
            raise ValueError("Matrix is singular and cannot be inverted")
        return type(self)._wrap(_MMatrix.inverse(self))

    def transpose(self):
        """転置したマトリクスを返す。

        Returns:
            Matrix: 自身と同じクラスの転置マトリクス。
        """
        return type(self)._wrap(_MMatrix.transpose(self))

    def transformPoint(self, value):
        """行ベクトル規約でXYZ位置を変換し、平行移動を含む独立したTranslateを返す。

        入力のXYZをw=1として扱い、MPointの元のwは無視する。
        計算はom2.MPoint(x, y, z, 1.0) * matrixのXYZ相当で、射影除算は行わない。
        自身と入力値は変更せず、ノードの移動やMaya座標空間の照会も行わない。
        位置とマトリクスの平行移動には同じ距離単位を使い、UI単位への換算はしない。

        Args:
            value (om2.MVector | om2.MPoint | Iterable[float]): 変換元のXYZ。MPointのwは使用しない。

        Returns:
            Translate: 新しい位置値。入力の派生型や追加Python状態は引き継がない。
        """
        result = _zero(Translate)
        if isinstance(value, _MVector):
            _MVector.__iadd__(result, value)
        else:
            x, y, z = _xyz(value)
            result.x = x
            result.y = y
            result.z = z
        _MVector.__imul__(result, self)
        result.x += _GET(self, 12)
        result.y += _GET(self, 13)
        result.z += _GET(self, 14)
        return result

    def transformVector(self, value):
        """行ベクトル規約でXYZ方向を変換し、平行移動を含まない独立したVectorを返す。

        XYZをw=0として扱い、Vector(value) * matrixと同じ方向変換を行う。
        MPointのwは無視する。正規化・法線の逆転置変換・UI単位変換は行わず、
        スケールやシアーによる長さの変化も結果へ含む。自身と入力値は変更しない。

        Args:
            value (om2.MVector | om2.MPoint | Iterable[float]): 変換元のXYZ方向。

        Returns:
            Vector: 新しい方向値。入力の派生型や追加Python状態は引き継がない。
        """
        result = _zero(Vector)
        if isinstance(value, _MVector):
            _MVector.__iadd__(result, value)
        else:
            x, y, z = _xyz(value)
            result.x = x
            result.y = y
            result.z = z
        _MVector.__imul__(result, self)
        return result

    def mirror(self, axis="x", pivot=(0.0, 0.0, 0.0)):
        """マトリクスが表す座標空間の軸に対する「ビヘイビア」ミラーマトリクスを返す。

        平行移動はpivotを中心にaxis成分を反転し、3x3部分の各行はaxis以外の
        2成分を反転する。Maya の ``mirrorJoint -mirrorBehavior`` と同じ規約で、
        軸そのものは反転せず 180 度回転した姿勢になるため、行列式の符号は保存される
        (幾何学的な鏡像とは異なり、対になったノードを同じローカル操作で対称に
        動かせる)。スケール・シアーは変わらない。要素の符号だけを反転するため、
        分解できないマトリクスにも使える。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または従来の0/1/2。
            pivot (Iterable[float]): 平行移動と同じ単位・空間の中心座標。

        Returns:
            Matrix: 呼び出したクラスのミラー後のマトリクス。

        Raises:
            ValueError: axisが不正、またはpivotが有限の3成分でない場合。
        """
        from ..util import mirrorArguments
        axes, center = mirrorArguments(axis, pivot)
        result = type(self)._wrap(self)
        for axis in axes:
            for row in range(3):
                for column in range(3):
                    if column != axis:
                        index = row * 4 + column
                        _SET(result, index, -_GET(result, index))
            _SET(result, 12 + axis, 2 * center[axis] - _GET(result, 12 + axis))
        return result

    def mirrorIt(self, axis="x", pivot=(0.0, 0.0, 0.0)):
        """自身をビヘイビアミラーする。

        Args:
            axis (str | int): mirrorと同じ反転軸。
            pivot (Iterable[float]): 平行移動と同じ単位・空間の中心。

        Returns:
            Matrix: 更新した自身。
        """
        result = self.mirror(axis, pivot)
        for index in range(16):
            _SET(self, index, _GET(result, index))
        return self

    def adjoint(self, *args):
        """Maya標準の随伴マトリクスを、新しいMatrixとして返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Matrix: 演算結果を保持する新しいmlib値。
        """
        return Matrix._wrap(_MMatrix.adjoint(self, *args))

    def homogenize(self, *args):
        """同次座標を正規化した、新しいMatrixを返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Matrix: 演算結果を保持する新しいmlib値。
        """
        return Matrix._wrap(_MMatrix.homogenize(self, *args))

    @classmethod
    def _wrap(cls, value):
        """om2 のマトリクスを複製した cls のインスタンスを返す。

        Python の ``__new__`` / ``__init__`` を通さない(利用者の派生クラスの
        ``__init__`` も呼ばない)。:func:`_assign` で写すため、符号付きゼロ・inf・NaN を
        含めて値は value と一致し、om2 のコピーコンストラクタ(多重定義の解決が遅い)より速い。

        Args:
            value (om2.MMatrix | om2.MFloatMatrix): 複製元。

        Returns:
            Matrix: cls の新しいインスタンス。
        """
        result = _MMatrix.__new__(cls)
        if isinstance(value, _MMatrix):
            _MMatrix.__init__(result)
            _MMatrix.__imul__(result, -0.0)
            _MMatrix.__iadd__(result, value)
        else:
            _MMatrix.__init__(result, value)
        return result

    def _checked_transformation(self):
        """分解できることを確かめてから MTransformationMatrix を作る。

        om2 はゼロスケールのマトリクスも黙って分解するため、3x3 の行列式が 0 なら
        ValueError にする。

        Returns:
            om2.MTransformationMatrix: 自身から作ったマトリクス。

        Raises:
            ValueError: いずれかのスケール軸がゼロなど、3x3 部分が特異な場合。
        """
        if self.det3x3() == 0.0:
            raise ValueError("Cannot decompose a matrix with a zero scale axis")
        return _MTransformationMatrix(self)

    def _translate(self):
        """番号12〜14を Translate として返す。

        Returns:
            Translate: 平行移動成分の新しいインスタンス。
        """
        result = _zero(Translate)
        result.x = _GET(self, 12)
        result.y = _GET(self, 13)
        result.z = _GET(self, 14)
        return result

    def _recompose(self, rotate=None, scale=None, shear=None):
        """分解値の一部を置き換えて、自身の値を組み立て直す。

        入力の形と分解を先に検査する。要素代入で失敗した場合、先行変更は自動では戻さない。

        Args:
            rotate (Iterable[float] | EulerRotate | Quaternion | None): 新しい回転。None は現在の値。
            scale (Iterable[float] | None): 新しいスケール。None は現在の値。
            shear (Iterable[float] | None): 新しいシアー。None は現在の値。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 現在のマトリクスを分解できない場合、または入力が不正な場合。
        """
        tm = self._checked_transformation()
        parts = _components(
            (_GET(self, 12), _GET(self, 13), _GET(self, 14)),
            tm.rotation(asQuaternion=True) if rotate is None else rotate,
            tm.scale(_K_TRANSFORM) if scale is None else scale,
            tm.shear(_K_TRANSFORM) if shear is None else shear,
        )
        self.setToIdentity()
        _compose_into(self, *parts)


def _flat_index(index):
    """(行, 列) を平坦な番号へ変換する。

    Args:
        index (tuple[int, int]): 行と列。それぞれ -4〜3。

    Returns:
        int: 0〜15 の番号。

    Raises:
        TypeError: 行・列が整数として扱えない場合。
        IndexError: 範囲外、または2要素でない場合。
    """
    try:
        row, column = index
    except ValueError:
        raise IndexError("Matrix index must be (row, column)") from None
    try:
        row, column = _as_index(row), _as_index(column)
    except TypeError:
        raise TypeError("Matrix row and column must be integers") from None
    if row < 0:
        row += 4
    if column < 0:
        column += 4
    if not (0 <= row < 4 and 0 <= column < 4):
        raise IndexError("Matrix index out of range")
    return row * 4 + column
