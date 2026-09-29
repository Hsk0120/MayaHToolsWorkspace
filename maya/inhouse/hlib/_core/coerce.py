"""hlib と Maya API 2.0 のオブジェクトを maya.cmds 用の名前・Node・Plug へ正規化する。

hlib のコマンド(``hlib.select``/``hlib.delete`` など)と、
ノードを引数に取るメソッドが共通で使う内部ヘルパー。受け付ける入力と変換結果:

.. list-table::
   :header-rows: 1

   * - 入力
     - ``to_name`` の結果
     - ``to_node`` の結果
   * - ``str``
     - そのまま(Maya へ問い合わせない)
     - ``Node(value)``
   * - ``Node``
     - ``full_name()`` (完全 DAG パス。DG ノードはノード名)
     - そのまま
   * - ``Plug`` (``ArrayPlug`` を含む)
     - ``full_name()`` (ノードの最短一意名 + 属性パス)
     - 所有ノード(``plug.node``)
   * - ``Component`` (単体)
     - ``full_name()`` (シェイプの完全パス + ``.vtx[3]`` 等)
     - 所有シェイプ(``component.shape``)
   * - ``om2.MObject`` (依存ノード)
     - 完全 DAG パス、または DG ノード名
     - ``Node(value)``
   * - ``om2.MDagPath``
     - ``fullPathName()`` (インスタンスのパスを保持)
     - ``Node(value)``
   * - ``om2.MPlug``
     - ``Plug.full_name()`` と同じ形式
     - 所有ノード

``to_names`` はさらに ``Components``・``Selection``・``Joints`` などのコレクションと、
list/tuple/set/ジェネレーターなどの反復可能オブジェクトを入れ子も含めて展開する。
``Components`` は連続する番号を ``vtx[0:9]`` のような範囲指定にまとめる。

例外の規則(``to_name``/``to_names``/``to_node_name``): 対応しない型は ``TypeError``、
空文字列・空の om2 オブジェクト・削除済みの対象は ``ValueError``、文字列を解決できない
(存在しない、または複数の対象に一致する)場合は ``RuntimeError``。``to_node`` は削除済みの
Node と、所有ノードが削除済みの Plug・Component をそのまま(無効な所有ノードとして)返し、
有効性の扱いは呼び出し側の API に任せる(``Node(...)`` と ``hlib.addConstraint`` は ``RuntimeError``)。
ただし ``deleteAttr`` で削除された属性の Plug・MPlug(所有ノードは有効)は、返す Node で
削除を表せないため、``to_node``・``Node(...)`` などノードを解決する処理でも
:class:`DeletedAttributeError` (``ValueError``)にする。
"""

import re

import maya.api.OpenMaya as om2

#: 属性パスの1区切り(``pnts[2]``、``pntx`` など)。属性名と、続く論理インデックスの並び。
_PLUG_PATH_TOKEN = re.compile(r"(\w+)((?:\[\d+\])*)\Z")

#: 区切り内の論理インデックス(``[2]`` の ``2``)。
_PLUG_PATH_INDEX = re.compile(r"\[(\d+)\]")

#: 配列要素の論理インデックスの上限(``MPlug.logicalIndex()`` が返す符号付き 32 ビット整数の最大値)。
#: ``MPlug.elementByLogicalIndex()`` はこれを超える番号を黙って別の番号へ変換する
#: (``2147483648``〜``4294967295`` は負の番号、``4294967296`` は ``0``)ため、属性パスでは
#: 範囲外として扱う。
MAX_LOGICAL_INDEX = 2147483647


class DeletedAttributeError(ValueError, RuntimeError):
    """``deleteAttr`` で削除された属性の Plug・MPlug を、ノードが必要な引数に渡した場合の例外。

    所有ノードは有効なまま属性だけが削除された Plug・MPlug は、所有ノードへ解決すると
    削除済みの対象を黙って受け付けてしまうため、``to_node``・``Node(...)``/``hlib.getNode``・
    ``hlib.addConstraint`` の拘束元・拘束先などでも例外にする。hlib のコマンド(``to_name``)と
    同じく ``ValueError`` として扱う。``Node(...)`` は解決できない対象をすべて
    ``RuntimeError`` にする規則のため、``RuntimeError`` としても捕捉できるようにしている
    (標準ライブラリの ``io.UnsupportedOperation`` が ``OSError`` と ``ValueError`` の両方を
    継承するのと同じ考え方)。
    """


def plug_path(mplug):
    """ノード名を除いた、maya.cmds で解決できる属性パスを返す。

    ロング名と、必要な配列インデックス(``worldMatrix[0]``、``pnts[2].pntx`` 等)・
    インスタンス番号を含み、エイリアスがあればエイリアス名を使う
    (``MPlug.name()`` の属性部分と同じ表記)。

    Args:
        mplug (om2.MPlug): 対象のプラグ。

    Returns:
        str: ``translateX`` や ``worldMatrix[0]`` のような属性パス。
    """
    # 名前付き引数より位置引数の方が呼び出しが速いため、位置で渡す。順に
    # includeNodeName, includeNonMandatoryIndices, includeInstancedIndices,
    # useAlias, useFullAttributePath, useLongNames。
    return mplug.partialName(False, True, True, True, False, True)


def selection_owner(selection, index, name=None):
    """MSelectionList の要素を所有するノードの MObject と DAG パスを返す。

    ノード・コンポーネントの要素は選択されたインスタンスの DAG パスを返す。
    属性(プラグ)の要素は ``MSelectionList.getDagPath()`` を使えず、選択リスト自体も
    インスタンスの情報を持たないため、インスタンス化された DAG ノードの属性は
    次の順にノード部分からインスタンスのパスを求める。

    1. name(要素を追加したときの文字列)。``|grpB|box1|boxShape.castsShadows`` は
       ``|grpB|box1|boxShape`` のインスタンスを指す。
    2. 選択文字列。``worldMatrix[1]`` のようなインスタンスごとの属性は、要素番号の
       インスタンスが選択文字列に現れる。

    ``|box1.castsShadows`` のように transform の名前でシェイプの属性を指す文字列は、
    ノード部分が指す transform のパスを所有シェイプまで伸ばす(``|box1|boxShape``)。
    どちらからも求められない場合は最初のインスタンスのパスを返す。

    Args:
        selection (om2.MSelectionList): 対象を含む選択リスト。
        index (int): 要素の位置。
        name (str | None): 要素を追加したときの文字列。分かっている場合に指定する。

    Returns:
        tuple[om2.MObject, om2.MDagPath | None]: 所有ノードの MObject と、DAG ノードで
            あれば DAG パス(DG ノードは None)。
    """
    mobject = selection.getDependNode(index)
    if not mobject.hasFn(om2.MFn.kDagNode):
        return mobject, None
    try:
        return mobject, selection.getDagPath(index)
    except (RuntimeError, TypeError):
        pass
    fn = om2.MFnDagNode(mobject)
    if fn.isInstanced():
        candidates = [name] if name else []
        candidates.extend(selection.getSelectionStrings(index))
        for text in candidates:
            # ノード名には "." を含められないため、最初の "." までがノード部分になる。
            owner = om2.MSelectionList()
            try:
                owner.add(text.split(".", 1)[0])
                dag_path = owner.getDagPath(0)
            except (RuntimeError, TypeError):
                continue
            if dag_path.node() == mobject:
                return mobject, dag_path
            # transform の名前でシェイプの属性を指す場合は、名前が指す transform の
            # インスタンスの下にある所有シェイプまでパスを伸ばす。
            for child in range(dag_path.childCount()):
                if dag_path.child(child) == mobject:
                    dag_path.push(mobject)
                    return mobject, dag_path
    return mobject, fn.getPath()


def unique_node_name(mobject):
    """ノードの MObject から maya.cmds で一意に解決できる最短名を返す。

    DAG ノードは最初のインスタンスの最短一意パス(``MDagPath.partialPathName()``)、
    DG ノードはノード名を返す。``Node.name()`` と同じ規則。

    Args:
        mobject (om2.MObject): 依存ノードの MObject。

    Returns:
        str: 最短一意名。
    """
    if mobject.hasFn(om2.MFn.kDagNode):
        return om2.MFnDagNode(mobject).getPath().partialPathName()
    return om2.MFnDependencyNode(mobject).name()


def _classes():
    """循環 import を避けるため、判定に使う hlib クラスを呼び出し時に取得する。

    Returns:
        tuple[type, type, type, type]: Node、Plug、Component、Components。
    """
    from ..components.component import Component, Components
    from ..nodes.node import Node
    from ..plugs.plug import Plug

    return Node, Plug, Component, Components


def _unsupported(value):
    """対応しない入力型の TypeError を作る。

    Args:
        value (object): 入力値。

    Returns:
        TypeError: 送出する例外。
    """
    return TypeError(
        f"対応していない型です: {type(value).__name__}"
        "(str / Node / Plug / Component / om2.MObject / om2.MDagPath / om2.MPlug を指定してください)"
    )


def _mobject_name(mobject):
    """依存ノードの MObject を完全 DAG パスまたは DG ノード名へ変換する。

    Args:
        mobject (om2.MObject): 変換対象。

    Returns:
        str: 完全 DAG パス(最初のインスタンス)、または DG ノード名。

    Raises:
        ValueError: 空、または削除済みノードの MObject の場合。
        TypeError: 属性・コンポーネント・データなど依存ノード以外を指す場合。
    """
    if mobject.isNull():
        raise ValueError("空の MObject は指定できません")
    if not om2.MObjectHandle(mobject).isValid():
        raise ValueError("削除済みノードの MObject は指定できません")
    if not mobject.hasFn(om2.MFn.kDependencyNode):
        raise TypeError("MObject には依存ノードを指定してください(属性・コンポーネント・データは不可)")
    if mobject.hasFn(om2.MFn.kDagNode):
        return om2.MFnDagNode(mobject).getPath().fullPathName()
    return om2.MFnDependencyNode(mobject).name()


def mplug_attribute_exists(mplug, node=None):
    """MPlug の属性が所有ノードに存在するか判定する(所有ノードは有効であること)。

    ``deleteAttr`` で削除された動的属性の MPlug は、Undo のために属性の MObject が保持された
    ままの場合があり ``MObjectHandle.isValid()`` だけでは判定できないため、所有ノードの
    ``MFnDependencyNode.attributeClass()`` で確かめる(ノードに無い属性は ``kInvalidAttr``)。

    Args:
        mplug (om2.MPlug): 判定するプラグ。
        node (om2.MObject | None): 所有ノード。分かっている場合に指定する。

    Returns:
        bool: 属性が存在する場合は True。
    """
    attribute = mplug.attribute()
    if attribute.isNull() or not om2.MObjectHandle(attribute).isValid():
        return False
    if node is None:
        node = mplug.node()
    kind = om2.MFnDependencyNode(node).attributeClass(attribute)
    return kind != om2.MFnDependencyNode.kInvalidAttr


def _mplug_name(mplug):
    """MPlug を ``Plug.full_name()`` と同じ形式の一意なプラグ名へ変換する。

    所有ノードが Undo の対象から外れて削除された(``flushUndo`` 後・Undo 無効・シーンの
    切り替え)MPlug は、``MPlug.node()`` の時点で Maya が異常終了し、API では検出できない。
    MPlug を削除操作をまたいで保持せず、hlib の Plug を保持すること(:doc:`/cmds_interop`)。

    Args:
        mplug (om2.MPlug): 変換対象。

    Returns:
        str: ``<ノードの最短一意名>.<属性パス>``。

    Raises:
        ValueError: 空の MPlug、所有ノードが削除済み、または属性が削除済み(``deleteAttr``)の場合。
    """
    if mplug.isNull:
        raise ValueError("空の MPlug は指定できません")
    node = mplug.node()
    if not om2.MObjectHandle(node).isValid():
        raise ValueError("削除済みノードの MPlug は指定できません")
    if not mplug_attribute_exists(mplug, node):
        raise ValueError("削除済みの属性の MPlug は指定できません")
    return unique_node_name(node) + "." + plug_path(mplug)


def _name(value, node_class, plug_class, component_class):
    """単一の対象を名前へ変換する(to_name の本体)。

    Args:
        value (object): 変換対象。
        node_class (type): Node クラス。
        plug_class (type): Plug クラス。
        component_class (type): Component クラス。

    Returns:
        str: maya.cmds へ渡せる名前。

    Raises:
        TypeError: 対応しない型の場合。
        ValueError: 空文字列、または無効な対象の場合。
    """
    if isinstance(value, str):
        name = value
    elif isinstance(value, node_class):
        name = value.full_name()
        if not name:
            raise ValueError("無効な(削除済みの)ノードは指定できません")
    elif isinstance(value, plug_class):
        name = value.full_name()
        if not name:
            raise ValueError("無効な(所有ノードまたは属性が削除済みの)Plug は指定できません")
    elif isinstance(value, component_class):
        try:
            name = value.full_name()
        except (RuntimeError, IndexError) as error:
            raise ValueError(f"無効なコンポーネントは指定できません: {error}") from error
    elif isinstance(value, om2.MPlug):
        name = _mplug_name(value)
    elif isinstance(value, om2.MDagPath):
        if not value.isValid() or not om2.MObjectHandle(value.node()).isValid():
            raise ValueError("無効な(削除済みの)MDagPath は指定できません")
        name = value.fullPathName()
    elif isinstance(value, om2.MObject):
        name = _mobject_name(value)
    else:
        raise _unsupported(value)
    if not name:
        raise ValueError("空でない名前を指定してください")
    return name


def to_name(value):
    """単一の対象を maya.cmds へ渡せる一意な名前へ変換する。

    文字列は解決せず(Maya へ問い合わせず)そのまま返す。解決済みの Node が
    必要な場合は to_node を使う。変換規則はモジュールの説明を参照。

    Args:
        value (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
            変換対象。

    Returns:
        str: maya.cmds で解決できる名前。

    Raises:
        TypeError: 対応しない型、依存ノード以外を指す MObject、または
            Components などの複数の対象を渡した場合(to_names を使う)。
        ValueError: 空文字列、または無効な(削除済み・範囲外の)対象の場合。
    """
    node_class, plug_class, component_class, _ = _classes()
    return _name(value, node_class, plug_class, component_class)


def node_inputs(values):
    """対象列を一度だけ展開し、名前とNodeの混在を変換前に拒否する。

    Args:
        values (object): 単体、または対象の反復可能列。既存のAPI型も保持する。
    Returns:
        list: 入力順の対象。空列は空のまま返す。
    Raises:
        TypeError: 同じ対象列に文字列とNodeが混在している場合。
    """
    node_class, plug_class, component_class, components_class = _classes()
    singles = (str, node_class, plug_class, component_class, components_class,
               om2.MObject, om2.MDagPath, om2.MPlug)
    result = []
    def collect(value):
        """単体を保持し、コレクションを一度だけ展開する。"""
        if isinstance(value, singles):
            result.append(value)
        else:
            try:
                iterator = iter(value)
            except TypeError:
                raise _unsupported(value) from None
            for item in iterator:
                collect(item)
    collect(values)
    if any(isinstance(value, str) for value in result) and any(isinstance(value, node_class) for value in result):
        raise TypeError("Names and Node objects cannot be mixed in the same target collection")
    return result


def to_names(values, allow_plugs=True):
    """単一の対象・コレクション・反復可能オブジェクトを名前のリストへ正規化する。

    単一の対象(to_name が受け付ける型)は1要素のリストになる。``Components``・
    ``Selection``・``Joints`` などのコレクションと、list/tuple/set/ジェネレーター
    などの反復可能オブジェクトは、入れ子も含めて保持順に展開する。
    ``ArrayPlug`` は要素へ展開せず、配列属性そのものの名前として扱う。
    ``Components`` は全番号をまとめて1回だけ検証し、保持順で連続する番号を
    ``|cube|cubeShape.vtx[0:9]`` のような範囲指定の名前にまとめる(要素数が多くても
    maya.cmds へ渡す名前が増えない)。

    Args:
        values (object): 変換対象。単一の対象、または対象を要素に持つ反復可能オブジェクト。
        allow_plugs (bool): False の場合、Plug(``ArrayPlug`` を含む)と ``om2.MPlug`` を
            TypeError にする(属性を渡しても maya.cmds が何もしないコマンド用。文字列は
            解決しないため対象外)。

    Returns:
        list[str]: 正規化した名前のリスト。空の反復可能オブジェクトは空リスト。

    Raises:
        TypeError: いずれかの要素が対応しない型の場合。allow_plugs が False で、
            Plug・MPlug が含まれる場合。同じ対象列に文字列とNodeが混在する場合。
        ValueError: いずれかの要素が空文字列、または無効な対象の場合。
    """
    node_class, plug_class, component_class, components_class = _classes()
    singles = (str, node_class, plug_class, component_class, om2.MObject, om2.MDagPath, om2.MPlug)
    names = []

    def collect(value):
        if not allow_plugs and isinstance(value, (plug_class, om2.MPlug)):
            raise TypeError(
                f"属性(Plug・MPlug)は指定できません: {type(value).__name__}"
                "(所有ノードを対象にする場合は plug.node を指定してください)"
            )
        if isinstance(value, singles):
            names.append(_name(value, node_class, plug_class, component_class))
            return
        if isinstance(value, components_class):
            try:
                # 全番号の検証はコレクションごとに1回だけ行い、連続する番号は範囲指定にまとめる。
                names.extend(value.compact_names())
            except (RuntimeError, IndexError) as error:
                raise ValueError(f"無効なコンポーネントは指定できません: {error}") from error
            return
        try:
            iterator = iter(value)
        except TypeError:
            raise _unsupported(value) from None
        for item in iterator:
            collect(item)

    collect(node_inputs(values))
    return names


def deleted_attribute_error(plug):
    """所有ノードが有効なまま属性が削除された Plug の例外を返す(該当しなければ None)。

    Args:
        plug (Plug): 判定する hlib の Plug。

    Returns:
        DeletedAttributeError | None: 属性が ``deleteAttr`` で削除済みなら送出する例外。
            所有ノードが削除済みの場合(無効な所有ノードとして扱う)と、有効な Plug は None。
    """
    if plug.node.is_valid() and not plug.is_valid():
        return DeletedAttributeError("削除済みの属性の Plug からノードは解決できません")
    return None


def to_node(value):
    """対象を Node インスタンスへ変換する。

    Plug・MPlug は所有ノード、Component・Components は所有シェイプへ解決する。

    Args:
        value (Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            変換対象。

    Returns:
        Node: value が Node ならそのまま、Plug なら ``plug.node``、コンポーネントなら
            ``shape``。それ以外は ``Node(value)`` (Maya へ解決し、型に応じたラッパーを返す)。
            削除済みの Node と、所有ノードが削除済みの Plug・Component は例外にせずそのまま
            返す(``Node.is_valid()`` が ``False``。扱いは呼び出し側で決める)。

    Raises:
        TypeError: 対応しない型の場合。
        ValueError: 所有ノードは有効で、属性が ``deleteAttr`` で削除済みの Plug・MPlug の場合
            (:class:`DeletedAttributeError`。``RuntimeError`` の派生でもある)。
        RuntimeError: 名前を解決できない(存在しない、または複数のノードに一致する)場合、
            または空・削除済みのノードを指す om2 オブジェクトの場合(``Node(value)`` と同じ)。
    """
    node_class, plug_class, component_class, components_class = _classes()
    if isinstance(value, node_class):
        return value
    if isinstance(value, plug_class):
        error = deleted_attribute_error(value)
        if error is not None:
            raise error
        return value.node
    if isinstance(value, (component_class, components_class)):
        return value.shape
    if isinstance(value, (str, om2.MObject, om2.MDagPath, om2.MPlug)):
        return node_class(value)
    raise _unsupported(value)


def to_node_name(value):
    """ノードが必要な単一の引数(``parent`` など)を、所有ノードの完全パスへ変換する。

    to_node と同じ規則で解決する(Plug・MPlug は所有ノード、Component は所有シェイプ)。
    ``"node.attribute"`` 形式の文字列も所有ノードになるため、maya.cmds のように
    プラグ名の ``parent`` が黙って無視されることはない。

    Args:
        value (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug): 変換対象。

    Returns:
        str: 所有ノードの完全 DAG パス(DG ノードはノード名)。

    Raises:
        TypeError: 対応しない型、または Components などの複数の対象を渡した場合。
        ValueError: 空文字列、または無効な(削除済みの。属性だけが削除された Plug・MPlug を
            含む)対象の場合。
        RuntimeError: 文字列を解決できない(存在しない、または複数のノードに一致する)場合。
    """
    # 型と有効性の検査は to_name と同じ規則(TypeError / ValueError)にそろえる。
    to_name(value)
    return to_node(value).full_name()


def _find_plug(mobject, name):
    """ノードの属性名(ロング名・ショート名・エイリアス)から MPlug を求める。

    ``MFnDependencyNode.findPlug()`` はエイリアスを解決しないため、見つからない場合は
    エイリアスの一覧(``bs.smile`` → ``weight[0]`` など)から属性パスを求めて解決する。

    Args:
        mobject (om2.MObject): 所有ノード。
        name (str): 属性名。

    Returns:
        om2.MPlug | None: プラグ。属性が無い場合は None。
    """
    fn = om2.MFnDependencyNode(mobject)
    try:
        return fn.findPlug(name, False)
    except RuntimeError:
        pass
    for alias, attribute_path in fn.getAliasList():
        if alias == name:
            return attribute_path_plug(mobject, attribute_path)
    return None


def has_out_of_range_index(attribute_path):
    """属性パスが :data:`MAX_LOGICAL_INDEX` を超える配列インデックスを含むか判定する。

    Args:
        attribute_path (str): ノード名を含まない属性パス(``input1D[4294967296]`` など)。

    Returns:
        bool: 範囲外のインデックスを含む場合は True。
    """
    return any(int(index) > MAX_LOGICAL_INDEX for index in _PLUG_PATH_INDEX.findall(attribute_path))


def has_unresolved_index(mplug):
    """論理インデックスが未確定(-1)の配列要素を経由するプラグか判定する。

    ``findPlug("input3Dx")`` のように配列複合属性の子を要素を指定せずに取得すると
    ``input3D[-1].input3Dx`` のようなプラグになり、maya.cmds では解決できない。

    Args:
        mplug (om2.MPlug): 判定するプラグ。

    Returns:
        bool: 未確定のインデックスを含む場合は True。
    """
    current = mplug
    while True:
        if current.isElement:
            if current.logicalIndex() < 0:
                return True
            current = current.array()
        elif current.isChild:
            current = current.parent()
        else:
            return False


def attribute_path_plug(mobject, attribute_path, first=None):
    """ノードと属性パス(``input1D[3]``、``pnts[2].pntx`` など)から MPlug を求める。

    ``.`` で区切った各区切りの属性名(ロング名・ショート名。先頭はエイリアスも可)と
    ``[i]`` の論理インデックスを順に辿る。存在しない配列要素もプラグとして返し、
    要素は作らない(シーンを変更しない)。

    Args:
        mobject (om2.MObject): 所有ノード。
        attribute_path (str): ノード名を含まない属性パス。
        first (om2.MPlug | None): 先頭の区切りの属性名に対応するプラグが既に分かっている
            場合に指定する(transform からシェイプへ伸ばして探した場合など)。

    Returns:
        om2.MPlug | None: プラグ。属性として解決できない場合(存在しない属性、範囲指定、
            配列でない属性へのインデックス、:data:`MAX_LOGICAL_INDEX` を超えるインデックス、
            配列要素の番号を指定しない子属性など)は None。
    """
    mplug = None
    for token in attribute_path.split("."):
        match = _PLUG_PATH_TOKEN.match(token)
        if match is None:
            return None
        name, indices = match.groups()
        if mplug is None:
            mplug = first if first is not None else _find_plug(mobject, name)
            if mplug is None:
                return None
        else:
            if mplug.isArray or not mplug.isCompound:
                return None
            for child_index in range(mplug.numChildren()):
                child = mplug.child(child_index)
                attribute = om2.MFnAttribute(child.attribute())
                if name in (attribute.name, attribute.shortName):
                    mplug = child
                    break
            else:
                return None
        for index in _PLUG_PATH_INDEX.findall(indices):
            index = int(index)
            if not mplug.isArray or index > MAX_LOGICAL_INDEX:
                # 範囲外の番号は elementByLogicalIndex() が別の番号へ変換してしまう
                # (input1D[4294967296] が input1D[0] を指す)ため、解決できない名前として扱う。
                return None
            mplug = mplug.elementByLogicalIndex(index)
    if mplug is None or has_unresolved_index(mplug):
        # 子属性名だけを指定した場合などの未確定(-1)のインデックスは maya.cmds で解決できない。
        return None
    return mplug


def _plug_from_path(text):
    """``"node.attr[i].child"`` 形式の文字列を、ノード部分と属性パスを辿って MPlug へ解決する。

    mesh の ``pnts[i]``、nurbsCurve・nurbsSurface・lattice の ``controlPoints[i]`` のように
    コンポーネント名としても解釈される属性は、MSelectionList が頂点・CV として登録し
    プラグとして取り出せないため、to_plug はこの関数で解決し直す(maya.cmds の
    ``connectAttr``/``setAttr`` などと同じく属性として扱う)。transform の名前で
    シェイプの属性を指す場合(``pCube1.pnts[3]``)は、唯一のシェイプ(中間オブジェクトを
    除く)へ伸ばして解決する。

    Args:
        text (str): 属性を指す名前。

    Returns:
        tuple[om2.MObject | om2.MDagPath, om2.MPlug] | None: 所有ノード(DAG ノードは
            名前が指すインスタンスの MDagPath)とプラグ。属性として解決できない場合
            (存在しない属性、範囲指定、配列でない属性へのインデックスなど)は None。
    """
    node_part, separator, attribute_path = text.partition(".")
    if not separator or not attribute_path:
        return None
    owner = om2.MSelectionList()
    try:
        owner.add(node_part)
    except RuntimeError:
        return None
    if owner.length() != 1:
        return None
    mobject = owner.getDependNode(0)
    dag_path = owner.getDagPath(0) if mobject.hasFn(om2.MFn.kDagNode) else None
    match = _PLUG_PATH_TOKEN.match(attribute_path.split(".", 1)[0])
    if match is None:
        return None
    first = _find_plug(mobject, match.group(1))
    if first is None:
        # transform の名前でシェイプの属性を指す場合は、唯一のシェイプで探す。
        if dag_path is None or not mobject.hasFn(om2.MFn.kTransform):
            return None
        shape_path = om2.MDagPath(dag_path)
        try:
            shape_path.extendToShape()
        except RuntimeError:
            return None
        mobject, dag_path = shape_path.node(), shape_path
        first = _find_plug(mobject, match.group(1))
        if first is None:
            return None
    mplug = attribute_path_plug(mobject, attribute_path, first)
    if mplug is None:
        return None
    return (dag_path if dag_path is not None else mobject), mplug


def to_plug(value):
    """対象を hlib の Plug インスタンスへ変換する。

    文字列は ``str(plug)``・``plug.full_name()`` が返す形式(``grp1|dup.translateX``、
    ``bs.weight[0]``、エイリアス名、``cubeShape.pnts[2].pntx`` など)を含め、
    maya.cmds と同じ規則で解決する。インスタンス化された DAG ノードの属性は、
    名前が指すインスタンスのノードを所有ノードにする。コンポーネント名としても
    解釈される属性(mesh の ``pnts[i]``、nurbsCurve・lattice の ``controlPoints[i]`` など)は、
    ``connectAttr`` などと同じく属性として解決する。

    Args:
        value (Plug | om2.MPlug | str): Plug、MPlug、または ``"node.attribute"`` 形式の属性名。

    Returns:
        Plug: value が Plug ならそのまま(削除済みでも例外にしない。``Plug.is_valid()`` で
            確かめる)、それ以外は属性型に応じた Plug ラッパー。

    Raises:
        TypeError: 対応しない型、または文字列が属性を指していない場合。
        ValueError: 空文字列、または空の MPlug の場合。
        RuntimeError: 文字列を解決できない(存在しない、または複数の対象に一致する)場合。
            MPlug の所有ノードが削除済み、または属性が ``deleteAttr`` で削除済みの場合
            (``Node(...)``・``Plug(...)`` の生成と同じ。Undo の対象から外れて削除された
            ノードの MPlug は検出できず、Maya が異常終了する)。
    """
    node_class, plug_class, _, _ = _classes()
    if isinstance(value, plug_class):
        return value
    if isinstance(value, om2.MPlug):
        if value.isNull:
            raise ValueError("空の MPlug は指定できません")
        return plug_class(node_class(value.node()), value)
    if isinstance(value, str):
        if not value:
            raise ValueError("空でない属性名を指定してください")
        selection = om2.MSelectionList()
        try:
            selection.add(value)
        except RuntimeError as error:
            raise RuntimeError(f"属性が見つかりません: {value}") from error
        if selection.length() != 1:
            raise RuntimeError(f"複数の対象に一致します。一意な属性名を指定してください: {value}")
        try:
            mplug = selection.getPlug(0)
        except TypeError as error:
            # pnts[i]・controlPoints[i] などは頂点・CV として登録されるため、属性パスを辿る。
            resolved = _plug_from_path(value)
            if resolved is None:
                raise TypeError(f"属性を指す名前ではありません: {value}") from error
            owner, mplug = resolved
            return plug_class(node_class(owner), mplug)
        mobject, dag_path = selection_owner(selection, 0, value)
        return plug_class(node_class(dag_path if dag_path is not None else mobject), mplug)
    raise TypeError(f"Plug、om2.MPlug、または属性名を指定してください: {type(value).__name__}")
