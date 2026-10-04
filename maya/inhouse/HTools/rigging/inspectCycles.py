"""Mayaのサイクル候補と実接続を読み取り、原因調査用の画面を表示する。"""

import time

import maya.cmds as cmds

import hlib
from hlib.nodes import Node
from hlib.scene import Cycle
from hlib.plugs import Plug
from hlib.utils import logger


_WINDOW = "HToolsInspectCycles"
_LIMITATION = (
    "検出順は実接続だけでなくノード内部の依存を含み、部分経路の場合もあります。\n"
    "直接接続は切断候補の参考情報です。原因や安全な切断箇所を断定するものではありません。\n"
    "時間制限時の結果は未完了の可能性があります。0件でもサイクルなしとは断定できません。\n"
    "expressionの実行時依存は検出できない場合があり、IK付きインスタンスは誤検出の場合があります。"
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
                names.append(plug.fullName())
                node = plug.node
                nodes[node.name()] = node.type()
                part = Cycle([plug])
                connections.update((a.fullName(), b.fullName()) for a, b in part.getConnections())
                parents.update((a.fullName(), b.name()) for a, b in part.getParents())
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
            names.append(target.fullName() if isinstance(target, Plug) else target.name())
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
    lines = ["Maya サイクル調査", "対象: " + (", ".join(result["targets"]) if result["targets"] else "シーン全体"),
             "DAG: {} / 上限: {}秒 / 検索: {:.3f}秒 / 最初のみ: {}".format(
                 result["includeDag"], result["seconds"], result["elapsed"], result["firstOnly"]),
             "検出経路: {}件".format(len(result["groups"])), "", _LIMITATION]
    if indices is None:
        indices = range(len(result["groups"]))
    for index in indices:
        group = result["groups"][index]
        lines.extend(["", "=== 経路 {}（完全・部分経路） ===".format(index + 1), "検出順:"])
        lines.extend("  {}. {}".format(i + 1, name) for i, name in enumerate(group["plugs"]))
        lines.append("ノードと型:")
        lines.extend("  {} ({})".format(name, kind) for name, kind in group["nodes"].items())
        lines.append("検出アトリビュートの直接接続（経路外への接続も含む）:")
        lines.extend("  {} -> {}".format(*pair) for pair in group["connections"])
        lines.append("親子関係（親 -> 子。依存の成立は別途確認）:")
        lines.extend("  {} -> {}".format(*pair) for pair in group["parents"])
        if group["errors"]:
            lines.append("読み取り失敗（再調査してください）:")
            lines.extend("  " + error for error in group["errors"])
    return "\n".join(lines)


class CycleInspector:
    """検出経路の絞り込み、ノード選択、レポート保存を行うMaya標準UI。"""

    def __init__(self):
        """結果を保持し、同名の既存ウィンドウを置き換える。"""
        self.result = None
        if cmds.window(_WINDOW, exists=True):
            cmds.deleteUI(_WINDOW)
        self.window = cmds.window(_WINDOW, title="サイクル原因調査", widthHeight=(820, 760))
        cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
        cmds.text(label="接続・親子関係を調査します。結果は調査時点の情報です。", align="left")
        self.scope = cmds.radioButtonGrp(numberOfRadioButtons=3, label="対象",
                                        labelArray3=["全体", "選択", "名前指定"], select=1)
        self.target = cmds.textFieldGrp(label="ノード / アトリビュート", placeholderText="例: rig:joint1.translateX")
        self.dag = cmds.checkBox(label="DAGの親子関係を含める", value=True)
        self.first = cmds.checkBox(label="最初の完全なサイクルのみ", value=False)
        self.seconds = cmds.floatFieldGrp(numberOfFields=1, label="検索上限（秒）", value1=10.0)
        self.scan_button = cmds.button(label="調査", command=self.scan)
        self.status = cmds.text(label="未調査", align="left")
        self.paths = cmds.textScrollList(height=130, allowMultiSelection=True,
                                        selectCommand=self.showDetails)
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=1)
        cmds.button(label="選択した経路のノードを選択", command=self.selectNodes)
        cmds.button(label="全結果を表示", command=self.showAll)
        cmds.button(label="全結果を保存…", command=self.saveReport)
        cmds.setParent("..")
        self.details = cmds.scrollField(editable=False, wordWrap=False, height=340, text=_LIMITATION)
        cmds.showWindow(self.window)

    def scan(self, *_):
        """UIの条件で調査し、古い結果を消してから新しい結果を表示する。"""
        self.result = None
        cmds.textScrollList(self.paths, edit=True, removeAll=True)
        cmds.scrollField(self.details, edit=True, text="調査中…")
        cmds.text(self.status, edit=True, label="調査中…")
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
                cmds.textScrollList(self.paths, edit=True, append="{}: {} ノード / {}".format(
                    index + 1, len(group["nodes"]), group["plugs"][0]))
            cmds.text(self.status, edit=True, label="{} 経路を検出（時間制限あり・完全性は保証されません）".format(
                len(self.result["groups"])))
            self.showAll()
        except (RuntimeError, ValueError, TypeError) as error:
            cmds.text(self.status, edit=True, label="調査失敗")
            cmds.scrollField(self.details, edit=True, text=str(error))
            logger.warning(str(error))
        finally:
            cmds.button(self.scan_button, edit=True, enable=True)

    def showDetails(self, *_):
        """一覧で選択された経路だけを詳細表示する。"""
        if self.result is not None:
            indices = cmds.textScrollList(self.paths, query=True, selectIndexedItem=True) or []
            cmds.scrollField(self.details, edit=True, text=formatReport(self.result, [i - 1 for i in indices]))

    def showAll(self, *_):
        """全経路のレポートを表示する。"""
        if self.result is not None:
            cmds.scrollField(self.details, edit=True, text=formatReport(self.result))

    def selectNodes(self, *_):
        """選択経路の現存ノードをhlibで解決して選択する。"""
        indices = cmds.textScrollList(self.paths, query=True, selectIndexedItem=True) or []
        if self.result is None or not indices:
            logger.warning("一覧から調査する経路を選択してください。")
            return
        names = dict.fromkeys(name for i in indices for name in self.result["groups"][i - 1]["nodes"])
        nodes = []
        for name in names:
            try:
                nodes.append(Node(name))
            except (RuntimeError, ValueError):
                logger.warning("ノードが見つかりません。再調査してください: {}".format(name))
        if nodes:
            hlib.select(nodes, replace=True)

    def saveReport(self, *_):
        """保存先を選び、全結果をUTF-8のテキストとして保存する。"""
        if self.result is None:
            logger.warning("先に調査を実行してください。")
            return
        paths = cmds.fileDialog2(fileMode=0, caption="サイクル調査レポートを保存", fileFilter="Text (*.txt)")
        if paths:
            try:
                with open(paths[0], "w", encoding="utf-8") as stream:
                    stream.write(formatReport(self.result))
                logger.info("レポートを保存しました: {}".format(paths[0]))
            except OSError as error:
                logger.warning("保存できませんでした: {}".format(error))


def run():
    """調査ウィンドウを表示する。

    Returns:
        CycleInspector: 表示したUIのインスタンス。
    """
    return CycleInspector()


if __name__ == "__main__":
    run()
