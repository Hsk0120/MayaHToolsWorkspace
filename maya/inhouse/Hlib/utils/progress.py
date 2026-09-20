"""Dependency-free progress reporting utilities."""

import sys


def progress_bar(iterable, prefix="", size=60, file=sys.stdout, notify=None):
    """Yield an iterable while writing progress and optionally notifying.

    Args:
        iterable: Sized iterable to process.
        prefix: Text placed before the progress bar.
        size: Number of characters in the bar.
        file: Output stream.
        notify: Optional callable accepting the rendered progress text.
    """
    count = len(iterable)
    if count == 0:
        return

    def show(index):
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