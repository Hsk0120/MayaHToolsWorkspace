"""バーのボタンから選べる選択セット(objectSet)を作る・使う・書き出す。

セットは ``animBarSelectSets`` という親のセットの中に置き、色の番号と表示名をアトリビュートに持つ。
シーンに保存されるので、ファイルを開き直しても残る。JSON への書出し・読込みもできる。
"""

import json

import mlib
from mlib.decorator import undoChunk

from . import keys

#: 選択セットをまとめる親のセットの名前。
ROOT_SET = "animBarSelectSets"

#: 色の番号を置くアトリビュート名。
COLOR_ATTRIBUTE = "animBarColor"

#: 表示名を置くアトリビュート名。
LABEL_ATTRIBUTE = "animBarLabel"

#: 選べる色の数(UIの色の表の数と同じ)。
COLOR_COUNT = 8


def sets():
    """選択セットを作った順に返す。

    Returns:
        list[ObjectSet]: 選択セット。
    """
    if not mlib.objExists(ROOT_SET):
        return []
    root = mlib.nodes.Node(ROOT_SET)
    return [member for member in root.getMembers() if isinstance(member, mlib.nodes.ObjectSet)]


def label(node):
    """選択セットの表示名を返す。

    Args:
        node (ObjectSet): 選択セット。

    Returns:
        str: 表示名。
    """
    return node.getPlug(LABEL_ATTRIBUTE).get() if node.hasAttr(LABEL_ATTRIBUTE) else node.getNodeName()


def color(node):
    """選択セットの色の番号を返す。

    Args:
        node (ObjectSet): 選択セット。

    Returns:
        int: 色の番号(0〜COLOR_COUNT-1)。
    """
    return int(node.getPlug(COLOR_ATTRIBUTE).get()) if node.hasAttr(COLOR_ATTRIBUTE) else 0


@undoChunk("animBarCreateSelectSet")
def createSet(name, members=None, colorIndex=0):
    """選択セットを作る。

    Args:
        name (str): 表示名。
        members (Iterable | None): メンバー。Noneは今の選択。
        colorIndex (int): 色の番号。

    Returns:
        ObjectSet: 作ったセット。

    Raises:
        ValueError: 名前が空、またはメンバーが無い場合。
    """
    if not name or not name.strip():
        raise ValueError("Select set name must not be empty")
    members = keys.selectedNodes() if members is None else list(members)
    if not members:
        raise ValueError("Select at least one object for the select set")
    root = _root()
    node = mlib.createNode("objectSet", name="animBarSet_" + mlib.util.legalizeName(name.strip()), skipSelect=True)
    node.addAttr(longName=LABEL_ATTRIBUTE, dataType="string").set(name.strip())
    node.addAttr(longName=COLOR_ATTRIBUTE, attributeType="long", defaultValue=int(colorIndex) % COLOR_COUNT)
    node.addMembers(*members)
    root.addMembers(node)
    return node


@undoChunk("animBarEditSelectSet")
def editSet(node, add=None, remove=None, name=None, colorIndex=None):
    """選択セットのメンバー・表示名・色を変える。

    Args:
        node (ObjectSet): 選択セット。
        add (Iterable | None): 足すメンバー。
        remove (Iterable | None): 外すメンバー。
        name (str | None): 新しい表示名。
        colorIndex (int | None): 新しい色の番号。

    Returns:
        ObjectSet: 選択セット。
    """
    if add:
        node.addMembers(*add)
    if remove:
        node.removeMembers(*remove)
    if name:
        node.getPlug(LABEL_ATTRIBUTE).set(name.strip())
    if colorIndex is not None:
        node.getPlug(COLOR_ATTRIBUTE).set(int(colorIndex) % COLOR_COUNT)
    return node


@undoChunk("animBarDeleteSelectSet")
def deleteSet(node):
    """選択セットを消す(メンバーのノードは消さない)。

    Args:
        node (ObjectSet): 選択セット。

    Returns:
        None: 値を返さない。
    """
    mlib.delete(node)


def selectSet(node, mode="replace"):
    """選択セットのメンバーを選ぶ。

    Args:
        node (ObjectSet): 選択セット。
        mode (str): ``"replace"``・``"add"``・``"remove"``・``"toggle"``。

    Returns:
        list: 選んだメンバー。
    """
    members = node.getMembers()
    flags = {"replace": {"replace": True}, "add": {"add": True}, "remove": {"deselect": True},
             "toggle": {"toggle": True}}
    if mode not in flags:
        raise ValueError("mode must be replace, add, remove or toggle")
    mlib.select(members, **flags[mode]) if members else (mlib.select(clear=True) if mode == "replace" else None)
    return members


def exportSets(path):
    """選択セットを JSON へ書き出す。メンバーは名前空間を除いた名前で書く。

    Args:
        path (str): 書き出すファイル。

    Returns:
        int: 書き出したセットの数。
    """
    data = [{"label": label(node), "color": color(node),
             "members": [_plain_name(member) for member in node.getMembers()]} for node in sets()]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return len(data)


@undoChunk("animBarImportSelectSets")
def importSets(path, namespace=""):
    """JSON の選択セットを読み込む。見つからないメンバーは飛ばす。

    Args:
        path (str): 読み込むファイル。
        namespace (str): メンバーの名前の前に付ける名前空間(``"char1"`` 等。空は付けない)。

    Returns:
        list[ObjectSet]: 作ったセット。
    """
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    prefix = namespace.rstrip(":") + ":" if namespace else ""
    created = []
    for entry in data:
        members = [prefix + name for name in entry.get("members", []) if mlib.objExists(prefix + name)]
        if members:
            created.append(createSet(entry["label"], members, entry.get("color", 0)))
    return created


def _root():
    """親のセットを返す(無ければ作る)。

    Returns:
        ObjectSet: 親のセット。
    """
    if mlib.objExists(ROOT_SET):
        return mlib.nodes.Node(ROOT_SET)
    return mlib.createNode("objectSet", name=ROOT_SET, skipSelect=True)


def _plain_name(member):
    """メンバーの名前から名前空間を除く。

    Args:
        member (Node | str): メンバー。

    Returns:
        str: 名前空間を除いた名前。
    """
    if isinstance(member, str):
        return member.rpartition(":")[2]
    return member.getNodeName(removeNamespace=True)
