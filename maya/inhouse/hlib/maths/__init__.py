"""hlib の数学型と変換演算を公開する。"""

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
