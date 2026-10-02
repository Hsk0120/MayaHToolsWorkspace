"""専用mayapyで拘束構成の正しさと評価時間を比較する。GUIへ送信しない。"""

import argparse
import json
import os
from pathlib import Path
import platform
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def build_scene(cmds, backend, count, maintain_offset, chain=False, validate=True):
    """キー付き入力と同数の追従バッファを作る。

    Args:
        cmds: Mayaコマンド。
        backend (str): parent、decompose、opm。
        count (int): 拘束数。
        maintain_offset (bool): 初期姿勢を保持する。
        chain (bool): 出力を階層化する。
        validate (bool): Trueは公開APIの安全性検査込み。性能シーンは同じ内部ビルダーを使う。

    Returns:
        list[str]: 評価を要求するワールド行列プラグ。
    """
    import maya.api.OpenMaya as om
    from hrig.setups.matrixFollow import MatrixFollow

    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    cmds.undoInfo(state=False)
    parents = [cmds.createNode("transform", name=name) for name in ("sourceRoot", "targetRoot")]
    cmds.setAttr(parents[0] + ".translate", 2, 3, 4)
    cmds.setAttr(parents[1] + ".rotate", 11, -17, 23)
    for attr, end in (("translateX", 9), ("rotateY", 63)):
        cmds.setKeyframe(parents[1], attribute=attr, time=1, value=0)
        cmds.setKeyframe(parents[1], attribute=attr, time=120, value=end)
    previous = parents[1]
    outputs = []
    for i in range(count):
        source = cmds.createNode("transform", name="source%d" % i, parent=parents[0])
        target = cmds.createNode(
            "transform", name="target%d" % i, parent=previous if chain else parents[1]
        )
        for attr, start, end in (
            ("translateX", i * 0.1, i * 0.1 + 4),
            ("translateY", 1, -3),
            ("rotateY", 7, 83),
            ("rotateZ", -5, 49),
        ):
            cmds.setKeyframe(source, attribute=attr, time=1, value=start)
            cmds.setKeyframe(source, attribute=attr, time=120, value=end)
        cmds.currentTime(1)
        if backend == "parent":
            cmds.parentConstraint(source, target, maintainOffset=maintain_offset)
        elif backend in ("opm", "cpp", "bifrost"):
            selected = "standard" if backend == "opm" else backend
            if validate:
                MatrixFollow.create(
                    source, target, maintain_offset=maintain_offset, backend=selected
                )
            else:
                import hlib
                from hlib.maths import Matrix

                source_node, target_node = hlib.getNode(source), hlib.getNode(target)
                offset = (
                    Matrix(target_node.plug("worldMatrix[0]").get())
                    * Matrix(source_node.plug("worldMatrix[0]").get()).inverse()
                    if maintain_offset
                    else Matrix()
                )
                MatrixFollow._build(
                    source_node,
                    target_node,
                    target_node.parent_node(),
                    offset,
                    target + "_followMatrix",
                    selected,
                )
        else:
            matrix = cmds.createNode("multMatrix")
            decompose = cmds.createNode("decomposeMatrix")
            offset = (
                om.MMatrix(cmds.getAttr(target + ".worldMatrix[0]"))
                * om.MMatrix(cmds.getAttr(source + ".worldMatrix[0]")).inverse()
                if maintain_offset
                else om.MMatrix()
            )
            cmds.setAttr(matrix + ".matrixIn[0]", *offset, type="matrix")
            cmds.connectAttr(source + ".worldMatrix[0]", matrix + ".matrixIn[1]")
            cmds.connectAttr(target + ".parentInverseMatrix[0]", matrix + ".matrixIn[2]")
            cmds.connectAttr(matrix + ".matrixSum", decompose + ".inputMatrix")
            cmds.connectAttr(target + ".rotateOrder", decompose + ".inputRotateOrder")
            cmds.connectAttr(decompose + ".outputTranslate", target + ".translate")
            cmds.connectAttr(decompose + ".outputRotate", target + ".rotate")
        outputs.append(target + ".worldMatrix[0]")
        previous = target
    return outputs


def evaluate(cmds, outputs, frames):
    """全出力を要求し、時刻更新とDG/EM評価を計測する。

    Args:
        cmds: Mayaコマンド。
        outputs (list[str]): 評価対象。
        frames (list[int]): 評価する時刻列。

    Returns:
        float: Python呼出しを含む経過秒。描画・スキンは含まない。
    """
    # 計測の外で確認し、キャッシュが再有効化された結果を採用しない。
    if cmds.evaluator(name="cache", query=True, enable=True):
        raise RuntimeError("Cached Playback must be disabled during benchmarking")
    started = time.perf_counter()
    for frame in frames:
        cmds.currentTime(frame, update=True)
        cmds.dgeval(outputs)
    return time.perf_counter() - started


def benchmark_skirt(cmds, args):
    """実スカートの回転専用拘束を比較し、結果をJSONへ保存する。

    Args:
        cmds: Mayaコマンド。
        args: 計測CLI設定。countは3骨列の列数へ切り下げる。

    Returns:
        int: 全モードで姿勢が一致した場合0。
    """
    from unittest.mock import patch
    import hlib
    from hrig.skirtRig import SkirtRig

    original = hlib.addConstraint
    results = []
    for mode in args.modes:
        reference = None
        for backend in ("parent", "orient"):
            cmds.file(new=True, force=True)
            cmds.currentUnit(linear="cm", angle="deg", time="film")
            cmds.undoInfo(state=False)

            def create(sources, target, **kwargs):
                """構築時だけ回転専用拘束の型を比較対象へ切り替える。"""
                kwargs["type"] = backend
                if backend == "orient":
                    kwargs.pop("skipTranslate", None)
                else:
                    kwargs["skipTranslate"] = ["x", "y", "z"]
                return original(sources, target, **kwargs)

            with patch.object(hlib, "addConstraint", side_effect=create):
                rig = SkirtRig.create(driver_count=8, chain_count=max(8, args.count // 3))
            for column, chain in enumerate(rig.driver_chains()):
                for depth, driver in enumerate(chain):
                    for axis, end in (("X", 35), ("Y", -27), ("Z", 42)):
                        for frame, value in (
                            (1, -end * 0.2),
                            (120, end * (1 + column * 0.1 + depth * 0.2)),
                        ):
                            cmds.setKeyframe(
                                driver.full_name(),
                                attribute="rotate" + axis,
                                time=frame,
                                value=value,
                            )
            for attr, start, end in (
                ("blend", 0.1, 1),
                ("falloff", 0.2, 4),
                ("translateX", 0, 12),
                ("rotateY", 0, 55),
            ):
                cmds.setKeyframe(rig.root.full_name(), attribute=attr, time=1, value=start)
                cmds.setKeyframe(rig.root.full_name(), attribute=attr, time=120, value=end)
            outputs = [joint + ".worldMatrix[0]" for joint in rig.joints()]
            cmds.evaluationManager(mode=mode)
            values = []
            for frame in (1, 7, 25, 60, 110, 120, 13):
                evaluate(cmds, outputs, [frame])
                values.extend(float(v) for plug in outputs for v in cmds.getAttr(plug))
            if reference is None:
                reference = values
            error = max(abs(a - b) for a, b in zip(reference, values))
            if error > 1e-6:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(
                        dict(
                            maya=cmds.about(version=True),
                            equivalent=False,
                            failure=dict(mode=mode, backend=backend, max_abs_error=error),
                            measurements=results,
                        ),
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                raise AssertionError("Skirt pose differs: " + str((mode, backend, error)))
            evaluate(cmds, outputs, list(range(1, 121)))
            samples = [
                evaluate(cmds, outputs, [1 + i % 120 for i in range(args.frames)])
                for _ in range(args.repeats)
            ]
            results.append(
                dict(
                    mode=mode,
                    backend=backend,
                    joints=len(outputs),
                    max_abs_error=error,
                    samples_seconds=samples,
                    median_ms_frame=statistics.median(samples) * 1000 / args.frames,
                    fallback=cmds.evaluationManager(query=True, fallbackTriggered=True),
                )
            )
            print(json.dumps(results[-1]), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            dict(
                maya=cmds.about(version=True),
                frames=args.frames,
                repeats=args.repeats,
                measurements=results,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


def main():
    """隔離Mayaを初期化して比較し、生測定値をJSONへ保存する。

    Returns:
        int: 成功時0。姿勢差や実行失敗は例外で停止する。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=("off", "serial", "parallel"),
        default=["off", "serial", "parallel"],
        help="比較する評価モード。serial parallelで直列・並列を比較",
    )
    parser.add_argument("--plugins", action="store_true", help="C++/Bifrostを追加した5構成を比較")
    parser.add_argument(
        "--skirt", action="store_true", help="実際のスカートのparent/orientを比較する"
    )
    args = parser.parse_args()
    if min(args.count, args.frames, args.repeats) < 1:
        parser.error("count/frames/repeats must be positive")
    if args.frames < 2:
        parser.error("frames must be at least 2 so every repetition changes time")
    if args.plugins and args.skirt:
        parser.error(
            "--plugins compares single-input followers; it cannot be combined with --skirt"
        )
    sys.path.insert(0, str(ROOT / "maya/inhouse"))
    import maya.standalone

    # 既に初期化されたGUIではここで停止し、シーンを変更しない。
    maya.standalone.initialize(name="python")
    from maya import cmds

    try:
        cmds.evaluator(name="cache", enable=False)
        if args.skirt:
            return benchmark_skirt(cmds, args)
        backends = (
            ("parent", "decompose", "opm", "cpp", "bifrost")
            if args.plugins
            else ("parent", "decompose", "opm")
        )
        if args.plugins:
            from hlib_bifrost.environment.bifrost import Bifrost

            Bifrost.ensure_available()
        result = {
            "maya": cmds.about(version=True),
            "api": cmds.about(apiVersion=True),
            "os": platform.platform(),
            "cpu": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "maya_threads": cmds.threadCount(query=True, numberOfThreads=True),
            "count": args.count,
            "frames": args.frames,
            "repeats": args.repeats,
            "cached_playback": bool(cmds.evaluator(name="cache", query=True, enable=True)),
            "requested_modes": args.modes,
            "metric": "wall seconds including currentTime + dgeval; no draw/skin",
            "verification": [],
            "measurements": [],
        }
        if args.plugins:
            result["bifrost_version"] = cmds.pluginInfo("bifrostGraph", query=True, version=True)
        # 全モード、offset両状態、親子チェーンで標準拘束と行列構成の出力を比較する。
        for mode in args.modes:
            for offset in (False, True):
                for chain in (False, True):
                    reference = None
                    for backend in backends:
                        outputs = build_scene(cmds, backend, 8, offset, chain)
                        cmds.evaluationManager(mode=mode)
                        values = []
                        for frame in (1, 8, 31, 67, 120, 15):
                            evaluate(cmds, outputs, [frame])
                            values.extend(float(v) for plug in outputs for v in cmds.getAttr(plug))
                        if reference is None:
                            reference = values
                        error = max(abs(a - b) for a, b in zip(reference, values))
                        result["verification"].append(
                            dict(
                                mode=mode,
                                offset=offset,
                                chain=chain,
                                backend=backend,
                                max_abs_error=error,
                            )
                        )
                        if error > 1e-6:
                            raise AssertionError(
                                "Pose mismatch: " + str(result["verification"][-1])
                            )
        cases = [
            (mode, backend, chain)
            for mode in args.modes
            for backend in backends
            for chain in (False, True)
        ]
        random.Random(20260929).shuffle(cases)
        frames = [1 + i % 120 for i in range(args.frames)]
        for mode, backend, chain in cases:
            print(json.dumps(dict(start=dict(mode=mode, backend=backend, chain=chain))), flush=True)
            started = time.perf_counter()
            outputs = build_scene(cmds, backend, args.count, True, chain, validate=False)
            build_seconds = time.perf_counter() - started
            cmds.evaluationManager(mode=mode)
            evaluate(cmds, outputs, list(range(1, 121)))
            samples = [evaluate(cmds, outputs, frames) for _ in range(args.repeats)]
            row = dict(
                mode=mode,
                actual_mode=cmds.evaluationManager(query=True, mode=True),
                cached_playback=bool(cmds.evaluator(name="cache", query=True, enable=True)),
                backend=backend,
                chain=chain,
                build_seconds=build_seconds,
                samples_seconds=samples,
                median_ms_frame=1000 * statistics.median(samples) / args.frames,
                min_ms_frame=1000 * min(samples) / args.frames,
                max_ms_frame=1000 * max(samples) / args.frames,
                nodes=len(cmds.ls()),
                fallback=cmds.evaluationManager(query=True, fallbackTriggered=True),
            )
            result["measurements"].append(row)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(row), flush=True)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    sys.exit(main())
