"""コピーしたプロジェクトから編集案だけを返す。元ファイルは一切更新しない。"""
import io
import json
import keyword
import os
from pathlib import Path
import sys
import tempfile
import tokenize


def codepoint_offset(text, units):
    """QtのUTF-16位置をPythonのコードポイント位置へ変換する。"""
    if not isinstance(units, int) or units < 0:
        raise ValueError("Invalid selection offset")
    encoded = text.encode("utf-16-le")
    if units * 2 > len(encoded):
        raise ValueError("Selection is outside the document")
    return len(encoded[:units * 2].decode("utf-16-le"))


def read_source(path):
    """Pythonのcoding宣言を尊重して改行を正規化する。"""
    data = path.read_bytes()
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")


def calculate(request):
    """隔離コピー上で抽出・移動・import整理の変更案を計算する。

    Args:
        request (dict): root/path/overlays/action/selection/name/destination。

    Returns:
        dict: 変更前本文とWorkspaceEdit。元のプロジェクトに書込みはしない。
    """
    # 任意依存は外部プロセスの専用配置だけから取得する。
    from rope.base.project import Project
    from rope.refactor.extract import ExtractMethod, ExtractVariable
    from rope.refactor.importutils import ImportOrganizer
    from rope.refactor.move import MoveGlobal
    from rope.refactor.rename import Rename

    root = Path(request["root"]).resolve(strict=True)
    source = Path(request["path"]).resolve()
    relative = source.relative_to(root)
    action = request["action"]
    name = request.get("name", "")
    if action in ("variable", "function", "rename_module") and (not name.isidentifier() or keyword.iskeyword(name)):
        raise ValueError("Use a valid Python identifier")
    texts = {}
    size = 0
    ignored = {".git", ".maya-output", "node_modules", "__pycache__", ".venv", "venv", ".ropeproject", "build", "release"}
    for folder, directories, files in os.walk(str(root), followlinks=False):
        directories[:] = [part for part in directories if part not in ignored and not Path(folder, part).is_symlink()
                          and not (hasattr(Path(folder, part), "is_junction") and Path(folder, part).is_junction())]
        for filename in files:
            path = Path(folder, filename)
            if path.suffix not in (".py", ".pyi") or path.is_symlink():
                continue
            path.resolve().relative_to(root)
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Refactoring refused: a source file exceeds 2 MiB")
            text = read_source(path)
            size += len(text)
            if len(texts) >= 5000 or size > 32 * 1024 * 1024:
                raise ValueError("Refactoring project is too large; choose a smaller project root")
            texts[path.relative_to(root).as_posix()] = text
    for path, text in request.get("overlays", {}).items():
        local = Path(path).resolve().relative_to(root).as_posix()
        if not isinstance(text, str) or len(text) > 2 * 1024 * 1024:
            raise ValueError("Invalid editor contents")
        texts[local] = text
    if len(texts) > 5000 or sum(len(text) for text in texts.values()) > 32 * 1024 * 1024:
        raise ValueError("Refactoring project with unsaved documents is too large")
    if relative.as_posix() not in texts:
        raise ValueError("The active Python document is unavailable")
    before = texts[relative.as_posix()]
    start = codepoint_offset(before, request.get("start", 0))
    end = codepoint_offset(before, request.get("end", 0))
    with tempfile.TemporaryDirectory(prefix="mce-refactor-") as temporary:
        staging = Path(temporary)
        for path, text in texts.items():
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            # coding宣言と実際のバイト列を一致させ、Ropeによる再読込で文字を壊さない。
            encoding, _ = tokenize.detect_encoding(io.BytesIO(text.encode("utf-8")).readline)
            target.write_bytes(text.encode(encoding))
        # ropefolder=Noneでユーザーのconfig.pyを読み込ませない。動的解析も無効にする。
        project = Project(str(staging), ropefolder=None, save_objectdb=False, save_history=False,
                          automatic_soa=False, soa_followed_calls=0, extension_modules=[], python_path=[])
        try:
            resource = project.get_resource(relative.as_posix())
            if action == "variable":
                changes = ExtractVariable(project, resource, start, end).get_changes(name, similar=False)
            elif action == "function":
                changes = ExtractMethod(project, resource, start, end).get_changes(name, similar=False)
            elif action in ("move", "move_new"):
                destination = Path(request["destination"]).resolve().relative_to(root).as_posix()
                if action == "move_new":
                    dest = root / destination
                    if dest.exists() or destination in texts or dest.suffix != ".py" or not dest.stem.isidentifier() or keyword.iskeyword(dest.stem):
                        raise ValueError("Choose a new Python module name")
                    if not dest.parent.is_dir():
                        raise ValueError("The destination folder must already exist")
                    (staging / destination).parent.mkdir(parents=True, exist_ok=True)
                    (staging / destination).write_text("", encoding="utf-8")
                    texts[destination] = ""
                if destination not in texts or destination == relative.as_posix():
                    raise ValueError("Choose a different existing Python module inside this project")
                changes = MoveGlobal(project, resource, start).get_changes(project.get_resource(destination))
            elif action == "rename_module":
                if source.name == "__init__.py":
                    raise ValueError("Package renaming is not supported")
                destination = relative.with_name(name + ".py").as_posix()
                if (root / destination).exists() or destination in texts:
                    raise ValueError("The destination already exists")
                changes = Rename(project, resource).get_changes(name)
            elif action == "imports":
                changes = ImportOrganizer(project).organize_imports(resource)
            else:
                raise ValueError("Unknown refactoring")
            if changes is not None:
                project.do(changes)
            after_texts = {p.relative_to(staging).as_posix(): read_source(p)
                           for p in staging.rglob("*") if p.is_file() and p.suffix in (".py", ".pyi")}
            expected = set(texts)
            if action == "rename_module":
                expected.remove(relative.as_posix())
                expected.add(destination)
            if set(after_texts) != expected:
                raise ValueError("Unexpected file operations in refactoring")
            edits, originals, operations = {}, {}, []
            new_path = destination if action == "move_new" else None
            for key, old in texts.items():
                if key == new_path:
                    operations.append({"kind": "create", "uri": (root / key).as_uri()})
                target_key = destination if action == "rename_module" and key == relative.as_posix() else key
                if target_key not in after_texts:
                    raise ValueError("Unexpected file deletion in refactoring")
                updated = after_texts[target_key]
                if updated != old or key == new_path:
                    address = (root / key).as_uri()
                    lines = old.split("\n")
                    finish = {"line": len(lines) - 1, "character": len(lines[-1].encode("utf-16-le")) // 2}
                    edits[address] = [{"range": {"start": {"line": 0, "character": 0}, "end": finish},
                                       "newText": updated}]
                    if key != new_path:
                        originals[address] = old
            if action == "rename_module":
                operations.append({"kind": "rename", "oldUri": source.as_uri(),
                                   "newUri": (root / destination).as_uri()})
                originals[source.as_uri()] = before
            return {"edit": {"changes": edits, "documentChanges": operations}, "before": originals}
        finally:
            project.close()


def main():
    """JSONを標準入出力で交換する。診断もJSONにしコードを実行しない。"""
    sys.path.insert(0, sys.argv[1])
    try:
        request = json.loads(sys.stdin.buffer.read(40 * 1024 * 1024).decode("utf-8"))
        result = calculate(request)
    except Exception as error:
        result = {"error": "{}: {}".format(type(error).__name__, error)}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True).encode("utf-8"))


if __name__ == "__main__":
    main()
