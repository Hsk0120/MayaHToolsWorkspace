"""UTF-8 JSONの一時保存と置換保存。読み込みではシーンを変更しない。"""
import json as _json
import os
from pathlib import Path
import tempfile
from .document import JsonDocument


def dumps(data, metadata=None, indent=2):
    """データをhlib形式のJSON文字列へ変換する。"""
    document = data if isinstance(data, JsonDocument) else JsonDocument(data, metadata or {})
    return _json.dumps(document.to_data(), ensure_ascii=False, allow_nan=False, indent=indent)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def loads(text):
    """文字列から元の値を復元する。SnapshotはSnapshot、参照は未解決の参照。"""
    return _read_document(text).data


def _read_document(text):
    def invalid(value):
        raise ValueError("Invalid JSON number: " + value)
    return JsonDocument.from_data(_json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid))


def dump(data, path=None, metadata=None, indent=2):
    """UTF-8で保存しPathを返す。省略時はOS一時領域の一意なファイル。

    明示パスは同一ディレクトリの一時ファイルからos.replaceする。
    親フォルダーは事前に用意する。自動削除は行わない。
    """
    text = dumps(data, metadata=metadata, indent=indent)
    target = Path(path).expanduser().resolve() if path is not None else None
    fd, name = tempfile.mkstemp(prefix="hlib_", suffix=".json", dir=str(target.parent) if target else None)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if target:
            os.replace(str(temporary), str(target))
        return target or temporary
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def load_document(path):
    """メタデータを含むJsonDocumentを読み込む。"""
    return _read_document(Path(path).read_text(encoding="utf-8"))


def load(path):
    """ファイルから値を読み込む。Mayaへは適用しない。"""
    return load_document(path).data
