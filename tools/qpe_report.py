"""QuickPathExplorerの実測JSONを集計し、ローカル比較メモを作る。"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]


def medianRange(values):
    """中央値と範囲を表示用文字列にする。

    Args:
        values (list[float]): 同じ単位の測定値。

    Returns:
        str: 中央値 [最小, 最大]。
    """
    return '{:.2f} [{:.2f}, {:.2f}]'.format(statistics.median(values), min(values), max(values))


def main():
    """既存の計測結果だけを読み、比較表と再現用ハッシュを保存する。"""
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    rows = json.loads((args.directory / 'results.json').read_text(encoding='utf-8'))
    lines = ['QuickPathExplorer C++ / Python 比較（2026-10-11）',
             '実行証跡: ' + str(args.directory.resolve()),
             '数値は中央値 [最小, 最大]。時間はms、メモリはMiB。',
             'Windows 11 Pro 10.0.26200 / Core i7-12700KF / RAM約64GB / Qt 6.8.3 / Maya 2027 / Python 3.13.9。',
             'C++ Release: MSVC 19.50 (v145)。Python単体はMaya同梱mayapyを使用。', '']
    for host in ('standalone', 'maya'):
        for language in ('cpp', 'python'):
            subset = [r for r in rows if r['host'] == host and r['implementation'] == language]
            if not subset:
                continue
            assert all(r['passed'] for r in subset)
            lines += ['{} / {} / {}回すべて成功'.format(host, language, len(subset)),
                      '  起動: ' + medianRange([r['startup_ms'] for r in subset])]
            for name in ('load_100', 'load_1000', 'load_10000', 'revisit_10000'):
                values = [c['ms'] for r in subset for c in r['cases'] if c['name'] == name]
                lines.append('  {}: {}'.format(name, medianRange(values)))
            totals = [sum(c['ms'] for c in r['cases'] if c['name'].startswith('depth_')) for r in subset]
            lines.append('  12段階の列移動の合計: ' + medianRange(totals))
            if host == 'standalone':
                lines.append('  プロセスのピークワーキングセット: ' + medianRange([r['peak_working_set_mib'] for r in subset]))
            lines.append('')
    lines += [
        '測定の範囲と制限:',
        '- 初回は新規QFileSystemModel内での初回。OSディスクキャッシュは消していない。ローカルの合成データのみ。',
        '- 100/1000/10000個の小さな.maプレースホルダー。Maya解析やサムネイル生成の速度ではない。',
        '- 読込通知と行数一致、その後のGUIイベント処理まで。画面の最終描画完了や操作中の最大停止時間ではない。',
        '- 1ms待機によるポーリングを含む。単体起動は外部から5msポーリング。画像保存は全ケース計測後。',
        '- 単体起動はプロセス作成からUI show後の最初のタイマー。Maya内は起動済みMaya内でドック作成。両者は別の指標。',
        '- Maya内は同じ専用GUIで交互に作成/破棄。初回以外はモジュール/DLL読込済み。Maya全体の起動時間は比較対象外。',
        '- Maya側には遅延初期化等のノイズがあり、C++初回100件で約7.2秒などの外れ値を含む。除外せず中央値と全範囲を残した。',
        '- C++/Pythonの順序を交互にして各6回。プロセス内キャッシュ再訪問は別計測。統計的有意差の検定は行っていない。',
        '- メモリは単体プロセス全体のピークワーキングセット。Maya内の追加メモリは未計測。',
        '- 共通処理の大部分は両版ともC++製Qt。C++一般とPython一般の演算性能差へ一般化しない。',
        '- ネットワーク共有、アクセス拒否、10万件以上、実データの画像/動画プレビュー、旧Maya、MayaなしのPCは未検証。',
        '', '保守性の評価:',
        '- Python: UI変更にネイティブ再ビルド不要。Maya側の呼出と同じ言語で修正・デバッグしやすい。',
        '- C++: MSVC/SDKとコンパイル・リンクが必要。MayaのQt ABIに合うDLLを管理し、更新にはUI破棄・通常はホスト再起動が必要。',
        '- 共通: Qtのバージョン差、ファイル監視、ネットワークI/O、設定、例外処理、テストの保守は両版に必要。',
        '- 今回のC++版もMayaドック/シーン操作には共通Python接続コードを使用する。完全なPython非依存版ではない。',
        '- 単体配布は両版とも未完。C++はQt DLL等、PythonはPython/PySide等の配布設計・依存確認が必要。',
        '- EXE/DLLだけの容量と.pyの容量は依存ランタイムを含まず、公平な配布サイズ比較には使わない。',
        '', '判断:',
        '今回のカラム閲覧中心の仕様では、Python版を先に育てる案を推奨する。',
        'C++単体起動の優位はあるが、一覧読込や階層移動の差だけでC++一本化を選ぶ根拠は弱い。',
        'C++版は比較用に保持し、将来の検索・索引・プレビュー等で実測したボトルネックがあれば再評価する。',
        '1万件の初回読込が約2秒かかる点は共通課題。言語変更と別にモデル/表示方法の改善を検討する。',
        '', '操作検証:',
        '専用Maya GUIで両版のドック/フロート、パスのReturn入力、列のクリック展開、フィルター、日本語パス、無効パス保持を確認。',
        '実際に保存した専用.maをOpen/Import/Referenceして内容を検証。',
        'functional-final/result.jsonに、追加した未保存シーンのOpenキャンセル・内容保持テストを含む最終操作検証を保存。',
        '計測時ソースからの最終変更は、このキャンセル検証とレポート処理。current-source-hashes.jsonはレポート生成時点のソース。',
        '', '再現:',
        'python tools/build_maya_plugin.py maya/inhouse/QuickPathExplorer --versions 2027',
        'python tools/qpe_compare.py --rounds 6',
        'python tools/qpe_report.py <証跡ディレクトリ>',
    ]
    destination = ROOT / 'docs/research/quick-path-explorer-comparison-20261011.txt'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    files = list((ROOT / 'maya/inhouse/QuickPathExplorer').rglob('*.cpp')) + list((ROOT / 'maya/inhouse/QuickPathExplorer/python').glob('*.py'))
    files += [ROOT / 'tools/qpe_compare.py', ROOT / 'tools/qpe_maya_suite.py', args.directory / 'config.json']
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (args.directory / 'current-source-hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print('\n'.join(lines[:40]))
    print('Report: ' + str(destination))


if __name__ == '__main__':
    main()
