"""版番号・ログ通知・進捗表示などの共通機能を公開する。"""

from . import units
from .curveFit import CurveFit
from .dampedSpring import DampedSpring
from .logger import debug, error, info, get_logger, raise_with_notify, warning
from .naming import legalizeName
from .progress import progressBar
from .version import Version

__all__ = [
    "Version",
    "debug",
    "error",
    "get_logger",
    "info",
    "legalizeName",
    "progressBar",
    "raise_with_notify",
    "warning",
    "CurveFit",
    "DampedSpring",
    "units",
]

# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('legalize_name', 'progress_bar'):
    globals().pop(_obsolete_name, None)
