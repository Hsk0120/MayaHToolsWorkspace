"""mlib の公開書込み API が Undo 1 回で変更前へ戻り、Redo で変更後へ戻ることを網羅的に確かめる。

構成:

- **検査ハーネス**: 1 件ごとに専用の子名前空間をカレントにして対象を用意し、変更前のスナップショット
  (関係ノードの UUID・名前・親子・ロック・全アトリビュート値・接続・ロック/キー/Channel Box の一覧・
  別名・enum 名・container の公開名、シーン全体の UUID 集合・選択・名前空間・カレント名前空間・
  カレントのディスプレイレイヤー)を取る。対象を通常経路(fast=False)で 1 回呼び、``cmds.undo()`` を
  1 回行って変更前と一致すること、``cmds.redo()`` で変更後と一致することを確かめる。
  戻らない場合は、Undo キュー名と残った差分、何回の Undo で戻るかを失敗メッセージに載せる。
- **ケース表** (``CASES``): シーンを変更する公開メソッド・関数を 1 行ずつ載せ、``subTest`` で回す。
- **網羅の番人** (``CoverageGuardTest``): 公開クラス・関数を inspect で列挙し、``fast`` 引数を持つか
  書込みを表す名前で始まるものが、ケース表か理由付きの除外表 (``EXCLUDED``) に載っていることを確かめる。
  新しい書込み API を追加するとこのテストが落ちるので、ケースを追加する。
- **fast=True の確認**: fast を持つ API は fast=True で Undo キューに何も積まないことを確かめる。

製品の不具合で失敗するケースは expectedFailure にせず、そのまま失敗として残す。
調査用に、環境変数 ``MLIB_UNDO_COVERAGE_ONLY`` へラベルの一部をカンマ区切りで指定すると、
一致するケースだけを実行する(未設定なら全件)。
"""

import inspect
import os
import re
import shutil
import sys
import tempfile
import traceback
import unittest
from pathlib import Path

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib import decorator
from mlib.common.drivenKey import DrivenKey
from mlib.common.namespace import Namespace
from mlib.common.scalarGraph import ScalarGraph
from mlib.common.selection import Selection
from mlib.maths import Matrix
from mlib.nodes import Container, DagContainer, DagPose, NurbsCurve, SkinCluster
from support.specCase import NamespaceCase


#: 関係ノードとして常にスナップショットへ含める既定ノード(割当て・レイヤー移動の検出用)。
DEFAULT_TRACKED = ("defaultLayer", "layerManager", "initialShadingGroup")

#: スナップショットで比べる小数の桁数。
FLOAT_PLACES = 6

#: 診断として試す Undo の最大回数。
MAX_UNDO_STEPS = 10

#: 差分メッセージに載せる最大行数。
MAX_DIFF_LINES = 25

#: 書込みと判断する名前の先頭(直後が大文字・数字・末尾のもの)。
WRITER_PREFIXES = (
    "set", "add", "remove", "connect", "disconnect", "create", "delete", "rename", "reset",
    "lock", "unlock", "mute", "unmute", "freeze", "bind", "unbind", "transfer", "redistribute",
    "copy", "load", "unload", "publish", "unpublish", "match", "mirror", "scale", "move", "parent",
    "reparent", "select", "duplicate", "restore", "append", "center", "make", "jointOrientToRotate",
    "normalize", "shift", "toggle", "show", "hide", "assign", "apply", "clear", "ensure", "try",
    "stop", "insert", "replace", "break", "bake", "key", "snap", "edit", "write", "save",
)
WRITER_PATTERN = re.compile(r"^(?:{})(?:[A-Z0-9_]|$)".format("|".join(WRITER_PREFIXES)))

#: 書込みとして扱う特殊メソッド(接続演算子)。
WRITER_OPERATORS = ("__rshift__", "__lshift__", "__floordiv__")

#: 網羅の番人が拾っても Undo 検査の対象にしない API と理由。
EXCLUDED = {
    "Reference.load": "外部ファイルの参照の読込み(ファイル I/O)。Undo 検査の対象外。",
    "Reference.unload": "外部ファイルの参照のアンロード(ファイル I/O)。Undo 検査の対象外。",
    "Reference.remove": "外部ファイルの参照の削除(ファイル I/O)。Undo 検査の対象外。",
    "common.references.createReference": "外部ファイルの参照作成(ファイル I/O)。Undo 検査の対象外。",
    "Plugin.load": "プラグイン管理。loadPlugin は Maya の Undo 対象外。",
    "Plugin.unload": "プラグイン管理。unloadPlugin は Maya の Undo 対象外。",
    "Plugin.ensureLoaded": "プラグイン管理。loadPlugin は Maya の Undo 対象外。",
    "Plugin.ensureNodePlugin": "プラグイン管理。loadPlugin は Maya の Undo 対象外。",
    "PluginPackage.loadPlugins": "プラグイン管理。loadPlugin は Maya の Undo 対象外。",
    "PluginPackage.tryLoad": "プラグイン管理とダイアログ表示。Undo 対象外。",
    "PluginPackage.showDialog": "UI のダイアログ表示だけでシーンを変更しない。",
    "ScriptJobs.add": "scriptJob の登録。Maya の Undo 対象外のイベント監視。",
    "ScriptJobs.stop": "scriptJob の解除。Maya の Undo 対象外のイベント監視。",
    "ScriptJob.stop": "scriptJob の解除。Maya の Undo 対象外のイベント監視。",
    "Nodes.copy": "Python のコレクションの複製で、シーンを変更しない。",
    "util.mirrorArguments": "ミラー用の引数を計算するだけで、シーンを変更しない。",
    "Version.replace": "版番号の値を作り直すだけで、シーンを変更しない。",
}


#: fast 引数を持つが fast=True を常に NotImplementedError で拒否する API と理由(仕様)。
#: fast の確認では、例外になり Undo キューへ何も積まないことを確かめる。
FAST_UNSUPPORTED = {
    "Plug.setEnumNames": "API 2.0 が既存 enum 項目の削除を公開しないため fast=True は未対応(docstring の仕様)。",
}


class _Case(object):
    """Undo 検査の 1 行。

    Attributes:
        key (str): 網羅の番人と照合する API 名(``Class.method`` / ``cmds.name`` 等)。
        label (str): subTest に表示する名前。
        setup (callable | None): ``setup(ctx)``。対象を用意して ctx の属性へ保持する。
        action (callable): ``action(ctx, **kwargs)``。対象 API を 1 回呼ぶ。kwargs は fast の指定。
        fastSkip (str | None): fast=True の確認をこのケースで行わない理由。
        mayaQuirk (str | None): 素の cmds でも同じ差が出る Maya 側の Undo/Redo の挙動の説明。
            指定したときだけ ignoreAttrs・unorderedFields を比較から外す。
        ignoreAttrs (tuple[str]): 比べないアトリビュート名(論理番号・親の名前を除いた末尾の名前)。
        unorderedFields (tuple[str]): 順序を無視して比べるノードの項目(例: ``userAttrs``)。
    """

    def __init__(self, key, label, setup, action, fastSkip=None, mayaQuirk=None, ignoreAttrs=(),
                 unorderedFields=()):
        self.key = key
        self.label = label
        self.setup = setup
        self.action = action
        self.fastSkip = fastSkip
        self.mayaQuirk = mayaQuirk
        self.ignoreAttrs = tuple(ignoreAttrs) if mayaQuirk else ()
        self.unorderedFields = tuple(unorderedFields) if mayaQuirk else ()


class _Context(object):
    """1 ケース分の作業領域。setup が作った名前・ラッパーを属性に持つ。

    Attributes:
        ns (str): このケースの名前空間(先頭の ``:`` なし)。
        tmp (Path): ファイルを書き出せる一時フォルダー。
    """

    def __init__(self, ns, tmp):
        self.ns = ns
        self.tmp = tmp

    def name(self, text):
        """このケースの名前空間付きの名前を返す。"""
        return self.ns + ":" + text


# ---------------------------------------------------------------- スナップショット

_MISSING = "<なし>"


def _normalize(value):
    """比較用に小数を丸め、list を tuple へそろえる。"""
    if isinstance(value, float):
        value = round(value, FLOAT_PLACES)
        return 0.0 if value == 0 else value
    if isinstance(value, (list, tuple)):
        return tuple(_normalize(item) for item in value)
    return value


def _scene_uuids():
    """シーン全体のノードの UUID 集合を返す。"""
    return frozenset(cmds.ls(cmds.ls() or [], uuid=True) or [])


def _pairs(flat):
    """``listConnections(connections=True)`` の平坦な列を 2 個ずつの組にする。"""
    return [(flat[index], flat[index + 1]) for index in range(0, len(flat), 2)]


#: 値を読んで比べるアトリビュートの種類(om2 の MFn 型)。コンパウンドアトリビュート・message・generic 等は読まない。
READABLE_API_TYPES = frozenset((
    om2.MFn.kNumericAttribute, om2.MFn.kDoubleLinearAttribute, om2.MFn.kFloatLinearAttribute,
    om2.MFn.kDoubleAngleAttribute, om2.MFn.kFloatAngleAttribute, om2.MFn.kTimeAttribute,
    om2.MFn.kEnumAttribute, om2.MFn.kMatrixAttribute, om2.MFn.kFloatMatrixAttribute,
))

#: 値を読んで比べる型付きアトリビュートのデータ型。
READABLE_DATA_TYPES = frozenset((
    om2.MFnData.kString, om2.MFnData.kStringArray, om2.MFnData.kDoubleArray,
    om2.MFnData.kIntArray, om2.MFnData.kMatrix,
))


def readable_checker(name):
    """name のアトリビュートの値を getAttr で読んでよいかを返す関数を作る。

    種類は om2 のアトリビュート定義だけで判断し、プラグの値には触れない。コンパウンドアトリビュート
    (またはそのマルチアトリビュートの要素)は子を個別に読むので値を取らない。Maya の getAttr は、値を表せない子を
    含むコンパウンドアトリビュートに NULL 要素入りの tuple を返し、その要素に触れると Maya が異常終了する
    (例: displayLayer の drawInfo、initialShadingGroup の dagSetMembers[0])。message は値を持たず、
    接続は別に記録する。

    Args:
        name (str): ノード名。

    Returns:
        callable: ``check(attr) -> bool``。attr は ``listAttr(multi=True)`` の要素。
    """
    selection = om2.MSelectionList()
    selection.add(name)
    node = om2.MFnDependencyNode(selection.getDependNode(0))
    cache = {}

    def check(attr):
        base = attr.rsplit(".", 1)[-1].split("[", 1)[0]
        if base not in cache:
            readable = False
            try:
                obj = node.attribute(base)
            except Exception:
                obj = om2.MObject()
            if not obj.isNull():
                kind = obj.apiType()
                if kind in READABLE_API_TYPES:
                    readable = True
                elif kind == om2.MFn.kTypedAttribute:
                    readable = om2.MFnTypedAttribute(obj).attrType() in READABLE_DATA_TYPES
            cache[base] = readable
        return cache[base]
    return check


#: 環境変数 MLIB_UNDO_COVERAGE_TRACE を設定すると、異常終了の調査用に読む順を出力する。
TRACE = bool(os.environ.get("MLIB_UNDO_COVERAGE_TRACE"))


def _trace(text):
    """TRACE が有効なら、異常終了しても残るよう標準出力へ即座に書く。"""
    if TRACE:
        sys.__stdout__.write("[undo coverage trace] " + text + "\n")
        sys.__stdout__.flush()


def _geometry_state(name, kind):
    """mesh・nurbsCurve の形状(頂点・面の並びと位置)を om2 で読む。他の型は None。

    形状データ(outMesh 等)は getAttr で読まないため、頂点の削除・番号の並べ替え・拡縮を
    ここで検出する。
    """
    if kind not in ("mesh", "nurbsCurve"):
        return None
    selection = om2.MSelectionList()
    selection.add(name)
    path = selection.getDagPath(0)
    try:
        if kind == "mesh":
            mesh = om2.MFnMesh(path)
            counts, connects = mesh.getVertices()
            points = mesh.getPoints()
            return (tuple(counts), tuple(connects),
                    tuple(_normalize((point.x, point.y, point.z)) for point in points))
        curve = om2.MFnNurbsCurve(path)
        return tuple(_normalize((point.x, point.y, point.z)) for point in curve.cvPositions())
    except (RuntimeError, ValueError):
        # 空の mesh・中間オブジェクト等で形状データが無い場合は比べない。
        return None


def _node_state(name):
    """1 ノードの比較用の状態を辞書で返す。"""
    state = {
        "name": cmds.ls(name, long=True)[0],
        "type": cmds.nodeType(name),
        "locked": cmds.lockNode(name, query=True, lock=True)[0],
    }
    if cmds.objectType(name, isAType="dagNode"):
        state["parents"] = tuple(cmds.listRelatives(name, allParents=True, fullPath=True) or [])
        state["children"] = tuple(cmds.listRelatives(name, children=True, fullPath=True) or [])
    attrs = {}
    readable = readable_checker(name)
    for attr in cmds.listAttr(name, multi=True) or []:
        if not readable(attr):
            continue
        try:
            _trace("  getAttr " + name + "." + attr)
            value = cmds.getAttr(name + "." + attr, silent=True)
        except Exception:
            continue
        if value is not None:
            attrs[attr] = _normalize(value)
    state["attrs"] = attrs
    _trace("  meta " + name)
    state["lockedAttrs"] = tuple(sorted(cmds.listAttr(name, locked=True) or []))
    state["keyableAttrs"] = tuple(sorted(cmds.listAttr(name, keyable=True) or []))
    state["channelBoxAttrs"] = tuple(sorted(cmds.listAttr(name, channelBox=True) or []))
    user = tuple(cmds.listAttr(name, userDefined=True) or [])
    state["userAttrs"] = user
    enums = {}
    for attr in user:
        try:
            enums[attr] = tuple(cmds.attributeQuery(attr, node=name, listEnum=True) or [])
        except Exception:
            continue
    state["enumNames"] = enums
    state["aliases"] = tuple(cmds.aliasAttr(name, query=True) or [])
    incoming = _pairs(cmds.listConnections(name, connections=True, plugs=True, source=True,
                                           destination=False) or [])
    outgoing = _pairs(cmds.listConnections(name, connections=True, plugs=True, source=False,
                                           destination=True) or [])
    state["connections"] = tuple(sorted(set((src, dst) for dst, src in incoming) | set(outgoing)))
    _trace("  container " + name)
    geometry = _geometry_state(name, state["type"])
    if geometry is not None:
        state["geometry"] = geometry
    if state["type"] in ("container", "dagContainer"):
        state["publishedNames"] = tuple(cmds.container(name, query=True, publishName=True) or [])
        state["boundAttrs"] = tuple(cmds.container(name, query=True, bindAttr=True) or [])
        state["containerNodes"] = tuple(sorted(cmds.container(name, query=True, nodeList=True) or []))
    return state


def take_snapshot(baseline):
    """Undo の前後で比べるシーンの状態を返す。

    Args:
        baseline (frozenset[str]): ケース開始前から存在したノードの UUID。これ以外のノードと
            ``DEFAULT_TRACKED`` を関係ノードとして詳しく記録する。

    Returns:
        dict: ``nodes`` (UUID→状態)・``scene`` (UUID 集合)と、シーン全体の状態。
    """
    scene = _scene_uuids()
    tracked = set(scene - baseline)
    for name in DEFAULT_TRACKED:
        if cmds.objExists(name):
            tracked.update(cmds.ls(name, uuid=True) or [])
    nodes = {}
    for uid in tracked:
        names = cmds.ls(uid, long=True) or []
        if names:
            nodes[uid] = _node_state(names[0])
    return {
        "nodes": nodes,
        "scene": scene,
        "selection": tuple(cmds.ls(selection=True, long=True) or []),
        "namespaces": tuple(sorted(cmds.namespaceInfo(":", listOnlyNamespaces=True, recurse=True,
                                                      absoluteName=True) or [])),
        "currentNamespace": cmds.namespaceInfo(currentNamespace=True, absoluteName=True),
        "currentLayer": cmds.editDisplayLayerGlobals(query=True, currentDisplayLayer=True),
    }


_GLOBAL_KEYS = ("selection", "namespaces", "currentNamespace", "currentLayer")


def _short(value):
    text = repr(value)
    return text if len(text) <= 90 else text[:87] + "..."


def diff_snapshots(expected, actual, ignore=frozenset(), case=None):
    """2 つのスナップショットの差分を人が読める行の list で返す(差が無ければ空)。

    Args:
        expected (dict): 期待するスナップショット。
        actual (dict): 実際のスナップショット。
        ignore (frozenset[tuple[str, str]]): 比べない (UUID, アトリビュート) の組。
        case (_Case | None): Maya 側の挙動として比較から外す項目を持つケース。

    Returns:
        list[str]: 差分の説明。
    """
    lines = []
    for key in _GLOBAL_KEYS:
        if expected[key] != actual[key]:
            lines.append("{}: {} -> {}".format(key, _short(expected[key]), _short(actual[key])))
    for uid in sorted(actual["scene"] - expected["scene"]):
        lines.append("余分なノード: " + actual["nodes"].get(uid, {}).get("name", uid))
    for uid in sorted(expected["scene"] - actual["scene"]):
        lines.append("失われたノード: " + expected["nodes"].get(uid, {}).get("name", uid))
    for uid in sorted(set(expected["nodes"]) & set(actual["nodes"])):
        before, after = expected["nodes"][uid], actual["nodes"][uid]
        label = before["name"]
        for field in sorted(set(before) | set(after)):
            if field == "attrs":
                continue
            old, new = before.get(field, _MISSING), after.get(field, _MISSING)
            if case is not None and field in case.unorderedFields and _MISSING not in (old, new):
                old, new = sorted(old), sorted(new)
            if old != new:
                lines.append("{} {}: {} -> {}".format(label, field, _short(before.get(field, _MISSING)),
                                                      _short(after.get(field, _MISSING))))
        attrs_before, attrs_after = before["attrs"], after["attrs"]
        for attr in sorted(set(attrs_before) | set(attrs_after)):
            if (uid, attr) in ignore:
                continue
            if case is not None and attr.rsplit(".", 1)[-1].split("[", 1)[0] in case.ignoreAttrs:
                continue
            old, new = attrs_before.get(attr, _MISSING), attrs_after.get(attr, _MISSING)
            if old is _MISSING and _is_materialized_element(after["name"], attr, new):
                continue
            if old != new:
                lines.append("{}.{}: {} -> {}".format(label, attr, _short(old), _short(new)))
    return lines


#: 実体化しただけのマルチアトリビュートの要素とみなす値(既定値)。
_DEFAULT_LIKE = (0, -1, "", ())


def _is_materialized_element(node, attr, value):
    """期待側に無く実際側にだけあるマルチアトリビュートの要素が、実体化しただけのものか。

    Maya は接続・評価で作ったマルチアトリビュートの要素を、Undo で接続を戻しても残す(例: worldMatrix[0]、
    instObjGroups[0].objectGroups[0])。保存されない出力か、既定値のままの要素だけを無視する。
    値を書き込んだ要素(例: Undo で戻らなかった Plug.set)は既定値でないので差分に残る。
    """
    if "[" not in attr or not cmds.objExists(node):
        return False
    if value in _DEFAULT_LIKE:
        return True
    base = attr.rsplit(".", 1)[-1].split("[", 1)[0]
    try:
        return not cmds.attributeQuery(base, node=node, storable=True)
    except Exception:
        return False


def unstable_attrs(first, second):
    """続けて取った 2 回のスナップショットで値が変わる (UUID, アトリビュート) を返す。"""
    unstable = set()
    for uid in set(first["nodes"]) & set(second["nodes"]):
        attrs_a, attrs_b = first["nodes"][uid]["attrs"], second["nodes"][uid]["attrs"]
        for attr in set(attrs_a) | set(attrs_b):
            if attrs_a.get(attr, _MISSING) != attrs_b.get(attr, _MISSING):
                unstable.add((uid, attr))
    return frozenset(unstable)


def _format(lines):
    shown = lines[:MAX_DIFF_LINES]
    rest = len(lines) - len(shown)
    text = "\n      ".join(shown)
    if rest > 0:
        text += "\n      ... ほか {} 件".format(rest)
    return text


# ---------------------------------------------------------------- 準備の補助

def _xf(text, parent=None):
    """カレント名前空間に transform を作り、名前を返す。"""
    flags = {"name": text, "skipSelect": True}
    if parent is not None:
        flags["parent"] = parent
    return cmds.ls(cmds.createNode("transform", **flags), long=True)[0]


def _node(kind, text, parent=None):
    """カレント名前空間に kind のノードを作り、名前を返す。"""
    flags = {"name": text, "skipSelect": True}
    if parent is not None:
        flags["parent"] = parent
    return cmds.ls(cmds.createNode(kind, **flags), long=True)[0]


def s_one(c):
    """transform a(tx=1, ry=0.3)を作る。"""
    c.a = _xf("a")
    cmds.setAttr(c.a + ".tx", 1.0)
    cmds.setAttr(c.a + ".ry", 0.3)
    c.na = mlib.getNode(c.a)


def s_two(c):
    """transform a・b を作る(b は離れた位置と回転・スケール)。"""
    s_one(c)
    c.b = _xf("b")
    cmds.setAttr(c.b + ".t", 3.0, 4.0, 5.0)
    cmds.setAttr(c.b + ".r", 0.2, 0.4, 0.6)
    cmds.setAttr(c.b + ".s", 2.0, 2.0, 2.0)
    c.nb = mlib.getNode(c.b)


def s_two_selected(c):
    """transform a・b を作り、a を選択する。"""
    s_two(c)
    cmds.select(c.a, replace=True)


def s_child(c):
    """親 p(tx=3)の子 a と、別の親 q を作る。"""
    c.p = _xf("p")
    cmds.setAttr(c.p + ".tx", 3.0)
    c.q = _xf("q")
    cmds.setAttr(c.q + ".ty", 2.0)
    c.a = _xf("a", parent=c.p)
    cmds.setAttr(c.a + ".tz", 1.0)
    c.na = mlib.getNode(c.a)


def s_hidden(c):
    """visibility=False の transform a を作る。"""
    s_one(c)
    cmds.setAttr(c.a + ".visibility", False)


def s_md(c):
    """input1X=5 の multiplyDivide を作る。"""
    c.md = _node("multiplyDivide", "md")
    cmds.setAttr(c.md + ".input1X", 5.0)
    cmds.setAttr(c.md + ".input2Y", 3.0)
    c.nmd = mlib.getNode(c.md)


def s_user(c):
    """ユーザー定義アトリビュートを持つ transform a と、接続先 b を作る。"""
    s_two(c)
    a = c.a
    for name in ("foo", "bar", "baz"):
        cmds.addAttr(a, longName=name, attributeType="double", keyable=True)
    cmds.setAttr(a + ".foo", 1.5)
    cmds.addAttr(a, longName="hiddenNum", attributeType="double", keyable=False)
    cmds.addAttr(a, longName="mode", attributeType="enum", enumName="a:b", keyable=True)
    cmds.addAttr(a, longName="label", dataType="string")
    cmds.setAttr(a + ".label", "old", type="string")
    cmds.addAttr(a, longName="arr", attributeType="double", multi=True)
    for index in range(3):
        cmds.setAttr("{}.arr[{}]".format(a, index), index + 1.0)
    cmds.addAttr(a, longName="links", attributeType="message", multi=True)
    cmds.addAttr(a, longName="pair", attributeType="compound", numberOfChildren=2)
    cmds.addAttr(a, longName="first", attributeType="double", parent="pair")
    cmds.addAttr(a, longName="second", attributeType="double", parent="pair")
    c.na = mlib.getNode(a)


def s_order(c):
    """数値のユーザー定義アトリビュート foo・bar・baz だけを持つ transform a を作る。"""
    s_one(c)
    for name in ("foo", "bar", "baz"):
        cmds.addAttr(c.a, longName=name, attributeType="double", keyable=True)
    cmds.setAttr(c.a + ".baz", 2.5)
    c.na = mlib.getNode(c.a)


def s_connected(c):
    """a.tx → b.ty の接続を作る。"""
    s_two(c)
    cmds.connectAttr(c.a + ".tx", c.b + ".ty")


def s_locked(c):
    """translateX をロックした transform a を作る。"""
    s_one(c)
    cmds.setAttr(c.a + ".tx", lock=True)


def s_keyed(c):
    """translateX にキーを 2 つ打った transform a を作る。"""
    s_one(c)
    cmds.setKeyframe(c.a, attribute="translateX", time=1, value=0.0)
    cmds.setKeyframe(c.a, attribute="translateX", time=10, value=5.0)
    c.curve = cmds.listConnections(c.a + ".tx", type="animCurve")[0]
    c.ncurve = mlib.getNode(c.curve)


def s_muted(c):
    """translateX をミュートした transform a を作る。"""
    s_keyed(c)
    cmds.mute(c.a + ".tx")


def s_cube(c):
    """履歴なしの polyCube(tx=1)を作る。"""
    c.cube = cmds.ls(cmds.polyCube(name="cube", constructionHistory=False)[0], long=True)[0]
    cmds.setAttr(c.cube + ".tx", 1.0)
    c.shape = cmds.listRelatives(c.cube, shapes=True, fullPath=True)[0]
    c.ncube = mlib.getNode(c.cube)
    c.nshape = mlib.getNode(c.shape)
    cmds.select(clear=True)


def s_offset_pivot(c):
    """ピボットを中心からずらした cube を作る。"""
    s_cube(c)
    cmds.setAttr(c.cube + ".rotatePivot", 2.0, 0.0, 0.0)
    cmds.setAttr(c.cube + ".scalePivot", 2.0, 0.0, 0.0)


def s_intermediate(c):
    """未使用の中間 Shape を持つ cube を作る。"""
    s_cube(c)
    c.orig = _node("mesh", "cubeOrig", parent=c.cube)
    cmds.setAttr(c.orig + ".intermediateObject", True)


def s_curve(c):
    """CV 3 個の 1 次 nurbsCurve を作る。"""
    c.crv = cmds.ls(cmds.curve(degree=1, point=[(0, 0, 0), (1, 0, 0), (1, 1, 0)], name="crv"),
                    long=True)[0]
    c.crvShape = cmds.listRelatives(c.crv, shapes=True, fullPath=True)[0]
    c.ncrvShape = mlib.getNode(c.crvShape)


def s_curves(c):
    """形状を差し替える nurbsCurve(crv)と、取得元の nurbsCurve(src。tx=2)を作る。"""
    s_curve(c)
    c.ncrv = mlib.getNode(c.crv)
    c.src = cmds.ls(cmds.curve(degree=1, point=[(0, 0, 0), (0, 2, 0)], name="src"), long=True)[0]
    cmds.setAttr(c.src + ".tx", 2.0)
    c.nsrc = mlib.getNode(c.src)


def s_locator(c):
    """spaceLocator を作る。"""
    c.loc = cmds.spaceLocator(name="loc")[0]
    c.locShape = cmds.listRelatives(c.loc, shapes=True, fullPath=True)[0]
    c.nloc = mlib.getNode(c.locShape)
    cmds.select(clear=True)


def s_joints(c):
    """cmds.joint で j0→j1→j2 の連鎖(inverseScale 接続あり)と、独立した jx を作る。"""
    cmds.select(clear=True)
    c.j0 = cmds.ls(cmds.joint(name="j0", position=(0, 0, 0)), long=True)[0]
    c.j1 = cmds.ls(cmds.joint(name="j1", position=(0, 1, 0)), long=True)[0]
    c.j2 = cmds.ls(cmds.joint(name="j2", position=(0, 2, 0)), long=True)[0]
    cmds.select(clear=True)
    c.jx = cmds.ls(cmds.joint(name="jx", position=(2, 0, 0)), long=True)[0]
    cmds.select(clear=True)
    c.nj0, c.nj1, c.nj2, c.njx = (mlib.getNode(name) for name in (c.j0, c.j1, c.j2, c.jx))


def s_joints_oriented(c):
    """j1 の jointOrient を 0 以外にした連鎖を作る。"""
    s_joints(c)
    cmds.setAttr(c.j1 + ".jointOrient", 0.1, 0.2, 0.3)


def s_joints_rotated(c):
    """j1 の rotate を 0 以外にした連鎖を作る。"""
    s_joints(c)
    cmds.setAttr(c.j1 + ".rotate", 0.1, 0.2, 0.3)


def s_loose_joints(c):
    """createNode で親子にした inverseScale 未接続の joint p・j を作る。"""
    c.jp = _node("joint", "jp")
    c.j = _node("joint", "j", parent=c.jp)
    cmds.setAttr(c.jp + ".s", 2.0, 2.0, 2.0)
    c.nj = mlib.getNode(c.j)


def s_skin(c):
    """2 段の cube を j0・j1 へバインドし、未登録の jx も用意する。"""
    c.mesh = cmds.ls(cmds.polyCube(name="skinMesh", subdivisionsY=2, constructionHistory=False)[0],
                     long=True)[0]
    s_joints(c)
    cmds.setAttr(c.j0 + ".ty", -0.5)
    c.skinName = cmds.skinCluster(c.j0, c.j1, c.mesh, toSelectedBones=True, name="skin")[0]
    c.skin = mlib.getNode(c.skinName)
    cmds.select(clear=True)


def s_unbound(c):
    """未バインドの cube と joint 連鎖を作る。"""
    c.mesh = cmds.ls(cmds.polyCube(name="skinMesh", subdivisionsY=2, constructionHistory=False)[0],
                     long=True)[0]
    s_joints(c)


def s_skin_unused(c):
    """ウェイト 0 の influence jx を加えたスキンを作る。"""
    s_skin(c)
    cmds.skinCluster(c.skinName, edit=True, addInfluence=c.jx, weight=0.0)


def s_skin_invalid(c):
    """頂点 0 に負のウェイトを書いたスキンを作る。"""
    s_skin(c)
    cmds.setAttr(c.skinName + ".weightList[0].weights[0]", -0.5)


def s_skin_unnormalized(c):
    """頂点 0 の合計が 1 でないスキンを作る。"""
    s_skin(c)
    cmds.setAttr(c.skinName + ".weightList[0].weights[0]", 0.3)
    cmds.setAttr(c.skinName + ".weightList[0].weights[1]", 0.3)


def s_skin_posed(c):
    """j1 を回したスキンを作る。"""
    s_skin(c)
    cmds.setAttr(c.j1 + ".rz", 0.5)


def s_skin_copy(c):
    """同じ joint へバインドした 2 つ目のメッシュを作り、元のウェイトを j0=1 にする。"""
    s_skin(c)
    c.mesh2 = cmds.ls(cmds.polyCube(name="skinMesh2", subdivisionsY=2, constructionHistory=False)[0],
                      long=True)[0]
    c.skin2 = cmds.skinCluster(c.j0, c.j1, c.mesh2, toSelectedBones=True, name="skin2")[0]
    count = cmds.polyEvaluate(c.mesh, vertex=True)
    for index in range(count):
        cmds.setAttr("{}.weightList[{}].weights[0]".format(c.skinName, index), 1.0)
        cmds.setAttr("{}.weightList[{}].weights[1]".format(c.skinName, index), 0.0)
    cmds.select(clear=True)


def s_skin_saved(c):
    """ウェイトをファイルへ書き出してから頂点 0 のウェイトを書き換えたスキンを作る。"""
    s_skin(c)
    c.path = str(c.tmp / (c.ns.replace(":", "_") + "_weights.json"))
    c.skin.dumpWeights(c.path)
    cmds.setAttr(c.skinName + ".weightList[0].weights[0]", 0.2)
    cmds.setAttr(c.skinName + ".weightList[0].weights[1]", 0.8)


def s_constraint(c):
    """b を a へ parentConstraint で拘束する。"""
    s_two(c)
    c.con = cmds.parentConstraint(c.a, c.b, name="pcon")[0]
    c.ncon = mlib.getNode(c.con)


def s_aim(c):
    """b を a へ aimConstraint で拘束する。"""
    s_two(c)
    c.con = cmds.aimConstraint(c.a, c.b, name="acon")[0]
    c.ncon = mlib.getNode(c.con)


def s_container(c):
    """空の container と、メンバーにしていない transform a を作る。"""
    s_one(c)
    cmds.select(clear=True)
    c.cont = cmds.container(name="cont")
    c.ncont = mlib.getNode(c.cont)
    cmds.select(clear=True)


def s_container_member(c):
    """transform a をメンバーにした container を作る。"""
    s_container(c)
    cmds.container(c.cont, edit=True, addNode=[c.a])


def s_container_published(c):
    """未 Bind の公開名 pub を持つ container を作る。"""
    s_container_member(c)
    cmds.container(c.cont, edit=True, publishName="pub")


def s_container_bound(c):
    """a.tx を公開名 pub へ Bind した container を作る。"""
    s_container_member(c)
    cmds.container(c.cont, edit=True, publishAndBind=[c.a + ".translateX", "pub"])


def s_layer(c):
    """空のディスプレイレイヤーと transform a を作る。"""
    s_one(c)
    c.layer = cmds.createDisplayLayer(name="layer", empty=True)
    c.nlayer = mlib.getNode(c.layer)
    cmds.select(clear=True)


def s_layer_member(c):
    """transform a をメンバーにしたディスプレイレイヤーを作る。"""
    s_layer(c)
    cmds.editDisplayLayerMembers(c.layer, c.a, noRecurse=True)


def s_set(c):
    """空の objectSet と transform a を作る。"""
    s_one(c)
    c.set = cmds.sets(empty=True, name="set")
    c.nset = mlib.getNode(c.set)


def s_set_member(c):
    """transform a をメンバーにした objectSet を作る。"""
    s_set(c)
    cmds.sets(c.a, edit=True, forceElement=c.set)


def s_shading(c):
    """cube・shadingEngine・lambert を作る。"""
    s_cube(c)
    cmds.sets(c.shape, edit=True, forceElement="initialShadingGroup")
    c.sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="sg")
    c.lambert = _node("lambert", "lam")
    c.nsg = mlib.getNode(c.sg)


def s_texture(c):
    """file・place2dTexture を作る。"""
    c.file = _node("file", "tex")
    c.place = _node("place2dTexture", "place")
    c.nfile = mlib.getNode(c.file)
    c.nplace = mlib.getNode(c.place)


def s_pose(c):
    """joint 連鎖の姿勢を dagPose に保存してから j1 を回す。"""
    s_joints(c)
    c.pose = cmds.dagPose(c.j0, c.j1, c.j2, save=True, name="pose")
    cmds.setAttr(c.j1 + ".rz", 0.5)
    c.npose = mlib.getNode(c.pose)


def s_reorder(c):
    """基準の 4 頂点の平面と、頂点番号だけを入れ替えた同形の平面を作る。"""
    c.ref = cmds.ls(cmds.polyPlane(name="ref", subdivisionsX=1, subdivisionsY=1,
                                   constructionHistory=False)[0], long=True)[0]
    shape = cmds.listRelatives(c.ref, shapes=True, fullPath=True)[0]
    selection = om2.MSelectionList()
    selection.add(shape)
    source = om2.MFnMesh(selection.getDagPath(0))
    points = source.getPoints()
    counts, connects = source.getVertices()
    order = [2, 0, 3, 1]
    inverse = {old: new for new, old in enumerate(order)}
    target = _xf("tgt")
    selection.add(target)
    mesh = om2.MFnMesh()
    mesh.create([points[old] for old in order], counts, [inverse[old] for old in connects],
                parent=selection.getDependNode(1))
    c.tgtShape = cmds.listRelatives(target, shapes=True, fullPath=True)[0]
    cmds.sets(c.tgtShape, edit=True, forceElement="initialShadingGroup")
    c.ntgt = mlib.getNode(c.tgtShape)


def s_driven(c):
    """ドライバー a.tx と駆動先 b.ty を用意する。"""
    s_two(c)
    c.driven = DrivenKey(mlib.getPlug(c.a + ".tx"), mlib.getPlug(c.b + ".ty"))


def s_driven_existing(c):
    """既にドリブンキーが 1 つある a.tx → b.ty を用意する。"""
    s_two(c)
    cmds.setDrivenKeyframe(c.b + ".ty", currentDriver=c.a + ".tx", driverValue=0.0, value=0.0)
    c.driven = DrivenKey(mlib.getPlug(c.a + ".tx"), mlib.getPlug(c.b + ".ty"))


def s_ns(c):
    """子名前空間 sub(ノード入り)と移動先 dest を作る。"""
    s_one(c)
    c.sub = ":" + c.name("sub")
    c.dest = ":" + c.name("dest")
    cmds.namespace(add="sub", parent=":" + c.ns)
    cmds.namespace(add="dest", parent=":" + c.ns)
    c.inSub = cmds.createNode("transform", name=c.sub + ":inSub", skipSelect=True)


def s_graph(c):
    """ScalarGraph 用の container と入力 a.tx を用意する。"""
    s_container(c)
    c.graph = ScalarGraph(container=c.cont)
    c.plug = mlib.getPlug(c.a + ".tx")


def s_graph_factory(c):
    """生成関数を渡した ScalarGraph と入力 a.tx を用意する。"""
    s_one(c)
    c.graph = ScalarGraph(createNode=mlib.createNode)
    c.plug = mlib.getPlug(c.a + ".tx")


# ---------------------------------------------------------------- 動作の補助

def a_undo_chunk_nested(c, **kwargs):
    """undoChunk を入れ子にして 3 回 setAttr する。"""
    with decorator.undoChunk("mlibUndoCoverageOuter"):
        cmds.setAttr(c.a + ".tx", 7.0)
        with decorator.undoChunk("mlibUndoCoverageInner"):
            cmds.setAttr(c.a + ".ty", 8.0)
            mlib.getPlug(c.a + ".tz").set(9.0)
        cmds.setAttr(c.a + ".sx", 2.0)


def a_undo_chunk_decorated(c, **kwargs):
    """@undoChunk で装飾した関数から複数の更新を行う。"""
    @decorator.undoChunk("mlibUndoCoverageDecorated")
    def edit():
        cmds.setAttr(c.a + ".tx", 7.0)
        mlib.createNode("transform", name="madeInChunk")
        cmds.setAttr(c.a + ".ty", 8.0)
    edit()


def a_undo_transaction_nested(c, **kwargs):
    """undoTransaction の中で undoChunk・mlib の更新を入れ子にする。"""
    with decorator.undoTransaction("mlibUndoCoverageTransaction"):
        cmds.setAttr(c.a + ".tx", 7.0)
        with decorator.undoChunk("mlibUndoCoverageInner"):
            c.na.setTranslate((1.0, 2.0, 3.0))
            with decorator.undoTransaction():
                c.na.rename("renamedInTransaction")


def a_undo_transaction_anonymous(c, **kwargs):
    """名前なしの undoTransaction を入れ子にする。"""
    with decorator.undoTransaction():
        cmds.setAttr(c.a + ".tx", 7.0)
        with decorator.undoTransaction():
            cmds.setAttr(c.a + ".ty", 8.0)


def a_reorder(c, **kwargs):
    c.ntgt.reorderVertices(c.ref, match="position", **kwargs)


def _matrix(tx, ty, tz):
    return Matrix([1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, tx, ty, tz, 1.0])


# ---------------------------------------------------------------- ケース表

#: 素の cmds.cutKey / cmds.setDrivenKeyframe(linear)でも Redo 後に keyTanInX/keyTanOutX が変わる。
_TANGENT_CACHE = "素の cmds でも Redo 後に接線の内部値 keyTanInX/keyTanOutX が 0 から 1 へ変わる"
_TANGENT_ATTRS = ("keyTanInX", "keyTanOutX", "keyTanInY", "keyTanOutY")

#: container を所有先にした ScalarGraph の fast は NotImplementedError(仕様)。
_CONTAINER_FAST = "container を所有先にした fast は NotImplementedError(仕様)"

C = _Case
CASES = [
    # cmds
    C("cmds.createNode", "createNode transform", None,
      lambda c, **kw: mlib.createNode("transform", name="made", **kw)),
    C("cmds.createNode", "createNode transform (選択あり)", None,
      lambda c, **kw: mlib.createNode("transform", name="made", skipSelect=False, **kw)),
    C("cmds.createNode", "createNode joint parent", s_one,
      lambda c, **kw: mlib.createNode("joint", name="madeJoint", parent=c.a, **kw)),
    C("cmds.createNode", "createNode mesh(shape)", None,
      lambda c, **kw: mlib.createNode("mesh", name="madeMesh", **kw)),
    C("cmds.createNode", "createNode network", None,
      lambda c, **kw: mlib.createNode("network", name="madeNetwork", skipSelect=True, **kw)),
    C("cmds.delete", "delete 2 nodes", s_two, lambda c, **kw: mlib.delete([c.a, c.b], **kw)),
    C("cmds.delete", "delete face component", s_cube,
      lambda c, **kw: mlib.delete(c.cube + ".f[0]", **kw),
      fastSkip="コンポーネントの削除は fast の対象外"),
    C("cmds.duplicate", "duplicate transform", s_one, lambda c, **kw: mlib.duplicate(c.a)),
    C("cmds.duplicate", "duplicate mesh", s_cube, lambda c, **kw: mlib.duplicate(c.cube)),
    C("cmds.select", "select replace", s_two, lambda c, **kw: mlib.select([c.a, c.b])),
    C("cmds.select", "select clear", s_two_selected, lambda c, **kw: mlib.select(clear=True)),
    # Node
    C("Node.setLocked", "setLocked", s_one, lambda c, **kw: c.na.setLocked(True, **kw)),
    C("Node.setNamespace", "setNamespace", s_ns,
      lambda c, **kw: c.na.setNamespace(c.dest, **kw)),
    C("Node.delete", "Node.delete", s_one, lambda c, **kw: c.na.delete(**kw)),
    C("Node.delete", "Node.delete shape transform", s_cube, lambda c, **kw: c.ncube.delete(**kw)),
    C("Node.rename", "rename", s_one, lambda c, **kw: c.na.rename("renamed", **kw)),
    C("Node.rename", "rename mesh transform", s_cube,
      lambda c, **kw: c.ncube.rename("renamedCube", **kw)),
    C("Node.resetAttrs", "resetAttrs named", s_md,
      lambda c, **kw: c.nmd.resetAttrs(["input1X"], **kw)),
    C("Node.resetAttrs", "resetAttrs keyable", s_md, lambda c, **kw: c.nmd.resetAttrs(**kw)),
    C("Node.setAttrFlags", "setAttrFlags", s_one,
      lambda c, **kw: c.na.setAttrFlags(["tx", "ty"], locked=True, keyable=False, **kw)),
    C("Node.addAttr", "addAttr double", s_one,
      lambda c, **kw: c.na.addAttr("extra", type="double", defaultValue=2.0, **kw)),
    C("Node.addAttr", "addAttr double3", s_one,
      lambda c, **kw: c.na.addAttr("vec", type="double3", **kw)),
    C("Node.addAttr", "addAttr string", s_one,
      lambda c, **kw: c.na.addAttr("note", type="string", **kw)),
    C("Node.addAttr", "addAttr enum", s_one,
      lambda c, **kw: c.na.addAttr("choice", type="enum", enumName="x:y", **kw)),
    C("Node.moveAttrOrder", "moveAttrOrder", s_order,
      lambda c, **kw: c.na.moveAttrOrder("baz", -1)),
    # DagNode
    C("DagNode.show", "show", s_hidden, lambda c, **kw: c.na.show(**kw)),
    C("DagNode.hide", "hide", s_one, lambda c, **kw: c.na.hide(**kw)),
    C("DagNode.setVisibility", "setVisibility", s_one,
      lambda c, **kw: c.na.setVisibility(False, **kw)),
    C("DagNode.setOutlinerVisibility", "setOutlinerVisibility", s_one,
      lambda c, **kw: c.na.setOutlinerVisibility(False, **kw)),
    C("DagNode.setColor", "setColor index on shapes", s_curves, lambda c, **kw: c.ncrv.setColor(13)),
    C("DagNode.setColor", "setColor rgb", s_one, lambda c, **kw: c.na.setColor((1.0, 0.5, 0.0))),
    # Transform
    C("Transform.setParent", "setParent", s_child, lambda c, **kw: c.na.setParent(c.q, **kw)),
    C("Transform.setParent", "setParent world", s_child, lambda c, **kw: c.na.setParent(None, **kw)),
    C("Transform.setParent", "setParent relative", s_child,
      lambda c, **kw: c.na.setParent(c.q, relative=True, **kw)),
    C("Transform.setParent", "setParent joint", s_loose_joints,
      lambda c, **kw: c.nj.setParent(None, **kw), fastSkip="fast の Joint は NotImplementedError(仕様)"),
    C("Transform.matchTransform", "matchTransform", s_two,
      lambda c, **kw: c.na.matchTransform(c.b)),
    C("Transform.mirrorTransform", "mirrorTransform", s_one,
      lambda c, **kw: c.na.mirrorTransform("x", **kw)),
    C("Transform.mirrorTransform", "mirrorTransform worldSpace", s_child,
      lambda c, **kw: c.na.mirrorTransform("yz", worldSpace=True, **kw)),
    C("Transform.setMatrix", "setMatrix", s_one,
      lambda c, **kw: c.na.setMatrix(_matrix(4.0, 5.0, 6.0), **kw)),
    C("Transform.setMatrix", "setMatrix worldSpace", s_child,
      lambda c, **kw: c.na.setMatrix(_matrix(4.0, 5.0, 6.0), worldSpace=True, **kw)),
    C("Transform.setTranslate", "setTranslate", s_one,
      lambda c, **kw: c.na.setTranslate((1.0, 2.0, 3.0), **kw)),
    C("Transform.setTranslate", "setTranslate worldSpace", s_child,
      lambda c, **kw: c.na.setTranslate((1.0, 2.0, 3.0), worldSpace=True, **kw)),
    C("Transform.setRotate", "setRotate", s_one,
      lambda c, **kw: c.na.setRotate((0.1, 0.2, 0.3), **kw)),
    C("Transform.setRotate", "setRotate worldSpace", s_child,
      lambda c, **kw: c.na.setRotate((0.1, 0.2, 0.3), worldSpace=True, **kw)),
    C("Transform.setScale", "setScale", s_one, lambda c, **kw: c.na.setScale((2.0, 3.0, 4.0), **kw)),
    C("Transform.setShear", "setShear", s_one, lambda c, **kw: c.na.setShear((0.1, 0.2, 0.3), **kw)),
    C("Transform.setQuaternion", "setQuaternion", s_one,
      lambda c, **kw: c.na.setQuaternion((0.0, 0.2588190451, 0.0, 0.9659258263), **kw)),
    C("Transform.setQuaternion", "setQuaternion jointOrient", s_joints,
      lambda c, **kw: c.nj1.setQuaternion((0.0, 0.0, 0.2588190451, 0.9659258263), r=False, **kw)),
    C("Transform.setPivot", "setPivot", s_one,
      lambda c, **kw: c.na.setPivot((1.0, 2.0, 3.0), **kw)),
    C("Transform.setPivot", "setPivot scale worldSpace", s_child,
      lambda c, **kw: c.na.setPivot((1.0, 2.0, 3.0), worldSpace=True, kind="scale", **kw)),
    C("Transform.centerPivot", "centerPivot", s_offset_pivot,
      lambda c, **kw: c.ncube.centerPivot(**kw)),
    C("Transform.makeIdentity", "makeIdentity apply", s_cube,
      lambda c, **kw: c.ncube.makeIdentity(apply=True, translate=True, rotate=True, scale=True)),
    C("Transform.addConstraint", "addConstraint parent", s_two,
      lambda c, **kw: c.nb.addConstraint(c.a, type="parent")),
    C("Transform.addConstraint", "addConstraint aim", s_two,
      lambda c, **kw: c.nb.addConstraint(c.a, type="aim", maintainOffset=True)),
    C("Transform.addConstraint", "addConstraint point", s_two,
      lambda c, **kw: c.nb.addConstraint(c.a, type="point")),
    C("Transform.deleteConstraints", "deleteConstraints", s_constraint,
      lambda c, **kw: c.nb.deleteConstraints(**kw)),
    C("Transform.deleteUnusedIntermediateShapes", "deleteUnusedIntermediateShapes", s_intermediate,
      lambda c, **kw: c.ncube.deleteUnusedIntermediateShapes(**kw)),
    C("Transform.replaceShapes", "replaceShapes", s_curves, lambda c, **kw: c.ncrv.replaceShapes(c.nsrc)),
    C("Transform.replaceShapes", "replaceShapes keepSource worldSpace", s_curves,
      lambda c, **kw: c.ncrv.replaceShapes(c.nsrc, keepSource=True, worldSpace=True)),
    C("NurbsCurve.create", "NurbsCurve.create periodic", None,
      lambda c, **kw: NurbsCurve.create([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], degree=3, closed=True,
                                        name="made")),
    C("NurbsCurve.setCvPositions", "setCvPositions worldSpace", s_curves,
      lambda c, **kw: c.ncrvShape.setCvPositions([(0, 1, 0), (1, 1, 0), (2, 2, 0)], worldSpace=True)),
    C("Transform.scaleGeometry", "Transform.scaleGeometry", s_cube,
      lambda c, **kw: c.ncube.scaleGeometry(2.0, **kw)),
    C("Transform.resetAttrs", "Transform.resetAttrs", s_two, lambda c, **kw: c.nb.resetAttrs(**kw)),
    C("Transform.resetAttrs", "Transform.resetAttrs named", s_two,
      lambda c, **kw: c.nb.resetAttrs(["translateX", "scale"], **kw)),
    # Shape
    C("Shape.scaleGeometry", "Mesh.scaleGeometry", s_cube,
      lambda c, **kw: c.nshape.scaleGeometry(2.0, **kw)),
    C("Shape.scaleGeometry", "Mesh.scaleGeometry indices", s_cube,
      lambda c, **kw: c.nshape.scaleGeometry(2.0, indices=[0, 1], pivot=(0.5, 0.5, 0.5), **kw)),
    C("Shape.scaleGeometry", "NurbsCurve.scaleGeometry", s_curve,
      lambda c, **kw: c.ncrvShape.scaleGeometry(2.0, **kw)),
    C("Locator.setPosition", "Locator.setPosition", s_locator,
      lambda c, **kw: c.nloc.setPosition((1.0, 2.0, 3.0), **kw)),
    C("Mesh.reorderVertices", "reorderVertices position", s_reorder, a_reorder),
    # Joint
    C("Joint.setSegmentScaleCompensate", "setSegmentScaleCompensate", s_joints,
      lambda c, **kw: c.nj1.setSegmentScaleCompensate(False, **kw)),
    C("Joint.jointOrientToRotate", "jointOrientToRotate", s_joints_oriented,
      lambda c, **kw: c.nj1.jointOrientToRotate(**kw)),
    C("Joint.freezeRotate", "freezeRotate", s_joints_rotated,
      lambda c, **kw: c.nj1.freezeRotate(**kw)),
    C("Joint.connectInverseScale", "connectInverseScale", s_loose_joints,
      lambda c, **kw: c.nj.connectInverseScale(**kw)),
    C("Joint.disconnectInverseScale", "disconnectInverseScale", s_joints,
      lambda c, **kw: c.nj1.disconnectInverseScale(**kw)),
    C("Joint.setRadius", "setRadius", s_joints, lambda c, **kw: c.nj1.setRadius(3.0, **kw)),
    C("Joint.removeInfluence", "Joint.removeInfluence", s_skin,
      lambda c, **kw: c.nj1.removeInfluence(c.skin)),
    C("Joint.reparentChildren", "reparentChildren", s_joints,
      lambda c, **kw: c.nj0.reparentChildren(c.jx, **kw)),
    # Constraint
    C("Constraint.setWeight", "Constraint.setWeight", s_constraint,
      lambda c, **kw: c.ncon.setWeight(0.5, **kw)),
    C("AimConstraint.setRestRotate", "AimConstraint.setRestRotate", s_aim,
      lambda c, **kw: c.ncon.setRestRotate((0.1, 0.2, 0.3), **kw)),
    C("AimConstraint.setOffset", "AimConstraint.setOffset", s_aim,
      lambda c, **kw: c.ncon.setOffset((0.1, 0.2, 0.3), **kw)),
    # AnimCurve
    C("AnimCurve.setKey", "AnimCurve.setKey new", s_keyed,
      lambda c, **kw: c.ncurve.setKey(0.2, 3.0, **kw)),
    C("AnimCurve.removeKey", "AnimCurve.removeKey", s_keyed,
      lambda c, **kw: c.ncurve.removeKey(0, **kw), mayaQuirk=_TANGENT_CACHE, ignoreAttrs=_TANGENT_ATTRS),
    C("AnimCurve.setTangent", "AnimCurve.setTangent", s_keyed,
      lambda c, **kw: c.ncurve.setTangent(0, inTangentType="flat", outTangentType="flat", **kw)),
    C("AnimCurve.setInfinity", "AnimCurve.setInfinity", s_keyed,
      lambda c, **kw: c.ncurve.setInfinity(pre="cycle", post="linear", **kw)),
    C("AnimCurve.shiftKeys", "AnimCurve.shiftKeys", s_keyed,
      lambda c, **kw: c.ncurve.shiftKeys(0.1, 1.0, **kw)),
    C("AnimCurve.scaleKeys", "AnimCurve.scaleKeys", s_keyed,
      lambda c, **kw: c.ncurve.scaleKeys(2.0, 2.0, **kw)),
    C("AnimCurve.mirror", "AnimCurve.mirror", s_keyed, lambda c, **kw: c.ncurve.mirror(**kw)),
    # Container
    C("Container.create", "Container.create", s_one,
      lambda c, **kw: Container.create(name="madeCont", members=[c.a])),
    C("DagContainer.create", "DagContainer.create", s_one,
      lambda c, **kw: DagContainer.create(name="madeDagCont", members=[c.a])),
    C("Container.addMembers", "Container.addMembers", s_container,
      lambda c, **kw: c.ncont.addMembers(c.a)),
    C("Container.removeMembers", "Container.removeMembers", s_container_member,
      lambda c, **kw: c.ncont.removeMembers(c.a)),
    C("Container.createNode", "Container.createNode", s_container,
      lambda c, **kw: c.ncont.createNode("transform", name="inCont")),
    C("Container.removeContainer", "Container.removeContainer", s_container_member,
      lambda c, **kw: c.ncont.removeContainer()),
    C("Container.publishName", "Container.publishName", s_container_member,
      lambda c, **kw: c.ncont.publishName("pub")),
    C("Container.bindAttr", "Container.bindAttr", s_container_published,
      lambda c, **kw: c.ncont.bindAttr("pub", c.a + ".translateX")),
    C("Container.publishAndBind", "Container.publishAndBind", s_container_member,
      lambda c, **kw: c.ncont.publishAndBind("pb", c.a + ".translateY")),
    C("Container.unbindAttr", "Container.unbindAttr", s_container_bound,
      lambda c, **kw: c.ncont.unbindAttr("pub")),
    C("Container.unpublishName", "Container.unpublishName", s_container_published,
      lambda c, **kw: c.ncont.unpublishName("pub")),
    # DagPose
    C("DagPose.create", "DagPose.create", s_joints,
      lambda c, **kw: DagPose.create([c.j0, c.j1, c.j2], name="madePose")),
    C("DagPose.restore", "DagPose.restore", s_pose, lambda c, **kw: c.npose.restore()),
    # DisplayLayer
    C("DisplayLayer.addMembers", "DisplayLayer.addMembers", s_layer,
      lambda c, **kw: c.nlayer.addMembers(c.a, **kw)),
    C("DisplayLayer.removeMembers", "DisplayLayer.removeMembers", s_layer_member,
      lambda c, **kw: c.nlayer.removeMembers(c.a, **kw)),
    C("DisplayLayer.setCurrent", "DisplayLayer.setCurrent", s_layer,
      lambda c, **kw: c.nlayer.setCurrent(**kw)),
    # ObjectSet
    C("ObjectSet.addMembers", "ObjectSet.addMembers", s_set,
      lambda c, **kw: c.nset.addMembers(c.a, **kw)),
    C("ObjectSet.removeMembers", "ObjectSet.removeMembers", s_set_member,
      lambda c, **kw: c.nset.removeMembers(c.a, **kw)),
    # Shading
    C("ShadingEngine.setShader", "ShadingEngine.setShader", s_shading,
      lambda c, **kw: c.nsg.setShader(c.lambert, **kw)),
    C("ShadingEngine.assign", "ShadingEngine.assign shape", s_shading,
      lambda c, **kw: c.nsg.assign(c.shape, **kw)),
    C("ShadingEngine.assign", "ShadingEngine.assign faces", s_shading,
      lambda c, **kw: c.nsg.assign([c.cube + ".f[0:1]"], **kw),
      fastSkip="fast はフェース単位を拒否する(仕様)"),
    C("File.setFilePath", "File.setFilePath", s_texture,
      lambda c, **kw: c.nfile.setFilePath("C:/mlibUndoCoverage/missing.png", **kw)),
    C("File.setColorSpace", "File.setColorSpace", s_texture,
      lambda c, **kw: c.nfile.setColorSpace("Raw", **kw)),
    C("Place2dTexture.connectTexture", "Place2dTexture.connectTexture", s_texture,
      lambda c, **kw: c.nplace.connectTexture(c.file, **kw)),
    # SkinCluster
    C("SkinCluster.bind", "SkinCluster.bind", s_unbound,
      lambda c, **kw: SkinCluster.bind(c.mesh, [c.j0, c.j1])),
    C("SkinCluster.copyWeightsTo", "SkinCluster.copyWeightsTo", s_skin_copy,
      lambda c, **kw: c.skin.copyWeightsTo(c.skin2)),
    C("SkinCluster.addInfluences", "SkinCluster.addInfluences", s_skin,
      lambda c, **kw: c.skin.addInfluences([c.jx])),
    C("SkinCluster.restoreBindPose", "SkinCluster.restoreBindPose", s_skin_posed,
      lambda c, **kw: c.skin.restoreBindPose()),
    C("SkinCluster.removeUnusedInfluences", "SkinCluster.removeUnusedInfluences", s_skin_unused,
      lambda c, **kw: c.skin.removeUnusedInfluences()),
    C("SkinCluster.removeInvalidWeights", "SkinCluster.removeInvalidWeights", s_skin_invalid,
      lambda c, **kw: c.skin.removeInvalidWeights(**kw)),
    C("SkinCluster.setWeights", "SkinCluster.setWeights", s_skin,
      lambda c, **kw: c.skin.setWeights([c.j0, c.j1], [0.25, 0.75], **kw)),
    C("SkinCluster.loadWeights", "SkinCluster.loadWeights", s_skin_saved,
      lambda c, **kw: c.skin.loadWeights(c.path, **kw)),
    C("SkinCluster.redistributeWeights", "SkinCluster.redistributeWeights", s_skin,
      lambda c, **kw: c.skin.redistributeWeights([0, 1, 2, 3, 4, 5], **kw)),
    C("SkinCluster.transferWeights", "SkinCluster.transferWeights", s_skin,
      lambda c, **kw: c.skin.transferWeights([(c.j1, c.j0)], **kw)),
    C("SkinCluster.removeInfluence", "SkinCluster.removeInfluence", s_skin,
      lambda c, **kw: c.skin.removeInfluence(c.j1)),
    C("SkinCluster.normalizeWeights", "SkinCluster.normalizeWeights", s_skin_unnormalized,
      lambda c, **kw: c.skin.normalizeWeights(**kw)),
    C("SkinCluster.setMaxInfluences", "SkinCluster.setMaxInfluences", s_skin,
      lambda c, **kw: c.skin.setMaxInfluences(1, **kw)),
    C("SkinCluster.setMaxInfluences", "SkinCluster.setMaxInfluences prune", s_skin,
      lambda c, **kw: c.skin.setMaxInfluences(1, prune=True, **kw)),
    # Plug
    C("Plug.set", "Plug.set double", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".tx").set(4.0, **kw)),
    C("Plug.set", "Plug.set bool", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".visibility").set(False, **kw)),
    C("Plug.set", "Plug.set enum", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".rotateOrder").set(2, **kw)),
    C("Plug.set", "Plug.set string", s_user,
      lambda c, **kw: mlib.getPlug(c.a + ".label").set("new", **kw)),
    C("Plug.set", "Plug.set matrix", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".offsetParentMatrix").set(_matrix(1.0, 2.0, 3.0), **kw)),
    C("Plug.set", "Plug.set compound", s_user,
      lambda c, **kw: mlib.getPlug(c.a + ".pair").set((3.0, 7.0), **kw)),
    C("Plug.set", "Plug.set multi element", s_user,
      lambda c, **kw: mlib.getPlug(c.a + ".arr[1]").set(9.0, **kw)),
    C("Double3Plug.set", "Double3Plug.set", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".translate").set((1.0, 2.0, 3.0), **kw)),
    C("Double3Plug.set", "Double3Plug.set rotate", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".rotate").set((0.1, 0.2, 0.3), **kw)),
    C("Plug.setIfChanged", "Plug.setIfChanged", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".tx").setIfChanged(4.0, **kw)),
    C("Plug.reset", "Plug.reset", s_one, lambda c, **kw: mlib.getPlug(c.a + ".tx").reset(**kw)),
    C("Plug.setKeyable", "Plug.setKeyable", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".tx").setKeyable(False, **kw)),
    C("Plug.setChannelBox", "Plug.setChannelBox", s_user,
      lambda c, **kw: mlib.getPlug(c.a + ".hiddenNum").setChannelBox(True, **kw)),
    C("Plug.setFlags", "Plug.setFlags", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".tx").setFlags(locked=True, keyable=False, **kw)),
    C("Plug.setLocked", "Plug.setLocked", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".tx").setLocked(True, **kw)),
    C("Plug.setLocked", "Plug.setLocked compound leaf", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".translate").setLocked(True, leaf=True, **kw)),
    C("Plug.unlock", "Plug.unlock", s_locked, lambda c, **kw: mlib.getPlug(c.a + ".tx").unlock(**kw)),
    C("Plug.mute", "Plug.mute", s_keyed, lambda c, **kw: mlib.getPlug(c.a + ".tx").mute()),
    C("Plug.unmute", "Plug.unmute", s_muted, lambda c, **kw: mlib.getPlug(c.a + ".tx").unmute(),
      mayaQuirk="素の cmds.mute(disable=True, force=True) も Undo 後に animCurve の stippleReverse が戻らない",
      ignoreAttrs=("stippleReverse",)),
    C("Plug.setMuted", "Plug.setMuted", s_keyed,
      lambda c, **kw: mlib.getPlug(c.a + ".tx").setMuted(True)),
    C("Plug.setAlias", "Plug.setAlias", s_user,
      lambda c, **kw: mlib.getPlug(c.a + ".foo").setAlias("fooAlias", **kw)),
    C("Plug.setKey", "Plug.setKey new curve", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".ty").setKey(time=3, value=1.0, **kw)),
    C("Plug.setKey", "Plug.setKey existing curve", s_keyed,
      lambda c, **kw: mlib.getPlug(c.a + ".tx").setKey(time=5, value=2.0, **kw)),
    C("Plug.setEnumNames", "Plug.setEnumNames", s_user,
      lambda c, **kw: mlib.getPlug(c.a + ".mode").setEnumNames(["x", "y", "z"], **kw)),
    C("Plug.delete", "Plug.delete", s_user, lambda c, **kw: mlib.getPlug(c.a + ".bar").delete(**kw),
      mayaQuirk="素の cmds.deleteAttr も Undo で戻したアトリビュートをユーザー定義の末尾へ置く",
      unorderedFields=("userAttrs",)),
    C("Plug.connect", "Plug.connect", s_two,
      lambda c, **kw: mlib.getPlug(c.b + ".ty").connect(c.a + ".tx", **kw)),
    C("Plug.connect", "Plug.connect force", s_connected,
      lambda c, **kw: mlib.getPlug(c.b + ".ty").connect(c.a + ".tz", force=True, **kw)),
    C("Plug.connectTo", "Plug.connectTo", s_two,
      lambda c, **kw: mlib.getPlug(c.a + ".tx").connectTo(c.b + ".ty", **kw)),
    C("Plug.disconnectInput", "Plug.disconnectInput", s_connected,
      lambda c, **kw: mlib.getPlug(c.b + ".ty").disconnectInput(**kw)),
    C("Plug.disconnect", "Plug.disconnect", s_connected,
      lambda c, **kw: mlib.getPlug(c.b + ".ty").disconnect(c.a + ".tx", **kw)),
    C("Plug.disconnectAll", "Plug.disconnectAll", s_connected,
      lambda c, **kw: mlib.getPlug(c.a + ".tx").disconnectAll(**kw)),
    C("Plug.__rshift__", "Plug >>", s_two,
      lambda c, **kw: mlib.getPlug(c.a + ".tx") >> mlib.getPlug(c.b + ".ty")),
    C("Plug.__lshift__", "Plug <<", s_two,
      lambda c, **kw: mlib.getPlug(c.b + ".ty") << mlib.getPlug(c.a + ".tx")),
    C("Plug.__floordiv__", "Plug //", s_connected,
      lambda c, **kw: mlib.getPlug(c.a + ".tx") // mlib.getPlug(c.b + ".ty")),
    C("BoolPlug.toggle", "BoolPlug.toggle", s_one,
      lambda c, **kw: mlib.getPlug(c.a + ".visibility").toggle()),
    C("MultiPlug.removeElement", "MultiPlug.removeElement", s_user,
      lambda c, **kw: mlib.getPlug(c.a + ".arr").removeElement(1, **kw)),
    C("MultiPlug.appendMessage", "MultiPlug.appendMessage", s_user,
      lambda c, **kw: mlib.getPlug(c.a + ".links").appendMessage(c.b, **kw)),
    # common
    C("DrivenKey.setKey", "DrivenKey.setKey new", s_driven,
      lambda c, **kw: c.driven.setKey(0.0, 0.0), mayaQuirk=_TANGENT_CACHE, ignoreAttrs=_TANGENT_ATTRS),
    C("DrivenKey.setKey", "DrivenKey.setKey add", s_driven_existing,
      lambda c, **kw: c.driven.setKey(1.0, 2.0)),
    C("Namespace.create", "Namespace.create", s_one,
      lambda c, **kw: Namespace.create("madeNs", parent=":" + c.ns)),
    C("Namespace.setCurrent", "Namespace.setCurrent", s_ns,
      lambda c, **kw: Namespace(c.sub).setCurrent()),
    C("Namespace.rename", "Namespace.rename", s_ns,
      lambda c, **kw: Namespace(c.sub).rename("renamedNs")),
    C("Namespace.move", "Namespace.move", s_ns, lambda c, **kw: Namespace(c.sub).move(c.dest)),
    C("Namespace.remove", "Namespace.remove", s_ns,
      lambda c, **kw: Namespace(c.sub).remove(":" + c.ns)),
    C("ScalarGraph.sum", "ScalarGraph.sum container", s_graph,
      lambda c, **kw: c.graph.sum("add", c.plug, 1.0, **kw), fastSkip=_CONTAINER_FAST),
    C("ScalarGraph.sum", "ScalarGraph.sum createNode", s_graph_factory,
      lambda c, **kw: c.graph.sum("add", c.plug, 1.0, subtract=True, **kw)),
    C("ScalarGraph.multiply", "ScalarGraph.multiply container", s_graph,
      lambda c, **kw: c.graph.multiply("mul", c.plug, 2.0, **kw), fastSkip=_CONTAINER_FAST),
    C("ScalarGraph.multiply", "ScalarGraph.multiply createNode", s_graph_factory,
      lambda c, **kw: c.graph.multiply("mul", c.plug, 2.0, **kw)),
    C("ScalarGraph.condition", "ScalarGraph.condition container", s_graph,
      lambda c, **kw: c.graph.condition("cond", c.plug, 1.0, 2.0, 3.0, **kw), fastSkip=_CONTAINER_FAST),
    C("ScalarGraph.condition", "ScalarGraph.condition createNode", s_graph_factory,
      lambda c, **kw: c.graph.condition("cond", c.plug, 1.0, 2.0, 3.0, **kw)),
    C("Selection.select", "Selection.select replace", s_two,
      lambda c, **kw: Selection([c.a, c.b]).select()),
    C("Selection.select", "Selection.select add", s_two_selected,
      lambda c, **kw: Selection([c.b]).select(mode="add")),
    # decorator
    C("decorator.undoChunk", "undoChunk nested", s_one, a_undo_chunk_nested),
    C("decorator.undoChunk", "undoChunk decorator", s_one, a_undo_chunk_decorated),
    C("decorator.undoTransaction", "undoTransaction nested", s_one, a_undo_transaction_nested),
    C("decorator.undoTransaction", "undoTransaction anonymous", s_one, a_undo_transaction_anonymous),
]
del C


def selected_cases():
    """``MLIB_UNDO_COVERAGE_ONLY`` で絞り込んだケースの list を返す(未設定なら全件)。"""
    words = [word for word in os.environ.get("MLIB_UNDO_COVERAGE_ONLY", "").split(",") if word]
    if not words:
        return list(CASES)
    return [case for case in CASES if any(word in case.label for word in words)]


def _progress(text):
    """異常終了した場合に console.log から直前のケースを特定できるよう、進行を出力する。"""
    sys.__stdout__.write("[undo coverage] " + text + "\n")
    sys.__stdout__.flush()


def _safe_step(command):
    """cmds.undo / cmds.redo を 1 回行う。積まれた項目が無いときの RuntimeError は無視する。

    Undo キューが空のことは呼出し側が別に検出して報告する。
    """
    try:
        command()
    except RuntimeError:
        pass


# ---------------------------------------------------------------- 公開 API の列挙

def _public_classes():
    """公開クラスを (クラス, 所属) の list で返す。"""
    classes = []
    for package in (mlib.nodes, mlib.plugs, mlib.components):
        for name in package.__all__:
            value = getattr(package, name)
            if inspect.isclass(value):
                classes.append(value)
        for value in getattr(package, "_WRAPPER_CLASSES", {}).values():
            classes.append(value)
    for name in mlib.common._exports:
        value = getattr(mlib.common, name)
        if inspect.isclass(value):
            classes.append(value)
    unique = []
    for value in classes:
        if value not in unique:
            unique.append(value)
    return sorted(unique, key=lambda value: value.__name__)


def _public_functions():
    """公開関数を {キー: 関数} で返す。"""
    functions = {}
    for name in mlib.cmds.__all__:
        functions["cmds." + name] = getattr(mlib.cmds, name)
    for module, prefix in ((mlib.decorator, "decorator."), (mlib.util, "util.")):
        for name in module.__all__:
            functions[prefix + name] = getattr(module, name)
    modules = [(mlib.common.units, "common.units.")]
    # 参照の列挙・作成は common._exports に無い正式入口なので明示的に読む。
    from mlib.common import references
    modules.append((references, "common.references."))
    for module, prefix in modules:
        names = getattr(module, "__all__", None) or [
            name for name, value in vars(module).items()
            if inspect.isfunction(value) and value.__module__ == module.__name__ and not name.startswith("_")]
        for name in names:
            functions[prefix + name] = getattr(module, name)
    return functions


def _owner_name(cls, definer):
    """メンバーを定義したクラスの公開名。非公開の mixin は直後に継承した公開クラス名にする。"""
    if not definer.__name__.startswith("_"):
        return definer.__name__
    mro = cls.__mro__
    for index in range(mro.index(definer) - 1, -1, -1):
        if not mro[index].__name__.startswith("_"):
            return mro[index].__name__
    return cls.__name__


def public_members():
    """公開 API を {キー: 呼出し可能オブジェクト} で返す。

    クラスのメンバーは定義したクラスの名前で 1 回だけ数える(継承した同じ実装は重複させない)。
    mlib 以外(om2 等)から継承したメンバーは含めない。
    """
    members = dict(_public_functions())
    for cls in _public_classes():
        for definer in cls.__mro__:
            if not definer.__module__.startswith("mlib."):
                continue
            for name, raw in vars(definer).items():
                if name.startswith("_") and name not in WRITER_OPERATORS:
                    continue
                if isinstance(raw, property):
                    if raw.fset is None:
                        continue
                    value = raw.fset
                elif isinstance(raw, (staticmethod, classmethod)):
                    value = raw.__func__
                elif inspect.isfunction(raw):
                    value = raw
                else:
                    continue
                key = _owner_name(cls, definer) + "." + name
                members.setdefault(key, value)
    return members


def accepts_fast(value):
    """呼出し可能オブジェクトが fast 引数を持つか。"""
    try:
        return "fast" in inspect.signature(value).parameters
    except (TypeError, ValueError):
        return False


def is_writer(key, value):
    """シーンを変更すると判断する公開 API か。"""
    name = key.rsplit(".", 1)[-1]
    return accepts_fast(value) or name in WRITER_OPERATORS or bool(WRITER_PATTERN.match(name))


PUBLIC_MEMBERS = public_members()


# ---------------------------------------------------------------- テスト

class _UndoHarness(NamespaceCase):
    """ケース 1 件ごとに子名前空間を作って後片付けする基底。"""

    PREFIX = "mlibUndoCoverage_"
    CLEAR_SELECTION = True
    UNLOCK_NODES = True

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mlibUndoCoverage_"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.tmp), ignore_errors=True)

    def setUp(self):
        super(_UndoHarness, self).setUp()
        self.current_layer = cmds.editDisplayLayerGlobals(query=True, currentDisplayLayer=True)
        self.case_index = 0

    def tearDown(self):
        cmds.namespace(set=":")
        if cmds.objExists(self.current_layer):
            cmds.editDisplayLayerGlobals(currentDisplayLayer=self.current_layer)
        super(_UndoHarness, self).tearDown()

    def begin(self):
        """ケース用の子名前空間をカレントにし、開始前のノード・名前空間を記録する。"""
        self.case_index += 1
        self.baseline = _scene_uuids()
        self.baseline_namespaces = set(cmds.namespaceInfo(":", listOnlyNamespaces=True, recurse=True,
                                                          absoluteName=True) or [])
        child = "c{:03d}".format(self.case_index)
        cmds.namespace(add=child, parent=":" + self.ns)
        ctx = _Context(self.ns + ":" + child, self.tmp)
        cmds.namespace(set=":" + ctx.ns)
        cmds.select(clear=True)
        return ctx

    def end(self, ctx):
        """ケースで増えたノード・名前空間を削除し、カレント・選択・レイヤーを戻す。"""
        cmds.namespace(set=":")
        if cmds.objExists(self.current_layer):
            cmds.editDisplayLayerGlobals(currentDisplayLayer=self.current_layer)
        extra = [cmds.ls(uid, long=True) for uid in _scene_uuids() - self.baseline]
        names = [found[0] for found in extra if found]
        for name in names:
            try:
                if cmds.lockNode(name, query=True, lock=True)[0]:
                    cmds.lockNode(name, lock=False)
            except Exception:
                pass
        # container を含む名前空間を deleteNamespaceContent で消してから flushUndo すると Maya が
        # 異常終了するため(cmds だけでも再現する Maya 側の不具合)、container を先に削除する。
        containers = [name for name in names if cmds.objExists(name)
                      and cmds.nodeType(name) in ("container", "dagContainer")]
        if containers:
            try:
                cmds.delete(containers)
            except Exception:
                pass
        namespaces = set(cmds.namespaceInfo(":", listOnlyNamespaces=True, recurse=True,
                                            absoluteName=True) or []) - self.baseline_namespaces
        for namespace in sorted(namespaces, key=lambda value: -value.count(":")):
            if cmds.namespace(exists=namespace):
                try:
                    cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)
                except Exception:
                    pass
        for name in names:
            if cmds.objExists(name):
                try:
                    cmds.delete(name)
                except Exception:
                    pass
        cmds.select(clear=True)
        cmds.flushUndo()


class UndoCoverageTest(_UndoHarness):
    """全ケースを通常経路で実行し、Undo 1 回・Redo 1 回の往復を確かめる。"""

    def test_undo_redo_round_trip(self):
        """各書込み API が Undo 1 回で変更前へ、Redo で変更後へ戻る。"""
        summary = []
        cases = selected_cases()
        for case in cases:
            _progress("undo " + case.label)
            with self.subTest(case.label):
                problems = self.run_case(case)
                if problems:
                    summary.append(case.label)
                    self.fail("{} [{}]\n  {}".format(case.label, case.key, "\n  ".join(problems)))
        print("[undo coverage] cases={} failed={}".format(len(cases), len(summary)))
        for label in summary:
            print("[undo coverage] FAILED " + label)

    def run_case(self, case):
        """1 ケースを実行し、問題点の説明を list で返す(問題が無ければ空)。"""
        ctx = self.begin()
        try:
            try:
                if case.setup is not None:
                    case.setup(ctx)
            except Exception:
                return ["setup で例外(テストの準備の誤り):\n" + traceback.format_exc()]
            cmds.flushUndo()
            before = take_snapshot(self.baseline)
            ignore = unstable_attrs(before, take_snapshot(self.baseline))
            member = PUBLIC_MEMBERS.get(case.key)
            kwargs = {"fast": False} if member is not None and accepts_fast(member) else {}
            try:
                _trace("phase action")
                case.action(ctx, **kwargs)
            except Exception:
                return ["通常経路の呼出しで例外:\n" + traceback.format_exc()]
            undo_name = cmds.undoInfo(query=True, undoName=True)
            queued = not cmds.undoInfo(query=True, undoQueueEmpty=True)
            after = take_snapshot(self.baseline)
            ignore = ignore | unstable_attrs(after, take_snapshot(self.baseline))
            problems = []
            changes = diff_snapshots(before, after, ignore, case)
            if not changes:
                problems.append("呼出しによる変更を検出できない(テストの準備の誤りの可能性)")
            if not queued:
                problems.append("呼出し後の Undo キューが空(Undo に何も記録されていない)")
            _trace("phase undo")
            _safe_step(cmds.undo)
            undone = take_snapshot(self.baseline)
            remaining = diff_snapshots(before, undone, ignore, case)
            steps = 1
            if remaining or not cmds.undoInfo(query=True, undoQueueEmpty=True):
                first = remaining
                while not cmds.undoInfo(query=True, undoQueueEmpty=True) and steps < MAX_UNDO_STEPS:
                    _safe_step(cmds.undo)
                    steps += 1
                    remaining = diff_snapshots(before, take_snapshot(self.baseline), ignore, case)
                    if not remaining:
                        break
                if not first:
                    problems.append("Undo 1 回で変更前と一致したが、キューに別の項目が残った"
                                    "(Undo 計 {} 回分の記録)".format(steps))
                elif remaining:
                    problems.append("Undo {} 回でも変更前に戻らない。Undo 1 回の後の差分:\n      {}".format(
                        steps, _format(first)))
                else:
                    problems.append("Undo 1 回では戻らず {} 回で戻る。Undo 1 回の後の差分:\n      {}".format(
                        steps, _format(first)))
            _trace("phase redo")
            for _ in range(steps):
                _safe_step(cmds.redo)
            redo_diff = diff_snapshots(after, take_snapshot(self.baseline), ignore, case)
            if redo_diff:
                problems.append("Redo {} 回で変更後と一致しない:\n      {}".format(steps, _format(redo_diff)))
            if problems:
                problems.insert(0, "undoName={!r} 変更={}件".format(undo_name, len(changes)))
            return problems
        finally:
            self.end(ctx)


class FastUndoQueueTest(_UndoHarness):
    """fast を持つ API は fast=True で Undo キューに何も積まない(仕様の確認)。"""

    def test_fast_records_nothing(self):
        """flush 後に fast=True で呼んでも undoQueueEmpty が True のまま。"""
        for case in selected_cases():
            member = PUBLIC_MEMBERS.get(case.key)
            if member is None or not accepts_fast(member) or case.fastSkip:
                continue
            _progress("fast " + case.label)
            with self.subTest(case.label):
                ctx = self.begin()
                try:
                    if case.setup is not None:
                        case.setup(ctx)
                    cmds.flushUndo()
                    if case.key in FAST_UNSUPPORTED:
                        with self.assertRaises(NotImplementedError):
                            case.action(ctx, fast=True)
                        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
                        continue
                    try:
                        case.action(ctx, fast=True)
                    except Exception:
                        self.fail("{} [{}] fast=True で例外:\n{}".format(case.label, case.key,
                                                                       traceback.format_exc()))
                    self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True),
                                    "{} [{}] fast=True なのに Undo キューへ記録された: undoName={!r}".format(
                                        case.label, case.key, cmds.undoInfo(query=True, undoName=True)))
                finally:
                    self.end(ctx)


class CoverageGuardTest(unittest.TestCase):
    """書込み API がケース表か除外表に載っていることを確かめる(網羅の番人)。"""

    def test_every_writer_has_case_or_exclusion(self):
        """書込みと判断した公開 API が、ケース表か理由付きの除外表に載っている。"""
        writers = sorted(key for key, value in PUBLIC_MEMBERS.items() if is_writer(key, value))
        covered = set(case.key for case in CASES)
        missing = [key for key in writers if key not in covered and key not in EXCLUDED]
        print("[undo coverage] writers={} cases={} covered={} excluded={}".format(
            len(writers), len(CASES), len(set(writers) & covered), len(set(writers) & set(EXCLUDED))))
        self.assertEqual(missing, [], "ケース表にも除外表にも無い書込み API。CASES へケースを追加するか、"
                                      "EXCLUDED へ理由を付けて載せる: {}".format(missing))

    def test_tables_name_existing_api(self):
        """ケース表・除外表の API 名が現存する公開 API を指す(改名・削除の取り残し防止)。"""
        stale = sorted((set(case.key for case in CASES) | set(EXCLUDED)) - set(PUBLIC_MEMBERS))
        self.assertEqual(stale, [], "存在しない API 名: {}".format(stale))

    def test_exclusions_are_not_also_cases(self):
        """除外表とケース表の両方に載る API が無い。"""
        both = sorted(set(case.key for case in CASES) & set(EXCLUDED))
        self.assertEqual(both, [])

    def test_fast_writers_have_fast_case(self):
        """fast を持つケース対象 API は、fast=True を確かめるケースを 1 つ以上持つ。"""
        missing = []
        for key in sorted(set(case.key for case in CASES)):
            member = PUBLIC_MEMBERS.get(key)
            if member is None or not accepts_fast(member):
                continue
            if not any(case.key == key and not case.fastSkip for case in CASES):
                missing.append(key)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
