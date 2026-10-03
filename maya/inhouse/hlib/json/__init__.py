"""Maya/hlibの参照・数学型・状態をJSONで一時保存する公開入口。"""
globals().pop("CurveSnapshot", None)

from .jsonText import JsonText
from .document import JsonDocument
from .references import NodeRef, PlugRef, ComponentRef
from .storage import dump, dumps, load, loads, loadDocument
from .snapshots import (Snapshot, SelectionSnapshot, AttributesSnapshot, PoseSnapshot,
                        NurbsCurveSnapshot, SkinWeightsSnapshot, AnimationSnapshot,
                        DrivenKeysSnapshot, ValidationReport, ApplyPlan, capture)
from .editors import EditorSnapshot

__all__ = ["JsonText", "JsonDocument", "NodeRef", "PlugRef", "ComponentRef", "dump", "dumps", "load", "loads",
           "loadDocument", "Snapshot", "SelectionSnapshot", "AttributesSnapshot", "PoseSnapshot",
           "NurbsCurveSnapshot", "SkinWeightsSnapshot", "AnimationSnapshot", "DrivenKeysSnapshot",
           "EditorSnapshot", "ValidationReport", "ApplyPlan", "capture"]


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('load_document',):
    globals().pop(_obsolete_name, None)
