# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""mlib の数学型と変換演算を公開する。

Vector 系・Quaternion・EulerRotate・Matrix は OpenMaya API 2.0
(``maya.api.OpenMaya``)の MVector / MQuaternion / MEulerRotation / MMatrix を
継承した可変の値型で、そのまま om2 の関数へ渡せる。演算は om2 の意味論に従う。
easing だけは標準ライブラリの math のみを使う純粋な関数群。
"""

from maya.api.OpenMaya import MSpace
from . import easing
from .eulerRotate import EulerRotate
from .matrix import Matrix
from .quaternion import Quaternion
from .scale import Scale
from .shear import Shear
from .translate import Translate
from .vector import Vector

__all__ = ['MSpace', 'EulerRotate', 'Matrix', 'Quaternion', 'Scale', 'Shear', 'Translate', 'Vector', 'easing']
