"""Mayaのサイクル候補と実接続を読み取り、原因調査用の画面を表示する。"""

import math
import re
import time

import maya.api.OpenMaya as om2
import maya.cmds as cmds


_WINDOW = "HToolsInspectCycles"
_SEPARATOR = "__HTOOLS_CYCLE_SEPARATOR__"
#: アトリビュートパスの1区切り(``name`` または ``name[i]``)。
_PATH_TOKEN = re.compile(r"^([^\[\]]+)(?:\[(\d+)\])?$")
_LIMITATION = (
    "The detection order includes dependencies inside nodes, not only real connections, and may be a partial path.\n"
    "Direct connections are only hints for where to cut. They do not identify the cause or a safe place to cut.\n"
    "Results may be incomplete when the time limit is reached. Zero results do not prove there is no cycle.\n"
    "Runtime dependencies of expressions may be missed, and instances with IK may be reported falsely."
)



def _warn(message):
    """警告をScript Editorとビューポートへ表示する。

    Args:
        message (str): 表示する英語のメッセージ。
    """
    cmds.warning(message)
    text = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    try:
        cmds.inViewMessage(amg='<font color="#ffcc00">{}</font>'.format(text), pos="midCenter", fade=True)
    except RuntimeError:
        pass


def _ownerPath(mobject, text=None):
    """プラグを所有するノードのDAGパスを求める。

    Args:
        mobject (om2.MObject): 所有ノード。
        text (str | None): 名前で指定した場合の文字列。インスタンスの判別に使う。

    Returns:
        om2.MDagPath | None: 名前が指すインスタンス(無ければ最初のパス)。DGノードはNone。
    """
    if not mobject.hasFn(om2.MFn.kDagNode):
        return None
    fn = om2.MFnDagNode(mobject)
    if text and fn.isInstanced():
        selection = om2.MSelectionList()
        try:
            selection.add(text.split(".", 1)[0])
            path = selection.getDagPath(0)
        except (RuntimeError, TypeError):
            path = None
        if path is not None and path.node() == mobject:
            return path
        # transformの名前でシェイプのアトリビュートを指す場合は、そのインスタンスの下へ伸ばす。
        for index in range(path.childCount() if path is not None else 0):
            if path.child(index) == mobject:
                path.push(mobject)
                return path
    return fn.getPath()


def _pathPlug(text):
    """``pnts[i]`` のようにコンポーネントとしても解釈される名前を、アトリビュートとして辿る。

    Args:
        text (str): ``"node.attr[i].child"`` 形式の名前。

    Returns:
        om2.MPlug: 解決したプラグ。

    Raises:
        TypeError: アトリビュートとして解決できない場合。
    """
    node, _, path = text.partition(".")
    selection = om2.MSelectionList()
    selection.add(node)
    fn = om2.MFnDependencyNode(selection.getDependNode(0))
    if fn.object().hasFn(om2.MFn.kTransform) and not fn.hasAttribute(path.split("[", 1)[0]):
        # transformの名前でシェイプのアトリビュートを指す場合は、唯一のシェイプで探す。
        shape = selection.getDagPath(0)
        try:
            shape.extendToShape()
        except RuntimeError:
            raise TypeError("Not an attribute name: {}".format(text))
        fn = om2.MFnDependencyNode(shape.node())
    mplug = None
    for token in path.split("."):
        match = _PATH_TOKEN.match(token)
        if match is None or not fn.hasAttribute(match.group(1)):
            raise TypeError("Not an attribute name: {}".format(text))
        attribute = fn.attribute(match.group(1))
        mplug = om2.MPlug(fn.object(), attribute) if mplug is None else mplug.child(attribute)
        if match.group(2) is not None:
            mplug = mplug.elementByLogicalIndex(int(match.group(2)))
    return mplug


def _findPlug(text):
    """アトリビュート名をプラグと所有ノードのDAGパスへ解決する。

    Args:
        text (str): ``"node.attribute"`` 形式の名前。

    Returns:
        tuple[om2.MPlug, om2.MDagPath | None]: プラグと所有ノードのパス。

    Raises:
        RuntimeError: 見つからない、または複数に一致する場合。
        TypeError: アトリビュートを指す名前ではない場合。
    """
    selection = om2.MSelectionList()
    try:
        selection.add(text)
    except RuntimeError:
        raise RuntimeError("Attribute not found: {}".format(text))
    if selection.length() != 1:
        raise RuntimeError("Matches multiple objects. Specify a unique attribute name: {}".format(text))
    try:
        mplug = selection.getPlug(0)
    except TypeError:
        mplug = _pathPlug(text)
    return mplug, _ownerPath(mplug.node(), text)


def _plugName(mplug, path):
    """最短一意のノード名とロング名のアトリビュートパスでプラグ名を作る。

    Args:
        mplug (om2.MPlug): 対象のプラグ。
        path (om2.MDagPath | None): 所有ノードのDAGパス。DGノードはNone。

    Returns:
        str: maya.cmdsで一意に解決できるプラグ名。
    """
    if path is None or (not path.isInstanced() and path.pathCount() == 1
                        and om2.MFnDependencyNode(mplug.node()).hasUniqueName()):
        return mplug.name()
    return path.partialPathName() + "." + mplug.partialName(False, True, True, True, False, True)


def _targetName(target):
    """調査対象の名前を、ノードは最短一意名、アトリビュートは :func:`_plugName` の形式へ揃える。

    Args:
        target (str): ノード名またはアトリビュート名。

    Returns:
        str: cycleCheckへ渡す名前。

    Raises:
        TypeError: 文字列以外、またはアトリビュートを指さない名前の場合。
        RuntimeError: 見つからない、または複数に一致する場合。
    """
    if not isinstance(target, str):
        raise TypeError("Specify node or attribute names.")
    if "." in target:
        return _plugName(*_findPlug(target))
    selection = om2.MSelectionList()
    try:
        selection.add(target)
    except RuntimeError:
        raise RuntimeError("Node not found or not unique: {}".format(target))
    mobject = selection.getDependNode(0)
    if mobject.hasFn(om2.MFn.kDagNode):
        return selection.getDagPath(0).partialPathName()
    return om2.MFnDependencyNode(mobject).name()


def _findCycles(names, include_dag, seconds, first_only):
    """シーンを変更せず循環候補を検出する。

    Args:
        names (list[str] | None): 調査対象の名前。Noneでシーン全体。
        include_dag (bool): DAGの親子関係を検出に含める。
        seconds (float): 検索時間の上限(秒)。
        first_only (bool): 最初の完全なサイクルだけを要求する。

    Returns:
        list[list[tuple[om2.MPlug, om2.MDagPath | None]]]: 検出順のプラグの経路。
            完全な循環とは限らず部分経路も含む。
    """
    options = dict(list=True, dag=include_dag, secondary=True,
                   timeLimit="{}sec".format(seconds), listSeparator=_SEPARATOR,
                   firstCycleOnly=first_only)
    if names is None:
        options["all"] = True
    paths, current = [], []
    for name in (cmds.cycleCheck(*(names or []), **options) or []) + [_SEPARATOR]:
        if name != _SEPARATOR:
            current.append(name)
        elif current:
            paths.append(current)
            current = []
    return [[_findPlug(name) for name in path] for path in paths]


def inspectCycles(targets=None, include_dag=True, seconds=10.0, first_only=False):
    """循環の照会結果を画面・保存用の文字列スナップショットへ変換する。

    Args:
        targets (Iterable[str] | str | None): 調査対象のノード名・アトリビュート名。Noneで全体。
        include_dag (bool): DAGを含める。
        seconds (float): 検索上限秒数。
        first_only (bool): 最初の完全なサイクルだけを要求する。

    Returns:
        dict: 検索条件・経過時間・経路・読み取り失敗。

    Raises:
        ValueError: 空の対象または不正な時間上限。
        TypeError: 対象の型が不正。
        RuntimeError: 検索または検出アトリビュートの解決に失敗。
    """
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Specify a finite search limit greater than 0 seconds.")
    names = None
    if targets is not None:
        targets = [targets] if isinstance(targets, str) else list(targets)
        names = [_targetName(target) for target in targets]
        if not names:
            raise ValueError("Select the nodes to inspect.")
    started = time.monotonic()
    cycles = _findCycles(names, include_dag, seconds, first_only)
    elapsed = time.monotonic() - started
    groups = []
    for cycle in cycles:
        nodes, connections, parents, errors = {}, set(), set(), []
        plugs = []
        for mplug, path in cycle:
            try:
                plugs.append(_plugName(mplug, path))
                fn = om2.MFnDependencyNode(mplug.node())
                nodes[path.partialPathName() if path is not None else fn.name()] = fn.typeName
                # 変換ノードを省略しない直接の入力元と出力先(経路外の接続も含む)。
                here = (mplug, path)
                edges = [((source, _ownerPath(source.node())), here) for source in mplug.connectedTo(True, False)[:1]]
                edges.extend((here, (dest, _ownerPath(dest.node()))) for dest in mplug.connectedTo(False, True))
                connections.update((_plugName(*a), _plugName(*b)) for a, b in edges)
                if path is not None:
                    child = path.partialPathName()
                    parents.update((parent, child) for parent in cmds.listRelatives(
                        path.fullPathName(), allParents=True, fullPath=True) or [])
            except (RuntimeError, ValueError, TypeError) as error:
                errors.append(str(error))
        groups.append(dict(plugs=plugs, nodes=nodes, connections=sorted(connections),
                           parents=sorted(parents), errors=errors))
    return dict(targets=names, includeDag=include_dag, seconds=seconds,
                elapsed=elapsed, firstOnly=first_only, groups=groups)


def formatReport(result, indices=None):
    """検出順と確認済みの実接続を区別したレポートを作る。

    Args:
        result (dict): inspectCyclesの戻り値。
        indices (Iterable[int] | None): 表示する経路の0始まりインデックス。

    Returns:
        str: コピー・保存できる調査レポート。
    """
    lines = ["Maya cycle inspection", "Targets: " + (", ".join(result["targets"]) if result["targets"] else "entire scene"),
             "DAG: {} / limit: {} s / search: {:.3f} s / first only: {}".format(
                 result["includeDag"], result["seconds"], result["elapsed"], result["firstOnly"]),
             "Detected paths: {}".format(len(result["groups"])), "", _LIMITATION]
    if indices is None:
        indices = range(len(result["groups"]))
    for index in indices:
        group = result["groups"][index]
        lines.extend(["", "=== Path {} (complete or partial) ===".format(index + 1), "Detection order:"])
        lines.extend("  {}. {}".format(i + 1, name) for i, name in enumerate(group["plugs"]))
        lines.append("Nodes and types:")
        lines.extend("  {} ({})".format(name, kind) for name, kind in group["nodes"].items())
        lines.append("Direct connections of the detected attributes (including connections outside the path):")
        lines.extend("  {} -> {}".format(*pair) for pair in group["connections"])
        lines.append("Parent-child relationships (parent -> child; verify the dependency separately):")
        lines.extend("  {} -> {}".format(*pair) for pair in group["parents"])
        if group["errors"]:
            lines.append("Read failures (inspect again):")
            lines.extend("  " + error for error in group["errors"])
    return "\n".join(lines)


class CycleInspector:
    """検出経路の絞り込み、ノード選択、レポート保存を行うMaya標準UI。"""

    def __init__(self):
        """結果を保持し、同名の既存ウィンドウを置き換える。"""
        self.result = None
        if cmds.window(_WINDOW, exists=True):
            cmds.deleteUI(_WINDOW)
        self.window = cmds.window(_WINDOW, title="Cycle Inspector", widthHeight=(820, 760))
        cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
        cmds.text(label="Inspects connections and parent-child relationships. Results reflect the scene at inspection time.", align="left")
        self.scope = cmds.radioButtonGrp(numberOfRadioButtons=3, label="Target",
                                        labelArray3=["Scene", "Selection", "By name"], select=1)
        self.target = cmds.textFieldGrp(label="Node / attribute", placeholderText="e.g. rig:joint1.translateX")
        self.dag = cmds.checkBox(label="Include DAG parent-child relationships", value=True)
        self.first = cmds.checkBox(label="First complete cycle only", value=False)
        self.seconds = cmds.floatFieldGrp(numberOfFields=1, label="Search limit (s)", value1=10.0)
        self.scan_button = cmds.button(label="Inspect", command=self.scan)
        self.status = cmds.text(label="Not inspected", align="left")
        self.paths = cmds.textScrollList(height=130, allowMultiSelection=True,
                                        selectCommand=self.showDetails)
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=1)
        cmds.button(label="Select Nodes in Selected Path", command=self.selectNodes)
        cmds.button(label="Show All Results", command=self.showAll)
        cmds.button(label="Save All Results…", command=self.saveReport)
        cmds.setParent("..")
        self.details = cmds.scrollField(editable=False, wordWrap=False, height=340, text=_LIMITATION)
        cmds.showWindow(self.window)

    def scan(self, *_):
        """UIの条件で調査し、古い結果を消してから新しい結果を表示する。

        Args:
            *_: Maya UIコールバックから渡される未使用の引数。
        """
        self.result = None
        cmds.textScrollList(self.paths, edit=True, removeAll=True)
        cmds.scrollField(self.details, edit=True, text="Inspecting…")
        cmds.text(self.status, edit=True, label="Inspecting…")
        cmds.button(self.scan_button, edit=True, enable=False)
        try:
            scope = cmds.radioButtonGrp(self.scope, query=True, select=True)
            targets = None
            if scope == 2:
                targets = cmds.ls(selection=True)
            elif scope == 3:
                targets = cmds.textFieldGrp(self.target, query=True, text=True).split()
            self.result = inspectCycles(
                targets, cmds.checkBox(self.dag, query=True, value=True),
                cmds.floatFieldGrp(self.seconds, query=True, value1=True),
                cmds.checkBox(self.first, query=True, value=True))
            for index, group in enumerate(self.result["groups"]):
                cmds.textScrollList(self.paths, edit=True, append="{}: {} nodes / {}".format(
                    index + 1, len(group["nodes"]), group["plugs"][0]))
            cmds.text(self.status, edit=True, label="{} paths detected (time-limited; completeness is not guaranteed)".format(
                len(self.result["groups"])))
            self.showAll()
        except (RuntimeError, ValueError, TypeError) as error:
            cmds.text(self.status, edit=True, label="Inspection failed")
            cmds.scrollField(self.details, edit=True, text=str(error))
            _warn(str(error))
        finally:
            cmds.button(self.scan_button, edit=True, enable=True)

    def showDetails(self, *_):
        """一覧で選択された経路だけを詳細表示する。

        Args:
            *_: Maya UIコールバックから渡される未使用の引数。
        """
        if self.result is not None:
            indices = cmds.textScrollList(self.paths, query=True, selectIndexedItem=True) or []
            cmds.scrollField(self.details, edit=True, text=formatReport(self.result, [i - 1 for i in indices]))

    def showAll(self, *_):
        """全経路のレポートを表示する。

        Args:
            *_: Maya UIコールバックから渡される未使用の引数。
        """
        if self.result is not None:
            cmds.scrollField(self.details, edit=True, text=formatReport(self.result))

    def selectNodes(self, *_):
        """選択経路の現存ノードを選択する。

        Args:
            *_: Maya UIコールバックから渡される未使用の引数。
        """
        indices = cmds.textScrollList(self.paths, query=True, selectIndexedItem=True) or []
        if self.result is None or not indices:
            _warn("Select a path in the list.")
            return
        names = dict.fromkeys(name for i in indices for name in self.result["groups"][i - 1]["nodes"])
        nodes = []
        for name in names:
            found = cmds.ls(name, long=True) or []
            if len(found) == 1:
                nodes.append(found[0])
            else:
                _warn("Node not found. Inspect again: {}".format(name))
        if nodes:
            cmds.select(nodes, replace=True)

    def saveReport(self, *_):
        """保存先を選び、全結果をUTF-8のテキストとして保存する。

        Args:
            *_: Maya UIコールバックから渡される未使用の引数。
        """
        if self.result is None:
            _warn("Run the inspection first.")
            return
        paths = cmds.fileDialog2(fileMode=0, caption="Save Cycle Inspection Report", fileFilter="Text (*.txt)")
        if paths:
            try:
                with open(paths[0], "w", encoding="utf-8") as stream:
                    stream.write(formatReport(self.result))
                om2.MGlobal.displayInfo("Saved the report: {}".format(paths[0]))
            except OSError as error:
                _warn("Could not save: {}".format(error))


def run():
    """調査ウィンドウを表示する。

    Returns:
        CycleInspector: 表示したUIのインスタンス。
    """
    return CycleInspector()


if __name__ == "__main__":
    run()
