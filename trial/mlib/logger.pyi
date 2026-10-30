# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""標準 logging と Maya のメッセージ表示を連携する。"""

import builtins
import logging
import os
import types
from typing import Any, NoReturn, TextIO

__all__ = ['MayaHandler', 'debug', 'error', 'getLogger', 'info', 'print', 'raiseWithNotify', 'warning']
LOGGER_NAME: Any
_VIEWPORT_COLORS: dict
_NO_CAUSE: Any
FULL_TRACEBACK_ENV: str
_PACKAGE_DIR: Any
_TRANSPARENT_MODULES: tuple

def _message_from(record: logging.LogRecord) -> str:
    """ビューポート向けにログ本文と引数を文字列へ整形する。

    Args:
        record (logging.LogRecord): 整形するレコード。

    Returns:
        str: getMessage()の結果。詳細トレースとFormatterはScript Editor側だけへ適用する。
    """
    ...


class MayaHandler(logging.Handler):
    """詳細ログをScript Editor、警告以上の本文をビューポートへ出力する。"""
    def emit(self, record: logging.LogRecord) -> None:
        """ログを Script Editor と必要に応じてビューポートへ出力する。

        Script Editorには標準loggingのFormatter・exc_info・stack_infoを適用する。
        WARNING以上では、例外トレースを含まないメッセージ本文をビューポートにも表示する。
        Formatterが失敗した場合は標準書式へ戻し、書式の失敗理由も詳細欄へ表示する。
        Maya APIをimportできなければ出力しない。Maya表示時のRuntimeErrorは抑制する。

        Args:
            record (logging.LogRecord): 出力するレコード。

        Returns:
            None: 値を返さない。
        """
        ...

def getLogger() -> logging.Logger:
    """Maya 向けハンドラを設定した共有ロガーを取得する。

    Returns:
        logging.Logger: コアパッケージ名のロガー。DEBUGレベル、親への伝播なし。
            reload前のMayaHandlerは現在の型へ置換し、通知を重複させない。
    """
    ...

def debug(message: object, *args: object, **kwargs: object) -> None:
    """診断レベルのログを出力する。

    Maya 上ではScript Editor に出力する。

    Args:
        message (object): ログメッセージまたは書式文字列。
        *args (object): logging に渡すメッセージ書式引数。
        **kwargs (object): exc_info、extra、stack_info、stacklevel など logging に渡すオプション。

    Returns:
        None: 値を返さない。
    """
    ...

def info(message: object, *args: object, **kwargs: object) -> None:
    """通常の情報をINFOレベルでScript Editorへ出力する。

    Args:
        message (object): ログメッセージまたは書式文字列。
        *args (object): loggingに渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    ...

def print(*objects: object, sep: str | None = ..., end: str | None = ..., file: TextIO | None = ..., flush: bool = ...) -> None:
    """Python標準のprintと同じ規則で出力する。

    Mayaでは通常Script Editorへ表示する。ログレベル・ビューポート通知は付けず、
    file指定や改行なし出力を維持する。INFOログが必要な場合はinfoを使う。

    Args:
        *objects (object): 出力する値。
        sep (str | None): 値の区切り。Noneは標準値の空白。
        end (str | None): 末尾。Noneは標準値の改行。
        file (TextIO | None): 書込み先。Noneは現在のsys.stdout。
        flush (bool): Trueなら出力先をフラッシュする。

    Returns:
        None: 値を返さない。
    """
    ...

def warning(message: object, *args: object, **kwargs: object) -> None:
    """警告をScript Editorとビューポートへ通知する。

    ログレベルを例外送出へ変換しない。引数・書式は標準loggingに従う。

    Args:
        message (object): メッセージまたは書式文字列。
        *args (object): loggingへ渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    ...

def error(message: object, *args: object, **kwargs: object) -> None:
    """エラーをScript Editorとビューポートへ通知する。

    ログレベルを例外送出へ変換しない。引数・書式は標準loggingに従う。
    通知して中断する場合はraiseWithNotifyを使う。

    Args:
        message (object): メッセージまたは書式文字列。
        *args (object): loggingへ渡す書式引数。
        **kwargs (object): exc_info、extra等のloggingオプション。

    Returns:
        None: 値を返さない。
    """
    ...

def raiseWithNotify(exceptionType: type[Exception], message: str, *args: object, fromException: BaseException | None = ..., **kwargs: object) -> NoReturn:
    """エラーを通知してから指定型の例外を送出する。

    利用者へ通知して中断するツール(HTools等)の入口用。mlib本体の例外は通知せずに送出し、
    Script Editorの表示と二重にしない。

    Args:
        exceptionType (type[Exception]): 生成する例外クラス。
        message (str): 通知と例外の先頭引数に使うメッセージ。
        *args (object): 例外コンストラクタへ渡す追加位置引数。ログには渡さない。
        fromException (BaseException | None): 指定時は ``raise ... from fromException``
            として例外連鎖を明示する(``None`` を渡すと連鎖を明示的に抑制する)。省略時は
            通常の ``raise`` と同じく、except 節内であれば暗黙の連鎖を保持する。
        **kwargs (object): 例外コンストラクタへ渡すキーワード引数。ログには渡さない。

    Returns:
        NoReturn: 正常には戻らない。

    Raises:
        Exception: exceptionType で指定した例外。コンストラクタが失敗した場合はその例外。
    """
    ...

def _internal_file(filename: str) -> bool:
    """フレームのファイルがmlib(拡張の ``<パッケージ名>_*`` を含む)の内部か判定する。

    テスト(``__tests__``)のファイルは利用者のコードとして扱う。

    Args:
        filename (str): ``frame.f_code.co_filename``。

    Returns:
        bool: パッケージ、または同じフォルダーに並ぶ拡張パッケージの中ならTrue。
    """
    ...

def _transparent_file(filename: str) -> bool:
    """with文・デコレーターの標準ライブラリのフレームか判定する。

    Args:
        filename (str): ``frame.f_code.co_filename``。

    Returns:
        bool: contextlib・functoolsのファイルならTrue。
    """
    ...

def _trimmed_traceback(trace: types.TracebackType | None) -> types.TracebackType | None:
    """末尾に続くmlib内部のフレームを除いたトレースバックを返す。

    最後の利用者のフレーム(mlib・contextlib・functools以外)より後ろがmlib内部だけの場合に、
    その利用者のフレームで終わる新しいトレースバックを作る。元のトレースバックは変更しない。
    利用者のフレームが無い(mlib内部だけの)場合や、末尾が利用者のコードの場合はそのまま返す。

    Args:
        trace (types.TracebackType | None): 表示するトレースバック。

    Returns:
        types.TracebackType | None: 省略したトレースバック、または元の値。
    """
    ...

def _install_exception_formatter() -> bool:
    """Script Editorのエラー表示で、mlib内部のフレームを省く書式関数を設定する。

    Maya公式の差し替え口 ``maya.utils.formatGuiException`` を、元の関数を呼ぶ関数で包む。
    Script Editorは最後のフレームのファイル・行を表示するため、mlibの中で送出した例外も
    利用者がmlibを呼んだ行を表示する。環境変数 ``MLIB_FULL_TRACEBACK`` を空以外にすると
    省かずに表示する(呼出しごとに判定する)。再読み込みでは以前の包みを外して設定し直す。
    Mayaが無い環境では何もしない。

    Returns:
        bool: 設定した場合はTrue。
    """
    ...
