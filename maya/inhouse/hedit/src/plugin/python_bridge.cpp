/** @file python_bridge.cpp
 * @brief Maya内のPython・MELの呼出しと、補完エンジンへの情報の受け渡し。
 */
#include "plugin/python_bridge.h"
#include "core/completion_engine.h"
#include "core/module_scanner.h"
#include "core/python_declarations.h"
#include "core/python_literal.h"
#include "plugin/mel.h"
#include <maya/MGlobal.h>
#include <QJsonArray>
#include <QJsonDocument>
#include <QHash>
#include <QJsonObject>
#include <QSet>
#include <QStringList>
#include <memory>

namespace hedit {
namespace python {
namespace {

/** @brief Pythonの式を評価して、結果をUTF-8のまま受け取る。
 * @param expression heditが組み立てた式(利用者のコードは渡さない)。
 * @param ok 評価できたかを入れる。nullptrなら入れない。
 * @return 結果(UTF-8)。失敗時は空(Script Editorに詳細が出る)。
 * @note 結果はJSONとしてQJsonDocumentへ渡すだけなので、QStringを経由しない(UTF-8→UTF-16→UTF-8の変換を省く。
 * maya.cmdsの公開名のJSONは約120KBある)。同梱のPythonが返すJSONはASCIIだけなので、途中に0の文字は無い。
 */
QByteArray evaluate(const QString& expression, bool* ok = nullptr) {
    MString result;
    const MStatus status = MGlobal::executePythonCommand(toMString(expression), result);
    if (ok) {
        *ok = bool(status);
    }
    return status ? QByteArray(result.asUTF8()) : QByteArray();
}

/** @brief Python側の失敗を記録する。補完の結果と一緒に画面へ知らせる(complete())。
 * @param error 理由。
 */
void recordError(const QString& error);

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
    // hedit.bridge.safe_callを通して呼ぶ。例外はPython側で受け止め、{"error": ...}として返ってくる。
    const QString target = QString("__import__('%1', fromlist=['%2']).%2").arg(module, function);
    const QString arguments = argument.isEmpty() ? target : target + ", " + argument;
    const QString expression = "__import__('hedit.bridge', fromlist=['safe_call']).safe_call(" + arguments + ")";
    bool evaluated = false;
    const QByteArray result = evaluate(expression, &evaluated);
    const bool failed = !evaluated || result.startsWith("{\"error\"");
    if (failed) {
        recordError(evaluated ? QJsonDocument::fromJson(result).object().value("error").toString()
                              : QString("hedit.bridge is unavailable"));
    }
    if (ok) {
        *ok = !failed;
    }
    return result;
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

/** @brief Pythonから受け取った、検索パスと組み込み・読み込み済みのトップレベル名の控え(hedit.bridge.module_names)。 */
struct CachedModuleNames {
    QString signature;    ///< 受け取ったときの印。空なら未取得。
    QStringList paths;    ///< sys.pathの各フォルダー(絶対パス)。
    QStringList names;    ///< トップレベル名(Pythonが並べた順)。
    QSet<QString> lookup; ///< namesと同じ名前の集合(import補完で走査結果と合わせる)。
};

struct BridgeState;
BridgeState& bridge();
QHash<QString, CachedModule>& bridgeLoadedModules();
const CachedModuleNames& moduleNames();

/** @brief 補完エンジンへ渡す、Pythonへの問い合わせの関数の一式を作る。 @return ModuleSource。 */
ModuleSource pythonModuleSource() {
    ModuleSource source;
    source.loadedModule = [](const QString& name, LoadedModule* module) {
        // 前回の印を渡し、公開名が変わっていなければ「unchanged」だけを受け取る(大きなJSONを毎回作らない)。
        QHash<QString, CachedModule>& loadedModules = bridgeLoadedModules();
        const auto cached = loadedModules.constFind(name);
        const QString known = cached != loadedModules.constEnd() ? cached->signature : QString();
        const QString arguments = pythonStringLiteral(name) + ", " + pythonStringLiteral(known);
        const QJsonObject data = QJsonDocument::fromJson(callFunction("hedit.bridge", "module_info", arguments)).object();
        if (!data.value("loaded").toBool()) {
            bridgeLoadedModules().remove(name);
            return false;
        }
        if (data.value("unchanged").toBool() && cached != loadedModules.constEnd()) {
            *module = cached->module;
            return true;
        }
        module->members = symbolTableFromJson(data.value("members").toObject());
        module->file = data.value("file").toString();
        bridgeLoadedModules().insert(name, {data.value("signature").toString(), *module});
        return true;
    };
    source.searchPaths = [] {
        return toStringList(QJsonDocument::fromJson(callFunction("hedit.bridge", "search_paths")).array());
    };
    source.describe = [](const QString& module, const QStringList& path, QString* signature, QString* doc) {
        const QString arguments = pythonStringLiteral(module) + ", " + pythonStringListLiteral(path);
        const QJsonObject data = QJsonDocument::fromJson(callFunction("hedit.bridge", "describe", arguments)).object();
        if (!data.value("found").toBool()) {
            return false;
        }
        *signature = data.value("signature").toString();
        *doc = data.value("doc").toString();
        return true;
    };
    source.topLevelNames = [] { return moduleNames().names; };
    return source;
}

/** @brief Pythonとの受け渡しの状態。プラグインで1つだけ持ち、initialize()で作ってshutdown()で壊す。
 * @details 以前は関数の中のstatic変数やグローバル変数に散らばっていて、作る・壊す順番が分かりにくかった。
 */
struct BridgeState {
    CompletionEngine engine{pythonModuleSource()};  ///< 補完エンジン。
    QHash<QString, CachedModule> loadedModules;     ///< モジュール名 → 前回受け取った公開名(印が同じなら使い回す)。
    CachedModuleNames moduleNames;                  ///< 前回受け取った検索パスとトップレベル名(印が同じなら使い回す)。
    bool environmentLoaded = false;                 ///< 組み込みの名前と予約語を受け取ったか。
    QString lastError;                              ///< 最後に起きたPython側の失敗(画面へ知らせたら空に戻す)。
    ModuleScanner moduleScanner;                    ///< importの行の補完に使うsys.pathの走査(C++のスレッド)。
};

/// プラグインで1つだけの状態。
std::unique_ptr<BridgeState> state;

BridgeState& bridge() {
    // initialize()より前・shutdown()の後に呼ぶのはプログラムの誤り。
    Q_ASSERT(state);
    return *state;
}

/** @brief 前回受け取った公開名の控えを返す。 @return モジュール名 → 控え。 */
QHash<QString, CachedModule>& bridgeLoadedModules() {
    return bridge().loadedModules;
}

void recordError(const QString& error) {
    if (state) {
        state->lastError = error;
    }
}

/** @brief 記録した失敗を取り出して消す。 @return 理由。無ければ空。 */
QString takeError() {
    QString error;
    if (state) {
        error.swap(state->lastError);
    }
    return error;
}

/** @brief 補完エンジンを返す。 @return プラグインで1つだけの補完エンジン。 */
CompletionEngine& engine() {
    return bridge().engine;
}

/** @brief Python側の検索パスと、組み込み・読み込み済みのトップレベル名を返す。
 * @return 控え。Pythonを呼べなければ空。
 * @details sys.pathとsys.modulesはPythonのオブジェクトなので、ここだけPythonに問い合わせる。
 * importの行では1文字ごとに呼ばれるので、前回の印を渡し、変わっていなければ「unchanged」だけを受け取って
 * 控えを使う(名前の並べ替え・JSONの作成と読み取りを毎回しない)。フォルダーの走査はしない(ModuleScannerがC++のスレッドで行う)。
 */
const CachedModuleNames& moduleNames() {
    CachedModuleNames& cached = bridge().moduleNames;
    bool ok = false;
    const QJsonObject data =
        QJsonDocument::fromJson(callFunction("hedit.bridge", "module_names", pythonStringLiteral(cached.signature), &ok))
            .object();
    if (!ok) {
        cached = CachedModuleNames();  // 以前と同じく、失敗したら空の一覧として扱う。次は全てを受け取り直す。
        return cached;
    }
    if (data.value("unchanged").toBool() && !cached.signature.isEmpty()) {
        return cached;
    }
    cached.signature = data.value("signature").toString();
    cached.paths = toStringList(data.value("paths").toArray());
    cached.names = toStringList(data.value("names").toArray());
    cached.lookup = QSet<QString>(cached.names.cbegin(), cached.names.cend());
    return cached;
}

}  // namespace

QString runPython(const QString& source, const QString& path) {
    // 保存済みのタブは、実行中だけ__file__をそのファイルにする(Maya標準のScript Editorには無い補助)。
    // 前後の切り替えは履歴に出さない。本文が例外で止まっても、後の呼出しで元に戻る。
    if (!path.isEmpty()) {
        callFunction("hedit.bridge", "push_main_file", pythonStringLiteral(path));
    }
    // 第2引数true: Script Editorの履歴に表示する。第3引数false: Undoの記録はコード自身に任せる。
    MGlobal::executePythonCommand(toMString(source), true, false);
    if (!path.isEmpty()) {
        callFunction("hedit.bridge", "pop_main_file");
    }
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
    bridge().loadedModules.clear();
    bridge().moduleNames = CachedModuleNames();
    bridge().environmentLoaded = true;
}

CompletionResult complete(const QString& source) {
    QString prefix;
    if (topLevelImportPrefix(source, &prefix)) {
        // 最初の走査は編集画面の作成時に始めている。まだ終わっていなければ最大0.5秒だけ待ち、
        // 最初のCtrl+Spaceから未読込のパッケージも候補に出す。以後の再走査は5秒間隔で裏で行う。
        const CachedModuleNames& modules = moduleNames();
        bridge().moduleScanner.refresh(modules.paths);
        bridge().moduleScanner.waitForFirst(500);
        bool pending = false;
        QSet<QString> names = modules.lookup;
        names.unite(bridge().moduleScanner.names(&pending));
        return completionItems(names, prefix, pending);
    }
    if (!bridge().environmentLoaded) {
        refreshCompletion();
    }
    takeError();  // 前の問い合わせの失敗を持ち越さない。
    CompletionResult result = engine().complete(source);
    const QString error = takeError();
    if (!error.isEmpty()) {
        result.error = "Python error: " + error;
    }
    return result;
}

HoverInfo describe(const QString& text, int end) {
    if (!bridge().environmentLoaded) {
        refreshCompletion();
    }
    return engine().describe(text, end);
}

DefinitionLocation definition(const QString& text, int end) {
    if (!bridge().environmentLoaded) {
        refreshCompletion();
    }
    return engine().definition(text, end);
}

QByteArray declarationsJson(const QString& source) {
    return QJsonDocument(symbolTableToJson(extractPythonDeclarations(source).symbols)).toJson(QJsonDocument::Compact);
}

AnalysisResult analyze(const QString& source) {
    return analysisResultFromJson(callFunction("hedit.analysis", "analyze", pythonStringLiteral(source)));
}

void startModuleScan() {
    bridge().moduleScanner.refresh(moduleNames().paths);
}

void initialize() {
    if (!state) {
        state = std::make_unique<BridgeState>();
    }
}

void shutdown() {
    if (state) {
        // 走査のスレッドのコードはhedit.mllの中にあるので、アンロードの前に必ず止めて合流する。
        state->moduleScanner.stop();
        state.reset();
    }
}

}  // namespace python
}  // namespace hedit
