"""HToolsの各ツールの説明ページ(Sphinx)を開く。

説明ページはGitHub Pagesの ``htools/<カテゴリ>/<ツール>.html`` に公開する
(元の文書は ``HTools/_docs``)。環境変数 ``HTOOLS_DOCS_URL`` に別の場所
(手元でビルドしたHTMLのフォルダーのURLなど)を入れると、そちらを開く。

Examples:
    ツールの画面のHelpから開く::

        from HTools import toolHelp
        toolHelp.openHelp("rigging", "coneReaderUI")
"""

import os

from maya import cmds

DOCS_URL = "https://hsk0120.github.io/MayaHToolsWorkspace/htools/"


def getHelpUrl(category=None, tool=None):
    """説明ページのURLを返す。

    Args:
        category (str | None): カテゴリのフォルダー名(``"rigging"`` など)。
            省略するとHTools全体の目次のページ。
        tool (str | None): ツールのファイル名(拡張子なし)。省略するとカテゴリの目次のページ。

    Returns:
        str: 説明ページのURL。
    """
    base = os.environ.get("HTOOLS_DOCS_URL") or DOCS_URL
    if not base.endswith("/"):
        base += "/"
    if not category:
        return base + "index.html"
    if not tool:
        return "{}{}/index.html".format(base, category)
    return "{}{}/{}.html".format(base, category, tool)


def openHelp(category=None, tool=None):
    """説明ページを既定のWebブラウザーで開く。

    Args:
        category (str | None): カテゴリのフォルダー名。省略すると全体の目次。
        tool (str | None): ツールのファイル名(拡張子なし)。省略するとカテゴリの目次。

    Returns:
        str: 開いたURL。
    """
    url = getHelpUrl(category, tool)
    # showHelp は Maya の設定どおりのブラウザーで開く(Qtを使わずに済む)。
    cmds.showHelp(url, absolute=True)
    return url
