"""Mayaのサイクル候補と実接続を読み取り、原因調査用の画面を表示する。"""

import math
import time

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
from mlib.common import Selection
from mlib.plugs.plug import MissingAttributeError

from HTools import toolHelp


_WINDOW = "HToolsInspectCycles"
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


def _findPlug(text):
    """アトリビュート名をプラグへ解決する。

    ``pnts[i]`` のようにコンポーネントとしても解釈される名前や、transform の名前でシェイプの
    アトリビュートを指す名前も、アトリビュートとして解決する。インスタンスは名前が指すものになる。

    Args:
        text (str): ``"node.attribute"`` 形式の名前。

    Returns:
        mlib.Plug: プラグ。所有ノードは名前が指すインスタンスのパスを持つ。

    Raises:
        RuntimeError: 見つからない、または複数に一致する場合。
        TypeError: アトリビュートを指す名前ではない場合。
    """
    try:
        return mlib.getPlug(text)
    except MissingAttributeError:
        raise RuntimeError("Attribute not found: {}".format(text))
    except TypeError:
        raise TypeError("Not an attribute name: {}".format(text))
    except RuntimeError:
        raise RuntimeError("Matches multiple objects. Specify a unique attribute name: {}".format(text))


def _targetName(target):
    """調査対象の名前を、ノードは最短一意名、アトリビュートは ``Plug.getName(full=True)`` の形式へ揃える。

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
        return _findPlug(target).getName(full=True)
    try:
        return mlib.getNode(target).getName()
    except RuntimeError:
        raise RuntimeError("Node not found or not unique: {}".format(target))


def _findCycles(names, include_dag, seconds, first_only):
    """シーンを変更せず循環候補を検出する。

    Args:
        names (list[str] | None): 調査対象の名前。Noneでシーン全体。
        include_dag (bool): DAGの親子関係を検出に含める。
        seconds (float): 検索時間の上限(秒)。
        first_only (bool): 最初の完全なサイクルだけを要求する。

    Returns:
        list[list[mlib.Plug]]: 検出順のプラグの経路。
            完全な循環とは限らず部分経路も含む。
    """
    return [list(path) for path in mlib.findCycles(names, dag=include_dag, timeLimit=seconds, firstOnly=first_only)]


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
        for plug in cycle:
            try:
                plugs.append(plug.getName(full=True))
                node = plug.getNode()
                nodes[node.getName()] = node.getType()
                # 変換ノードを省略しない直接の入力元と出力先(経路外の接続も含む)。
                source = plug.getConnections(input=True)
                edges = [(source, plug)] if source is not None else []
                edges.extend((plug, dest) for dest in plug.getConnections(output=True))
                connections.update((a.getName(full=True), b.getName(full=True)) for a, b in edges)
                if isinstance(node, mlib.DagNode):
                    child = node.getName()
                    parents.update((parent.getName(full=True), child) for parent in node.getParent(instances=True))
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
        cmds.rowLayout(numberOfColumns=4, adjustableColumn=1)
        cmds.button(label="Select Nodes in Selected Path", command=self.selectNodes)
        cmds.button(label="Show All Results", command=self.showAll)
        cmds.button(label="Save All Results…", command=self.saveReport)
        # このツールの説明ページ(Sphinx)を開く。runpy で __main__ として動くので名前は文字列で渡す。
        cmds.button(label="Help", command=lambda *_: toolHelp.openHelp("rigging", "inspectCycles"))
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
                targets = [item.getName() if isinstance(item, mlib.Node) else str(item)
                           for item in Selection.capture().getItems()]
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
            found = mlib.ls(name, long=True)
            if len(found) == 1:
                nodes.append(found[0])
            else:
                _warn("Node not found. Inspect again: {}".format(name))
        if nodes:
            mlib.select(nodes, replace=True)

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
