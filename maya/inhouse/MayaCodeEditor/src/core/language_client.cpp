/** @file language_client.cpp
 * @brief LSPのフレーミング、初期化、取消と寿命管理。
 */
#include "core/language_client.h"
#include "core/json_file.h"
#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QPointer>
#include <QUrl>

namespace mce {
LanguageClient::LanguageClient(QObject* parent) : QObject(parent) {
    connect(&process_, &QProcess::readyReadStandardOutput, this, [this] { read(); });
    connect(&process_, &QProcess::readyReadStandardError, this, [this] { process_.readAllStandardError(); });
    connect(&process_, &QProcess::errorOccurred, this, [this](QProcess::ProcessError) { fail(process_.errorString()); });
    connect(&process_, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished), this,
            [this](int, QProcess::ExitStatus) { fail("Language analysis stopped; basic completion remains available"); });
    connect(&timeout_, &QTimer::timeout, this, [this] {
        const QPointer<LanguageClient> guard(this);
        const auto ids = pending_.keys();
        for (int id : ids) {
            if (pending_.contains(id) && pending_[id].expires < QDateTime::currentMSecsSinceEpoch()) {
                auto reply = pending_.take(id).reply;
                notify("$/cancelRequest", {{"id", id}});
                if (reply) reply(QJsonValue(), "Language analysis timed out");
                if (!guard) return;
            }
        }
    });
    timeout_.start(1000);
}

LanguageClient::~LanguageClient() {
    timeout_.stop();
    process_.disconnect(this);
    pending_.clear();
    // QProcessが起動したプロセスだけを終了する。他のMayaや解析サーバーを列挙しない。
    if (process_.state() != QProcess::NotRunning) {
        send({{"jsonrpc", "2.0"}, {"id", ++nextId_}, {"method", "shutdown"}, {"params", QJsonObject()}});
        notify("exit", {});
        process_.closeWriteChannel();
        if (!process_.waitForFinished(500)) {
            process_.kill();
            process_.waitForFinished(1000);
        }
    }
}

bool LanguageClient::start(const QJsonObject& configuration) {
    if (process_.state() != QProcess::NotRunning) return true;
    const QString path = qEnvironmentVariable("MCE_LANGUAGE_SERVER_CONFIG",
        qEnvironmentVariable("LOCALAPPDATA") + "/MayaCodeEditor/language-server/server.json");
    QJsonObject config;
    if (!readJsonFile(path, &config) || !QFileInfo::exists(config.value("node").toString())
        || !QFileInfo::exists(config.value("server").toString())) {
        if (onStatus) onStatus("Basic completion (language server setup required)");
        return false;
    }
    settings_ = configuration;
    ready_ = false;
    buffer_.clear();
    // 再起動でもstartedの接続を増やさない。
    process_.disconnect(&process_, &QProcess::started, this, nullptr);
    connect(&process_, &QProcess::started, this, [this] {
        const QString root = settings_.value("root").toString(QDir::currentPath());
        const QString uri = QUrl::fromLocalFile(root).toString();
        const QJsonObject textCapabilities = QJsonDocument::fromJson(R"json({
            "completion": {"completionItem": {"snippetSupport": true,
                "documentationFormat": ["plaintext"], "resolveSupport": {"properties": ["documentation", "detail"]}}},
            "hover": {"contentFormat": ["plaintext"]},
            "signatureHelp": {"signatureInformation": {"documentationFormat": ["plaintext"], "parameterInformation": {"labelOffsetSupport": true}}},
            "publishDiagnostics": {"versionSupport": true},
            "codeAction": {"codeActionLiteralSupport": {"codeActionKind": {"valueSet": ["quickfix", "refactor", "source.organizeImports"]}}},
            "semanticTokens": {"requests": {"full": true},
                "tokenTypes": ["class", "function", "method", "variable", "parameter", "property", "namespace", "type", "typeParameter", "keyword", "comment", "string", "number", "operator"],
                "tokenModifiers": ["declaration", "readonly", "static", "deprecated", "defaultLibrary"], "formats": ["relative"]},
            "inlayHint": {}
        })json").object();
        request("initialize", {{"processId", double(QCoreApplication::applicationPid())}, {"rootUri", uri},
                {"workspaceFolders", QJsonArray{QJsonObject{{"uri", uri}, {"name", QFileInfo(root).fileName()}}}},
                {"capabilities", QJsonObject{{"general", QJsonObject{{"positionEncodings", QJsonArray{"utf-16"}}}},
                {"workspace", QJsonObject{{"configuration", true}, {"workspaceFolders", true}, {"applyEdit", false}}},
                {"textDocument", textCapabilities}}}}, [this](const QJsonValue& value, const QString& error) {
            if (!error.isEmpty()) { fail(error); return; }
            capabilities_ = value.toObject().value("capabilities").toObject();
            notify("initialized", {});
            ready_ = true;
            if (onStatus) onStatus("Type analysis ready");
            if (onReady) onReady();
        });
    });
    process_.setProgram(config.value("node").toString());
    process_.setArguments({config.value("server").toString(), "--stdio"});
    process_.setWorkingDirectory(QFileInfo(path).absolutePath());
    process_.start();
    return true;
}

void LanguageClient::configure(const QJsonObject& settings) {
    if (settings_ == settings) return;
    settings_ = settings;
    if (ready_) notify("workspace/didChangeConfiguration", {{"settings", settings_}});
}

int LanguageClient::request(const QString& method, const QJsonObject& params, Reply reply) {
    const int id = ++nextId_;
    pending_.insert(id, {std::move(reply), QDateTime::currentMSecsSinceEpoch() + 30000});
    send({{"jsonrpc", "2.0"}, {"id", id}, {"method", method}, {"params", params}});
    return id;
}

void LanguageClient::notify(const QString& method, const QJsonObject& params) {
    send({{"jsonrpc", "2.0"}, {"method", method}, {"params", params}});
}

void LanguageClient::cancel(int id) {
    if (pending_.remove(id)) notify("$/cancelRequest", {{"id", id}});
}

void LanguageClient::send(const QJsonObject& object) {
    if (process_.state() != QProcess::Running) return;
    const QByteArray body = QJsonDocument(object).toJson(QJsonDocument::Compact);
    const QString trace = qEnvironmentVariable("MCE_LANGUAGE_TRACE");
    if (!trace.isEmpty()) {
        QFile file(trace);
        if (file.open(QIODevice::Append)) file.write("SEND " + body + '\n');
    }
    process_.write("Content-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
}

void LanguageClient::read() {
    const QPointer<LanguageClient> guard(this);
    buffer_ += process_.readAllStandardOutput();
    constexpr int maximum = 32 * 1024 * 1024;
    if (buffer_.size() > maximum) { fail("Language response exceeded limit"); process_.kill(); return; }
    for (;;) {
        const int end = buffer_.indexOf("\r\n\r\n");
        if (end < 0) return;
        int length = -1;
        for (const auto& line : buffer_.left(end).split('\n')) {
            if (line.toLower().startsWith("content-length:")) {
                bool ok = false;
                length = line.mid(15).trimmed().toInt(&ok);
                if (!ok) length = -1;
            }
        }
        if (length < 0 || length > maximum) { fail("Invalid language response"); process_.kill(); return; }
        if (buffer_.size() < end + 4 + length) return;
        const auto object = QJsonDocument::fromJson(buffer_.mid(end + 4, length)).object();
        buffer_.remove(0, end + 4 + length);
        dispatch(object);
        // 下見ダイアログのイベントループ中に所有画面を閉じることがある。
        if (!guard) return;
    }
}

void LanguageClient::dispatch(const QJsonObject& object) {
    const QString trace = qEnvironmentVariable("MCE_LANGUAGE_TRACE");
    if (!trace.isEmpty()) {
        QFile file(trace);
        if (file.open(QIODevice::Append)) file.write(QJsonDocument(object).toJson(QJsonDocument::Compact) + '\n');
    }
    const QString method = object.value("method").toString();
    if (object.contains("id") && !method.isEmpty()) {
        QJsonValue result;
        if (method == "workspace/configuration") {
            QJsonArray values;
            for (const auto& item : object.value("params").toObject().value("items").toArray()) {
                QJsonValue value = settings_;
                for (const auto& part : item.toObject().value("section").toString().split('.', Qt::SkipEmptyParts)) value = value.toObject().value(part);
                values.append(value.isUndefined() ? QJsonValue(QJsonValue::Null) : value);
            }
            result = values;
        } else if (method == "workspace/applyEdit") {
            result = QJsonObject{{"applied", false}, {"failureReason", "Use the reviewed editor action"}};
        }
        send({{"jsonrpc", "2.0"}, {"id", object.value("id")}, {"result", result.isUndefined() ? QJsonValue(QJsonValue::Null) : result}});
    } else if (object.contains("id")) {
        const int id = object.value("id").toInt();
        if (!pending_.contains(id)) return;
        const auto pending = pending_.take(id);
        if (pending.reply) pending.reply(object.value("result"), object.value("error").toObject().value("message").toString());
    } else if (onNotification) {
        onNotification(method, object.value("params").toObject());
    }
}

void LanguageClient::fail(const QString& reason) {
    ready_ = false;
    pending_.clear();
    if (onStatus) onStatus(reason);
}
}  // namespace mce
