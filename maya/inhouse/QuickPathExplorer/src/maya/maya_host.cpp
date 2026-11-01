/** @file maya_host.cpp @brief GUIスレッドのMayaコマンドと設定復元。Pythonを実行しない。 */
#include "maya_host.h"
#include "../core/settings_store.h"
#include "../core/file_operations.h"
#include <maya/MGlobal.h>
#include <maya/MFileIO.h>
#include <maya/MQtUtil.h>
#include <maya/MString.h>
#include <maya/MStringArray.h>
#include <QApplication>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QMessageBox>
#include <QMenu>
#include <QCursor>
#include <QRegularExpression>
#include <QSaveFile>
#include <QUuid>
#include <stdexcept>
#include <exception>
namespace qpe {
namespace {
/** @brief UTF-8をMayaへ渡す。 @param text 入力。 @return Maya文字列。 */
MString mayaString(const QString& text) { MString value; value.setUTF8(text.toUtf8().constData()); return value; }
/** @brief MEL文字列結果を得る。 @param code 照会。 @return UTF-8結果。 */
QString stringQuery(const QString& code) { MString result; const auto status = MGlobal::executeCommand(mayaString(code), result, false, false); if (!status) throw std::runtime_error(status.errorString().asUTF8()); return QString::fromUtf8(result.asUTF8()); }
/** @brief MEL真偽値結果を得る。 @param code 照会。 @return 値。 */
bool boolQuery(const QString& code) { int result = 0; const auto status = MGlobal::executeCommand(mayaString(code), result, false, false); if (!status) throw std::runtime_error(status.errorString().asUTF8()); return result != 0; }
/** @brief 標準Recent Filesへ成功後だけ登録。補助失敗は本操作と区別。 */
void recordRecent() {
    try { const auto path = stringQuery("file -q -sceneName"); if (path.isEmpty()) return;
        MStringArray types; const auto status = MGlobal::executeCommand("file -q -type", types, false, false);
        if (!status || !types.length()) throw std::runtime_error("Could not query current scene type");
        mayaCommand("addRecentFile(" + melQuote(path) + ", " + melQuote(QString::fromUtf8(types[0].asUTF8())) + ")");
    } catch (const std::exception& e) { MGlobal::displayWarning(mayaString("QuickPathExplorer: Recent Files update failed: " + QString::fromUtf8(e.what()))); }
}
/** @brief 未保存シーンの選択を要求する。 @return 切替可能か。 */
bool allowSceneChange() {
    if (!boolQuery("file -q -modified")) return true;
    const auto answer = QMessageBox::question(QApplication::activeWindow(), "Unsaved scene", "Save changes before switching scenes?",
        QMessageBox::Save | QMessageBox::Discard | QMessageBox::Cancel, QMessageBox::Cancel);
    if (answer == QMessageBox::Save) { mayaCommand("SaveScene"); return !boolQuery("file -q -modified"); }
    return answer == QMessageBox::Discard;
}
/** @brief 存在する保存先への上書きを確認。 @param path 保存先。 @return 継続可否。 */
bool allowOverwrite(const QString& path) { return !QFileInfo::exists(path) || QMessageBox::question(QApplication::activeWindow(), "Overwrite file", "Replace this file?\n" + path, QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) == QMessageBox::Yes; }
/** @brief 保存済みで未変更の現在シーンだけに確認用情報を付ける。 @return 保存したか。 */
bool saveSidecar() {
    const auto scene = stringQuery("file -q -sceneName");
    if (scene.isEmpty() || !QFileInfo(scene).isFile()) throw std::invalid_argument("Save the scene first");
    if (boolQuery("file -q -modified")) throw std::invalid_argument("Save scene changes before saving its information and thumbnail");
    const auto metadata = scene + ".qpe.json", thumbnail = scene + ".qpe.png";
    if ((QFileInfo::exists(metadata) || QFileInfo::exists(thumbnail)) && QMessageBox::question(QApplication::activeWindow(), "Update scene information and thumbnail",
        "Replace QPE information for\n" + scene, QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return false;
    MStringArray refs, nodes, visible;
    if (!MGlobal::executeCommand("file -q -reference", refs, false, false) || !MGlobal::executeCommand("ls -type file", nodes, false, false)) throw std::runtime_error("Could not query scene dependencies");
    QJsonArray references, textures;
    for (unsigned i = 0; i < refs.length(); ++i) references.append(QString::fromUtf8(refs[i].asUTF8()));
    for (unsigned i = 0; i < nodes.length(); ++i) textures.append(stringQuery("getAttr " + melQuote(QString::fromUtf8(nodes[i].asUTF8()) + ".fileTextureName")));
    QJsonObject values{{"scene", scene}, {"maya", QString::fromUtf8(MGlobal::mayaVersion().asUTF8())}, {"project", stringQuery("workspace -q -rootDirectory")},
        {"references", references}, {"textures", textures}, {"sceneModified", QFileInfo(scene).lastModified().toMSecsSinceEpoch() / 1000.0}};
    // playblastはGUIスレッドで現在フレームだけを読む。画像は一時名で生成してから原子的に置換する。
    MGlobal::executeCommand("getPanel -visiblePanels", visible, false, false);
    QString panel = stringQuery("getPanel -withFocus");
    if (panel.isEmpty() || stringQuery("getPanel -typeOf " + melQuote(panel)) != "modelPanel") {
        panel.clear(); for (unsigned i = 0; i < visible.length(); ++i) { const auto name = QString::fromUtf8(visible[i].asUTF8()); if (stringQuery("getPanel -typeOf " + melQuote(name)) == "modelPanel") { panel = name; break; } }
    }
    if (!panel.isEmpty()) {
        const auto temporary = QFileInfo(scene).dir().filePath(".qpe-thumb-" + QUuid::createUuid().toString(QUuid::WithoutBraces) + ".png");
        double frame = 0; MGlobal::executeCommand("currentTime -q", frame, false, false);
        try {
            mayaCommand("playblast -completeFilename " + melQuote(temporary) + " -format image -compression png -frame " + QString::number(frame, 'g', 17)
                + " -viewer false -showOrnaments false -offScreen -widthHeight 640 360 -percent 100 -forceOverwrite -editorPanelName " + melQuote(panel));
            QFile input(temporary); QSaveFile output(thumbnail); output.setDirectWriteFallback(false);
            if (!input.open(QIODevice::ReadOnly) || !output.open(QIODevice::WriteOnly)) throw std::runtime_error("Could not write scene thumbnail");
            const auto bytes = input.readAll(); if (bytes.isEmpty() || output.write(bytes) != bytes.size() || !output.commit()) throw std::runtime_error("Could not commit scene thumbnail");
            input.close(); QFile::remove(temporary);
        } catch (...) { QFile::remove(temporary); throw; }
    } else values["thumbnailNote"] = "No visible model panel";
    saveJson(metadata, values); return true;
}
/** @brief ネームスペースを明示検証。 @param path 入力ファイル。 @param values 読込設定。 @return 絶対ネームスペース。 */
QString namespaceFor(const QString& path, const QJsonObject& values) {
    const auto mode = values["mode"].toString("file");
    if (mode == "root") return ":";
    auto name = mode == "custom" ? values["name"].toString().trimmed() : QFileInfo(path).completeBaseName();
    if (mode != "custom") { name.replace(QRegularExpression("[^\\p{L}\\p{N}_]"), "_"); if (name.isEmpty()) name = "file"; if (name[0].isDigit()) name.prepend('_'); }
    if (!QRegularExpression("^:?[\\p{L}_][\\p{L}\\p{N}_]*(?::[\\p{L}_][\\p{L}\\p{N}_]*)*$").match(name).hasMatch()) throw std::invalid_argument("Enter a valid namespace, for example shot:characterA");
    return name.startsWith(':') ? name : ':' + name;
}
/** @brief 設定を復元しながらFBXを読み込む。 @param path 元。 @param values FBX設定。 */
bool fbxOpen(const QString& path, const QJsonObject& values) {
    const auto mode = values["mode"].toString("open"); const bool timeline = values["timeline"].toBool();
    if (!QStringList{"open", "add", "merge", "exmerge", "exmergekeyedxforms"}.contains(mode)) throw std::invalid_argument("Invalid FBX mode");
    if (mode == "open" && !allowSceneChange()) return false;
    if (!boolQuery("pluginInfo -q -loaded fbxmaya")) mayaCommand("loadPlugin -quiet fbxmaya");
    QString restore;
    for (const auto& flag : {"minTime", "maxTime", "animationStartTime", "animationEndTime"}) {
        double value = 0; MGlobal::executeCommand(mayaString(QString("playbackOptions -q -") + flag), value, false, false);
        restore += QString(" -%1 %2").arg(flag).arg(value, 0, 'g', 17);
    }
    mayaCommand("FBXPushSettings");
    const auto restoreSettings = [&] {
        std::exception_ptr failure;
        try { mayaCommand("FBXPopSettings"); } catch (...) { failure = std::current_exception(); }
        // FBX設定の復元が失敗しても、利用者の再生範囲を戻す処理は必ず試す。
        try { if (!timeline) mayaCommand("playbackOptions" + restore); }
        catch (...) { if (!failure) failure = std::current_exception(); else MGlobal::displayWarning("QPE: Could not restore playback range"); }
        if (failure) std::rethrow_exception(failure);
    };
    try {
        mayaCommand("FBXImportMode -v " + melQuote(mode == "open" ? "add" : mode));
        mayaCommand(QString("FBXImportFillTimeline -v ") + (timeline ? "true" : "false"));
        mayaCommand("FBXProperty \"Import|IncludeGrp|Animation\" -v true");
        if (mode == "open") mayaCommand("file -open -force -type \"FBX\" -options \"v=0;\" " + melQuote(path));
        else mayaCommand("FBXImport -f " + melQuote(path));
    } catch (...) { try { restoreSettings(); } catch (const std::exception& e) { MGlobal::displayWarning(e.what()); } throw; }
    restoreSettings(); if (mode == "open") recordRecent(); return true;
}
}
QString melQuote(const QString& value) {
    QString text = value; text.replace('\\', "\\\\"); text.replace('"', "\\\""); text.replace('\n', "\\n"); text.replace('\r', "\\r"); text.replace('\t', "\\t"); return '"' + text + '"';
}
void mayaCommand(const QString& code) { const auto status = MGlobal::executeCommand(mayaString(code + ';'), false, true); if (!status) throw std::runtime_error(status.errorString().asUTF8()); }
HostServices mayaServices() {
    HostServices host; host.maya = true; host.dpi = MQtUtil::dpiScale(1.0f); host.perform = mayaPerform;
    host.scenePath = [] { return stringQuery("file -q -sceneName"); }; host.projectPath = [] { return stringQuery("workspace -q -rootDirectory"); };
    host.namespaces = [] {
        MStringArray names; if (!MGlobal::executeCommand("namespaceInfo -listOnlyNamespaces -recurse -absoluteName \":\"", names, false, false)) throw std::runtime_error("Could not list namespaces");
        QStringList result{":"}; for (unsigned i = 0; i < names.length(); ++i) { const auto value = QString::fromUtf8(names[i].asUTF8()); if (value != ":UI" && value != ":shared") result.append(value); } return result;
    }; return host;
}
bool mayaPerform(const QString& action, const QStringList& paths, const QJsonObject& options) {
    if (action == "sidecar") return saveSidecar();
    if (action == "new") { if (!allowSceneChange()) return false; mayaCommand("file -new -force"); return true; }
    if (action == "options") {
        QMenu menu; for (const auto& pair : QList<QPair<QString, QString>>{{"Open", "OpenSceneOptions"}, {"Import", "ImportOptions"}, {"Reference", "CreateReferenceOptions"}, {"Save As", "SaveSceneAsOptions"}, {"Export Selection", "ExportSelectionOptions"}, {"Set Project", "SetProject"}})
            menu.addAction(pair.first, [pair] { try { mayaCommand(pair.second); } catch (const std::exception& e) { MGlobal::displayWarning(e.what()); } });
        menu.exec(QCursor::pos()); return true;
    }
    if (action == "save" && !stringQuery("file -q -sceneName").isEmpty()) { mayaCommand("file -save"); recordRecent(); return true; }
    if (action == "save" || action == "saveAs" || action == "export") {
        const QString type = options["fileType"].toString("mayaBinary");
        if (type != "mayaBinary" && type != "mayaAscii") throw std::invalid_argument("Invalid Maya file type");
        QString name = options["fileName"].toString().trimmed(); QString path;
        if (name.isEmpty()) path = QFileDialog::getSaveFileName(QApplication::activeWindow(), action == "export" ? "Export Selection" : "Save Scene As", options["directory"].toString(), type == "mayaBinary" ? "Maya Binary (*.mb)" : "Maya ASCII (*.ma)");
        else { validateFileName(name); path = QDir(options["directory"].toString()).absoluteFilePath(name); }
        if (path.isEmpty()) return false;
        const QString ext = type == "mayaBinary" ? ".mb" : ".ma";
        if (!path.endsWith(ext, Qt::CaseInsensitive)) { if (path.endsWith(".ma", Qt::CaseInsensitive) || path.endsWith(".mb", Qt::CaseInsensitive)) path.chop(3); path += ext; }
        path = QDir::fromNativeSeparators(path); if (!QFileInfo(path).isAbsolute() || !QFileInfo(QFileInfo(path).absolutePath()).isDir()) throw std::invalid_argument("Invalid save directory");
        if (!allowOverwrite(path)) return false;
        if (action == "export") { if (!boolQuery("size(`ls -selection`) > 0")) throw std::invalid_argument("Select objects in Maya first"); mayaCommand("file -exportSelected -force -type " + melQuote(type) + ' ' + melQuote(path)); }
        else { const auto status = MFileIO::saveAs(mayaString(path), type.toUtf8().constData(), true); if (!status || !QFileInfo::exists(path)) throw std::runtime_error("Maya could not save to the requested path"); recordRecent(); }
        return true;
    }
    if (action != "open" && action != "import" && action != "reference") throw std::invalid_argument("Unsupported Maya action");
    if (paths.isEmpty() || (action == "open" && paths.size() != 1)) throw std::invalid_argument("Select files to read (one for Open)");
    // 全件の入力だけを先に検証。部分成功した後に不正なnamespaceを発見しない。
    const auto read = options[action].toObject();
    if (action != "open") {
        if (!QStringList{"file", "custom", "root"}.contains(read["mode"].toString("file"))) throw std::invalid_argument("Invalid namespace mode");
        if (!QStringList{"", "all", "topOnly", "none"}.contains(read["loadReferenceDepth"].toString())) throw std::invalid_argument("Invalid reference load depth");
        if (action == "import" && !QStringList{"keep", "override", "combine"}.contains(read["importTimeRange"].toString("keep"))) throw std::invalid_argument("Invalid import time range");
    }
    for (const auto& path : paths) {
        if (!QFileInfo(path).isFile()) throw std::invalid_argument("Select an existing file");
        if (action != "open") namespaceFor(path, read);
        if (action == "reference" && QFileInfo(path).canonicalFilePath().compare(QFileInfo(stringQuery("file -q -sceneName")).canonicalFilePath(), Qt::CaseInsensitive) == 0) throw std::invalid_argument("Cannot reference the current scene into itself");
    }
    if (paths.size() > 1 && QMessageBox::question(QApplication::activeWindow(), "QuickPathExplorer", action + QString(" %1 files?").arg(paths.size()), QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return false;
    for (QString path : paths) {
        path = QDir::fromNativeSeparators(path);
        if (action == "open") {
            if (QFileInfo(path).suffix().compare("fbx", Qt::CaseInsensitive) == 0) { if (!fbxOpen(path, options["fbx"].toObject())) return false; }
            else { if (!allowSceneChange()) return false; mayaCommand("file -open -force " + melQuote(path)); recordRecent(); }
            continue;
        }
        const auto ns = namespaceFor(path, read); QString parent = ":"; const auto parts = ns.mid(1).split(':');
        for (int i = 0; i + 1 < parts.size(); ++i) {
            const auto child = parent + (parent == ":" ? "" : ":") + parts[i];
            if (!boolQuery("namespace -exists " + melQuote(child))) mayaCommand("namespace -addNamespace " + melQuote(parts[i]) + " -parent " + melQuote(parent)); parent = child;
        }
        QString command = "file -" + action + " -namespace " + melQuote(ns);
        const QStringList common{"mergeNamespacesOnClash", "groupReference", "executeScriptNodes"};
        const auto flags = common + (action == "import" ? QStringList{"preserveReferences", "removeDuplicateNetworks", "mergeBaseAnimLayer", "renameAll", "importFrameRate", "ignoreVersion"} : QStringList{"deferReference", "lockReference"});
        const QStringList switches{"groupReference", "ignoreVersion", "lockReference", "preserveReferences", "removeDuplicateNetworks"};
        for (const auto& flag : flags) {
            const bool value = (flag == "mergeNamespacesOnClash" && ns == ":") || read[flag].toBool(flag == "executeScriptNodes" || flag == "preserveReferences");
            // Python cmdsのboolと異なり、MELの引数なしスイッチにはtrue/falseを付けない。
            if (switches.contains(flag)) { if (value) command += " -" + flag; }
            else command += " -" + flag + (value ? " true" : " false");
        }
        const auto depth = read["loadReferenceDepth"].toString(); if (!depth.isEmpty() && !read["deferReference"].toBool()) command += " -loadReferenceDepth " + melQuote(depth);
        if (action == "import") command += " -importTimeRange " + melQuote(read["importTimeRange"].toString("keep"));
        mayaCommand(command + ' ' + melQuote(path));
    }
    return true;
}
}
