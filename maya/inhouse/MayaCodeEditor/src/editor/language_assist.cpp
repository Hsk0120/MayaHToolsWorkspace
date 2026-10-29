/** @file language_assist.cpp
 * @brief 型解析の結果を表示し、編集案を下見と世代確認付きで適用する。
 */
#include "editor/language_assist.h"
#include "editor/code_editor.h"
#include "editor/code_navigation.h"
#include "editor/editor_preferences.h"
#include "editor/problems_panel.h"
#include "core/script_file.h"
#include "core/json_file.h"
#include <QDialog>
#include <QAbstractButton>
#include <QPushButton>
#include <QLineEdit>
#include <QDialogButtonBox>
#include <QDir>
#include <QDateTime>
#include <QFileInfo>
#include <QFile>
#include <QFileDialog>
#include <QProcessEnvironment>
#include <QInputDialog>
#include <QJsonDocument>
#include <QLabel>
#include <QPlainTextEdit>
#include <QRegularExpression>
#include <QTextBlock>
#include <QUrl>
#include <QUuid>
#include <QVBoxLayout>
#include <algorithm>

namespace mce {
namespace {
/** @brief Windowsのドライブ文字とURIエスケープの差を吸収する。 @param a URI。 @param b URI。 @return 同じローカル文書か。 */
bool sameUri(const QString& a, const QString& b) {
    const QUrl left(a), right(b);
    return left.isLocalFile() && right.isLocalFile()
        ? QDir::cleanPath(left.toLocalFile()).compare(QDir::cleanPath(right.toLocalFile()), Qt::CaseInsensitive) == 0
        : a == b;
}
/** @brief LSPの文字列/MarkupContentをプレーンテキストへ変換する。 @param value 文書。 @return テキスト。 */
QString documentation(const QJsonValue& value) {
    if (value.isString()) return value.toString();
    if (value.isArray()) {
        QStringList parts;
        for (const auto& part : value.toArray()) parts.append(documentation(part));
        return parts.join("\n\n");
    }
    return value.toObject().value("value").toString();
}
/** @brief 識別子種別を補完アイコンへ変換する。 @param kind LSP種別。 @return 既存アイコン名。 */
QString category(int kind) {
    if (kind == 2 || kind == 3) return "function";
    if (kind == 7 || kind == 8) return "class";
    if (kind == 9) return "module";
    if (kind == 14) return "keyword";
    return "variable";
}
/** @brief 解析対象ファイルの更新時刻とサイズを記録する。 @param path フォルダー。 @return パスと更新印。 */
QHash<QString, QString> watchedFiles(const QString& path) {
    QHash<QString, QString> entries;
    for (const auto& name : QDir(path).entryList({"*.py", "*.pyi", "pyrightconfig.json", "pyproject.toml"}, QDir::Files)) {
        const QString file = QDir(path).filePath(name);
        const QFileInfo info(file);
        entries.insert(file, QString::number(info.lastModified().toMSecsSinceEpoch()) + ':' + QString::number(info.size()));
    }
    return entries;
}
}  // namespace

LanguageAssist::LanguageAssist(QJsonObject config, const EditorPreferences& preferences, ProblemsPanel* problems,
                               Context context, QObject* parent)
    : QObject(parent), client_(this), config_(std::move(config)), preferences_(preferences), problems_(problems), context_(std::move(context)) {
    client_.onStatus = context_.status;
    client_.onReady = [this] { documents_.clear(); diagnostics_.clear(); diagnosticVersions_.clear(); sync(); timer_.start(); };
    connect(&watcher_, &QFileSystemWatcher::directoryChanged, this, [this](const QString& path) {
        const auto old = watchedEntries_.value(path);
        const auto current = watchedFiles(path);
        QJsonArray events;
        for (auto it = current.cbegin(); it != current.cend(); ++it)
            if (old.value(it.key()) != it.value()) events.append(QJsonObject{{"uri", QUrl::fromLocalFile(it.key()).toString()}, {"type", old.contains(it.key()) ? 2 : 1}});
        for (auto it = old.cbegin(); it != old.cend(); ++it)
            if (!current.contains(it.key())) events.append(QJsonObject{{"uri", QUrl::fromLocalFile(it.key()).toString()}, {"type", 3}});
        watchedEntries_[path] = current;
        if (ready() && !events.isEmpty()) client_.notify("workspace/didChangeWatchedFiles", {{"changes", events}});
    });
    client_.onNotification = [this](const QString& method, const QJsonObject& args) { notification(method, args); };
    timer_.setSingleShot(true);
    timer_.setInterval(350);
    connect(&timer_, &QTimer::timeout, this, [this] { sync(); decorate(); });
    refresh();
    client_.start(config_);
}

void LanguageAssist::watch(const QString& path) {
    if (watchedEntries_.contains(path) || watchedEntries_.size() >= 200) return;
    watchedEntries_[path] = watchedFiles(path);
    watcher_.addPath(path);
}

void LanguageAssist::restart() {
    ++epoch_;
    if (ready()) client_.request("workspace/executeCommand", {{"command", "basedpyright.restartserver"}, {"arguments", QJsonArray()}},
        [this](const QJsonValue&, const QString& error) { context_.status(error.isEmpty() ? "Type analysis refreshed" : error); timer_.start(); });
    else client_.start(config_);
}

LanguageAssist::~LanguageAssist() {
    timer_.stop();
    refactorProcess_.disconnect(this);
    if (refactorProcess_.state() != QProcess::NotRunning) {
        refactorProcess_.kill();
        refactorProcess_.waitForFinished(1000);
    }
    for (auto* editor : context_.editors()) editor->onExternalCompletionAccepted = {};
}

void LanguageAssist::addRoot(const QString& root) {
    const QString path = QFileInfo(root).absoluteFilePath();
    if (!QFileInfo(path).isDir() || roots_.contains(path)) return;
    ++epoch_;
    roots_.insert(path);
    watch(path);
    if (ready()) client_.notify("workspace/didChangeWorkspaceFolders", {{"event", QJsonObject{
        {"added", QJsonArray{QJsonObject{{"uri", QUrl::fromLocalFile(path).toString()}, {"name", QFileInfo(path).fileName()}}}},
        {"removed", QJsonArray()}}}});
    config_.insert("root", path);
    refresh();
}

void LanguageAssist::refactor(CodeEditor* editor, const QString& action) {
    if (!editor || editor->isMel()) return;
    const QPointer<LanguageAssist> self(this);
    const QPointer<CodeEditor> target(editor);
    if (refactorProcess_.state() != QProcess::NotRunning) { context_.status("A refactoring is already running"); return; }
    sync();
    QJsonObject config;
    const QString configPath = qEnvironmentVariable("MCE_LANGUAGE_SERVER_CONFIG", qEnvironmentVariable("LOCALAPPDATA") + "/MayaCodeEditor/language-server/server.json");
    if (!readJsonFile(configPath, &config) || !QFileInfo::exists(config.value("refactorHelper").toString())) {
        context_.status("Run tools/setup_language_server.py to install refactoring support"); return;
    }
    const QString root = config_.value("root").toString();
    const QString path = QUrl(uri(editor)).toLocalFile();
    if (path.isEmpty()) { context_.status("Language analysis must be ready before refactoring"); return; }
    const auto cursor = editor->textCursor();
    if ((action == "variable" || action == "function") && !cursor.hasSelection()) {
        context_.status("Select an expression or statements first"); return;
    }
    QString name, destination;
    if (action == "move" || action == "move_new") {
        destination = action == "move" ? QFileDialog::getOpenFileName(editor, "Move global symbol to existing module", root, "Python (*.py)")
                                      : QFileDialog::getSaveFileName(editor, "Move global symbol to new module", root, "Python (*.py)");
        if (!self || !target || destination.isEmpty()) return;
        if (action == "move_new" && QFileInfo(destination).suffix().isEmpty()) destination += ".py";
    } else if (action != "imports") {
        bool ok = false;
        name = QInputDialog::getText(editor, action == "rename_module" ? "Rename module" : "Extract " + action,
                                     action == "rename_module" ? "New module name (without .py)" : "New name", QLineEdit::Normal, QString(), &ok);
        if (!self || !target || !ok || name.isEmpty()) return;
    }
    QJsonObject overlays;
    const QString prefix = QDir::cleanPath(root) + '/';
    for (const auto& doc : documents_) {
        const QString local = QDir::fromNativeSeparators(QUrl(doc.uri).toLocalFile());
        if (local.startsWith(prefix, Qt::CaseInsensitive)) overlays.insert(local, doc.editor->toPlainText());
    }
    const QJsonObject input{{"root", root}, {"path", path}, {"overlays", overlays}, {"action", action},
        {"start", cursor.selectionStart()}, {"end", cursor.selectionEnd()}, {"name", name}, {"destination", destination}};
    const quint64 epoch = epoch_;
    refactorProcess_.disconnect(this);
    refactorTimeout_.disconnect(this);
    refactorTimeout_.setSingleShot(true);
    connect(&refactorTimeout_, &QTimer::timeout, this, [this] {
        refactorProcess_.kill(); context_.status("Refactoring timed out; no changes applied");
    });
    connect(&refactorProcess_, &QProcess::started, this, [this, input] {
        refactorProcess_.write(QJsonDocument(input).toJson(QJsonDocument::Compact));
        refactorProcess_.closeWriteChannel();
    });
    connect(&refactorProcess_, &QProcess::errorOccurred, this, [this](QProcess::ProcessError) {
        refactorTimeout_.stop(); context_.status(refactorProcess_.errorString());
    });
    connect(&refactorProcess_, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished), this,
        [this, epoch](int exitCode, QProcess::ExitStatus status) {
            refactorTimeout_.stop();
            const auto result = QJsonDocument::fromJson(refactorProcess_.readAllStandardOutput()).object();
            if (exitCode || status != QProcess::NormalExit || result.isEmpty()) { context_.status("Refactoring failed; no changes applied"); return; }
            if (result.contains("error")) { context_.status(result.value("error").toString()); return; }
            if (epoch != epoch_) { context_.status("Documents changed during analysis; request the action again"); return; }
            const auto originals = result.value("before").toObject();
            for (auto it = originals.begin(); it != originals.end(); ++it) {
                QString current, error; bool opened = false;
                for (const auto& doc : documents_) if (sameUri(doc.uri, it.key())) { current = doc.editor->toPlainText(); opened = true; }
                if (!opened && !readScriptFile(QUrl(it.key()).toLocalFile(), &current, &error)) { context_.status(error); return; }
                if (current != it.value().toString()) { context_.status("A refactoring target changed; nothing applied"); return; }
            }
            preview(result.value("edit").toObject());
        });
    auto environment = QProcessEnvironment::systemEnvironment();
    environment.remove("PYTHONHOME"); environment.remove("PYTHONPATH"); environment.remove("MAYA_LOCATION");
    environment.insert("PYTHONUTF8", "1");
    refactorProcess_.setProcessEnvironment(environment);
    refactorProcess_.setProgram(config.value("refactorPython").toString());
    refactorProcess_.setArguments({"-I", config.value("refactorHelper").toString(), config.value("refactorLibrary").toString()});
    refactorProcess_.start();
    refactorTimeout_.start(30000);
    context_.status("Preparing refactoring preview…");
}

void LanguageAssist::refresh() {
    ++epoch_;
    auto based = config_.value("basedpyright").toObject();
    auto analysis = based.value("analysis").toObject();
    analysis.insert("autoImportCompletions", preferences_.option("autoImports"));
    analysis.insert("diagnosticMode", "openFilesOnly");
    analysis.insert("typeCheckingMode", "standard");
    analysis.insert("baselineMode", "discard");
    analysis.insert("inlayHints", QJsonObject{{"variableTypes", true}, {"functionReturnTypes", true}, {"callArgumentNames", true}});
    based.insert("analysis", analysis);
    config_.insert("basedpyright", based);
    client_.configure(config_);
    if (client_.ready()) timer_.start();
}

void LanguageAssist::attach(CodeEditor* editor) {
    editor->onExternalCompletionAccepted = [this, editor](const QString& name) { return accept(editor, name); };
    connect(editor, &QPlainTextEdit::textChanged, this, [this, editor, previous = editor->toPlainText()]() mutable {
        const QString text = editor->toPlainText();
        if (text == previous) return;
        previous = text;
        ++epoch_;
        editor->setLanguageDecorations({}, {});
        timer_.start();
    });
    connect(editor, &QObject::destroyed, this, [this, editor] {
        const auto doc = documents_.take(editor);
        if (client_.ready() && !doc.uri.isEmpty()) client_.notify("textDocument/didClose", {{"textDocument", QJsonObject{{"uri", doc.uri}}}});
        completions_.remove(editor);
        completionVersions_.remove(editor);
        diagnosticVersions_.remove(editor);
        diagnostics_.remove(editor);
        ++epoch_;
    });
    timer_.start();
}

QString LanguageAssist::uri(CodeEditor* editor) const { return documents_.value(editor).uri; }

void LanguageAssist::sync() {
    if (!client_.ready()) return;
    for (auto* editor : context_.editors()) {
        if (context_.ensureLoaded) context_.ensureLoaded(editor);
        if (editor->property("textPending").toBool()) continue;
        if (editor->isMel()) {
            if (documents_.contains(editor)) {
                client_.notify("textDocument/didClose", {{"textDocument", QJsonObject{{"uri", documents_.take(editor).uri}}}});
                ++epoch_;
            }
            continue;
        }
        QString path = editor->filePath();
        if (path.isEmpty()) {
            path = editor->property("analysisPath").toString();
            if (path.isEmpty()) {
                path = QDir(config_.value("root").toString(QDir::currentPath())).filePath("__mce_unsaved_" + QUuid::createUuid().toString(QUuid::WithoutBraces) + ".py");
                editor->setProperty("analysisPath", path);  // 仮想URIのみ。ファイルは作らない。
            }
        }
        const QString address = QUrl::fromLocalFile(QFileInfo(path).absoluteFilePath()).toString();
        watch(QFileInfo(path).absolutePath());
        auto& doc = documents_[editor];
        const QString text = editor->toPlainText();
        if (doc.uri != address) {
            if (!doc.uri.isEmpty()) client_.notify("textDocument/didClose", {{"textDocument", QJsonObject{{"uri", doc.uri}}}});
            doc = {editor, address, text, 1};
            client_.notify("textDocument/didOpen", {{"textDocument", QJsonObject{{"uri", address}, {"languageId", "python"}, {"version", doc.version}, {"text", text}}}});
            ++epoch_;
        } else if (doc.text != text) {
            doc.text = text;
            ++doc.version;
            ++epoch_;
            client_.notify("textDocument/didChange", {{"textDocument", QJsonObject{{"uri", address}, {"version", doc.version}}}, {"contentChanges", QJsonArray{QJsonObject{{"text", text}}}}});
        }
    }
}

QJsonObject LanguageAssist::position(QTextDocument* document, int at) {
    const auto block = document->findBlock(qBound(0, at, document->characterCount() - 1));
    return {{"line", block.blockNumber()}, {"character", at - block.position()}};
}

int LanguageAssist::offset(const QString& text, const QJsonObject& pos) {
    int line = pos.value("line").toInt(-1);
    const int column = pos.value("character").toInt(-1);
    if (line < 0 || column < 0) return -1;
    int start = 0;
    while (line-- > 0) {
        const int end = text.indexOf('\n', start);
        if (end < 0) return -1;
        start = end + 1;
    }
    const int end = text.indexOf('\n', start);
    return start + column <= (end < 0 ? text.size() : end) ? start + column : -1;
}

bool LanguageAssist::editedText(const QString& text, const QJsonArray& edits, QString* result) {
    struct Edit { int start; int end; QString text; };
    QList<Edit> values;
    for (const auto& value : edits) {
        const auto item = value.toObject();
        const auto range = item.value("range").toObject();
        const int a = offset(text, range.value("start").toObject());
        const int b = offset(text, range.value("end").toObject());
        if (a < 0 || b < a || !item.value("newText").isString()) return false;
        values.append({a, b, item.value("newText").toString()});
    }
    std::stable_sort(values.begin(), values.end(), [](const Edit& a, const Edit& b) {
        return a.start != b.start ? a.start > b.start : a.end > b.end;
    });
    int previous = text.size() + 1;
    *result = text;
    for (const auto& edit : values) {
        if (edit.end > previous) return false;
        result->replace(edit.start, edit.end - edit.start, edit.text);
        previous = edit.start;
    }
    return true;
}

QJsonObject LanguageAssist::params(CodeEditor* editor, int at) const {
    return {{"textDocument", QJsonObject{{"uri", uri(editor)}}}, {"position", position(editor->document(), at)}};
}

void LanguageAssist::request(CodeEditor* editor, const QString& method, QJsonObject arguments, bool caret, LanguageClient::Reply reply) {
    const auto key = QString::number(quintptr(editor)) + method;
    client_.cancel(requests_.value(key));
    const QPointer<CodeEditor> guard(editor);
    const quint64 epoch = epoch_;
    const QString text = editor->toPlainText();
    const int at = editor->textCursor().position();
    requests_[key] = client_.request(method, arguments, [this, guard, epoch, text, at, caret, reply](const QJsonValue& value, const QString& error) {
        if (!guard) return;
        if (epoch != epoch_ || guard->toPlainText() != text) { guard->setProperty("languageDiscard", "document changed"); return; }
        if (caret && (guard != context_.current() || !guard->hasFocus() || guard->textCursor().position() != at)) {
            guard->setProperty("languageDiscard", QString("focus=%1 current=%2 caret=%3/%4").arg(guard->hasFocus()).arg(guard == context_.current()).arg(guard->textCursor().position()).arg(at));
            return;
        }
        if (!error.isEmpty()) { context_.status(error); return; }
        reply(value, error);
    });
}

bool LanguageAssist::complete(CodeEditor* editor) {
    if (!ready() || editor->isMel()) return false;
    sync();
    request(editor, "textDocument/completion", params(editor, editor->textCursor().position()), true,
        [this, editor](const QJsonValue& value, const QString&) {
            const auto array = value.isArray() ? value.toArray() : value.toObject().value("items").toArray();
            QList<CompletionItem> items;
            completions_[editor].clear();
            for (const auto& entry : array) {
                const auto object = entry.toObject();
                const QString name = object.value("label").toString();
                if (name.isEmpty()) continue;
                const int kind = object.value("kind").toInt();
                if (kind == 14 && !preferences_.option(option::kIncludeKeywords)) continue;
                items.append({name, object.value("detail").toString(), kind == 14 ? "keyword" : QString(), category(kind),
                    object.value("sortText").toString(), object.value("filterText").toString()});
                completions_[editor].insert(name, object);
            }
            completionVersions_[editor] = documents_.value(editor).version;
            // 静的に判別できないMaya公開名だけ、既存の非実行型補完へ戻す。
            if (items.isEmpty() && context_.fallbackComplete
                && !pythonInputState(editor->document(), editor->textCursor().position()).insideText()) {
                const auto fallback = context_.fallbackComplete(editor->toPlainText().left(editor->textCursor().position()));
                if (fallback.error.isEmpty()) items = fallback.items;
            }
            editor->showCompletions(items);
            editor->setProperty("languageCompletionCount", items.size());
        });
    return true;
}

void LanguageAssist::detail(CodeEditor* editor) {
    const QString name = editor->currentCompletion();
    if (!completions_.value(editor).contains(name)) return;
    request(editor, "completionItem/resolve", completions_.value(editor).value(name), true,
        [this, editor, name](const QJsonValue& value, const QString&) {
            if (editor->currentCompletion() != name) return;
            auto resolved = value.toObject();
            resolved.insert("_mceResolved", true);
            completions_[editor].insert(name, resolved);
            HoverInfo info;
            info.signature = value.toObject().value("detail").toString();
            info.doc = documentation(value.toObject().value("documentation"));
            editor->showCompletionDetail(info);
        });
}

bool LanguageAssist::accept(CodeEditor* editor, const QString& name) {
    if (!completions_.value(editor).contains(name)) return false;
    sync();
    if (completionVersions_.value(editor) != documents_.value(editor).version) { completions_.remove(editor); editor->hideCompletions(); return true; }
    const auto selected = completions_.value(editor).value(name);
    const int at = editor->textCursor().position();
    const int prefix = editor->completionPrefix().size();
    editor->hideCompletions();
    const auto apply = [this, editor, selected, at, prefix](const QJsonValue& response, const QString&) {
        const auto item = response.isObject() ? response.toObject() : selected;
        QJsonArray edits = item.value("additionalTextEdits").toArray();
        QJsonObject edit = item.value("textEdit").toObject();
        if (edit.contains("replace")) edit.insert("range", edit.value("replace"));
        if (!edit.contains("range")) edit = {{"range", QJsonObject{{"start", position(editor->document(), at - prefix)}, {"end", position(editor->document(), at)}}},
            {"newText", item.value("insertText").toString(item.value("label").toString())}};
        SnippetExpansion snippet;
        const bool isSnippet = item.value("insertTextFormat").toInt(1) == 2;
        if (isSnippet) {
            if (!expandSnippet(edit.value("newText").toString(), &snippet)) {
                context_.status("Unsupported snippet syntax; document was not changed"); return;
            }
            edit.insert("newText", snippet.text);
        }
        edits.append(edit);
        QString after;
        const QString before = editor->toPlainText();
        if (!editedText(before, edits, &after)) { context_.status("Completion edit was invalid"); return; }
        const int start = offset(before, edit.value("range").toObject().value("start").toObject());
        int caret = start + edit.value("newText").toString().size();
        for (const auto& additional : item.value("additionalTextEdits").toArray()) {
            const auto a = additional.toObject();
            const auto range = a.value("range").toObject();
            const int left = offset(before, range.value("start").toObject());
            const int right = offset(before, range.value("end").toObject());
            if (right <= start) caret += a.value("newText").toString().size() - (right - left);
        }
        editor->applyLanguageText(after, caret);
        if (isSnippet) editor->startSnippet(caret - snippet.text.size(), snippet.stops);
        completions_.remove(editor);
        sync();
    };
    // 編集に必要な情報は補完応答で受け取る（遅延解決は説明だけを広告する）。
    // Enter/Tab直後の入力より先に確定し、解決待ちによる入力の取り消し・順序逆転を防ぐ。
    apply(selected, QString());
    return true;
}

bool LanguageAssist::signature(CodeEditor* editor) {
    if (!ready() || editor->isMel()) return false;
    sync();
    request(editor, "textDocument/signatureHelp", params(editor, editor->textCursor().position()), true,
        [editor](const QJsonValue& value, const QString&) {
            const auto object = value.toObject();
            const auto signatures = object.value("signatures").toArray();
            if (signatures.isEmpty()) { editor->hideSignatureHelp(); return; }
            const int active = qBound(0, object.value("activeSignature").toInt(), int(signatures.size()) - 1);
            const auto signature = signatures[active].toObject();
            QString label = signature.value("label").toString();
            const auto parameters = signature.value("parameters").toArray();
            const int argument = signature.value("activeParameter").toInt(object.value("activeParameter").toInt());
            int start = -1, end = -1;
            if (argument >= 0 && argument < parameters.size()) {
                const auto p = parameters[argument].toObject().value("label");
                if (p.isArray()) { start = p.toArray()[0].toInt(); end = p.toArray()[1].toInt(); }
                else { start = label.indexOf(p.toString()); end = start + p.toString().size(); }
            }
            QString html = label.toHtmlEscaped();
            if (start >= 0 && end >= start && end <= label.size()) html = label.left(start).toHtmlEscaped() + "<b><u>" + label.mid(start, end - start).toHtmlEscaped() + "</u></b>" + label.mid(end).toHtmlEscaped();
            if (signatures.size() > 1) html.prepend(QString("<small>Overload %1 / %2</small><br>").arg(active + 1).arg(signatures.size()));
            editor->showSignatureHelp("<pre>" + html + "</pre>" + documentation(signature.value("documentation")).toHtmlEscaped().replace("\n", "<br>"));
        });
    return true;
}

bool LanguageAssist::hover(CodeEditor* editor, int end) {
    if (!ready() || editor->isMel()) return false;
    sync();
    request(editor, "textDocument/hover", params(editor, qMax(0, end - 1)), false,
        [this, editor, end](const QJsonValue& value, const QString&) {
            if (editor != context_.current() || !editor->hasFocus()) return;
            const QString text = documentation(value.toObject().value("contents"));
            if (!text.isEmpty()) editor->showPeek("<pre>" + text.toHtmlEscaped() + "</pre>", end);
        });
    return true;
}

void LanguageAssist::notification(const QString& method, const QJsonObject& arguments) {
    if (method != "textDocument/publishDiagnostics") return;
    const QString address = arguments.value("uri").toString();
    for (const auto& doc : documents_) {
        if (!doc.editor || !sameUri(doc.uri, address) || doc.text != doc.editor->toPlainText()) continue;
        // バージョンなしの診断は、どの編集に対応するか保証できないため反映しない。
        if (arguments.value("version").toInt(-1) != doc.version) continue;
        diagnostics_[doc.editor] = arguments.value("diagnostics").toArray();
        diagnosticVersions_[doc.editor] = doc.version;
        AnalysisResult result;
        if (preferences_.option(option::kStaticAnalysis)) {
            for (const auto& entry : diagnostics_[doc.editor]) {
                const auto item = entry.toObject();
                if (item.value("severity").toInt() > 2) continue;
                const auto range = item.value("range").toObject();
                const auto start = range.value("start").toObject();
                const auto finish = range.value("end").toObject();
                result.diagnostics.append({item.value("severity").toInt() == 1 ? "error" : "warning", start.value("line").toInt() + 1,
                    item.value("message").toString(), start.value("character").toInt() + 1,
                    start.value("line") == finish.value("line") ? qMax(1, finish.value("character").toInt() - start.value("character").toInt()) : 0});
            }
        }
        doc.editor->setDiagnostics(result.diagnostics);
        if (doc.editor == context_.current()) { problems_->showResult(result, true); problems_->setVisible(preferences_.option(option::kStaticAnalysis)); }
        doc.editor->setProperty("languageDiagnosticCount", result.diagnostics.size());
    }
}

void LanguageAssist::decorate() {
    auto* editor = context_.current();
    if (!ready() || !editor || editor->isMel()) return;
    const auto doc = documents_.value(editor);
    if (diagnosticVersions_.value(editor, -1) == doc.version)
        notification("textDocument/publishDiagnostics", {{"uri", doc.uri}, {"version", doc.version}, {"diagnostics", diagnostics_.value(editor)}});
    if (!preferences_.option("semanticColors") || !preferences_.option("inlayHints"))
        editor->setLanguageDecorations(preferences_.option("semanticColors") ? editor->property("languageTokens").toJsonArray() : QJsonArray(),
                                      preferences_.option("inlayHints") ? editor->property("languageHints").toJsonArray() : QJsonArray());
    if (preferences_.option("semanticColors")) {
        request(editor, "textDocument/semanticTokens/full", {{"textDocument", QJsonObject{{"uri", uri(editor)}}}}, false,
            [this, editor](const QJsonValue& value, const QString&) {
                if (!preferences_.option("semanticColors")) return;
                const auto legend = client_.capabilities().value("semanticTokensProvider").toObject().value("legend").toObject().value("tokenTypes").toArray();
                const auto data = value.toObject().value("data").toArray();
                QJsonArray ranges;
                int line = 0, column = 0;
                for (int i = 0; i + 4 < data.size(); i += 5) {
                    line += data[i].toInt();
                    column = data[i].toInt() == 0 ? column + data[i + 1].toInt() : data[i + 1].toInt();
                    const int type = data[i + 3].toInt();
                    if (type >= 0 && type < legend.size()) ranges.append(QJsonObject{{"line", line}, {"column", column}, {"length", data[i + 2]}, {"type", legend[type]}});
                }
                editor->setLanguageDecorations(ranges, editor->property("languageHints").toJsonArray());
            });
    }
    if (preferences_.option("inlayHints")) {
        request(editor, "textDocument/inlayHint", {{"textDocument", QJsonObject{{"uri", uri(editor)}}}, {"range", QJsonObject{{"start", QJsonObject{{"line", 0}, {"character", 0}}}, {"end", position(editor->document(), editor->document()->characterCount() - 1)}}}}, false,
            [this, editor](const QJsonValue& value, const QString&) {
                if (preferences_.option("inlayHints")) editor->setLanguageDecorations(editor->property("languageTokens").toJsonArray(), value.toArray());
            });
    }
}

void LanguageAssist::navigate(CodeEditor* editor, bool references, bool peek) {
    if (!ready() || !editor || editor->isMel()) return;
    sync();
    auto args = params(editor, editor->textCursor().position());
    if (references) args.insert("context", QJsonObject{{"includeDeclaration", true}});
    request(editor, references ? "textDocument/references" : "textDocument/definition", args, true,
        [this, editor, peek](const QJsonValue& value, const QString&) { locations(editor, value.isArray() ? value.toArray() : QJsonArray{value}, peek); });
}

void LanguageAssist::locations(CodeEditor* editor, const QJsonArray& values, bool peek) {
    const QPointer<LanguageAssist> self(this);
    const QPointer<CodeEditor> source(editor);
    QStringList labels;
    QList<QJsonObject> locations;
    for (const auto& value : values) {
        auto object = value.toObject();
        if (object.contains("targetUri")) { object.insert("uri", object.value("targetUri")); object.insert("range", object.value("targetSelectionRange")); }
        if (object.value("uri").toString().isEmpty()) continue;
        locations.append(object);
        labels.append(QString("%1:%2").arg(QUrl(object.value("uri").toString()).toLocalFile()).arg(object.value("range").toObject().value("start").toObject().value("line").toInt() + 1));
    }
    if (locations.isEmpty()) { context_.status("No locations found"); return; }
    int index = 0;
    if (locations.size() > 1) {
        bool ok = false;
        const auto choice = QInputDialog::getItem(editor, "Locations", "Select location", labels, 0, false, &ok);
        if (!self || !source || !ok) return;
        index = labels.indexOf(choice);
    }
    const auto target = locations[index];
    const auto point = target.value("range").toObject().value("start").toObject();
    CodeEditor* destination = nullptr;
    for (const auto& doc : documents_) if (sameUri(doc.uri, target.value("uri").toString())) destination = doc.editor;
    if (peek) {
        QString text, error;
        if (destination) text = destination->toPlainText();
        else if (!readScriptFile(QUrl(target.value("uri").toString()).toLocalFile(), &text, &error)) { context_.status(error); return; }
        const auto lines = text.split('\n').mid(qMax(0, point.value("line").toInt() - 2), 12);
        editor->showPeek("<pre>" + lines.join('\n').toHtmlEscaped() + "</pre>", editor->textCursor().position());
    } else {
        if (!destination) destination = context_.open(QUrl(target.value("uri").toString()).toLocalFile());
        if (!destination) return;
        const int at = offset(destination->toPlainText(), point);
        if (at < 0) return;
        if (context_.activate) context_.activate(destination);
        QTextCursor cursor(destination->document()); cursor.setPosition(at); destination->setTextCursor(cursor); destination->ensureCursorVisible(); destination->setFocus();
    }
}

void LanguageAssist::rename(CodeEditor* editor) {
    if (!ready() || !editor || editor->isMel()) return;
    const QPointer<LanguageAssist> self(this);
    const QPointer<CodeEditor> target(editor);
    bool ok = false;
    const QString name = QInputDialog::getText(editor, "Rename symbol", "New name", QLineEdit::Normal, QString(), &ok);
    if (!self || !target || !ok || name.isEmpty()) return;
    sync();
    auto args = params(editor, editor->textCursor().position()); args.insert("newName", name);
    request(editor, "textDocument/rename", args, true, [this](const QJsonValue& value, const QString&) { preview(value.toObject()); });
}

void LanguageAssist::actions(CodeEditor* editor) {
    if (!ready() || !editor || editor->isMel()) return;
    sync();
    const auto cursor = editor->textCursor();
    const auto args = QJsonObject{{"textDocument", QJsonObject{{"uri", uri(editor)}}}, {"range", QJsonObject{{"start", position(editor->document(), cursor.selectionStart())}, {"end", position(editor->document(), cursor.selectionEnd())}}}, {"context", QJsonObject{{"diagnostics", diagnostics_.value(editor)}}}};
    request(editor, "textDocument/codeAction", args, true, [this, editor](const QJsonValue& value, const QString&) {
        QList<QJsonObject> actions; QStringList titles;
        for (const auto& action : value.toArray()) {
            const auto object = action.toObject();
            if (object.contains("disabled") || !object.contains("edit")) continue;
            actions.append(object); titles.append(object.value("title").toString());
        }
        if (titles.isEmpty()) { context_.status("No safe edit actions at this position"); return; }
        bool ok = false;
        const QPointer<LanguageAssist> self(this);
        const QString choice = QInputDialog::getItem(editor, "Code actions", "Action", titles, 0, false, &ok);
        if (self && ok) preview(actions[titles.indexOf(choice)].value("edit").toObject());
    });
}

void LanguageAssist::preview(const QJsonObject& edit) {
    QJsonObject changes = edit.value("changes").toObject();
    QSet<QString> created;
    QList<QPair<QString, QString>> renames;
    QHash<QString, QByteArray> bytes;
    QString operations;
    for (const auto& entry : edit.value("documentChanges").toArray()) {
        const auto object = entry.toObject();
        if (object.contains("kind")) {
            const QString kind = object.value("kind").toString();
            const QUrl destination(object.value(kind == "create" ? "uri" : "newUri").toString());
            const QString path = destination.toLocalFile();
            if ((kind != "create" && kind != "rename") || !destination.isLocalFile()
                || QFileInfo::exists(path) || QFileInfo(path).suffix() != "py" || !QFileInfo(QFileInfo(path).absolutePath()).isDir()) {
                context_.status("File operation refused: choose an unused local Python module path"); return;
            }
            for (const auto& doc : documents_) if (sameUri(doc.uri, destination.toString())) {
                context_.status("Destination is already open; close it before refactoring"); return;
            }
            if (kind == "create") {
                if (created.contains(path)) { context_.status("Duplicate file creation"); return; }
                created.insert(path);
                if (!changes.contains(destination.toString())) changes.insert(destination.toString(), QJsonArray());
                operations += "New unsaved module: " + path + "\n";
            } else {
                const QUrl source(object.value("oldUri").toString());
                const QString old = source.toLocalFile();
                QFile file(old);
                if (!source.isLocalFile() || QFileInfo(old).isSymLink() || QFileInfo(old).suffix() != "py"
                    || QFileInfo(old).absolutePath() != QFileInfo(path).absolutePath() || !file.open(QIODevice::ReadOnly)) {
                    context_.status("Only existing Python modules in the same folder can be renamed"); return;
                }
                for (const auto& pair : renames) if (pair.first == old || pair.second == path) {
                    context_.status("Duplicate module rename"); return;
                }
                renames.append(qMakePair(old, path)); bytes.insert(old, file.readAll());
                if (!changes.contains(source.toString())) changes.insert(source.toString(), QJsonArray());
                operations += "Rename on disk: " + old + " -> " + path + "\n";
            }
            continue;
        }
        const auto document = object.value("textDocument").toObject();
        const QString address = document.value("uri").toString();
        if (!document.value("version").isNull() && !document.value("version").isUndefined()) {
            bool valid = false;
            for (const auto& doc : documents_) if (sameUri(doc.uri, address) && doc.version == document.value("version").toInt()) valid = true;
            if (!valid) { context_.status("Edit version is stale"); return; }
        }
        changes.insert(address, object.value("edits"));
    }
    struct Plan { QString uri; QString path; QString before; QString after; QPointer<CodeEditor> editor; };
    QList<Plan> plans;
    QString summary = operations + "\n";
    for (auto it = changes.begin(); it != changes.end(); ++it) {
        const QUrl url(it.key());
        if (!url.isLocalFile()) { context_.status("Only local Python documents can be edited"); return; }
        Plan plan; plan.uri = it.key(); plan.path = url.toLocalFile();
        for (const auto& doc : documents_) if (sameUri(doc.uri, plan.uri)) plan.editor = doc.editor;
        if (plan.editor) plan.before = plan.editor->toPlainText();
        else if (!created.contains(plan.path)) {
            QString error;
            if (!readScriptFile(plan.path, &plan.before, &error)) { context_.status(error); return; }
        }
        if (!editedText(plan.before, it.value().toArray(), &plan.after)) { context_.status("Invalid or overlapping edits"); return; }
        if (plan.after == plan.before && !bytes.contains(plan.path) && !created.contains(plan.path)) continue;
        summary += plan.path + "\n--- Before ---\n" + plan.before + "\n+++ After +++\n" + plan.after + "\n\n";
        plans.append(plan);
    }
    if (plans.isEmpty()) { context_.status("No changes"); return; }
    const QPointer<LanguageAssist> self(this);
    QPointer<QDialog> dialog = new QDialog(context_.current());
    dialog->setWindowTitle("Review changes — text remains unsaved; module renames apply on disk"); dialog->resize(850, 600);
    auto* layout = new QVBoxLayout(dialog); auto* view = new QPlainTextEdit(dialog); view->setReadOnly(true); view->setPlainText(summary); layout->addWidget(view);
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Apply | QDialogButtonBox::Cancel, dialog); layout->addWidget(buttons);
    connect(buttons->button(QDialogButtonBox::Apply), &QAbstractButton::clicked, dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject);
    const int decision = dialog->exec();
    if (dialog) dialog->deleteLater();
    if (!self || !dialog || decision != QDialog::Accepted) return;
    // 対象を全件検証してから変更する。下見中の入力や外部編集を上書きしない。
    for (auto& plan : plans) {
        QString current, error;
        if (plan.editor) current = plan.editor->toPlainText();
        else if (!created.contains(plan.path) && !readScriptFile(plan.path, &current, &error)) { context_.status(error); return; }
        if (current != plan.before) { context_.status("Document changed during preview; request the action again"); return; }
    }
    for (const auto& path : created) if (QFileInfo::exists(path)) { context_.status("New module path is now occupied"); return; }
    for (const auto& pair : renames) {
        QFile file(pair.first);
        if (QFileInfo::exists(pair.second) || !file.open(QIODevice::ReadOnly) || file.readAll() != bytes.value(pair.first)) {
            context_.status("Module changed on disk during preview; nothing applied"); return;
        }
    }
    for (auto& plan : plans) {
        if (!plan.editor) plan.editor = context_.open(plan.path);
        if (!plan.editor || plan.editor->toPlainText() != plan.before) { context_.status("Could not open all edit targets; nothing applied"); return; }
    }
    QList<QPair<QString, QString>> moved;
    for (const auto& pair : renames) {
        if (!QFile::rename(pair.first, pair.second)) {
            QString rollback;
            for (auto it = moved.crbegin(); it != moved.crend(); ++it)
                if (!QFile::rename(it->second, it->first)) rollback += " Recovery needed: " + it->second;
            context_.status("Module rename failed; text was not changed." + rollback); return;
        }
        moved.append(pair);
    }
    lastRefactoring_.clear(); lastRenames_ = renames; renameBytes_ = bytes; lastCreated_ = created;
    for (const auto& plan : plans) {
        lastRefactoring_.append({plan.editor, plan.before, plan.after, plan.path});
        for (const auto& pair : renames) if (plan.path == pair.first) plan.editor->setFilePath(pair.second);
        plan.editor->applyLanguageText(plan.after, qMin(plan.editor->textCursor().position(), int(plan.after.size())));
    }
    refactoringApplied_ = true;
    sync();
    context_.status(QString("Updated %1 document(s); review and save. Edit > Refactor > Undo last refactoring restores the group.").arg(plans.size()));
}

void LanguageAssist::restoreRefactoring(bool redo) {
    if (lastRefactoring_.isEmpty() || refactoringApplied_ == redo) { context_.status("No refactoring to restore"); return; }
    for (const auto& plan : lastRefactoring_) {
        QString expectedPath = plan.path;
        for (const auto& pair : lastRenames_) if (refactoringApplied_ && plan.path == pair.first) expectedPath = pair.second;
        if (!plan.editor || QFileInfo(plan.editor->filePath()).absoluteFilePath().compare(QFileInfo(expectedPath).absoluteFilePath(), Qt::CaseInsensitive) != 0
            || plan.editor->toPlainText() != (redo ? plan.before : plan.after)) {
            context_.status("A target was edited, renamed or closed; group restore cancelled without changes"); return;
        }
    }
    // 保存済みの新規ファイルは削除しない。外部変更やユーザーの保存を取り消さない。
    for (const auto& path : lastCreated_) if (QFileInfo::exists(path)) {
        context_.status("New module has been saved; use individual document Undo"); return;
    }
    QList<QPair<QString, QString>> operations;
    for (const auto& pair : lastRenames_) {
        const QString from = redo ? pair.first : pair.second;
        const QString to = redo ? pair.second : pair.first;
        QFile file(from);
        if (QFileInfo::exists(to) || !file.open(QIODevice::ReadOnly) || file.readAll() != renameBytes_.value(pair.first)) {
            context_.status("A module was saved or changed on disk; group restore cancelled"); return;
        }
        operations.append(qMakePair(from, to));
    }
    QList<QPair<QString, QString>> moved;
    for (const auto& pair : operations) {
        if (!QFile::rename(pair.first, pair.second)) {
            QString rollback;
            for (auto it = moved.crbegin(); it != moved.crend(); ++it)
                if (!QFile::rename(it->second, it->first)) rollback += " Recovery needed: " + it->second;
            context_.status("Restore rename failed; text was not changed." + rollback); return;
        }
        moved.append(pair);
    }
    for (const auto& plan : lastRefactoring_) {
        QString path = plan.path;
        for (const auto& pair : lastRenames_) if (redo && plan.path == pair.first) path = pair.second;
        plan.editor->setFilePath(path);
        const QString text = redo ? plan.after : plan.before;
        plan.editor->applyLanguageText(text, qMin(plan.editor->textCursor().position(), int(text.size())));
    }
    refactoringApplied_ = redo;
    sync(); context_.status(redo ? "Refactoring reapplied" : "Refactoring restored");
}
}  // namespace mce
