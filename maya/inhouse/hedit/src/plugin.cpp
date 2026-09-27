/** @file plugin.cpp
 * @brief Mayaコマンド登録、ログ購読、Qt編集画面への橋渡し。
 * @details QPointerは対象の破棄時にnullとなり、古いアドレスの使用を防ぐ。
 * Maya APIはこのファイルで扱い、本文編集はeditor.cppへ分離する。
 */
#include "editor.h"
#include "dock.h"
#include "modulescan.h"
#include "embedded_python.h"
#include "mayautil.h"
#include "version.h"
#include <maya/MFnPlugin.h>
#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>
#include <maya/MArgDatabase.h>
#include <maya/MGlobal.h>
#include <maya/MQtUtil.h>
#include <maya/MCommandMessage.h>
#include <maya/MSceneMessage.h>
#include <maya/MMessage.h>
#include <QMutex>
#include <QMutexLocker>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QPointer>
#include <QTimer>
#include <optional>
#include <QDir>
#include <QFile>
#include <QSaveFile>
#include <QFileInfo>
#include <QApplication>
#include <QThread>
#include <QTextEdit>
#include <QPlainTextEdit>
#include <QTextDocument>
#include <QTextCursor>

namespace {
QPointer<QMainWindow> window;
MCallbackId outputCallback = 0;
QMetaObject::Connection reporterConnection;
QPointer<QTextDocument> nativeDocument;
MCommandMessage::MessageType nativeMessageType=MCommandMessage::kDisplay;
QMutex outputMutex;
QList<hedit::OutputMessage> pendingOutput;
int pendingSize=0;
bool omittedOutput=false;
MCallbackId exitCallback = 0;
bool exiting=false;
/** @brief Maya出力を有界キューへ追加し、メインスレッドの通知では表示も更新する。
 * @param message Mayaの出力文字列。
 * @param type 警告・エラー等の分類。
 * @param clientData 未使用。
 */
void onOutput(const MString& message, MCommandMessage::MessageType type, void* clientData) {
    if (exiting) return;
    QString text = QString::fromUtf8(message.asUTF8());
    // CRLFをQtの段落として二重に挿入しない。printの分割通知には改行を足さない。
    text.replace("\r\n","\n"); text.replace('\r','\n');
    auto kind=hedit::OutputKind::Normal;
    switch (type) {
    case MCommandMessage::kWarning: kind=hedit::OutputKind::Warning; break;
    case MCommandMessage::kError: kind=hedit::OutputKind::Error; break;
    case MCommandMessage::kResult: kind=hedit::OutputKind::Result; break;
    case MCommandMessage::kInfo: kind=hedit::OutputKind::Info; break;
    case MCommandMessage::kHistory: kind=hedit::OutputKind::History; break;
    default: break;
    }
    QMutexLocker lock(&outputMutex);
    if (text.size()>512*1024) { text=text.right(512*1024); if (!text.isEmpty() && text.at(0).isLowSurrogate()) text.remove(0,1); omittedOutput=true; }
    if (text.isEmpty()) return;
    pendingSize+=text.size();
    if (!pendingOutput.isEmpty() && pendingOutput.last().kind==kind) pendingOutput.last().text+=text;
    else pendingOutput.append({text,kind});
    while (pendingSize>1024*1024 && pendingOutput.size()>1) { pendingSize-=pendingOutput.first().text.size(); pendingOutput.removeFirst(); omittedOutput=true; }
    if (pendingSize>1024*1024) { pendingOutput.last().text=pendingOutput.last().text.right(512*1024); if (pendingOutput.last().text.at(0).isLowSurrogate()) pendingOutput.last().text.remove(0,1); pendingSize=pendingOutput.last().text.size(); omittedOutput=true; }
    // takeOutputが同じmutexを取得するため、描画前に必ずロックを解放する。
    lock.unlock();
    // 読み込み中はQtタイマーが動かない。Mayaのメインスレッドからだけ直接描画する。
    // ワーカー通知は既存タイマーへ任せ、UIへの他スレッドアクセスを避ける。
    if (qApp && QThread::currentThread()==qApp->thread()) hedit::refreshEditorOutput(window.data());
}
/** @brief Maya終了の開始時に、reporterからhedit画面への出力転送を止める。
 * @param clientData 未使用。
 * @details 終了処理中もMayaはMELの履歴をreporterへ追記するが、その時点のhedit画面は
 * ネイティブウィンドウの解体途中で、追記を描画するとQtのアクセシビリティ更新で落ちる。
 */
void onMayaExiting(void* clientData) {
    exiting=true;
    QObject::disconnect(reporterConnection);
    nativeDocument=nullptr;
}
/** @brief ロック中にキューを交換する。 @return 未取得の出力。上限超過時は省略通知も含む。 */
QList<hedit::OutputMessage> takeOutput() {
    QMutexLocker lock(&outputMutex);
    QList<hedit::OutputMessage> result; result.swap(pendingOutput); pendingSize=0;
    if (omittedOutput) result.prepend({"[hedit: older buffered output omitted]\n",hedit::OutputKind::Info});
    omittedOutput=false; return result;
}
/** @brief Maya内のPython式を呼ぶ。
 * @param expression heditが生成したブリッジ用の式。
 * @return Python結果または失敗の説明。
 */
QString python(const QString& expression) {
    MString result;
    auto utf8 = expression.toUtf8();
    MString script; script.setUTF8(utf8.constData());
    MStatus status = MGlobal::executePythonCommand(script, result);
    return status ? QString::fromUtf8(result.asUTF8()) : QString("hedit: Python bridge failed; see Script Editor.");
}
using hedit::mel;
using hedit::melQuote;
/// importの行の補完に使う、sys.pathのトップレベル名の走査器(C++のスレッドで走査する)。
hedit::ModuleScanner moduleScanner;
/** @brief Python側の検索パスと、組み込み・読み込み済みのトップレベル名を取り出す。
 * @param names 組み込みモジュールとsys.modulesのトップレベル名を入れる。
 * @return sys.pathの各フォルダー(絶対パス)。
 * @details sys.pathとsys.modulesはPythonのオブジェクトなので、ここだけPythonへ問い合わせる(約1ms)。
 * フォルダーの走査はしない(ModuleScannerがC++のスレッドで行う)。
 */
QStringList pythonModulePaths(QSet<QString>* names) {
    const auto data=QJsonDocument::fromJson(python("__import__('hedit.bridge', fromlist=['module_names']).module_names()").toUtf8()).object();
    if (names) for (const auto& value: data.value("names").toArray()) names->insert(value.toString());
    QStringList paths;
    for (const auto& value: data.value("paths").toArray()) paths.append(value.toString());
    return paths;
}
/** @brief 補完候補を返す。importの行のトップレベル名はC++で、それ以外はPythonで求める。
 * @param source カーソルまでの本文。
 * @return 補完のJSON(``items``と``pending``)。
 * @details 最初の走査は編集画面の作成時に始めている。まだ終わっていなければ最大0.5秒だけ待ち、
 * 最初のCtrl+Spaceから未読込のパッケージも候補に出す。以後の再走査は5秒間隔で裏で行う。
 */
QByteArray completion(const QString& source) {
    QString prefix;
    if (hedit::topLevelImportPrefix(source,&prefix)) {
        QSet<QString> names;
        moduleScanner.refresh(pythonModulePaths(&names));
        moduleScanner.waitForFirst(500);
        bool pending=false;
        names.unite(moduleScanner.names(&pending));
        return hedit::completionItems(names,prefix,pending);
    }
    QByteArray quoted=QJsonDocument(QJsonArray{source}).toJson(QJsonDocument::Compact);
    quoted=quoted.mid(1,quoted.size()-2);
    return python("__import__('hedit.bridge', fromlist=['complete']).complete("+QString::fromUtf8(quoted)+")").toUtf8();
}
/** @brief MayaのUI名から、reporterが表示に使うQtの文書を探す。
 * @param control cmdScrollFieldReporterのUI名(フルパスでも可)。
 * @return 表示文書。見つからなければnullptr。所有者はMayaのUI。
 * @details reporterの実体はQTextEditまたはQPlainTextEdit、もしくはそれを子に持つ
 * ウィジェットなので、本体→子の順に探す。
 */
QTextDocument* findReporterDocument(const QString& control) {
    MString name; name.setUTF8(control.toUtf8().constData());
    QWidget* widget=MQtUtil::findControl(name);
    if (!widget) return nullptr;
    auto rich=qobject_cast<QTextEdit*>(widget);
    auto plain=qobject_cast<QPlainTextEdit*>(widget);
    if (!rich && !plain) { rich=widget->findChild<QTextEdit*>(); plain=widget->findChild<QPlainTextEdit*>(); }
    return rich ? rich->document() : plain ? plain->document() : nullptr;
}
/// ライブ出力の整形に使う専用reporterを入れた非表示ウィンドウのUI名。
QString reporterWindow;
/** @brief ライブ出力の整形専用に、非表示のreporterを作る。
 * @return reporterのUI名。作れなければ空。
 * @details 標準Script Editorの設定・履歴は変更しない。作成中に変わるMayaの
 * 現在の親レイアウトは元に戻す(他ツールのUI作成へ影響させないため)。
 * releaseOutputReporter()で破棄する。
 */
QString createOutputReporter() {
    const QString previous=mel("setParent -q");
    reporterWindow=mel("window");
    mel("columnLayout");
    const QString reporter=mel("cmdScrollFieldReporter");
    if (!previous.isEmpty()) mel("setParent "+melQuote(previous));
    return reporter;
}
/** @brief createOutputReporter()で作った非表示ウィンドウを破棄する。 */
void releaseOutputReporter() {
    if (!reporterWindow.isEmpty() && hedit::melBool("window -exists "+melQuote(reporterWindow)))
        mel("deleteUI -window "+melQuote(reporterWindow));
    reporterWindow.clear();
}
/** @brief Mayaが保持している過去の出力を、初回表示用に読み取る。
 * @return 詰めた履歴(最大512Ki文字)。Maya側ですでに破棄された履歴は含まない。
 * @details 標準Script Editorのreporterがあればその表示文書を読み、なければ標準の
 * エディタを開かずに一時的な非表示reporterで読む。設定・選択・履歴は変更しない。
 */
QString outputHistory() {
    QString reporter=mel("global string $gCommandReporter; string $heditReporter = $gCommandReporter;");
    QString temporary;
    if (reporter.isEmpty() || !hedit::melBool("cmdScrollFieldReporter -exists "+melQuote(reporter))) {
        temporary=mel("window");
        mel("columnLayout");
        reporter=mel("cmdScrollFieldReporter");
    }
    QString text;
    if (auto document=findReporterDocument(reporter)) text=document->toPlainText();
    else text=mel("cmdScrollFieldReporter -q -text "+melQuote(reporter));
    if (!temporary.isEmpty()) mel("deleteUI -window "+melQuote(temporary));
    text=text.right(512*1024);
    if (!text.isEmpty() && text.at(0).isLowSurrogate()) text.remove(0,1);
    return hedit::compactHistory(text);
}
/** @brief Mayaのバージョン別のタブ復元先を決める。
 * @return tabs.jsonの絶対パス(Windowsの区切り文字)。
 * @details 環境変数HEDIT_SESSION_FILEがあればそれを使う(隔離テスト用)。
 * 名前変更前の保存先heditorにある未保存タブ・UI状態・設定は、新しい保存先に同名の
 * ファイルがまだない場合だけコピーする。旧データは削除しない。
 */
QString sessionPath() {
    const QString override=qEnvironmentVariable("HEDIT_SESSION_FILE");
    if (!override.isEmpty()) return override;
    const QDir base(mel("internalVar -userPrefDir"));
    const QDir destination(base.filePath("hedit")), legacy(base.filePath("heditor"));
    for (const char* name: {"tabs.json","ui.json","preferences.ini"}) {
        const QString source=legacy.filePath(name), target=destination.filePath(name);
        if (QFileInfo(source).isFile() && !QFileInfo::exists(target)) {
            QDir().mkpath(destination.path());
            QFile::copy(source,target);
        }
    }
    return QDir::toNativeSeparators(destination.filePath("tabs.json"));
}
/** @brief Maya自身の整形済み文書を差分購読する。
 * @return reporter文書へ接続できた場合true。
 * @details Pythonの#とMEL/APIの//を推測せず標準reporterの追記を使用する。
 * 全履歴の再取得やイベントループの再入は行わない。
 */
bool connectNativeOutput() {
    // 専用reporterより先に購読し、文字列には手を加えず色・フィルタ用の種別を保持する。
    outputCallback=MCommandMessage::addCommandOutputCallback(
        [](const MString&,MCommandMessage::MessageType type,void*) {
            if (qApp && QThread::currentThread()==qApp->thread()) nativeMessageType=type;
        });
    nativeDocument=findReporterDocument(createOutputReporter());
    if (!nativeDocument) return false;
    // hedit専用文書だけを制限し、長時間使用時の履歴メモリを有界にする。
    nativeDocument->setMaximumBlockCount(5000);
    reporterConnection=QObject::connect(nativeDocument.data(), &QTextDocument::contentsChange, nativeDocument.data(),
        [](int position,int removed,int added) {
            if (!nativeDocument || !added) return;
            QTextCursor cursor(nativeDocument);
            cursor.setPosition(position);
            cursor.setPosition(qMin(position+added,nativeDocument->characterCount()-1),QTextCursor::KeepAnchor);
            auto text=cursor.selectedText();
            text.replace(QChar::ParagraphSeparator,'\n'); text.replace(QChar::LineSeparator,'\n');
            const auto type=nativeMessageType;
            MString message; message.setUTF8(text.toUtf8().constData());
            onOutput(message,type,nullptr);
        });
    return true;
}
/** @brief 編集画面を返す。未作成なら作る(初回はMayaの過去の出力も取り込む)。
 * @param create falseなら作らずに既存の画面だけ返す。
 * @return 編集画面。作れない・未作成(create=false)ならnullptr。所有者は親(ドック)。
 */
QMainWindow* ensureEditor(bool create) {
    if (window || !create) return window.data();
    if (MGlobal::mayaState() != MGlobal::kInteractive) {
        MGlobal::displayError("hedit UI requires interactive Maya."); return nullptr;
    }
    {
        {
            if (!nativeDocument) {
                // 同じメインスレッドで履歴を一度取得してから購読を開始する。
                // 既存ログと新規コールバックの境界を分け、二重表示を防ぐ。
                const auto lines=outputHistory().split('\n');
                QMutexLocker lock(&outputMutex);
                for (int i=0;i<lines.size();++i) {
                    auto line=lines.at(i); if (i==lines.size()-1 && line.isEmpty()) break;
                    auto kind=hedit::OutputKind::Normal;
                    if (line.startsWith("// Result:") || line.startsWith("# Result:")) kind=hedit::OutputKind::Result;
                    else if (line.startsWith("// Warning:") || line.startsWith("# Warning:")) kind=hedit::OutputKind::Warning;
                    else if (line.startsWith("// Error:") || line.startsWith("# Error:")) kind=hedit::OutputKind::Error;
                    pendingOutput.append({line+'\n',kind}); pendingSize+=line.size()+1;
                }
                lock.unlock();
                if (!connectNativeOutput()) {
                    if (outputCallback) { MMessage::removeCallback(outputCallback); outputCallback=0; }
                    releaseOutputReporter();
                    MGlobal::displayError("hedit: native output reporter unavailable.");
                    return nullptr;
                }
            }
            window = hedit::createEditor(MQtUtil::mainWindow(), [](const QString& source) {
                // MayaのPython実行・履歴・共通出力を使用する。stdoutを横取りしない。
                auto utf8 = source.toUtf8();
                MString script;
                script.setUTF8(utf8.constData());
                MGlobal::executePythonCommand(script, true, false);
                return QString();
            }, [] { return python("__import__('hedit.bridge', fromlist=['configuration']).configuration()").toUtf8(); }, takeOutput,
            completion, sessionPath(), [](const QString& source) {
                QByteArray quoted=QJsonDocument(QJsonArray{source}).toJson(QJsonDocument::Compact);
                quoted=quoted.mid(1,quoted.size()-2);
                return python("__import__('hedit.analysis', fromlist=['analyze']).analyze("+QString::fromUtf8(quoted)+")").toUtf8();
            }, [](const QString& source) {
                MString script; auto bytes=source.toUtf8(); script.setUTF8(bytes.constData());
                MGlobal::executeCommand(script,true,false);
                return QString();
            });
            // ドックの中で探せるよう名前を付ける(テストや旧版の回収処理が使う)。
            window->setObjectName("hedit");
            // importの補完に使うsys.pathの走査を先に始め、最初のCtrl+Spaceまでに終えておく。
            moduleScanner.refresh(pythonModulePaths(nullptr));
        }
    }
    return window.data();
}
/** @brief heditのMayaコマンド。
 * @details フラグなしは編集画面を(未作成なら作って)そのアドレスを返す。
 * 公開フラグ: ``-show``(``-sh``)/``-floating``(``-f``)/``-restore``(``-r``)/``-saveState``(``-ss``)/
 * ``-sessionPath``(``-sp``)。内部フラグ: ``-closed``(``-cl``, ドックのcloseCommand)、
 * ``-quitting``(``-qt``, 終了通知のscriptJob)。いずれもMELから呼べ、Pythonを必要としない。
 */
class Command : public MPxCommand {
public:
    /** @brief Maya用ファクトリー。 @return Mayaが所有するコマンド。 */
    static void* creator() { return new Command; }
    /** @brief コマンドのフラグを定義する。 @return 表示・復元・状態保存・復元先のフラグを持つ構文。 */
    static MSyntax newSyntax() {
        MSyntax syntax;
        syntax.addFlag("-sh","-show");
        syntax.addFlag("-f","-floating",MSyntax::kBoolean);
        syntax.addFlag("-r","-restore");
        syntax.addFlag("-ss","-saveState");
        syntax.addFlag("-sp","-sessionPath");
        syntax.addFlag("-cl","-closed");
        syntax.addFlag("-qt","-quitting");
        return syntax;
    }
    /** @brief フラグに応じて画面を開く・復元する・状態を保存する・復元先を返す。
     * @param args Mayaコマンド引数。
     * @return 成功でkSuccess。画面が必要な操作はバッチ等ではkFailure。
     */
    MStatus doIt(const MArgList& args) override {
        MStatus status;
        MArgDatabase database(syntax(),args,&status);
        if (!status) return status;
        if (database.isFlagSet("-sp")) {
            // 画面を作らないためバッチ/mayapyでも使える。
            setResult(hedit::toMString(sessionPath()));
            return MS::kSuccess;
        }
        if (database.isFlagSet("-cl")) { hedit::dock::closed(); return MS::kSuccess; }
        if (database.isFlagSet("-qt")) { hedit::dock::quitting(); return MS::kSuccess; }
        if (database.isFlagSet("-ss")) { hedit::dock::record(); return MS::kSuccess; }
        if (database.isFlagSet("-r")) return hedit::dock::restore() ? MS::kSuccess : MS::kFailure;
        if (database.isFlagSet("-sh")) {
            std::optional<bool> floating;
            if (database.isFlagSet("-f")) { bool value=false; database.getFlagArgument("-f",0,value); floating=value; }
            if (MGlobal::mayaState() != MGlobal::kInteractive) {
                MGlobal::displayError("hedit UI requires interactive Maya."); return MS::kFailure;
            }
            hedit::dock::show(floating);
            return MS::kSuccess;
        }
        QMainWindow* editor=ensureEditor(true);
        if (!editor) return MS::kFailure;
        setResult(MString(QString::number(reinterpret_cast<quintptr>(editor)).toLatin1().constData()));
        return MS::kSuccess;
    }
};
/** @brief Windowメニューの緑のHアイコン(旧icons/hedit.svg)。.mll単体で使えるよう同梱する。 */
const char* kMenuIconSvg =
    "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\">\n"
    "  <rect x=\"1\" y=\"1\" width=\"22\" height=\"22\" rx=\"4\" fill=\"#69b66c\"/>\n"
    "  <path d=\"M7 6v12M17 6v12M7 12h10\" fill=\"none\" stroke=\"#17251a\" stroke-width=\"3\"/>\n"
    "</svg>\n";
/** @brief 同梱アイコンをユーザー設定フォルダーへ書き出し、そのパスを返す。
 * @return アイコンの絶対パス。書き出せない場合は空(メニューはアイコンなしで登録する)。
 * @details ``menuItem -image``はファイルのパスしか受け付けないため、メモリ上のSVGを
 * タブ保存と同じ``<userPrefDir>/hedit/``へ置く。内容が同じなら書き直さない。
 */
QString writeMenuIcon() {
    const QString prefs=QString::fromUtf8(MGlobal::executeCommandStringResult("internalVar -userPrefDir").asUTF8());
    if (prefs.isEmpty() || !QDir().mkpath(prefs+"/hedit")) return QString();
    const QString path=QDir::cleanPath(prefs+"/hedit/hedit.svg");
    const QByteArray svg(kMenuIconSvg);
    QFile current(path);
    if (current.open(QIODevice::ReadOnly) && current.readAll()==svg) return path;
    current.close();
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly) || file.write(svg)!=svg.size() || !file.commit()) return QString();
    return path;
}
/** @brief Windowメニュー末尾へhedit項目を一度だけ登録する(MEL経由。Pythonは使わない)。
 * @param icon メニュー項目のアイコン(緑のH)の絶対パス。空ならアイコンなしで登録する。
 * @return MEL実行結果。
 * @details クリック時のコマンド自体は``import hedit; hedit.show()``(Python)のままだが、
 * これはエディタ本体の起動にPythonが必要なためで、メニュー登録処理自体はC++から
 * ``MGlobal::executeCommand``でMELを直接実行する。メインメニューが既にあれば同期的に
 * 登録する。``evalDeferred``はloadPluginの処理中にidleが回ると、Mayaがまだ未ロードと
 * 扱う時点で実行され得るため、メインメニュー構築前(起動初期のautoload)だけに使う。
 * べき等: 既存の項目があれば何もしない。
 */
MStatus installMenu(const QString& icon) {
    // MEL文字列リテラルへ埋め込むため、バックスラッシュと二重引用符をエスケープする。
    QString escaped=icon; escaped.replace("\\","\\\\"); escaped.replace("\"","\\\"");
    const QString image=icon.isEmpty() ? QString() : "        -image \""+escaped+"\"\n";
    QString mel = QString(
        "global proc hedit_installMenu()\n"
        "{\n"
        "    if (`about -batch`) return;\n"
        "    if (`menuItem -exists \"heditWindowMenuItem\"`) return;\n"
        "    string $parent = \"MayaWindow|mainWindowMenu\";\n"
        "    if (!`menu -exists $parent`) return;\n"
        "    buildViewMenu MayaWindow|mainWindowMenu;\n"
        "    if (!`menuItem -exists \"heditWindowMenuDivider\"`)\n"
        "        menuItem -parent $parent -divider true \"heditWindowMenuDivider\";\n"
        "    menuItem -parent $parent -label \"hedit - Python / MEL\"\n"
        "        -annotation \"Open hedit (additional script editor)\"\n"
        "        -sourceType \"mel\"\n"
        "        -command \"hedit -show\"\n")
        + image +
        "        \"heditWindowMenuItem\";\n"
        "}\n"
        "if (`menu -exists \"MayaWindow|mainWindowMenu\"`) hedit_installMenu();\n"
        "else evalDeferred -lowestPriority \"hedit_installMenu\";\n";
    MString command; command.setUTF8(mel.toUtf8().constData());
    return MGlobal::executeCommand(command, false, false);
}
/** @brief プラグイン解除時にWindowメニュー項目を取り除く(MEL経由)。
 * @return MEL実行結果。
 */
MStatus uninstallMenu() {
    MString mel =
        "if (`menuItem -exists \"heditWindowMenuItem\"`) deleteUI \"heditWindowMenuItem\";\n"
        "if (`menuItem -exists \"heditWindowMenuDivider\"`) deleteUI \"heditWindowMenuDivider\";\n";
    return MGlobal::executeCommand(mel, false, false);
}
}
/** @brief コマンドを登録し、Windowメニュー登録と前回画面の復元の予約を行う。
 * @param object Mayaのプラグインオブジェクト。
 * @return コマンド登録結果。
 * @details メニュー登録(MEL)・ドッキングと開閉状態の復元(dock.cpp)はC++で行い、Pythonを介さない。
 * 補完・構文チェック用のPythonはembedded_python.hに同梱し、import hookとして登録する。
 * ``scripts/userSetup.py``(起動時に``loadPlugin('hedit')``を呼ぶだけ)・Plug-in Managerでの
 * 明示ロード・Mayaのプラグインautoloadのいずれでもここが呼ばれるため、プラグインのロードだけで
 * メニュー登録・前回の画面復元が完了する。
 */
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "hedit", HEDIT_VERSION, "Any");
    auto status=plugin.registerCommand("hedit", Command::creator, Command::newSyntax);
    if (!status) return status;
    // import hookはmayapy(standalone)でも登録する。補完等のPython APIはGUIに依存しないため。
    auto installed=hedit::embedded::installModules();
    if (!installed) {
        MGlobal::displayError("hedit: failed to install embedded Python modules.");
        plugin.deregisterCommand("hedit");
        return installed;
    }
    if (MGlobal::mayaState()==MGlobal::kInteractive) {
        exiting=false;
        exitCallback=MSceneMessage::addCallback(MSceneMessage::kMayaExiting, onMayaExiting);
        hedit::dock::configure(ensureEditor, sessionPath);
        installMenu(writeMenuIcon());
        // プラグイン登録中の再入を避け、前回画面の復元は次のイベントループへ送る。
        QTimer::singleShot(0, hedit::dock::lifetime(), [] { hedit::dock::restorePrevious(); });
    }
    return status;
}
/** @brief タブを保存し、通知・UI・コマンドを解除する。
 * @param object Mayaのプラグインオブジェクト。
 * @return 解除結果。保存確認の取消は失敗。
 * @note コールバックを先に外し、破棄済み画面への通知を防ぐ。
 */
MStatus uninitializePlugin(MObject object) {
    // タブ復元データを保存。保存できない場合は確認し、キャンセルなら解除を拒否する。
    if (window && !window->close()) return MS::kFailure;
    if (MGlobal::mayaState()==MGlobal::kInteractive) {
        uninstallMenu();
        hedit::dock::uninstall();
    }
    QObject::disconnect(reporterConnection); nativeDocument=nullptr;
    releaseOutputReporter();
    if (outputCallback) {
        MStatus status = MMessage::removeCallback(outputCallback);
        if (!status) return status;
        outputCallback = 0;
    }
    if (exitCallback) { MMessage::removeCallback(exitCallback); exitCallback = 0; }
    // 走査スレッドのコードはhedit.mllの中にあるため、アンロード前に止めて合流する。
    moduleScanner.stop();
    if (MGlobal::mayaState()==MGlobal::kInteractive) hedit::dock::release();
    delete window.data(); window = nullptr;
    takeOutput();
    MFnPlugin plugin(object); return plugin.deregisterCommand("hedit");
}
