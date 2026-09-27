"""Maya GUIのscriptJobを明示的に登録・解除する。

importだけでは監視を開始しない。バッチ・再生中の評価用途には使用せず、
所有者が不要になった時点でstop()を呼ぶ。シーンへスクリプトは保存しない。
"""

from .scriptJob import ScriptJob
from .scriptJobs import ScriptJobs

__all__ = ["ScriptJob", "ScriptJobs"]
