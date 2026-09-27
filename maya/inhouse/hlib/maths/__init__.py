"""hlib の数学型と変換演算を公開する。

Vector 系・Quaternion・EulerRotation・Matrix は OpenMaya API 2.0
(``maya.api.OpenMaya``)の MVector / MQuaternion / MEulerRotation / MMatrix を
継承した可変の値型で、そのまま om2 の関数へ渡せる。演算は om2 の意味論に従う。
easing だけは標準ライブラリの math のみを使う純粋な関数群。
"""

# importlib.reloadは辞書を保持するため、廃止した公開名を明示的に除く。
for _obsolete in ("Translate", "Rotate"):
    globals().pop(_obsolete, None)

from . import easing
from .euler_rotation import EulerRotation
from .matrix import Matrix
from .quaternion import Quaternion
from .scale import Scale
from .shear import Shear
from .translation import Translation
from .vector import Vector

__all__ = [
    "EulerRotation",
    "Matrix",
    "Quaternion",
    "Scale",
    "Shear",
    "Translation",
    "Vector",
    "easing",
]
