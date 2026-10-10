"""Mayaの検証映像と数値結果を実行単位で保存する共通ツール。"""

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import uuid
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


def _digest(path, algorithm):
    """大きな動画を一括ロードせずにハッシュ値を取得する。"""
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_info():
    """保存した映像のコード版と未コミット変更の有無を取得する。"""
    def read(arguments):
        return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()
    try:
        return {"commit": read(["rev-parse", "HEAD"]), "dirty": bool(read(["status", "--porcelain"]))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def _write_report(folder, record):
    """JSONと動画プレイヤー・共有リンク付きHTMLを生成する。"""
    (folder / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    title = html.escape(record["title"])
    drive = record.get("drive")
    link = ('<p><a href="{}">Google Driveで動画を見る</a></p>'.format(html.escape(drive["url"], quote=True))
            if drive else "<p>クラウド保存は未完了です。</p>")
    content = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    content += '<title>{0}</title><body style="max-width:1000px;margin:auto;padding:16px;font-family:sans-serif"><h1>{0}</h1>'.format(title)
    content += '<video controls playsinline preload="metadata" poster="poster.png" style="width:100%" src="verification.mp4"></video>'
    content += link + '<p>数値検証: {}</p><pre style="white-space:pre-wrap">{}</pre></body></html>'.format(
        "成功" if record.get("ok") else "失敗／未判定", html.escape(json.dumps(record, ensure_ascii=False, indent=2)))
    (folder / "index.html").write_text(content, encoding="utf-8")


def encodeVideo(folder, record, encoder, width=1280, height=720):
    """保存済み実フレームを、凡例・交差判定を焼き込んだMP4へ変換する。

    Args:
        folder (Path): 実行フォルダ。
        record (dict): fps、frame_count、各フレームの診断。
        encoder (str): FFmpeg実行ファイル。
        width (int): 出力幅。
        height (int): 出力高さ。
    """
    folder = Path(folder).resolve()
    filters = ["scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2".format(width, height, width, height)]
    font = Path("C:/Windows/Fonts/arial.ttf")
    if font.is_file() and record["frames"] and "raw_intersections" in record["frames"][0]:
        filters.append("drawbox=x=0:y=0:w=iw:h=100:color=black:t=fill")
        # HUDが非アクティブviewportで描画されない場合も、動画上の凡例を確実に残す。
        shutil.copyfile(font, folder / "caption-font.ttf")
        (folder / "legend.txt").write_text("RED = UNCORRECTED   |   GREEN = CORRECTED", encoding="utf-8")
        style = "drawtext=fontfile=caption-font.ttf:fontsize=24:fontcolor=white:x=20:box=1:boxcolor=black@0.7"
        filters.append(style + ":y=20:textfile=legend.txt")
        for status in ((False, False), (True, False), (False, True), (True, True)):
            matching = [i for i, frame in enumerate(record["frames"]) if
                        (bool(frame["raw_intersections"]), bool(frame["corrected_intersections"])) == status]
            if not matching:
                continue
            runs = []
            start = end = matching[0]
            for value in matching[1:]:
                if value == end + 1:
                    end = value
                else:
                    runs.append((start, end))
                    start = end = value
            runs.append((start, end))
            filename = "status-{}-{}.txt".format(*status)
            (folder / filename).write_text("RED: {}   |   GREEN: {}".format(
                "BODY HIT" if status[0] else "CLEAR", "BODY HIT" if status[1] else "CLEAR"), encoding="utf-8")
            condition = "+".join("between(n,{},{})".format(a, b) for a, b in runs)
            filters.append(style + ":y=60:textfile={}:enable='{}'".format(filename, condition))
        # 説明用動画の段階名を大きく表示する。実フレーム側のHUDにも同じ段階名を残す。
        start = 0
        stages = [frame.get("presentation_stage") for frame in record["frames"]]
        while start<len(stages):
            end = start
            while end+1<len(stages) and stages[end+1]==stages[start]:
                end += 1
            if stages[start]:
                filename = "stage-{}.txt".format(start)
                (folder/filename).write_text(stages[start], encoding="utf-8")
                filters.append("drawtext=fontfile=caption-font.ttf:fontsize=28:fontcolor=white:x=20:y=110:"
                               "box=1:boxcolor=black@0.8:textfile={}:enable='between(n,{},{})'".format(filename, start, end))
            start = end+1
    arguments = [str(encoder), "-hide_banner", "-nostdin", "-y", "-framerate", str(record["fps"]), "-start_number", "0",
                 "-i", str(folder / "frames/frame_%05d.png"), "-frames:v", str(record["frame_count"]), "-vf", ",".join(filters),
                 "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(folder / "verification.mp4")]
    with (folder / "encode.log").open("w", encoding="utf-8") as log:
        subprocess.run(arguments, cwd=folder, stdout=log, stderr=subprocess.STDOUT, check=True)
    record.update(video_size=(folder / "verification.mp4").stat().st_size,
                  video_sha256=_digest(folder / "verification.mp4", "sha256"))
    _write_report(folder, record)


def recordVideo(title, frame_count, fps, panel, evaluate, *, ffmpeg=None, width=1280, height=720):
    """各フレームを実viewportから取得し、MP4と検証結果を保存する。

    Args:
        title (str): 検証名。
        frame_count (int): 記録するフレーム数。
        fps (float): 映像の再生速度。シーンの時間単位に合わせて指定する。
        panel (str): 記録対象の既存modelPanel。
        evaluate (callable): フレーム番号を受け取り、姿勢を更新して診断dictを返す関数。
            コールバックによるシーン変更の復元は呼び出し側で行う。
        ffmpeg (str | None): FFmpeg実行ファイル。省略時はPATHから取得する。
        width (int): MP4の幅。偶数。
        height (int): MP4の高さ。偶数。

    Returns:
        pathlib.Path: 実行結果の保存フォルダ。
    """
    if frame_count < 1 or not math.isfinite(fps) or fps <= 0 or width < 2 or height < 2 or width % 2 or height % 2:
        raise ValueError("フレーム数・fps・偶数の映像寸法を確認してください。")
    encoder = ffmpeg or shutil.which("ffmpeg")
    if not encoder or not Path(encoder).is_file():
        raise FileNotFoundError("FFmpeg実行ファイルをffmpeg引数で指定してください。")
    from maya import cmds
    import maya.OpenMaya as om
    import maya.OpenMayaUI as omui
    if cmds.about(batch=True) or panel not in cmds.getPanel(type="modelPanel"):
        raise ValueError("表示中のMaya GUI modelPanelが必要です。")
    folder = ROOT / ".maya-output" / "verification" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    frames = folder / "frames"
    frames.mkdir(parents=True)
    record = {"title": title, "created_at": datetime.now(timezone.utc).isoformat(), "maya": cmds.about(version=True),
              "git": _git_info(), "fps": fps, "frame_count": frame_count, "capture": "M3dView.readColorBuffer",
              "ok": False, "frames": [], "drive": None}
    original_time = cmds.currentTime(query=True)
    try:
        view = omui.M3dView()
        omui.M3dView.getM3dViewFromModelPanel(panel, view)
        for index in range(frame_count):
            diagnostic = evaluate(index)
            record["frames"].append(diagnostic)
            cmds.refresh(force=True)
            view.refresh(False, True)
            image = om.MImage()
            view.readColorBuffer(image, True)
            image.writeToFile(str(frames / ("frame_{:05d}.png".format(index))), "png")
        shutil.copyfile(frames / "frame_00000.png", folder / "poster.png")
        encodeVideo(folder, record, encoder, width, height)
        video = folder / "verification.mp4"
        record.update(ok=all(frame.get("ok") is True for frame in record["frames"]), video_size=video.stat().st_size,
                      video_sha256=_digest(video, "sha256"))
    except Exception as error:
        record["error"] = str(error)
        raise
    finally:
        cmds.currentTime(original_time, edit=True)
        _write_report(folder, record)
    return folder


def attachDrive(folder, metadata):
    """Driveで読み戻したメタデータを検証結果へ登録する。

    Args:
        folder (str | Path): recordVideoが生成したフォルダ。
        metadata (dict): Drive APIまたはDriveプラグインが返したメタデータ。
            md5Checksumが取得できた場合はリモートのチェックサムも検査する。

    Returns:
        str: Driveが返した閲覧URL。アップロードと共有設定自体は行わない。
    """
    folder = Path(folder).resolve()
    folder.relative_to((ROOT / ".maya-output" / "verification").resolve())
    record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    url = metadata.get("webViewLink") or metadata.get("url", "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "drive.google.com" or not metadata.get("id"):
        raise ValueError("Driveが返した正式な閲覧URLとidが必要です。")
    video = folder / "verification.mp4"
    if (metadata.get("mimeType") or metadata.get("mime_type")) != "video/mp4" or int(metadata.get("size", -1)) != video.stat().st_size:
        raise ValueError("アップロードした動画の形式またはサイズが一致しません。")
    if _digest(video, "sha256") != record["video_sha256"]:
        raise ValueError("録画後にローカル動画が変更されています。")
    if metadata.get("md5Checksum") and metadata["md5Checksum"] != _digest(video, "md5"):
        raise ValueError("Drive上の動画のチェックサムが一致しません。")
    shared = any(p.get("type") == "anyone" and p.get("role") == "reader" and p.get("allowFileDiscovery") is False
                 for p in metadata.get("permissions", []))
    record["drive"] = {"id": metadata["id"], "url": url, "link_viewer_verified": shared,
                       "remote_checksum_verified": bool(metadata.get("md5Checksum"))}
    _write_report(folder, record)
    (folder / "drive-link.rst").write_text("`検証動画をGoogle Driveで見る <{}>`_\n".format(url), encoding="utf-8")
    return url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drive読み戻しJSONから閲覧リンクを登録する。")
    parser.add_argument("folder")
    parser.add_argument("metadata", help="get_file_metadataのJSONファイル")
    args = parser.parse_args()
    print(attachDrive(args.folder, json.loads(Path(args.metadata).read_text(encoding="utf-8"))))
