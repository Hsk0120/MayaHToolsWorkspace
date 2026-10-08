"""Mayaのサイクル候補と実接続を読み取り、原因調査用の画面を表示する。"""

import time

import maya.cmds as cmds

import hlib
from hlib.nodes import Node
from hlib.common import Cycle
from hlib.plugs import Plug
from hlib import logger


_WINDOW = "HToolsInspectCycles"
_LIMITATION = (
    "The detection order includes dependencies inside nodes, not only real connections, and may be a partial path.\n"
    "Direct connections are only hints for where to cut. They do not identify the cause or a safe place to cut.\n"
    "Results may be incomplete when the time limit is reached. Zero results do not prove there is no cycle.\n"
    "Runtime dependencies of expressions may be missed, and instances with IK may be reported falsely."
)



def inspectCycles(targets=None, include_dag=True, seconds=10.0, first_only=False):
    """Cycleの照会結果を画面・保存用の文字列スナップショットへ変換する。

    Args:
        targets (Iterable[str | Node | Plug] | None): 調査対象。Noneで全体。
        include_dag (bool): DAGを含める。
        seconds (float): 検索上限秒数。
        first_only (bool): 最初の完全なサイクルだけを要求する。

    Returns:
        dict: 検索条件・経過時間・経路・読み取り失敗。
    """
    if targets is not None:
        targets = [targets] if isinstance(targets, (str, Node, Plug)) else list(targets)
    started = time.monotonic()
    cycles = Cycle.find(targets, include_dag, seconds, first_only)
    elapsed = time.monotonic() - started
    groups = []
    for cycle in cycles:
        nodes, connections, parents, errors = {}, set(), set(), []
        names = []
        for plug in cycle.plugs:
            try:
                names.append(plug.getFullName())
                node = plug.getNode()
                nodes[node.getName()] = node.getType()
                part = Cycle([plug])
                connections.update((a.getFullName(), b.getFullName()) for a, b in part.getConnections())
                parents.update((a.getFullName(), b.getName()) for a, b in part.getParents())
            except (RuntimeError, ValueError, TypeError) as error:
                errors.append(str(error))
        groups.append(dict(plugs=names, nodes=nodes, connections=sorted(connections),
                           parents=sorted(parents), errors=errors))
    names = None
    if targets is not None:
        names = []
        for target in targets:
            if isinstance(target, str):
                target = hlib.getPlug(target) if "." in target else Node(target)
            names.append(target.getFullName() if isinstance(target, Plug) else target.getName())
    return dict(targets=names, includeDag=include_dag, seconds=float(seconds),
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
                targets = hlib.ls(selection=True)
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
            logger.warning(str(error))
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
        """選択経路の現存ノードをhlibで解決して選択する。

        Args:
            *_: Maya UIコールバックから渡される未使用の引数。
        """
        indices = cmds.textScrollList(self.paths, query=True, selectIndexedItem=True) or []
        if self.result is None or not indices:
            logger.warning("Select a path in the list.")
            return
        names = dict.fromkeys(name for i in indices for name in self.result["groups"][i - 1]["nodes"])
        nodes = []
        for name in names:
            try:
                nodes.append(Node(name))
            except (RuntimeError, ValueError):
                logger.warning("Node not found. Inspect again: {}".format(name))
        if nodes:
            hlib.select(nodes, replace=True)

    def saveReport(self, *_):
        """保存先を選び、全結果をUTF-8のテキストとして保存する。

        Args:
            *_: Maya UIコールバックから渡される未使用の引数。
        """
        if self.result is None:
            logger.warning("Run the inspection first.")
            return
        paths = cmds.fileDialog2(fileMode=0, caption="Save Cycle Inspection Report", fileFilter="Text (*.txt)")
        if paths:
            try:
                with open(paths[0], "w", encoding="utf-8") as stream:
                    stream.write(formatReport(self.result))
                logger.info("Saved the report: {}".format(paths[0]))
            except OSError as error:
                logger.warning("Could not save: {}".format(error))


def run():
    """調査ウィンドウを表示する。

    Returns:
        CycleInspector: 表示したUIのインスタンス。
    """
    return CycleInspector()


if __name__ == "__main__":
    run()
