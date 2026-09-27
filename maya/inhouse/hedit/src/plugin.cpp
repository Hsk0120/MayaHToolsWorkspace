/** @file plugin.cpp
 * @brief Mayaコマンド登録、ログ購読、Qt編集画面への橋渡し。
 * @details QPointerは対象の破棄時にnullとなり、古いアドレスの使用を防ぐ。
 * Maya APIはこのファイルで扱い、本文編集はeditor.cppへ分離する。
 */
#include "editor.h"
#include "embedded_python.h"
#include <maya/MFnPlugin.h>
#include <maya/MPxCommand.h>
#include <maya/MGlobal.h>
#include <maya/MQtUtil.h>
#include <maya/MCommandMessage.h>
#include <maya/MSceneMessage.h>
#include <maya/MMessage.h>
#include <QMutex>
#include <QMutexLocker>
#include <QJsonDocument>
#include <QJsonArray>
#include <QPointer>
#include <QDir>
#include <QFile>
#include <QSaveFile>
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
    const auto address=python("__import__('hedit.bridge', fromlist=['create_output_reporter']).create_output_reporter()").toULongLong();
    auto widget=reinterpret_cast<QWidget*>(static_cast<quintptr>(address));
    if (!widget) return false;
    auto rich=qobject_cast<QTextEdit*>(widget);
    auto plain=qobject_cast<QPlainTextEdit*>(widget);
    if (!rich && !plain) { rich=widget->findChild<QTextEdit*>(); plain=widget->findChild<QPlainTextEdit*>(); }
    nativeDocument=rich ? rich->document() : plain ? plain->document() : nullptr;
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
/** @brief cmds.hedit()から編集画面のアドレスを返すコマンド。 */
class Command : public MPxCommand {
public:
    /** @brief Maya用ファクトリー。 @return Mayaが所有するコマンド。 */
    static void* creator() { return new Command; }
    /** @brief 編集画面を一度だけ生成する。
     * @param args 未使用のMayaコマンド引数。
     * @return GUI生成成功でkSuccess。バッチ等ではkFailure。
     */
    MStatus doIt(const MArgList& args) override {
        if (MGlobal::mayaState() != MGlobal::kInteractive) {
            MGlobal::displayError("hedit UI requires interactive Maya."); return MS::kFailure;
        }
        if (!window) {
            if (!nativeDocument) {
                // 同じメインスレッドで履歴を一度取得してから購読を開始する。
                // 既存ログと新規コールバックの境界を分け、二重表示を防ぐ。
                auto snapshot=python("__import__('hedit.bridge', fromlist=['output_history']).output_history()");
                auto history=QJsonDocument::fromJson(("["+snapshot+"]").toUtf8()).array();
                if (!history.isEmpty()) {
                    auto historyText=history.first().toString();
                    historyText.replace("\r\n","\n"); historyText.replace('\r','\n');
                    const auto lines=historyText.split('\n');
                    QMutexLocker lock(&outputMutex);
                    for (int i=0;i<lines.size();++i) {
                        auto line=lines.at(i); if (i==lines.size()-1 && line.isEmpty()) break;
                        auto kind=hedit::OutputKind::Normal;
                        if (line.startsWith("// Result:") || line.startsWith("# Result:")) kind=hedit::OutputKind::Result;
                        else if (line.startsWith("// Warning:") || line.startsWith("# Warning:")) kind=hedit::OutputKind::Warning;
                        else if (line.startsWith("// Error:") || line.startsWith("# Error:")) kind=hedit::OutputKind::Error;
                        pendingOutput.append({line+'\n',kind}); pendingSize+=line.size()+1;
                    }
                }
                if (!connectNativeOutput()) {
                    if (outputCallback) { MMessage::removeCallback(outputCallback); outputCallback=0; }
                    python("__import__('hedit.bridge', fromlist=['release_output_reporter']).release_output_reporter()");
                    MGlobal::displayError("hedit: native output reporter unavailable.");
                    return MS::kFailure;
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
            [](const QString& source) {
                QByteArray quoted = QJsonDocument(QJsonArray{source}).toJson(QJsonDocument::Compact);
                quoted = quoted.mid(1, quoted.size()-2);
                return python("__import__('hedit.bridge', fromlist=['complete']).complete(" + QString::fromUtf8(quoted) + ")").toUtf8();
            }, python("__import__('hedit.bridge', fromlist=['session_path']).session_path()"), [](const QString& source) {
                QByteArray quoted=QJsonDocument(QJsonArray{source}).toJson(QJsonDocument::Compact);
                quoted=quoted.mid(1,quoted.size()-2);
                return python("__import__('hedit.analysis', fromlist=['analyze']).analyze("+QString::fromUtf8(quoted)+")").toUtf8();
            }, [](const QString& source) {
                MString script; auto bytes=source.toUtf8(); script.setUTF8(bytes.constData());
                MGlobal::executeCommand(script,true,false);
                return QString();
            });
        }
        setResult(MString(QString::number(reinterpret_cast<quintptr>(window.data())).toLatin1().constData()));
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
        "        -sourceType \"python\"\n"
        "        -command \"import hedit; hedit.show()\"\n")
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
/** @brief コマンドを登録し、Windowメニュー登録(C++/MEL)とPython側の画面復元を予約する。
 * @param object Mayaのプラグインオブジェクト。
 * @return コマンド登録結果。
 * @details hedit本体(復元・補完・静的解析等)は``.mll``に同梱され、``scripts/``配下の
 * ``.py``ファイルには依存しない。``hedit.*``モジュールの実体はembedded_python.hに
 * 文字列として同梱し、ロード時にMaya同梱のCPython上へ``sys.modules``として直接展開する
 * (``embedded_python::installModules``)。Windowメニューの登録自体はPythonを介さず、
 * ここから直接``installMenu()``(MEL)で行う。前回画面の復元だけは``PySide``/
 * ``MayaQWidgetDockableMixin``が要るため``startup.plugin_loaded()``(Python)に委ねる。
 * ``scripts/userSetup.py``(起動時に``loadPlugin('hedit')``を呼ぶだけの最小ブートストラップ)・
 * Plug-in Managerでの明示ロード・Mayaのプラグインautoloadのいずれでもここが呼ばれるため、
 * プラグインのロードだけでメニュー登録・前回の画面復元が完了するようにしている。
 */
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "hedit", "0.2.10", "Any");
    auto status=plugin.registerCommand("hedit", Command::creator);
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
        installMenu(writeMenuIcon());
        MGlobal::executePythonCommand("from hedit import startup; startup.plugin_loaded()",false,false);
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
        MGlobal::executePythonCommand("from hedit import startup; startup.uninstall()",false,false);
    }
    QObject::disconnect(reporterConnection); nativeDocument=nullptr;
    python("__import__('hedit.bridge', fromlist=['release_output_reporter']).release_output_reporter()");
    if (outputCallback) {
        MStatus status = MMessage::removeCallback(outputCallback);
        if (!status) return status;
        outputCallback = 0;
    }
    if (exitCallback) { MMessage::removeCallback(exitCallback); exitCallback = 0; }
    MGlobal::executePythonCommand("import sys\nif 'hedit.docking' in sys.modules: sys.modules['hedit.docking'].release()", false, false);
    delete window.data(); window = nullptr;
    takeOutput();
    MFnPlugin plugin(object); return plugin.deregisterCommand("hedit");
}
