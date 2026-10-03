"""版番号・ログ通知・進捗表示などの共通機能を公開する。"""

from .version import Version
from .logger import debug, error, info, get_logger, raise_with_notify, warning
from .naming import legalizeName
from .progress import progressBar

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
]

from .curveFit import CurveFit
from .dampedSpring import DampedSpring

__all__ += ["CurveFit", "DampedSpring"]

from . import units
__all__ += ["units"]


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('legalize_name', 'progress_bar'):
    globals().pop(_obsolete_name, None)
