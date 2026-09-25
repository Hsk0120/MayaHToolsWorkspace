"""UTF-8 JSONの一時保存と置換保存。読み込みではシーンを変更しない。"""
import json as _json
import os
from pathlib import Path
import tempfile
from .document import JsonDocument


def dumps(data, metadata=None, indent=2):
    """データをhlib形式のJSON文字列へ変換する。

    Args:
        data (object): 対応する値・Snapshot・JsonDocument。
        metadata (dict | None): 付加情報。dataがJsonDocumentなら無視し、そのmetadataを使う。
        indent (int | str | None): json.dumpsへ渡すインデント。既定2。
    Returns:
        str: hlib.json形式のJSON文字列。
    Raises:
        TypeError: 未対応型・文字列以外の辞書キー等の場合。
        ValueError: 非有限値等の場合。"""
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
    """JSON文字列からデータを復元する。シーンには適用しない。

    Args:
        text (str | bytes | bytearray): hlib.json形式のJSON。
    Returns:
        object: 保存された値。Snapshotは対応型、ノード等は未解決参照として返す。
    Raises:
        ValueError: JSON構文・重複キー・非有限値・形式/版が不正な場合。
        KeyError: 必須フィールドが欠落している場合。"""
    return _read_document(text).data


def _read_document(text):
    def invalid(value):
        raise ValueError("Invalid JSON number: " + value)
    return JsonDocument.from_data(_json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid))


def dump(data, path=None, metadata=None, indent=2):
    """UTF-8で保存する。明示パスは同じフォルダーの一時ファイルから置換する。

    Args:
        data (object): 対応する値・Snapshot・JsonDocument。
        path (str | pathlib.Path | None): 保存先。NoneならOS一時領域の一意なファイル。
        metadata (dict | None): 付加情報。dataがJsonDocumentなら無視する。
        indent (int | str | None): JSONインデント。既定2。
    Returns:
        pathlib.Path: 保存されたファイルの絶対パス。自動削除しない。
    Raises:
        OSError: 親フォルダーがない、書き込みや置換に失敗した場合。
        TypeError: 未対応データの場合。
        ValueError: 非有限値等の場合。

    親フォルダーは事前に用意する。シーンの変更やUndo操作は行わない。"""
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
    """メタデータを含むJsonDocumentを読み込む。

    Args:
        path (str | pathlib.Path): UTF-8のhlib JSONファイル。
    Returns:
        JsonDocument: データとメタデータ。シーンには適用しない。
    Raises:
        OSError: ファイルを読み込めない場合。
        ValueError: デコード・JSON構文・形式/版等が不正な場合。
        KeyError: 必須フィールドが欠落している場合。"""
    return _read_document(Path(path).read_text(encoding="utf-8"))


def load(path):
    """ファイルからデータだけを読み込む。シーンには適用しない。

    Args:
        path (str | pathlib.Path): UTF-8のhlib JSONファイル。
    Returns:
        object: 復元した値・Snapshot・未解決参照。
    Raises:
        OSError: ファイルを読み込めない場合。
        ValueError: デコード・JSON構文・形式/版等が不正な場合。
        KeyError: 必須フィールドが欠落している場合。"""
    return load_document(path).data
