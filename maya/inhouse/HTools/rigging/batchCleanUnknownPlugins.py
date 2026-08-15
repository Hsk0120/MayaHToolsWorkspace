"""シーン参照を再帰巡回して unknownPlugin を一括除去するユーティリティ。"""

from collections import deque
import os

import maya.cmds as cmds


DEFAULT_TARGET_PLUGINS = (
    "wobble2009",
    "DF_locator_09win32",
    "NoiseD",
    "shaveNode",
    "wmSolid",
    "wobble2013-x64",
)


def _normalize_path(path):
    return os.path.normcase(os.path.normpath(path))


def _list_unknown_plugins():
    return cmds.unknownPlugin(q=True, l=True) or []


def _list_reference_paths():
    refs = cmds.file(q=True, r=True, withoutCopyNumber=True) or []
    return [ref for ref in refs if isinstance(ref, str) and ref]


def _remove_target_unknown_plugins(target_plugins, remove_all_unknown=False):
    unknown_plugins = _list_unknown_plugins()
    if remove_all_unknown:
        to_remove = unknown_plugins
    else:
        target_lower = {name.lower() for name in target_plugins}
        to_remove = [name for name in unknown_plugins if name.lower() in target_lower]

    removed = []
    failed = []
    for plugin_name in to_remove:
        try:
            cmds.unknownPlugin(plugin_name, remove=True)
            removed.append(plugin_name)
        except Exception as exc:
            failed.append((plugin_name, str(exc)))

    return removed, failed, unknown_plugins


def _remove_unknown_nodes_if_needed(remove_unknown_nodes=False):
    if not remove_unknown_nodes:
        return []

    unknown_nodes = cmds.ls(type="unknown") or []
    if unknown_nodes:
        cmds.delete(unknown_nodes)
    return unknown_nodes


def _open_scene(scene_path, force=True):
    cmds.file(scene_path, o=True, f=force, prompt=False, ignoreVersion=True)


def batch_clean_unknown_plugins(
    root_scene_path=None,
    include_references=True,
    target_plugins=None,
    remove_all_unknown=False,
    remove_unknown_nodes=False,
    save_scene=True,
    force=True,
    reopen_root_scene=True,
):
    """現在シーン(または指定シーン)から参照を巡回して unknownPlugin を除去する。"""
    if target_plugins is None:
        target_plugins = DEFAULT_TARGET_PLUGINS

    current_scene = cmds.file(q=True, sn=True)
    start_scene = root_scene_path or current_scene
    if not start_scene:
        raise RuntimeError("root_scene_path が未指定で、現在シーンも未保存です。")

    start_scene = os.path.abspath(start_scene)
    if not os.path.exists(start_scene):
        raise RuntimeError("開始シーンが見つかりません: {0}".format(start_scene))

    queue = deque([start_scene])
    visited = set()

    report = {
        "processed": [],
        "saved": [],
        "skipped": [],
        "failed_scenes": [],
        "removed_plugins": {},
        "failed_plugin_removals": {},
        "removed_unknown_nodes": {},
    }

    while queue:
        scene_path = os.path.abspath(queue.popleft())
        normalized = _normalize_path(scene_path)
        if normalized in visited:
            continue
        visited.add(normalized)

        if not os.path.exists(scene_path):
            report["skipped"].append(scene_path)
            continue

        try:
            _open_scene(scene_path, force=force)
        except Exception as exc:
            report["failed_scenes"].append((scene_path, str(exc)))
            continue

        removed_plugins, failed_plugin_removals, unknown_before = _remove_target_unknown_plugins(
            target_plugins=target_plugins,
            remove_all_unknown=remove_all_unknown,
        )

        removed_unknown_nodes = _remove_unknown_nodes_if_needed(
            remove_unknown_nodes=remove_unknown_nodes
        )

        changed = bool(removed_plugins or removed_unknown_nodes)
        if changed and save_scene:
            try:
                cmds.file(save=True, force=force)
                report["saved"].append(scene_path)
            except Exception as exc:
                report["failed_scenes"].append((scene_path, "save failed: {0}".format(exc)))

        if removed_plugins:
            report["removed_plugins"][scene_path] = removed_plugins
        if failed_plugin_removals:
            report["failed_plugin_removals"][scene_path] = failed_plugin_removals
        if removed_unknown_nodes:
            report["removed_unknown_nodes"][scene_path] = removed_unknown_nodes

        report["processed"].append(
            {
                "scene": scene_path,
                "unknown_before": unknown_before,
                "removed_plugins": removed_plugins,
                "removed_unknown_nodes": removed_unknown_nodes,
            }
        )

        if include_references:
            for ref in _list_reference_paths():
                ref_path = os.path.abspath(ref)
                ref_norm = _normalize_path(ref_path)
                if ref_norm not in visited:
                    queue.append(ref_path)

    if reopen_root_scene and os.path.exists(start_scene):
        try:
            _open_scene(start_scene, force=force)
        except Exception:
            pass

    print("=== batch_clean_unknown_plugins report ===")
    print("processed:", len(report["processed"]))
    print("saved:", len(report["saved"]))
    print("skipped:", len(report["skipped"]))
    print("failed_scenes:", len(report["failed_scenes"]))

    if report["removed_plugins"]:
        print("--- removed plugins by scene ---")
        for scene, plugins in report["removed_plugins"].items():
            print(scene)
            for plugin_name in plugins:
                print("  -", plugin_name)

    if report["failed_plugin_removals"]:
        print("--- failed plugin removals ---")
        for scene, items in report["failed_plugin_removals"].items():
            print(scene)
            for plugin_name, error in items:
                print("  -", plugin_name, "::", error)

    if report["failed_scenes"]:
        print("--- failed scenes ---")
        for scene, error in report["failed_scenes"]:
            print("  -", scene, "::", error)

    return report


if __name__ == "__main__":
    # 現在シーンを起点に、参照先まで含めて既知の旧プラグイン名を除去する。
    batch_clean_unknown_plugins()
