# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""マトリクスを介して Transform ノードを操作する。"""

import math
import numbers
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace
from ..core.attributeType import value_reader
from ..core.fastWrite import require_writable
from ..core.nodeEdit import require_editable
from ..decorator import _edit_context, _merge_flags, _pick_alias, _require_bool, nativeUnits, undoChunk, undoTransaction
from ..maths import EulerRotate, Matrix, Quaternion, Scale, Shear, Translate, Vector
from ..maths.eulerRotate import orderIndex
from ..plugs.plug import Plug
from ..util import _angle_unit, _from_radians, _to_radians, _world_space
from ..util import _ArgumentError, _UNSET
from .dagNode import DagNode
from .node import Node, Nodes
from typing import Any, Iterable, Sequence
from mlib.components.component import Component
from mlib.components.component import Components
from mlib.nodes.constraint import Constraint
from mlib.nodes.shadingEngine import ShadingEngine
from mlib.nodes.shape import Shape

_TRANSFORM_SOURCE_CONSTRAINTS: frozenset
_TRANSFORM_ATTRIBUTES: dict
_NEAR_ZERO_AXIS: float

def _transform_attribute(name: str) -> om2.MObject:
    """transform ノード型のアトリビュートの MObject を取得する(初回だけ問い合わせて保持する)。

    joint など transform の派生型も同じアトリビュートの MObject を共有するため、
    ``om2.MPlug(node, attribute)`` で名前の検索なしに MPlug を作れる。

    Args:
        name (str): アトリビュートのロング名(``matrix`` / ``worldMatrix`` など)。

    Returns:
        om2.MObject: transform ノード型のアトリビュート。
    """
    ...

def _match_scale_signs(quaternion: om2.MQuaternion, scale: Iterable[float], shear: Iterable[float], references: Iterable[Iterable[float]]) -> tuple:
    """分解したスケールの符号の組み合わせを、基準のスケールの符号へ揃える。

    2軸のスケールの符号を同時に反転し、残りの軸まわりの 180 度回転で補償しても
    マトリクスは変わらない(D を2軸が -1 の対角マトリクスとして S·Sh·R = (S·D)·(D·Sh·D)·(D·R))。
    行列式の符号は変えられないため、references を先頭から順に調べ、反転が必要な軸が
    0 個または 2 個(行列式の符号と合う)の最初の基準に揃える。どの基準とも合わない
    (奇数個の軸が違う)場合は入力(om2 の規約)のまま返す。

    Args:
        quaternion (om2.MQuaternion): 分解した回転。
        scale (Iterable[float]): 分解したスケール。
        shear (Iterable[float]): 分解したシアー(XY、XZ、YZ)。
        references (Iterable[Iterable[float]]): 符号を合わせる基準のスケールの候補。
            優先する順に並べる(setScale で要求した値、現在の scale チャンネル値など)。

    Returns:
        tuple: (quaternion, scale, shear)。scale と shear は3要素の tuple。
    """
    ...

def _closest_euler(quaternion: om2.MQuaternion, reference: om2.MEulerRotation) -> om2.MEulerRotation:
    """回転を reference の回転順序で表し、reference に最も近い等価な解を返す。

    Args:
        quaternion (om2.MQuaternion): 変換する回転。
        reference (om2.MEulerRotation): 基準の回転(回転順序と解の選択に使う)。

    Returns:
        om2.MEulerRotation: reference と同じ回転順序の、reference に最も近い解
        (``MEulerRotation.closestSolution``。360 度の周期と、中間軸を反転した別解を考慮する)。
    """
    ...


class Transform(DagNode):
    """Transformのノード参照とDAGパスを保持し、変換値を照会・設定する。

    マトリクス・TRS・ピボットを扱い、Shapeの頂点やCVの編集とは区別する。
    距離はcm、角度はradを基本とし、MayaのUI単位とは独立する。
    ローカル側の基準は各メソッドで異なる。
    通常の変更はmaya.cmdsでUndoに記録し、対応するfastはOpenMayaで直接更新する。
    safeを持つsetterは書けない成分を残すが、目標値との一致や全体の巻き戻しは保証しない。
    """
    def addConstraint(self, sources: Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug | Iterable, type: str = ..., maintainOffset: bool = ..., *, typ: str = ..., mo: bool = ..., createCache: Sequence[float] = ..., cc: Sequence[float] = ..., decompRotationToChild: bool = ..., dr: bool = ..., deleteCache: bool = ..., dc: bool = ..., edit: bool = ..., e: bool = ..., layer: str = ..., l: str = ..., name: str = ..., n: str = ..., query: bool = ..., q: bool = ..., remove: bool = ..., rm: bool = ..., skipRotate: str | Sequence[str] = ..., sr: str | Sequence[str] = ..., skipTranslate: str | Sequence[str] = ..., st: str | Sequence[str] = ..., targetList: bool = ..., tl: bool = ..., weight: float = ..., w: float = ..., weightAliasList: bool = ..., wal: bool = ..., offset: Sequence[float] = ..., o: Sequence[float] = ..., skip: str | Sequence[str] = ..., sk: str | Sequence[str] = ..., scaleCompensate: bool = ..., sc: bool = ..., aimVector: Sequence[float] = ..., aim: Sequence[float] = ..., upVector: Sequence[float] = ..., u: Sequence[float] = ..., worldUpObject: Node | Plug | Component | str | om2.MObject | om2.MDagPath | om2.MPlug = ..., wuo: Node | Plug | Component | str | om2.MObject | om2.MDagPath | om2.MPlug = ..., worldUpType: str = ..., wut: str = ..., worldUpVector: Sequence[float] = ..., wu: Sequence[float] = ..., **kwargs) -> Constraint:
        """指定したターゲットで自身を制御するコンストレイントを作成する。

        選択状態で対象を補完しない。通常のcmds更新をUndo有効時にまとめ、途中失敗の変更は戻さない。

        Args:
            sources (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug | Iterable):
                単一参照またはその列。Plug/MPlugは所有ノード、Component/Componentsは所有Shapeへ解決する。
                アトリビュート・コンポーネント文字列も同様。parent/point/orient/scale/aim/poleVectorは
                Transform(Joint・IkHandleを含む)に解決される入力だけを受け付ける。
            type (str): parent、point、orient、scale、aim、poleVector、
                geometry、normal、tangent、pointOnPoly。Constraint接尾辞付きも可。既定parent。
            maintainOffset (bool): 既定False。parent/point/orient/scale/aimだけへ渡すMayaのmaintainOffset。
            createCache (Sequence[float]): MayaのcreateCacheフラグ。開始・終了時刻の2値をUI時間単位で指定する。
            cc (Sequence[float]): createCacheの別名。同時指定は不可。
            decompRotationToChild (bool): MayaのdecompRotationToChildフラグ。省略時はMayaの既定に従う。
            dr (bool): decompRotationToChildの別名。同時指定は不可。
            deleteCache (bool): MayaのdeleteCacheフラグ。省略時はMayaの既定に従う。
            dc (bool): deleteCacheの別名。同時指定は不可。
            edit (bool): Trueは作成専用のこのメソッドでは拒否する。
            e (bool): editの別名。同時指定は不可。
            layer (str): Mayaのlayerフラグ。省略時はMayaの既定に従う。
            l (str): layerの別名。同時指定は不可。
            name (str): Mayaのnameフラグ。省略時はMayaの既定に従う。
            n (str): nameの別名。同時指定は不可。
            query (bool): Trueは作成専用のこのメソッドでは拒否する。
            q (bool): queryの別名。同時指定は不可。
            remove (bool): Mayaのremoveフラグ。省略時はMayaの既定に従う。
            rm (bool): removeの別名。同時指定は不可。
            skipRotate (str | Sequence[str]): MayaのskipRotateフラグ。省略時はMayaの既定に従う。
            sr (str | Sequence[str]): skipRotateの別名。同時指定は不可。
            skipTranslate (str | Sequence[str]): MayaのskipTranslateフラグ。省略時はMayaの既定に従う。
            st (str | Sequence[str]): skipTranslateの別名。同時指定は不可。
            targetList (bool): MayaのtargetListフラグ。省略時はMayaの既定に従う。
            tl (bool): targetListの別名。同時指定は不可。
            weight (float): Mayaのweightフラグ。省略時はMayaの既定に従う。
            w (float): weightの別名。同時指定は不可。
            weightAliasList (bool): MayaのweightAliasListフラグ。省略時はMayaの既定に従う。
            wal (bool): weightAliasListの別名。同時指定は不可。
            offset (Sequence[float]): Mayaのoffsetフラグ。(x, y, z)の3値を指定する。
            o (Sequence[float]): offsetの別名。同時指定は不可。
            skip (str | Sequence[str]): Mayaのskipフラグ。省略時はMayaの既定に従う。
            sk (str | Sequence[str]): skipの別名。同時指定は不可。
            scaleCompensate (bool): MayaのscaleCompensateフラグ。省略時はMayaの既定に従う。
            sc (bool): scaleCompensateの別名。同時指定は不可。
            aimVector (Sequence[float]): MayaのaimVectorフラグ。(x, y, z)の3値を指定する。
            aim (Sequence[float]): aimVectorの別名。同時指定は不可。
            upVector (Sequence[float]): MayaのupVectorフラグ。(x, y, z)の3値を指定する。
            u (Sequence[float]): upVectorの別名。同時指定は不可。
            worldUpObject (Node | Plug | Component | str | om2.MObject | om2.MDagPath | om2.MPlug): ワールドアップの参照ノード。Plug/Componentは所有ノードへ解決する。Componentsは不可。
            wuo (Node | Plug | Component | str | om2.MObject | om2.MDagPath | om2.MPlug): worldUpObjectの別名。同時指定は不可。
            worldUpType (str): MayaのworldUpTypeフラグ。省略時はMayaの既定に従う。
            wut (str): worldUpTypeの別名。同時指定は不可。
            worldUpVector (Sequence[float]): MayaのworldUpVectorフラグ。(x, y, z)の3値を指定する。
            wu (Sequence[float]): worldUpVectorの別名。同時指定は不可。
            **kwargs: 選んだMaya constraintコマンドへ渡す追加の作成フラグ。
            typ (str): typeの別名。同時指定は不可。
            mo (bool): maintainOffsetの別名。同時指定は不可。

        Returns:
            Constraint: 対応する具象ラッパー。同じ種類が既存なら Maya の規則で
                ターゲットが追加される場合がある。

        Raises:
            ValueError: 未対応の型・空のソース、query/edit=True、または無効なworldUpObjectの場合。
            TypeError: 型名・参照型・長短フラグが不正、または上記6型のターゲットがTransformでない場合。
            RuntimeError: ノードが無効、ターゲットの名前を解決できない(存在しない、または
                複数のノードに一致する)場合、または Maya が作成を拒否した場合。
            DeletedAttributeError: 削除済みアトリビュートのPlug/MPlugの場合。ValueErrorとRuntimeErrorの派生。

        Note:
            PoleVectorはRP IKハンドル、Geometry/Normal/PointOnPolyは対応形状、TangentはNURBSカーブが必要。
        """
        ...
    def deleteConstraints(self, *, fast: bool = ...) -> list[str]:
        """自身に作用するコンストレイントと、その入力側のpairBlendを削除する。

        pairBlend・unitConversionだけを上流へ辿り、unitConversionは残す。
        ターゲットTransform・animCurveは削除せず、姿勢維持・ベイク・入力の再接続はしない。
        対象外への共有出力と削除対象の参照・ロックを先に検査する。

        Args:
            fast (bool): Falseはcmds.deleteをUndo有効時にまとめる。
                Trueは入力を外してOM2で削除し、Undoへ記録しない。設定は変えず、
                後続失敗で切断や削除を自動では戻さない。

        Returns:
            list[str]: 削除前の完全名をソートしたリスト。対象がなければ空リスト。

        Raises:
            TypeError: fastがbool以外の場合。
            RuntimeError: 無効参照、共有出力、参照・ロックされた削除対象、またはMayaの処理失敗。
        """
        ...
    def mfn(self) -> om2.MFnTransform:
        """この Transform で最も具体的な om2 function set を取得する。

        呼び出すたびに新しい ``om2.MFnTransform`` を保持する DAG パスから作る。
        Joint など派生型もこの function set を使う。

        Returns:
            om2.MFnTransform: この Transform の function set。

        Raises:
            RuntimeError: 保持していた DAG パスが無効な場合。
        """
        ...
    def resetAttrs(self, attributes: str | Iterable[str] | None = ..., *, fast: bool = ...) -> list[Plug]:
        """指定アトリビュートを定義上の既定値へ戻す。省略時は translate・rotate・scale・shear。

        :meth:`Node.resetAttrs` の override。省略時の既定(キー設定可能な全アトリビュート)を
        TRS とシアーの 4 チャンネルに置き換える。明示指定時の扱いは Node と同じ。

        Args:
            attributes (str | Iterable[str] | None): tx/translateX/translateなど。
                省略時はtranslate・rotate・scale・shear。ロック・入力接続のある子は除外し、除外のある
                コンパウンドアトリビュートだけ書ける子の Plug を返す。明示指定時は除外せずエラーを送出する。独自数値アトリビュートも可。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            list[Plug]: リセットしたアトリビュート(指定順)。

        Raises:
            TypeError: 名前が文字列でない、fastがbool以外、または既定値を扱えない型の場合。
            AttributeError: 指定アトリビュートが存在しない場合。
            RuntimeError: 明示指定したアトリビュートがロックや入力接続などで変更できない場合。

        Note:
            フリーズではなく値を戻す操作なので姿勢は変わる。jointOrient・ピボット・
            offsetParentMatrixは明示指定しない限り変更しない。ロック解除・接続切断は
            行わない。途中の失敗は例外とし、完了済みの変更は通常Undoで戻せる。
        """
        ...
    def scaleGeometry(self, scale: float | Iterable[float], worldSpace: bool = ..., pivot: Iterable[float] = ..., indices: Iterable[int | tuple[int, int]] | None = ..., *, fast: bool = ...) -> Transform:
        """直下の非中間Shapeの頂点・CVを拡縮する。Transformのマトリクスは変更しない。

        Shapeごとに検証・更新するため、後続Shapeの拒否でも先行変更は残る。
        共有形状は全インスタンスに影響する。

        Args:
            scale (float | Iterable[float]): 一様倍率、またはXYZ倍率。
            worldSpace (bool): Trueはワールド空間、Falseは各Shapeのオブジェクト空間。
            pivot (Iterable[float]): 指定空間の拡縮中心。cm。既定は原点。
            indices (Iterable[int | tuple[int, int]] | None): 各Shapeに共通の頂点/CV番号。
                Noneは全要素。サーフェスは(U, V)の組。
            fast (bool): Trueは履歴なしメッシュ・非周期カーブをOM2で更新(Undoなし)。
                Falseは通常更新をUndo有効時にまとめる。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fast・番号の型が不正な場合。
            ValueError: 倍率・中心・空間が不正な場合。
            IndexError: 対象番号が範囲外の場合。
            RuntimeError: Mayaが変更を拒否した場合。
            NotImplementedError: 未対応Shape、またはfastの編集条件に対応しない場合。
        """
        ...
    def getPivot(self, worldSpace: bool = ..., *, kind: str = ...) -> Translate:
        """回転またはスケールピボットの位置をcm単位で取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはxformのobjectSpaceに相当する
                MSpace.kPreTransform。
            kind (str): rotateは回転、scaleはスケールピボット。

        Returns:
            Translate: ノードと独立した新しい位置の値。UI距離単位によらずcm。

        Raises:
            ValueError: kindがrotate/scaleでない場合。
        """
        ...
    def setPivot(self, value: Iterable[float], worldSpace: bool = ..., *, kind: str = ..., preserve: bool = ..., fast: bool = ...) -> Transform:
        """指定した種類のピボットを変更する。既定ではノードの姿勢を保つ。

        Args:
            value (Iterable[float]): 新しいピボット位置のXYZ3成分。UI距離単位によらずcm。
            worldSpace (bool): Trueはワールド空間、FalseはxformのobjectSpaceに相当する
                MSpace.kPreTransform。
            kind (str): rotate/scale/both。bothは両方を同じ位置へ設定する。
            preserve (bool): Trueはピボット補償値を調整してマトリクスを保つ。
                Falseは補償せず、姿勢が変わる場合がある。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: preserveがboolでない、または対象がJointの場合。
            ValueError: kind、座標の要素数・有限値が不正な場合。
            RuntimeError: ノードが無効、変更するピボットまたは補償値(preserve=True時)の
                成分がロック・入力接続されている場合、または Maya が設定を拒否した場合。
                ロックの検査は通常・fastとも更新前に行い、何も変更しない。

        Note:
            Jointは独立したピボットの変更をサポートしないため、更新前に拒否する。
        """
        ...
    def centerPivot(self, *, fast: bool = ...) -> Transform:
        """バウンディングボックス中心へ回転・スケールピボットを移す。

        通常はxform(centerPivots=True)、fastはAPIで得た中心をsetPivotへ渡す。
        preserve=Trueでピボット補償値を調整し、コンポーネント選択は使わない。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fastがbool以外、またはfastで対象がJointの場合。
            RuntimeError: 無効参照の場合、ピボットまたは補償値の成分がロック・入力接続
                されている場合(通常・fastとも更新前に検査する)、またはMayaが更新を拒否した場合。
        """
        ...
    def getChildren(self, shapes: bool = ..., intermediates: bool = ..., *, allDescendents: bool = ..., order: str = ..., leaves: bool = ..., includeSelf: bool = ..., underWorld: bool = ...) -> list[DagNode]:
        """指定条件に合う直接の子、または子孫を取得する。

        Args:
            shapes (bool): TrueはShapeも含める。既定FalseはTransformのみ。
            intermediates (bool): Trueは中間オブジェクトも含める。
            allDescendents (bool): Trueは子孫全体。既定は直接の子だけ。
            order (str): depthFirstまたはbreadthFirst。
            leaves (bool): 子Transformを持たないTransformだけを再帰取得する。
            includeSelf (bool): 自身も対象へ含める。葉の自身も取得する場合はTrue。
            underWorld (bool): Shape下のアンダーワールドも探索する。

        Returns:
            list[DagNode]: DAGの子順に並んだノード。該当なしは空リスト。
        """
        ...
    def getUnusedIntermediateShapes(self) -> list[Shape]:
        """直下から削除可能な未使用中間Shapeを取得する。

        shadingEngineへの標準メンバー接続を除き、出力接続がない中間Shapeを対象とする。
        入力履歴だけが残るShapeも対象。参照・ノードロック・インスタンス・子DAGを持つ
        Shapeは除外する。子Transform以下は検索せず、シーンは変更しない。

        Returns:
            list[Shape]: DAGの子順の削除候補。対象なしは空リスト。

        Raises:
            RuntimeError: 無効なTransform、またはMayaの照会失敗。
        """
        ...
    def deleteUnusedIntermediateShapes(self, *, fast: bool = ...) -> Transform:
        """直下の未使用中間Shapeだけを削除し、自身を返す。

        getUnusedIntermediateShapes()と同じ判定で、使用中・参照・ロック・
        インスタンス等は残す。Transformや上流の履歴ノードは削除しない。
        Maya標準削除を1回のUndoにまとめ、途中の失敗時は巻き戻す。
        通常モードはUndoが有効な状態で使用する。

        Args:
            fast (bool): TrueはOpenMayaでShapeだけを直接削除し、Undoなし。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: 無効なTransform、または削除失敗。
        """
        ...
    def getShapes(self, intermediates: bool = ...) -> list[Shape]:
        """このTransform直下のShapeを取得する。

        Args:
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            list[Shape]: 条件に一致するShapeのリスト。
        """
        ...
    def replaceShapes(self, source: Transform | Shape | str, *, keepSource: bool = ..., worldSpace: bool = ...) -> Transform:
        """自身のShapeを、sourceの中間でないShapeへ置き換えて自身を返す。

        自身の直下の既存Shape(中間Shapeを含む)を削除し、sourceのShapeを ``cmds.parent(shape=True)`` で
        自身の直下へ移す。自身のtranslate・rotate・scale・pivot・接続・子Transformは変更しない。
        移したShapeは ``<自身の名前>Shape``、2個目以降は ``<自身の名前>Shape<番号>`` へ改名する。
        コントローラーの形状差し替えを想定した操作で、全体を1回のUndoにまとめ、途中で失敗した場合は
        巻き戻す。

        Args:
            source (Transform | Shape | str): 形状の取得元。Transformは直下の中間でないShape全部、
                Shapeはそれ1つを使う。
            keepSource (bool): Trueならsourceを複製して使い、元のノードを変更しない。Falseはsourceの
                Shapeを移動し、Shapeが無くなり子も残らない取得元のTransformを削除する。
            worldSpace (bool): Trueは取得元のTransformのワールド変換を形状へ焼き込み、ワールド空間での
                見た目を保つ。False(既定)はShapeのローカル座標をそのまま使う(``parent -relative -shape``)。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: keepSource・worldSpaceがbool以外、またはsourceがTransform・Shapeでない場合。
            ValueError: sourceが自身・自身のShape・中間Shapeの場合、または使えるShapeが無い場合。
            RuntimeError: 自身・sourceが無効、またはロック・参照等でMayaが変更を拒否した場合。
        """
        ...
    def getShape(self, index: int = ..., intermediates: bool = ...) -> Shape | None:
        """指定位置のShapeを取得する。

        Args:
            index (int): Shapeの番号。既定0。
            intermediates (bool): ``True`` の場合は中間Shapeも含める。

        Returns:
            Shape | None: 指定位置のShape。範囲外ではNone。
        """
        ...
    def getTransform(self) -> Transform:
        """Transform自身を取得する。

        Returns:
            Transform: 自身。
        """
        ...
    def setParent(self, parent: Node | str | om2.MObject | om2.MDagPath | None = ..., relative: bool = ..., add: bool = ..., *, fast: bool = ...) -> Transform:
        """Transformの親を変更する。

        Args:
            parent (Node | str | om2.MObject | om2.MDagPath | None): 新しい親。None はワールド直下。
                ``Node(parent)`` で解決できる型(Plug・Component は所有ノード)を受け付ける。
            relative (bool): True は親変更前のローカル変換を保持する。既定 False は Maya の既定動作
                (ワールド姿勢を保つ)。
            add (bool): True は既存の親を維持して追加の親を設定する。parent が None の場合は渡されない。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。Joint・インスタンス・親の追加は未対応
                (NotImplementedError)。通常経路の Joint は cmds.parent に従い、relative=False の
                ときだけ親 joint の scale を inverseScale へ接続する(relative=True では接続しない。
                Maya の仕様)。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fastがbool以外、または fast で parent が Transform 以外の場合。
            RuntimeError: 自身が無効、または fast でロック・参照・循環により変更できない場合。
            NotImplementedError: fast で Joint・インスタンス・add=True を指定した場合。
        """
        ...
    def matchTransform(self, target: Transform | str | om2.MObject | om2.MDagPath, position: bool = ..., rotation: bool = ..., scale: bool = ..., pivots: bool = ...) -> Transform:
        """自身の変換を指定Transformへ合わせる。選択状態は使用しない。

        maya.cmds.matchTransformと同じ空間・joint・ピボット処理を使用し、Undo有効時に
        一つのチャンクへ記録する。fast引数は持たない。
        shearの一致やマトリクス全体のコピーは保証しない。

        Args:
            target (Transform | str | om2.MObject | om2.MDagPath): 合わせ先のTransformまたはjoint。
                mlib.nodes.Node._resolve_input が受け付ける型(Plug は所有ノード)を指定できる。
            position (bool): 位置を合わせる。
            rotation (bool): 回転を合わせる。
            scale (bool): スケールを合わせる。
            pivots (bool): 回転・スケールピボットも合わせる。

        Returns:
            Transform: 自身。全フラグFalseなら何も変更しない。

        Raises:
            TypeError: targetがTransformではない場合。
            RuntimeError: ノードが無効、またはMayaが変更を拒否した場合。
            DeletedAttributeError: targetに、アトリビュートが削除済みの Plug / MPlug を渡した場合
                (ValueError と RuntimeError の両方の派生)。
        """
        ...
    def mirrorTransform(self, axis: str | int = ..., worldSpace: bool = ..., pivot: Iterable[float] = ..., *, fast: bool = ...) -> Transform:
        """位置と向きを指定空間でビヘイビアミラーする。

        Matrix.mirrorと同じ回転規約で、負スケールによる形状反転ではない。
        Shapeの頂点・CVは編集しない。子孫は通常の親変換として追従する。
        指定空間のスケール・シアーを保つが、親に非一様スケールがある場合は
        ローカルのスケール・シアーが変わる場合がある。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または0/1/2。xはYZ平面。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            pivot (Iterable[float]): 指定空間の中心。内部距離単位cm。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 入力不正、特異な親マトリクス、未対応のピボット/rotateAxisの場合。
            RuntimeError: ロックや入力接続で更新できない場合。

        Note:
            setMatrix() と同じ制約があり、非ゼロのピボット・
            TransformのrotateAxisは更新前に拒否する。
        """
        ...
    def getShadingEngines(self) -> list[ShadingEngine]:
        """直下の非中間Shapeで使用中のセット。インスタンス経路を保持。

        Returns:
            list[ShadingEngine]: 直下の非中間Shapeで使用中のセット。インスタンス経路を保持。
        """
        ...
    def getMatrix(self, worldSpace: bool = ..., p: bool = ..., inv: bool = ...) -> Matrix:
        """指定空間の評価済みマトリクスを取得する。

        p=Falseのローカル値は ``matrix`` アトリビュート、ワールド値は保持パスの
        inclusiveMatrixを使う。offsetParentMatrixはローカル値に含まれず、ワールド値に含まれる。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            p (bool): Trueは親側のマトリクス。worldSpace=Trueは保持パスのexclusiveMatrix、
                Falseは親パスのinclusiveMatrix * exclusiveMatrixInverseで求める。
            inv (bool): Trueは選んだマトリクスの逆マトリクス。

        Returns:
            Matrix: 呼出し時点のマトリクスの独立した複製。

        Raises:
            RuntimeError: ノードまたは保持するDAGパスが無効な場合。
        """
        ...
    def setMatrix(self, matrix: Matrix | Sequence[Any], worldSpace: bool = ..., safe: bool = ..., get: bool = ..., *, fast: bool = ...) -> Transform | dict[str, Translate | EulerRotate | Scale | Shear]:
        """マトリクスを分解し、translate・rotate・scale・shearのうち値が変わるものへ設定する。

        ピボット・rotateAxis・jointOrient・offsetParentMatrixは変更しない。
        スケールの符号とEulerの等価解は現在のチャンネル値を基準に選ぶ。
        分解した書込み値が現在のチャンネル値(距離cm・角度radの内部値)と完全に一致する
        チャンネルは書き込まない。書き込まないチャンネルはロック・接続されていても例外にせず、
        attributeChangedの通知とUndoの記録も書き込んだチャンネルだけになる(通常・fast・safe共通)。
        safeで書けない成分を残した結果、入力マトリクスと一致しない場合がある。

        Args:
            matrix (Matrix | sequence): 適用するマトリクス。
            worldSpace (bool): Trueはワールドマトリクスを保持パスのexclusiveMatrixInverseで
                ローカルへ変換する。既定Falseは ``matrix`` アトリビュートと同じ空間。
            safe (bool): 書けない成分を保持し、書ける成分だけを更新する。
            get (bool): Trueは書き込まず、ローカルの設定予定値を返す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | dict[str, Translate | EulerRotate | Scale | Shear]: 通常は自身。
                get=Trueはtranslate・rotate・scale・shearの辞書(距離cm・角度rad)。
                safe/fastによらず計算だけ行い、書込み可否やsafe適用後の結果は検証しない。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: マトリクスが不正・分解不能、またはワールド指定時に親側のマトリクスが反転不能の場合。
            RuntimeError: ノードが無効、またはMayaが書込みを拒否した場合。
        """
        ...
    def getTranslate(self, worldSpace: bool = ..., at: int = ...) -> Translate:
        """基準位置を取得する。既定は回転ピボット位置。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseは親側の空間で表す位置。
                getPivotのオブジェクト空間とは異なる。
            at (int): 0以下=親原点、1=translate、2=回転ピボット、
                3=スケールピボット、4以上=マトリクス原点。

        Returns:
            Translate: ノードと独立したcm単位の位置。既定at=2はtranslateチャンネル値ではない。
        """
        ...
    def setTranslate(self, value: Iterable[float], worldSpace: bool = ..., at: int = ..., safe: bool = ..., get: bool = ..., *, fast: bool = ...) -> Transform | list[float]:
        """指定基準の位置へ移動する。ピボットや回転は変更しない。

        at=0以下は位置の絶対設定ではなく、親空間へ変換した入力から現在のtranslateを
        引いた値を設定する。例えば現在2・入力5ならtranslateは3になる。

        Args:
            value (Iterable[float]): cm単位の位置。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            at (int): getTranslateと同じ基準。既定2。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずローカルtranslateの設定予定値だけを返す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: 自身。get=Trueはcm単位の独立したXYZ3成分のlist。
                safe指定時も書込み可否を反映した最終結果の予測ではない。
        """
        ...
    def getRotate(self, worldSpace: bool = ..., *, order: int | str | None = ..., unit: str | None = ...) -> EulerRotate | tuple[float, float, float]:
        """選択空間のマトリクスの回転を Euler 回転として取得する。

        rotateAxisと、JointではjointOrientを含む回転を返す。スケール符号は現在のチャンネルを基準にする。

        回転順序と等価解の選び方は二段の規則に従う。

        * ``order`` を省略、またはノードの rotateOrder と同じ順序を指定した場合は、ノードの
          rotateOrder で表し、Euler の等価解は Transform では現在の rotate チャンネル、
          Joint ではゼロ回転に最も近いものを選ぶ(``setRotate`` の往復でチャンネル値が保たれる)。
        * それ以外の順序を指定した場合は、クォータニオンを ``asEulerRotation().reorder(order)``
          で素直に分解した値(等価解の選択なし)を返す。``order=0`` (xyz)は旧 ``getEuler`` と同じ値。

        Args:
            worldSpace (bool): Trueはワールド、既定Falseはローカルマトリクスの回転。
            order (int | str | None): 戻り値の回転順序。``"xyz"`` などの名前、または om2 の番号
                (``MEulerRotation.kXYZ`` 〜 ``kZYX``、Maya の rotateOrder と同じ 0〜5)。
                None はノードの rotateOrder。
            unit (str | None): None(既定)はEulerRotateを返す。``"deg"`` / ``"rad"``
                (``"degree"`` 等の別名も可)を指定すると、その単位の数値3成分のtupleを返す。

        Returns:
            EulerRotate | tuple[float, float, float]: unit=Noneでは内部がradの独立した回転値。
                ``order`` の回転順序(省略時はノードの rotateOrder)。unit指定時は同じ回転のXYZ成分を
                指定単位で表したtuple。

        Raises:
            TypeError: unit が文字列・None 以外の場合。
            ValueError: worldSpace が bool 以外、order・unit が未対応、またはマトリクスを分解できない場合。
                いずれかのスケール軸の長さが 1e-10 以下(Maya は scale 0 を 1e-12 として評価する)の
                ときも含む。
        """
        ...
    def setRotate(self, value: Iterable[float] | EulerRotate | Quaternion, worldSpace: bool = ..., safe: bool = ..., get: bool = ..., *, unit: str = ..., fast: bool = ...) -> Transform | list[float]:
        """選択空間の回転を設定する。書込むrotateは現在値に最も近い等価解を使う。

        3成分はノードのrotateOrderで解釈し、EulerRotateは値自身の回転順序を使う。
        rotateAxisとJointのjointOrientを保ち、マトリクス経由でチャンネル値を計算する。
        書き込むのはrotateチャンネルだけで、translate・scale・shearは書き込まない
        (ロック・接続されていても例外にせず、通知・Undoの記録もrotateだけ。通常・fast・safe共通)。
        ピボットが0でない場合は、cmds.setAttrでrotateを設定したときと同じくピボットの周りに回る。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 回転値。EulerRotate/Quaternionは
                対応するOpenMaya基底型も受理する。書込みはノードのrotateOrderに揃える。
            worldSpace (bool): Trueはワールド、既定Falseはローカルマトリクスの回転。
            safe (bool): 書けない成分を保持する。目標回転との一致は保証しない。
            get (bool): Trueは書き込まず、ローカルrotateの設定予定値を返す。
            unit (str): 数値3成分とget=Trueの戻り値の角度の単位。既定 ``"deg"`` は度、``"rad"`` は
                ラジアン(``"degree"`` / ``"radians"`` 等の別名も可)。EulerRotate/Quaternionは自身の
                単位(rad)を持つため、unitに関係なく換算しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: 通常は自身。get=Trueはunitの単位(既定は度)の独立したXYZ3成分のlist。
                safe適用後の最終結果を予測する値ではない。

        Raises:
            TypeError: fastがbool以外、またはunitが文字列以外の場合。
            ValueError: unitが未対応の単位名、値が3成分でない、マトリクスが分解不能、
                または必要な親マトリクスが反転不能の場合。
            RuntimeError: ノードが無効、またはアトリビュートを書き込めない場合。
        """
        ...
    def getScale(self, worldSpace: bool = ...) -> Scale:
        """指定空間のスケール値を取得する。

        Args:
            worldSpace (bool): ワールド指定。Falseはscaleチャンネル。

        Returns:
            Scale: 独立した無次元のXYZ3成分。ローカルではSSCを除くチャンネル値、
                ワールドではAPI規約の分解値で、チャンネルの符号と一致するとは限らない。
        """
        ...
    def setScale(self, value: Iterable[float], worldSpace: bool = ..., safe: bool = ..., get: bool = ..., *, fast: bool = ...) -> Transform | list[float]:
        """scaleチャンネルだけを設定する。

        ワールド指定では要求スケールをローカル設定値へ変換する。
        変換後も書込み先はscaleだけで、rotateやshearは変更しない。

        Args:
            value (Iterable[float]): 無次元のXYZスケール3成分。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずチャンネル値を返す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: 自身。get=Trueは独立したローカルXYZ設定値のlist。
        """
        ...
    def getShear(self, worldSpace: bool = ...) -> Shear:
        """指定空間のシアー値を取得する。

        Args:
            worldSpace (bool): ワールド指定。Falseはshearチャンネル。

        Returns:
            Shear: 独立した無次元のXY・XZ・YZ3成分。
                ローカルはチャンネル値、ワールドはAPI規約のマトリクス分解値。
        """
        ...
    def setShear(self, value: Iterable[float], worldSpace: bool = ..., safe: bool = ..., get: bool = ..., *, fast: bool = ...) -> Transform | list[float]:
        """shearチャンネルだけを設定する。

        ワールド指定では要求シアーをローカル設定値へ変換する。
        変換後も書込み先はshearだけで、rotateやscaleは変更しない。

        Args:
            value (Iterable[float]): 無次元のXY・XZ・YZシアー3成分。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まずチャンネル値を返す。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: 自身。get=Trueは独立したローカルXY・XZ・YZ設定値のlist。
        """
        ...
    def getQuaternion(self, worldSpace: bool = ..., ra: bool = ..., r: bool = ..., jo: bool = ...) -> Quaternion:
        """回転成分を選んで取得する。既定ではrotateAxisを含めない。

        ローカル空間ではrotateAxis・rotate・JointのjointOrientの順に、選んだ回転を合成する。
        ワールド空間では保持パスのマトリクスから求め、除外する回転成分を取り除く。
        ra/r/joの許容組合せはsetQuaternionと同一ではない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ra (bool): rotateAxisを含める。
            r (bool): rotateを含める。
            jo (bool): jointOrientを含める。

        Returns:
            Quaternion: ノードと独立した、指定成分の合成回転。成分順はXYZW。

        Raises:
            ValueError: 回転成分と空間指定が未対応の組合せの場合。
        """
        ...
    def setQuaternion(self, value: Quaternion | om2.MQuaternion | Iterable[float], worldSpace: bool = ..., ra: bool = ..., r: bool = ..., jo: bool = ..., safe: bool = ..., get: bool = ..., *, unit: str = ..., fast: bool = ...) -> Transform | list[float]:
        """回転成分の指定に従いrotate・jointOrient・rotateAxisを設定する。

        受理する組合せでは、r=Trueはrotate、r=FalseかつJointでjo=TrueはjointOrient、
        それ以外のr=FalseはrotateAxisだけを書き込む。ra/r/joの許容組合せは
        getQuaternionと同一ではない。

        Args:
            value (Quaternion | om2.MQuaternion | Iterable[float]): xyzwの回転。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ra (bool): 入力にrotateAxisを含む。
            r (bool): rotateを更新する。FalseはjointOrientまたはrotateAxis。
            jo (bool): jointOrientを含む。
            safe (bool): 書けない成分を無視する。
            get (bool): 書き込まず計算したEuler成分を返す。
            unit (str): get=Trueの戻り値の角度の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。書込みと入力のクォータニオンには影響しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Transform | list[float]: get=Falseでは自身。get=Trueでは書込み先のEuler3成分を
                unitの単位(既定は度)のlistとして返し、safe/fastの指定によらずシーンは変更しない。
                入力のQuaternionや、XYZWの4成分を返す操作ではない。
                rotateの設定予定値はノードのrotateOrder、他の書込み先はXYZ順序。

        Raises:
            TypeError: unitが文字列以外の場合。
            ValueError: 回転成分と空間指定が未対応の組合せ、またはunitが未対応の単位名の場合。
        """
        ...
    def makeIdentity(self, *, apply: bool = ..., a: bool = ..., jointOrient: bool = ..., jo: bool = ..., normal: int = ..., n: int = ..., preserveNormals: bool = ..., pn: bool = ..., rotate: bool = ..., r: bool = ..., scale: bool = ..., s: bool = ..., translate: bool = ..., t: bool = ..., query: bool = ..., q: bool = ..., edit: bool = ..., e: bool = ..., **kwargs: object) -> Transform:
        """自身を対象にcmds.makeIdentityを実行する。

        省略したフラグはMayaの既定に従う。通常更新をUndo有効時にまとめ、途中失敗の変更は戻さない。

        Args:
            **kwargs (object): MayaのmakeIdentityへ渡す追加フラグ。
            apply (bool): Mayaのapplyフラグ。省略時はMayaの既定に従う。
            a (bool): applyの別名。同時指定は不可。
            jointOrient (bool): MayaのjointOrientフラグ。省略時はMayaの既定に従う。
            jo (bool): jointOrientの別名。同時指定は不可。
            normal (int): Mayaのnormalフラグ。省略時はMayaの既定に従う。
            n (int): normalの別名。同時指定は不可。
            preserveNormals (bool): MayaのpreserveNormalsフラグ。省略時はMayaの既定に従う。
            pn (bool): preserveNormalsの別名。同時指定は不可。
            rotate (bool): Mayaのrotateフラグ。省略時はMayaの既定に従う。
            r (bool): rotateの別名。同時指定は不可。
            scale (bool): Mayaのscaleフラグ。省略時はMayaの既定に従う。
            s (bool): scaleの別名。同時指定は不可。
            translate (bool): Mayaのtranslateフラグ。省略時はMayaの既定に従う。
            t (bool): translateの別名。同時指定は不可。
            query (bool): Mayaのqueryフラグ。省略時はMayaの既定に従う。
            q (bool): queryの別名。同時指定は不可。
            edit (bool): Mayaのeditフラグ。省略時はMayaの既定に従う。
            e (bool): editの別名。同時指定は不可。

        Returns:
            Transform: 自身。

        Raises:
            TypeError: 長短フラグを同時指定した場合。
            RuntimeError: ノードが無効、または Maya が拒否した場合。
        """
        ...
    def getClosestAxisToVector(self, refVector: Vector | Iterable[float], includeNegative: bool = ...) -> str:
        """自身のローカル軸のうち、ワールド空間の方向ベクトルに最も近いものを求める。

        各ローカル軸をワールドマトリクス(回転・スケールのみ、平行移動は無視)で変換し、
        正規化した上で refVector との内積が最大のものを選ぶ。

        Args:
            refVector (Vector | Iterable[float]): 比較対象のワールド空間方向ベクトル。
            includeNegative (bool): True の場合、負方向の軸(-x/-y/-z)も候補に含める。

        Returns:
            str: 最も近い軸名("x"、"y"、"z"。includeNegative が True なら
                "-x"、"-y"、"-z" も返り得る)。

        Raises:
            ValueError: refVector またはいずれかのローカル軸がワールド変換後にゼロベクトルになる場合。
            RuntimeError: ノードが無効な場合。
        """
        ...
    def _color_targets(self) -> list[DagNode]:
        """:meth:`setColor`・:meth:`getColor` の対象を返す。

        Returns:
            list[DagNode]: 直下の中間でないShape。Shapeが無ければ自身。
        """
        ...
    def _local_matrix(self, matrix: Matrix | Sequence[Any], ws: bool) -> Matrix:
        """setMatrixの入力を検証し、ローカル空間のマトリクスへ変換する。シーンは更新しない。

        Args:
            matrix (Matrix | sequence): 適用するマトリクス。
            ws (bool): 検証済みのワールド空間指定。Trueは保持パスのexclusiveMatrixInverseを掛ける。

        Returns:
            Matrix: ローカル空間のマトリクス。

        Raises:
            ValueError: マトリクスが不正、またはワールド指定時の親が反転不能な場合。
            RuntimeError: ノードが無効な場合。
        """
        ...
    @staticmethod
    def _detach_inputs(objects: Iterable[om2.MObject]) -> None:
        """限定削除の上流ノードが孤立履歴として連鎖削除されることを防ぐ。

        Args:
            objects (Iterable[om2.MObject]): 削除予定のノード。

        Returns:
            None: 値を返さない。

        Note:
            直接API更新なのでUndoへ記録しない。削除modifierとは別に先に確定する。
        """
        ...
    def _set_parent_fast(self, parent: Node | None, relative: bool, add: bool, *, validate_only: bool = ...) -> Transform:
        """対応するTransformだけを検証してAPIで再親付けする。

        Args:
            parent (Node | None): 新しい親。Noneはワールド。
            relative (bool): ローカル変換を保持するか。
            add (bool): 既存の親に追加するか。Trueは未対応。
            validate_only (bool): Trueは全件事前検証用。DAGを変更しない。

        Returns:
            Transform: 自身。

        Raises:
            RuntimeError: 参照・ロック・循環・特異マトリクスにより変更できない場合。
            NotImplementedError: Joint・インスタンス・親追加の場合。
        """
        ...
    def _static_value(self, name: str) -> tuple[float, ...] | object:
        """ノード型に組み込みの数値アトリビュートの内部単位の値を、Plugラッパーを作らずに読む。

        ``getPlug(name).get()`` と同じ読取関数(距離cm・角度rad)をMPlugへ直接適用する。
        コンパウンドアトリビュートは子の値のtuple、単一の値はその値を返す。計算の途中で何度も読む
        translate・ピボット等のために使い、値はキャッシュしない。ノードが無効な場合と
        読取関数を持たない型は、従来どおり ``getPlug(name).get()`` の結果・例外に委ねる。

        Args:
            name (str): 静的アトリビュートのロング名。

        Returns:
            tuple[float, ...] | object: コンパウンドアトリビュートなら子の値のtuple、それ以外は値。
        """
        ...
    def _inverse_scale_values(self):
        """jointの有効なinverseScaleを返す。それ以外は単位スケール。"""
        ...
    def _scale_channel_value(self, value, ws, shear=...):
        """ワールドのscale/shear要求を、SSCを除いたチャンネル値へ変換する。

        Args:
            value: 変換・設定する入力値。
            ws: Trueはワールド空間、Falseはローカル空間。
            shear: XY/XZ/YZのシアー成分。
        """
        ...
    def _component_quaternion(self, name: str) -> om2.MQuaternion:
        """回転アトリビュートをQuaternionへ変換する。

        rotateはノードの回転順序、rotateAxis・jointOrient等はXYZで解釈する。

        Args:
            name (str): 回転アトリビュート名。

        Returns:
            om2.MQuaternion: 新しい回転値。
        """
        ...
    def _rotate_order(self) -> int:
        """ノードの rotateOrder を om2 の回転順序の番号として取得する。

        Returns:
            int: 0(xyz)〜5(zyx)。om2.MEulerRotation.kXYZ〜kZYX と同じ番号。
        """
        ...
    def _require_pivots_writable(self, kinds: Iterable[str], preserve: bool) -> None:
        """変更するピボットと補償値の全成分が書き込めるか、更新前に検査する。

        Args:
            kinds (Iterable[str]): 検査するピボットの種類(rotate/scale)。
            preserve (bool): Trueは補償値(rotatePivotTranslate等)も検査する。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: いずれかの成分がロック・入力接続・書込み不能の場合。
        """
        ...
    def _channel_state(self) -> tuple:
        """現在の scale チャンネル値と rotate チャンネル値を内部単位で取得する。

        分解の解を現在のチャンネル値に近づけるための基準に使う。

        Returns:
            tuple: (scale の3成分の tuple, rotate の om2.MEulerRotation)。rotate は
            ラジアンで、順序はノードの rotateOrder。ノードが無効なら
            ((1.0, 1.0, 1.0), XYZ 順序の 0 回転)。
        """
        ...
    def _decompose_like_channels(self, matrix: Matrix, scale_reference: Iterable[float] | None = ...) -> tuple:
        """マトリクスを分解し、スケールの符号の組み合わせを基準のスケールへ揃える。

        om2.MTransformationMatrix の規約(行列式が負なら Z が負)で分解してから、
        :func:`_match_scale_signs` で符号を揃える。基準は scale_reference (指定時)、
        次に現在の scale チャンネル値の順に、行列式の符号と合う最初のもの。これにより
        scale が (-1, 1, 1) のようなミラーのノードでも、取得・設定の往復でチャンネル値の
        符号と回転が保たれ、``setScale`` では要求した符号がそのまま入る。

        Args:
            matrix (Matrix): 分解するマトリクス。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール
                (``setScale`` で要求した値)。None なら現在の scale チャンネル値だけ。

        Returns:
            tuple: (translate(Translate), quaternion(om2.MQuaternion),
            scale(tuple), shear(tuple), reference(om2.MEulerRotation))。reference は
            現在の rotate チャンネル値で、Euler の解を選ぶ基準に使う。

        Raises:
            ValueError: マトリクスを分解できない場合(いずれかのスケール軸がゼロなど)。
        """
        ...
    def _replace_components(self, matrix: Matrix, rotate: Iterable[float] | EulerRotate | Quaternion | None = ..., scale: Iterable[float] | None = ..., shear: Iterable[float] | None = ...) -> Matrix:
        """マトリクスの回転・スケール・シアーの一部を置き換えた新しいマトリクスを返す。

        置き換えない成分は :meth:`_decompose_like_channels` の分解値(スケールの符号を
        現在のチャンネルへ揃えた値)を使う。平行移動はマトリクスの値をそのまま保つ。

        Args:
            matrix (Matrix): 元のマトリクス。
            rotate (Iterable[float] | EulerRotate | Quaternion | None): 新しい回転。
                3成分は XYZ 順序のラジアン。None は現在の値。
            scale (Iterable[float] | None): 新しいスケール。None は現在の値。
            shear (Iterable[float] | None): 新しいシアー。None は現在の値。

        Returns:
            Matrix: 合成し直した新しいマトリクス。

        Raises:
            ValueError: 元のマトリクスを分解できない場合、または入力が不正な場合。
        """
        ...
    def _rotate_reference(self, reference: om2.MEulerRotation) -> om2.MEulerRotation:
        """:meth:`getRotate` が Euler の解を選ぶ基準を返す。

        transform ではマトリクスの回転と rotate チャンネルが同じ回転(rotateAxis が 0 の場合)
        なので、現在の rotate チャンネル値をそのまま基準にする。

        Args:
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: 基準の回転(順序はノードの rotateOrder)。
        """
        ...
    def _channel_rotate(self, quaternion: om2.MQuaternion, reference: om2.MEulerRotation) -> om2.MEulerRotation:
        """ローカルマトリクスの回転を、rotate チャンネルへ書き込む値へ変換する。

        transformではrotateAxisを除いてrotateチャンネルの回転を求める。

        Args:
            quaternion (om2.MQuaternion): ローカルマトリクスの回転。
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: ノードの rotateOrder で表した、reference に最も近い解。
        """
        ...
    def _quaternion_channel_values(self, value: om2.MQuaternion | Iterable[float], ws: bool, ra: bool, r: bool, jo: bool) -> tuple[str, om2.MEulerRotation]:
        """回転の指定から書込み先とEuler値だけを求め、シーンは変更しない。

        Args:
            value (om2.MQuaternion | Iterable[float]): 入力回転。
            ws (bool): 検証済みのワールド空間指定。
            ra (bool): 入力へrotateAxisを含めるか。
            r (bool): rotateを更新するか。
            jo (bool): jointOrientを含めるか。

        Returns:
            tuple[str, om2.MEulerRotation]: 書込み先名とrad単位の計算値。
        """
        ...
    def _apply_local_matrix(self, matrix: Matrix, scale_reference: Iterable[float] | None = ..., *, fast: bool = ...) -> None:
        """ローカルマトリクスの各成分をMayaアトリビュートへ適用する。

        マトリクスを1回だけ分解し、平行移動・回転・スケール・シアーのうち現在値と
        異なるものを順に書き込む(:meth:`_apply_channel_values`)。
        分解は om2.MTransformationMatrix の規約に、次の2点の選択を加えたもの。

        * スケールの符号の組み合わせは、行列式の符号が許す限り scale_reference
          (``setScale`` で要求した値)、次に現在の scale チャンネルに揃える
          (:meth:`_decompose_like_channels`)。
        * 回転はノードの rotateOrder で表し、等価な解のうち現在の rotate チャンネル値に
          最も近いものを選ぶ(``om2.MEulerRotation.closestSolution``)。

        同じマトリクスの再適用で、不要なスケール符号や等価なEuler解の変化を避ける。
        計算値は距離cm・角度radで、書込みは共通のPlug処理へ委譲する。
        ピボット・rotateAxis・jointOrient・SSCの補正を含める。

        Args:
            matrix (Matrix): ローカル空間のマトリクス。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール。
                None なら現在の scale チャンネル値に合わせる。
            fast (bool): Trueなら各チャンネルをOpenMayaで更新する。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: マトリクスを分解できない場合。
            RuntimeError: Maya がアトリビュートの書き込みを拒否した場合。
        """
        ...
    def _apply_channel_values(self, values: dict[str, Iterable[float]], safe: bool = ..., *, fast: bool = ...) -> None:
        """計算済みの内部単位値のうち、現在値と異なるものだけを辞書の保持順に設定する。

        書込み値が現在のチャンネル値(内部単位)と完全に一致するチャンネルは書き込まない。
        書き込まないチャンネルはロック・接続されていても例外にせず、通知・Undoの記録も残らない。

        Args:
            values (dict[str, Iterable[float]]): チャンネル名と設定値。
            safe (bool): 書けない成分を残す。通常時は失敗を伝播する。
            fast (bool): 子のPlugへ渡す更新モード。

        Returns:
            None: 値を返さない。
        """
        ...
    def _channel_equals(self, name: str, value: tuple | object) -> bool:
        """内部単位の書込み値が、チャンネルの現在値と完全に一致するかを返す。

        Args:
            name (str): 組み込みの数値アトリビュートのロング名。
            value (tuple | object): 書込み予定の値。コンパウンドアトリビュートは成分のtuple。

        Returns:
            bool: 成分数と各成分が完全に一致すればTrue。読取れない場合はFalse(書込みへ委ねる)。
        """
        ...
    def _set_channel_value(self, name: str, value: Iterable[float], safe: bool = ..., *, fast: bool = ...) -> Plug | int:
        """内部単位のチャンネル値を、基底Plug.setへ渡す。

        Double3の回転変換を再実行せず、入力された順序の数値を使う。
        通常更新はMayaに従い、fastは接続済み入力への直接書込みを拒否する。
        参照取得・tuple化の失敗はsafeで抑制しない。

        Args:
            name (str): 設定するチャンネル名。
            value (Iterable[float]): 数値列。距離cm、角度rad。
            safe (bool): Plug.setに対応する書込み失敗を数えるか。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug | int: Plug.setの戻り値。通常はPlug、safe=Trueは失敗数。
        """
        ...
    def _matrix_channel_values(self, matrix, scale_reference=...):
        """マトリクスからtranslate/rotate/scale/shearの設定値を計算する。シーンは更新しない。

        Args:
            matrix: 変換または数値計算に使うマトリクス。
            scale_reference: スケール補正の基準となるノードまたは値。
        """
        ...
