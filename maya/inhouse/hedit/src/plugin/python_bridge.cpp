/** @file python_bridge.cpp
 * @brief Maya内のPython・MELの呼出し。
 */
#include "plugin/python_bridge.h"
#include "core/module_scanner.h"
#include "plugin/mel.h"
#include <maya/MGlobal.h>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSet>
#include <QStringList>

namespace hedit {
namespace python {
namespace {

/// importの行の補完に使う、sys.pathのトップレベル名の走査器(C++のスレッドで走査する)。
ModuleScanner moduleScanner;

/** @brief Pythonの式を評価して、結果を文字列で受け取る。
 * @param expression heditが組み立てた式(利用者のコードは渡さない)。
 * @return 結果。失敗時は案内の文字列(Script Editorに詳細が出る)。
 */
QString evaluate(const QString& expression) {
    MString result;
    const MStatus status = MGlobal::executePythonCommand(toMString(expression), result);
    if (!status) {
        return "hedit: Python bridge failed; see Script Editor.";
    }
    return fromMString(result);
}

/** @brief 文字列を、Pythonの文字列リテラルとして式に埋め込める形にする。
 * @param text 埋め込む文字列(本文など、引用符や改行を含み得る)。
 * @return ``"..."``の形の文字列。
 * @details JSONの文字列はPythonの文字列リテラルとしてもそのまま読める。
 * そこで ["本文"] というJSONの配列を作り、前後の[]を外して使う(エスケープを自分で書かなくて済む)。
 */
QString pythonStringLiteral(const QString& text) {
    const QByteArray array = QJsonDocument(QJsonArray{text}).toJson(QJsonDocument::Compact);
    return QString::fromUtf8(array.mid(1, array.size() - 2));
}

/** @brief 同梱のPythonモジュールの関数を呼び、戻り値の文字列を受け取る。
 * @param module モジュール名(例: ``hedit.bridge``)。
 * @param function 関数名。
 * @param argument 渡す引数の式。空なら引数なしで呼ぶ。
 * @return 関数の戻り値(JSON文字列)。
 * @details ``import``文を使わずに``__import__``で呼ぶのは、Script Editorの名前空間(__main__)に
 * 変数名を残さないため。
 */
QString callFunction(const QString& module, const QString& function, const QString& argument = QString()) {
    const QString expression = QString("__import__('%1', fromlist=['%2']).%2(%3)").arg(module, function, argument);
    return evaluate(expression);
}

/** @brief Python側の検索パスと、組み込み・読み込み済みのトップレベル名を受け取る。
 * @param names 組み込みモジュールとsys.modulesのトップレベル名を入れる。nullptrなら入れない。
 * @return sys.pathの各フォルダー(絶対パス)。
 * @details sys.pathとsys.modulesはPythonのオブジェクトなので、ここだけPythonに問い合わせる(約1ms)。
 * フォルダーの走査はしない(ModuleScannerがC++のスレッドで行う)。
 */
QStringList modulePaths(QSet<QString>* names) {
    const QJsonObject data = QJsonDocument::fromJson(callFunction("hedit.bridge", "module_names").toUtf8()).object();
    if (names) {
        for (const QJsonValue& value : data.value("names").toArray()) {
            names->insert(value.toString());
        }
    }
    QStringList paths;
    for (const QJsonValue& value : data.value("paths").toArray()) {
        paths.append(value.toString());
    }
    return paths;
}

}  // namespace

QString runPython(const QString& source) {
    // 第2引数true: Script Editorの履歴に表示する。第3引数false: Undoの記録はコード自身に任せる。
    MGlobal::executePythonCommand(toMString(source), true, false);
    return QString();
}

QString runMel(const QString& source) {
    MGlobal::executeCommand(toMString(source), true, false);
    return QString();
}

QByteArray refreshCompletion() {
    return callFunction("hedit.bridge", "configuration").toUtf8();
}

QByteArray complete(const QString& source) {
    QString prefix;
    if (topLevelImportPrefix(source, &prefix)) {
        // 最初の走査は編集画面の作成時に始めている。まだ終わっていなければ最大0.5秒だけ待ち、
        // 最初のCtrl+Spaceから未読込のパッケージも候補に出す。以後の再走査は5秒間隔で裏で行う。
        QSet<QString> names;
        moduleScanner.refresh(modulePaths(&names));
        moduleScanner.waitForFirst(500);
        bool pending = false;
        names.unite(moduleScanner.names(&pending));
        return completionItems(names, prefix, pending);
    }
    return callFunction("hedit.bridge", "complete", pythonStringLiteral(source)).toUtf8();
}

QByteArray analyze(const QString& source) {
    return callFunction("hedit.analysis", "analyze", pythonStringLiteral(source)).toUtf8();
}

void startModuleScan() {
    moduleScanner.refresh(modulePaths(nullptr));
}

void stopModuleScan() {
    moduleScanner.stop();
}

}  // namespace python
}  // namespace hedit
