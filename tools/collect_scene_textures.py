"""開いているシーンと同じフォルダにfileテクスチャをコピーして参照を更新する。"""
import filecmp
import os
import shutil
from pathlib import Path

from maya import cmds


def _copy_texture(source, folder):
    """同名・同内容は再利用し、異なる場合は連番を付ける。"""
    number = 1
    while True:
        name = source.name if number == 1 else f"{source.stem}_{number}{source.suffix}"
        dest = folder / name
        try:
            output = dest.open("xb")
        except FileExistsError:
            if dest.is_file() and filecmp.cmp(source, dest, shallow=False):
                return dest
            number += 1
            continue
        try:
            with output, source.open("rb") as existing:
                shutil.copyfileobj(existing, output)
        except Exception:
            dest.unlink()
            raise
        return dest


def collect():
    """通常の単一画像を収集する。シーンの保存は呼び出し側で行う。"""
    scene = cmds.file(query=True, sceneName=True)
    if not scene:
        raise RuntimeError("先にシーンを保存してください")
    folder = Path(scene).parent
    plans = []
    for node in cmds.ls(type="file") or []:
        plug = node + ".fileTextureName"
        raw = cmds.getAttr(plug)
        if not raw:
            continue
        if cmds.getAttr(node + ".uvTilingMode") or cmds.getAttr(node + ".useFrameExtension"):
            raise RuntimeError(f"タイルまたは連番テクスチャが含まれています: {node}")
        source = Path(cmds.workspace(expandName=os.path.expandvars(raw))).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"{node}: {source}")
        if source.parent == folder.resolve():
            if Path(raw).is_absolute():
                continue
        if not cmds.getAttr(plug, settable=True):
            raise RuntimeError(f"参照先を書き換えられません: {plug}")
        plans.append((node, source, cmds.getAttr(node + ".colorSpace")))

    if not plans:
        return {}
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Undoを有効にしてください")
    copies = {src: _copy_texture(src, folder) for src in dict.fromkeys(p[1] for p in plans)}
    chunk = "CollectSceneTextures"
    changed = False
    cmds.undoInfo(openChunk=True, chunkName=chunk)
    try:
        try:
            for node, source, space in plans:
                cmds.setAttr(node + ".fileTextureName", copies[source].as_posix(), type="string")
                changed = True
                if cmds.getAttr(node + ".colorSpace") != space:
                    cmds.setAttr(node + ".colorSpace", space, type="string")
        finally:
            cmds.undoInfo(closeChunk=True)
    except Exception:
        if changed and cmds.undoInfo(query=True, undoName=True) == chunk:
            cmds.undo()
        raise
    return {node: str(copies[source]) for node, source, _ in plans}


if __name__ == "__main__":
    for node, path in collect().items():
        print(f"{node} -> {path}")
