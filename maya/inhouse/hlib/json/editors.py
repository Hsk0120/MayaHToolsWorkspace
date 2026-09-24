"""既存エディターとタイムラインの状態保存。"""
from .snapshots import Snapshot, ApplyPlan, _units


def _state(kind, name, flags=None):
    from maya import cmds
    from ..editors.viewport import Viewport
    from ..editors.outliner import Outliner
    if kind == "timeline":
        values = {key: cmds.playbackOptions(query=True, **{key: True}) for key in
                  ("animationStartTime", "animationEndTime", "minTime", "maxTime")}
        values["currentTime"] = cmds.currentTime(query=True)
    else:
        classes = {"viewport": Viewport, "outliner": Outliner}
        cls = classes[kind]
        flags = flags or cls._flags
        if set(flags) - set(cls._flags):
            raise ValueError("Unsupported editor flags")
        command = cmds.modelEditor if kind == "viewport" else cmds.outlinerEditor
        if cmds.about(batch=True) or not command(name, exists=True):
            raise ValueError("GUI editor does not exist: " + name)
        values = {flag: command(name, query=True, **{flag: True}) for flag in flags}
    return {"editor": kind, "target": name, "values": values}


class EditorSnapshot(Snapshot):
    """Viewport/Outlinerの公開設定とTimeSliderの時刻・範囲。選択範囲と再生状態は含めない。"""

    def plan(self, mapping=None, namespace_map=None):
        """UI名のmappingを適用して前後の設定を検証する。"""
        from maya import cmds
        from .codec import encode
        plan = ApplyPlan(self, dict(mapping or {}), dict(namespace_map or {}))
        if self.kind != "editor" or type(self.version) is not int or self.version != 1:
            plan.errors.append("Unsupported editor snapshot version/kind")
            return plan
        if namespace_map:
            plan.errors.append("Editor snapshots use UI-name mapping, not namespaces")
        if self.units != _units():
            plan.errors.append("Maya units differ")
        seen = set()
        for record in self.records:
            try:
                kind = record["editor"]
                target = plan.mapping.get(record["target"], record["target"])
                if (kind, target) in seen:
                    raise ValueError("Duplicate editor target")
                seen.add((kind, target))
                current = _state(kind, target, tuple(record["values"]))
                if kind == "timeline":
                    v = record["values"]
                    if set(v) != set(current["values"]) or not v["animationStartTime"] <= v["minTime"] <= v["maxTime"] <= v["animationEndTime"]:
                        raise ValueError("Invalid timeline bounds")
                    if cmds.play(query=True, state=True):
                        raise ValueError("Stop playback before applying timeline state")
                elif any(type(v) is not type(current["values"][k]) for k, v in record["values"].items()):
                    raise ValueError("Editor flag type differs")
                after = dict(record, target=target)
                encode(after)
                plan.changes.append({"target": target, "before": current, "after": after})
            except (KeyError, TypeError, ValueError, RuntimeError) as error:
                plan.errors.append(str(error))
        return plan

    def apply(self, mapping=None, namespace_map=None):
        """検証後に専用Undoコマンドで設定する。Undo対象のUIは存続している必要がある。"""
        from maya import cmds
        from . import _editor_command
        plan = self.plan(mapping, namespace_map)
        if plan.errors:
            raise ValueError("\n".join(plan.errors))
        if not cmds.undoInfo(query=True, state=True):
            raise RuntimeError("Snapshot.apply requires Undo enabled")
        _editor_command.apply(plan.changes)
        return plan


def capture_editors(targets):
    """hlibのViewport/Outliner/TimeSliderまたはその列を取得する。"""
    from ..editors.viewport import Viewport
    from ..editors.outliner import Outliner
    from ..editors.timeSlider import TimeSlider
    types = (Viewport, Outliner, TimeSlider)
    items = [targets] if isinstance(targets, types) else list(targets)
    records = []
    for item in items:
        if isinstance(item, TimeSlider):
            records.append(_state("timeline", "timeline"))
        elif isinstance(item, (Viewport, Outliner)):
            records.append(_state("viewport" if isinstance(item, Viewport) else "outliner", item.name()))
        else:
            raise TypeError("Expected Viewport, Outliner or TimeSlider")
    return EditorSnapshot("editor", records, _units())
