"""子のプロセスでも、``byMlib/`` の mlib 版への差し替え(``tools/by_mlib.py``)を有効にする。

``tools/by_mlib.py`` が ``PYTHONPATH`` の先頭にこのフォルダーを足し、環境変数 ``BY_MLIB_ROOTS`` に
対象のツールのフォルダーを入れて子のプロセスを起動する。Python が起動時にこのファイルを読み込む。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import by_mlib

    by_mlib.install()
finally:
    sys.path.pop(0)
