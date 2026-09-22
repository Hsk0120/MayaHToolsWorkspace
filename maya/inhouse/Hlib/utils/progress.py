"""反復処理の進捗をストリームへ出力する。"""

import sys


def progress_bar(iterable, prefix="", size=60, file=sys.stdout, notify=None):
    """進捗を出力しながら入力要素を順に返す。

    最初に0件の進捗を表示し、各 yield の再開後に進捗を更新する。空入力では何も出力しない。最後まで消費した場合のみ末尾の改行を出力する。

    Args:
        iterable (Sized): len() と反復に対応する入力。
        prefix (str): 進捗バーの前に付ける文字列。
        size (int): バーの表示幅。既定は60。
        file (TextIO): write/flush を備える出力先。既定はモジュール読み込み時の sys.stdout。
        notify (Callable[[str], object] | None): 表示文字列を受け取る任意の通知関数。戻り値は無視する。

    Yields:
        object: 入力の各要素をそのまま返す。
    """
    count = len(iterable)
    if count == 0:
        return

    def show(index):
        """現在の処理数から進捗表示を更新する。

        出力先を flush してから、指定があれば notify に表示文字列を渡す。

        Args:
            index (int): 処理済み要素数。

        Returns:
            None: 値を返さない。
        """
        filled = int(size * index / count)
        text = f"{prefix}[{'#' * filled}{'.' * (size - filled)}] {index}/{count}"
        file.write(text + "\r")
        file.flush()
        if notify is not None:
            notify(text)

    show(0)
    for index, item in enumerate(iterable, 1):
        yield item
        show(index)
    file.write("\n")
    file.flush()