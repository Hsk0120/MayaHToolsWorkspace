"""DAG階層とメンバーの所有を扱うMaya dagContainer。"""

from .container import Container
from .transform import Transform


class DagContainer(Transform, Container):
    """Transform操作とContainerの所属・公開操作を持つコンテナ。

    所属・公開操作は :class:`~mlib.nodes.container._ContainerMixin` に定義したものを
    Container と共有する。DAGの子もMaya標準の所属管理に従う。removeMembersは子を階層からも
    外し、removeContainerはメンバーを残して箱を解除する。
    解除時はローカル値が維持されるため、ワールド姿勢は変化する場合がある。

    基底の例外: Maya の dagContainer は transform の派生で container を継承しないが、
    このクラスは所属・公開操作を共有し ``isinstance(x, Container)`` を保つため Container も基底に持つ。
    Maya の継承チェーン上の抽象祖先(entity・containerBase)に対応するクラスは無く、``isinstance`` は
    Maya の継承を表さない。継承の判定は ``isType()`` を使う。
    """
