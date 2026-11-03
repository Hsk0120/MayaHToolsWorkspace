"""Maya のペイントの仕組み(artUserPaintCtx)で、Skin Weight Kit のブラシを使えるようにする。

独自のプラグインは作らず、Maya 標準のユーザーペイントのツールに、頂点ごとの処理を MEL の関数として渡す。
ブラシの大きさ・強さ(Opacity・Value)・減衰は、Maya のツール設定(Tool Settings)で変える。
ストロークの始めにパネルから設定(ブラシの種類・アクティブなインフルエンス等)を読み、計算は
:class:`skinWeightKit.core.paint.PaintSession` が行う。1ストロークは1回の Undo で戻せる。
"""

import maya.cmds as cmds
import maya.mel as mel

import mlib

from ..core import paint as paint_core
from ..core import smoothing
from ..core import target as target_module

#: ペイントのコンテキストの名前。
CONTEXT = "skinWeightKitPaintContext"

#: Maya が呼ぶ MEL の関数の名前。
INITIALIZE, SET_VALUE, FINALIZE, CLEANUP = ("swkPaintInitialize", "swkPaintSetValue", "swkPaintFinalize",
                                            "swkPaintCleanup")

#: 今のストロークと、ストロークの設定を返す関数、作った隣の頂点の重み(メッシュと設定ごとに使い回す)。
_state = {"session": None, "provider": None, "neighbors": {}}


def _define_procedures():
    """Maya のペイントから呼ぶ MEL の関数を定義する(何度呼んでもよい)。"""
    module = "import skinWeightKit.ui.paint as _swkPaint; _swkPaint."
    mel.eval('global proc string {0}(string $name) {{ python("{1}_initialize(\'" + $name + "\')"); return ""; }}'
             .format(INITIALIZE, module))
    mel.eval('global proc {0}(int $slot, int $index, float $value) {{ python("{1}_setValue(" + $index + ", " + '
             '$value + ")"); }}'.format(SET_VALUE, module))
    mel.eval('global proc {0}(int $slot) {{ python("{1}_finalize()"); }}'.format(FINALIZE, module))
    mel.eval('global proc {0}(string $name) {{ python("{1}_cleanup()"); }}'.format(CLEANUP, module))


def start(provider):
    """ブラシのツールにする。

    Args:
        provider (Callable[[], dict]): ストロークの始めに呼び、``mode``・``influence``・``source``・``method``・
            ``radius``・``keepMax`` の設定を返す関数(パネルが渡す)。

    Returns:
        str: コンテキストの名前。
    """
    _define_procedures()
    _state["provider"] = provider
    _state["neighbors"] = {}
    if not cmds.artUserPaintCtx(CONTEXT, exists=True):
        cmds.artUserPaintCtx(CONTEXT)
    cmds.artUserPaintCtx(CONTEXT, edit=True, initializeCmd=INITIALIZE, setValueCommand=SET_VALUE,
                         finalizeCmd=FINALIZE, toolCleanupCmd=CLEANUP, whichTool="userPaint", fullpaths=True,
                         outwhilepaint=True, brushfeedback=False, selectedattroper="additive")
    cmds.setToolTo(CONTEXT)
    return CONTEXT


def isActive():
    """ブラシのツールを使っているかを返す。

    Returns:
        bool: 使っていればTrue。
    """
    return cmds.currentCtx() == CONTEXT


def _neighbors(mesh, method, radius):
    """隣の頂点の重みを、メッシュと設定ごとに作って使い回す。"""
    key = (str(mesh), method, round(float(radius), 6))
    if key not in _state["neighbors"]:
        _state["neighbors"][key] = smoothing.neighborWeights(mesh, method, radius)
    return _state["neighbors"][key]


def _initialize(name):
    """ストロークの始め。パネルの設定でストロークを準備する。"""
    _state["session"] = None
    try:
        settings = _state["provider"]() if _state["provider"] is not None else {"mode": "smooth"}
        meshes = target_module._meshes_of(mlib.getNode(name))
        if not meshes:
            raise ValueError("{} is not a mesh".format(name))
        mesh = meshes[0]
        skins = mesh.getSkinClusters()
        current = target_module.Target(mesh, skins[0] if skins else None, None)
        neighbors = None
        if settings.get("mode", "smooth") in ("smooth", "sharpen"):
            neighbors = _neighbors(mesh, settings.get("method", "uniform"), settings.get("radius", 0.0))
        _state["session"] = paint_core.PaintSession(
            current, settings.get("mode", "smooth"), settings.get("influence"), settings.get("source"),
            settings.get("method", "uniform"), settings.get("radius", 0.0), settings.get("keepMax", False), neighbors)
    except (ValueError, RuntimeError) as error:
        cmds.warning("Skin Weight Kit: {}".format(error))


def _setValue(index, value):
    """頂点を塗る(ストロークの間、頂点ごとに呼ばれる)。"""
    if _state["session"] is not None:
        _state["session"].dab(index, value)


def _finalize():
    """ストロークの終わり。1回の Undo で書く。"""
    session, _state["session"] = _state["session"], None
    if session is not None:
        session.finish()


def _cleanup():
    """ツールを抜けるとき。途中のストロークがあれば確定する。"""
    _finalize()
    _state["neighbors"] = {}
