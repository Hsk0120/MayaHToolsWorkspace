"""既存エディターとタイムラインの状態保存。"""

from .snapshots import Snapshot, ApplyPlan, _units


def _state(kind, name, flags=None):
    """エディタまたはタイムラインの対応する設定値を問い合わせる。

    Args:
        kind (str): viewport、outliner、timeline のいずれか。
        name (str): UI 名。timeline では参照しない。
        flags (Iterable[str] | None): 照会するフラグ。省略時は対応する全フラグ。

    Returns:
        dict: editor、target、values。時間は現在の Maya 時間単位。
    """
    from maya import cmds
    from ..common._editor import _query_settings
    from ..common.viewport import Viewport
    from ..common.outliner import Outliner
    if kind == "timeline":
        from ..common.timeSlider import TimeSlider
        values = {flag: TimeSlider._query_value(flag) for flag in
                  ("animationStartTime", "animationEndTime", "minTime", "maxTime", "currentTime")}
    else:
        classes = {"viewport": Viewport, "outliner": Outliner}
        cls = classes[kind]
        flags = flags or cls._flags
        if set(flags) - set(cls._flags):
            raise ValueError("Unsupported editor flags")
        command = cmds.modelEditor if kind == "viewport" else cmds.outlinerEditor
        if cmds.about(batch=True) or not command(name, exists=True):
            raise ValueError("GUI editor does not exist: " + name)
        values = _query_settings(command, name, flags)
    return {"editor": kind, "target": name, "values": values}


class EditorSnapshot(Snapshot):
    """Viewport/Outlinerの公開設定とTimeSliderの時刻・範囲を保存・比較する。

    標準コマンドだけでは全設定のUndoを保証できないため、applyは未対応。
    独自プラグインは使用しない。選択範囲と再生状態は含めない。
    """

    @classmethod
    def capture(cls, targets):
        """既存エディターまたはタイムラインの公開設定を取得する。

        Args:
            targets (Viewport | Outliner | TimeSlider | Iterable): 対象またはその列。

        Returns:
            EditorSnapshot: 保存・読み込み・比較用の設定値。applyは未対応。
        """
        from .snapshots import capture
        return capture(targets, kind="editor")

    @property
    def supportsApply(self):
        """bool: False。標準コマンドだけで全設定のUndoを保証できないため。"""
        return False

    def plan(self, mapping=None, namespace_map=None):
        """UI 名の対応を適用し、変更候補と検証エラーを収集する。

        Args:
            mapping (dict | None): 保存した UI 名から現在の UI 名への対応。
            namespace_map (dict | None): 非空の指定は未対応としてエラーに記録する。

        Returns:
            ApplyPlan: 変更候補とエラー。全 UI 状態の Undo を保証できないため、
                現在は適用未対応のエラーを必ず含む。シーンや UI は変更しない。
        """
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
        plan.errors.append("EditorSnapshot.apply is unsupported: native commands cannot guarantee Undo for all editor state; custom plugins are not used")
        return plan

    def apply(self, mapping=None, namespace_map=None):
        """変更前にNotImplementedErrorを送出する。保存・読み込み・比較のみ対応。

        Args:
            mapping (dict | None): Snapshot共通インターフェースの引数。この型では適用自体が未対応。
            namespace_map (dict | None): Snapshot共通インターフェースの引数。この型では適用自体が未対応。
        Raises:
            NotImplementedError: 全エディター状態のUndoを標準コマンドだけでは保証できないため。
        """
        raise NotImplementedError("EditorSnapshot supports capture/load/plan only; applying editor state without guaranteed Undo is not supported")


def captureEditors(targets):
    """Maya エディタの設定値をスナップショットとして取得する。

    Args:
        targets (Viewport | Outliner | TimeSlider | Iterable): 対象 UI またはその列。

    Returns:
        EditorSnapshot: 対象名・対応する設定値・現在の Maya 単位を保持するデータ。
            UI オブジェクト自体ではない。復元の適用は未対応。

    Raises:
        TypeError: 対応していない UI 型を指定した場合。
    """
    from ..common.viewport import Viewport
    from ..common.outliner import Outliner
    from ..common.timeSlider import TimeSlider
    types = (Viewport, Outliner, TimeSlider)
    items = [targets] if isinstance(targets, types) else list(targets)
    records = []
    for item in items:
        if isinstance(item, TimeSlider):
            records.append(_state("timeline", "timeline"))
        elif isinstance(item, (Viewport, Outliner)):
            records.append(_state("viewport" if isinstance(item, Viewport) else "outliner", item.name))
        else:
            raise TypeError("Expected Viewport, Outliner or TimeSlider")
    return EditorSnapshot("editor", records, _units())


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('capture_editors',):
    globals().pop(_obsolete_name, None)
