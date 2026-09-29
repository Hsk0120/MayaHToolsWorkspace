/** @file python_bridge.cpp
 * @brief Maya内のPython・MELの呼出しと、補完エンジンへの情報の受け渡し。
 */
#include "plugin/python_bridge.h"
#include "core/completion_engine.h"
#include "core/module_scanner.h"
#include "core/python_declarations.h"
#include "plugin/mel.h"
#include <maya/MGlobal.h>
#include <QJsonArray>
#include <QJsonDocument>
#include <QHash>
#include <QJsonObject>
#include <QSet>
#include <QStringList>

namespace hedit {
namespace python {
namespace {

/** @brief Pythonの式を評価して、結果を文字列で受け取る。
 * @param expression heditが組み立てた式(利用者のコードは渡さない)。
 * @param ok 評価できたかを入れる。nullptrなら入れない。
 * @return 結果。失敗時は空(Script Editorに詳細が出る)。
 */
QString evaluate(const QString& expression, bool* ok = nullptr) {
    MString result;
    const MStatus status = MGlobal::executePythonCommand(toMString(expression), result);
    if (ok) {
        *ok = bool(status);
    }
    return status ? fromMString(result) : QString();
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

/** @brief 同梱のPythonモジュールの関数を呼び、戻り値の文字列(JSON)を受け取る。
 * @param module モジュール名(例: ``hedit.bridge``)。
 * @param function 関数名。
 * @param argument 渡す引数の式。空なら引数なしで呼ぶ。
 * @param ok 呼べたかを入れる。nullptrなら入れない。
 * @return 関数の戻り値。
 * @details ``import``文を使わずに``__import__``で呼ぶのは、Script Editorの名前空間(__main__)に
 * 変数名を残さないため。1回の式で全て渡すので(QString::argの複数引数版)、引数の中の%1などは置き換わらない。
 */
QByteArray callFunction(const QString& module, const QString& function, const QString& argument = QString(),
                        bool* ok = nullptr) {
    const QString expression = QString("__import__('%1', fromlist=['%2']).%2(%3)").arg(module, function, argument);
    return evaluate(expression, ok).toUtf8();
}

/** @brief JSONの配列を文字列の一覧にする。 @param array 配列。 @return 一覧。 */
QStringList toStringList(const QJsonArray& array) {
    QStringList result;
    for (const QJsonValue& value : array) {
        result.append(value.toString());
    }
    return result;
}

/** @brief Pythonから受け取った、読み込み済みのモジュールの情報の控え。 */
struct CachedModule {
    QString signature;    ///< 受け取ったときの印(hedit.bridge._signature)。
    LoadedModule module;  ///< 受け取った情報。
};

/// モジュール名 → 前回受け取った情報。印が変わっていなければ、公開名をもう一度受け取らずにこれを使う。
QHash<QString, CachedModule> loadedModules;

/** @brief 補完エンジンへ渡す、Pythonへの問い合わせの関数の一式を作る。 @return ModuleSource。 */
ModuleSource pythonModuleSource() {
    ModuleSource source;
    source.loadedModule = [](const QString& name, LoadedModule* module) {
        // 前回の印を渡し、公開名が変わっていなければ「unchanged」だけを受け取る(大きなJSONを毎回作らない)。
        const auto cached = loadedModules.constFind(name);
        const QString known = cached != loadedModules.constEnd() ? cached->signature : QString();
        const QString arguments = pythonStringLiteral(name) + ", " + pythonStringLiteral(known);
        const QJsonObject data = QJsonDocument::fromJson(callFunction("hedit.bridge", "module_info", arguments)).object();
        if (!data.value("loaded").toBool()) {
            loadedModules.remove(name);
            return false;
        }
        if (data.value("unchanged").toBool() && cached != loadedModules.constEnd()) {
            *module = cached->module;
            return true;
        }
        module->members = symbolTableFromJson(data.value("members").toObject());
        module->file = data.value("file").toString();
        loadedModules.insert(name, {data.value("signature").toString(), *module});
        return true;
    };
    source.searchPaths = [] {
        return toStringList(QJsonDocument::fromJson(callFunction("hedit.bridge", "search_paths")).array());
    };
    source.topLevelNames = [] {
        return toStringList(QJsonDocument::fromJson(callFunction("hedit.bridge", "module_names")).object()
                                .value("names").toArray());
    };
    return source;
}

/** @brief 補完エンジンを返す。プラグインで1つだけ使う。
 * @return 初めて呼んだときに作る(関数の中のstatic変数は1回だけ作られる)。
 */
CompletionEngine& engine() {
    static CompletionEngine instance(pythonModuleSource());
    return instance;
}

/// 組み込みの名前と予約語をPythonから受け取ったか。最初の補完の前に1回受け取る。
bool environmentLoaded = false;

/// importの行の補完に使う、sys.pathのトップレベル名の走査器(C++のスレッドで走査する)。
ModuleScanner moduleScanner;

/** @brief Python側の検索パスと、組み込み・読み込み済みのトップレベル名を受け取る。
 * @param names 組み込みモジュールとsys.modulesのトップレベル名を入れる。nullptrなら入れない。
 * @return sys.pathの各フォルダー(絶対パス)。
 * @details sys.pathとsys.modulesはPythonのオブジェクトなので、ここだけPythonに問い合わせる(約1ms)。
 * フォルダーの走査はしない(ModuleScannerがC++のスレッドで行う)。
 */
QStringList modulePaths(QSet<QString>* names) {
    const QJsonObject data = QJsonDocument::fromJson(callFunction("hedit.bridge", "module_names")).object();
    if (names) {
        for (const QJsonValue& value : data.value("names").toArray()) {
            names->insert(value.toString());
        }
    }
    return toStringList(data.value("paths").toArray());
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

void refreshCompletion() {
    const QJsonObject data = QJsonDocument::fromJson(callFunction("hedit.bridge", "environment")).object();
    CompletionEnvironment environment;
    environment.builtins = toStringList(data.value("builtins").toArray());
    environment.keywords = toStringList(data.value("keywords").toArray());
    engine().setEnvironment(environment);
    engine().clearCaches();
    loadedModules.clear();
    environmentLoaded = true;
}

CompletionResult complete(const QString& source) {
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
    if (!environmentLoaded) {
        refreshCompletion();
    }
    return engine().complete(source);
}

QByteArray declarationsJson(const QString& source) {
    return QJsonDocument(symbolTableToJson(extractPythonDeclarations(source).symbols)).toJson(QJsonDocument::Compact);
}

AnalysisResult analyze(const QString& source) {
    return analysisResultFromJson(callFunction("hedit.analysis", "analyze", pythonStringLiteral(source)));
}

void startModuleScan() {
    moduleScanner.refresh(modulePaths(nullptr));
}

void stopModuleScan() {
    moduleScanner.stop();
}

}  // namespace python
}  // namespace hedit
