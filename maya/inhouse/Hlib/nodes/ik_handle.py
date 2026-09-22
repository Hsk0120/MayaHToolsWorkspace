"""Maya の IK ハンドルを Transform として扱う。"""

from ..core.registry import node_wrapper
from .transform import Transform


@node_wrapper("ikHandle")
class IkHandle(Transform):
    """極ベクトル拘束の作成を含む Transform 操作に対応する IK ハンドル。"""
