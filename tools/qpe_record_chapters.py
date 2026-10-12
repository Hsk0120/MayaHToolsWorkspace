"""隔離Mayaを章ごとに起動し、操作動画一式を順番に生成する。"""
import argparse
import json
from pathlib import Path
from run_mlib_gui_versions import run_version


def main():
    """作業中Mayaに接続せず、所有する検証GUIだけを使う。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('--chapters', nargs='+', default=['navigation', 'files', 'organize', 'settings', 'maya', 'advanced', 'productivity', 'finder'])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg = next((root/'.maya-output/qpe-standalone-build/venv/Lib/site-packages/imageio_ffmpeg/binaries').glob('ffmpeg*.exe'))
    results = {}
    for chapter in args.chapters:
        suite = 'qpe_ui_finder' if chapter == 'finder' else 'qpe_record_'+chapter if chapter in ('advanced', 'productivity') else 'qpe_record_full'
        result = run_version('2027', out/chapter, Path('C:/Program Files/Autodesk'), 480, shutdown_timeout=45,
            suite_path=root/'tools'/(suite+'.py'), environment={'QPE_FFMPEG': str(ffmpeg), 'QPE_REVIEW_CHAPTER': chapter})
        results[chapter] = result
        result['crashDumps'] = [str(path) for path in (out/chapter).rglob('*.dmp')]
        if result['crashDumps']:
            result['status'] = 'failed'
            result['shutdownError'] = 'Maya generated a crash dump despite recording completion'
        (out/'summary.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf8')
        print(chapter, result['status'], flush=True)


if __name__ == '__main__':
    main()
