/** @file modulescan.cpp
 * @brief トップレベル名の補完(importの行)と、sys.pathの別スレッド走査。
 * @details Pythonの旧実装(Index.complete/scan_top)と同じ候補・並び順・件数上限を返す。
 */
#include "modulescan.h"
#include <QDirIterator>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <algorithm>
#include <chrono>

namespace hedit {
bool isIdentifier(const QString& name) {
    if (name.isEmpty() || !(name.at(0).isLetter() || name.at(0)==QLatin1Char('_'))) return false;
    for (const QChar character: name)
        if (!(character.isLetterOrNumber() || character==QLatin1Char('_') || character.isMark())) return false;
    return true;
}

QSet<QString> scanTopLevel(const QStringList& paths, const std::atomic_bool* cancel) {
    QSet<QString> result;
    for (const QString& path: paths) {
        if (cancel && *cancel) break;
        QDirIterator entries(path, QDir::AllEntries|QDir::NoDotAndDotDot|QDir::Hidden|QDir::System);
        while (entries.hasNext()) {
            entries.next();
            const QString name=entries.fileName();
            // os.scandirと同じく、.pyで終わるものは拡張子を除いた名前、フォルダーは識別子のものだけ。
            if (name.endsWith(QLatin1String(".py"))) result.insert(name.left(name.size()-3));
            else if (entries.fileInfo().isDir() && isIdentifier(name)) result.insert(name);
        }
    }
    return result;
}

bool topLevelImportPrefix(const QString& source, QString* prefix) {
    static const QRegularExpression importLine(QStringLiteral("^\\s*(import|from)\\s+[\\w.]*$"),
        QRegularExpression::UseUnicodePropertiesOption);
    static const QRegularExpression token(QStringLiteral("[A-Za-z_][\\w.]*$|(?<=\\.)$"),
        QRegularExpression::UseUnicodePropertiesOption);
    const QString line=source.mid(source.lastIndexOf(QLatin1Char('\n'))+1);
    if (!importLine.match(line).hasMatch()) return false;
    const QString name=token.match(source).captured(0);
    // import maya.cm のようなドット付きはモジュールの中身の補完なので、Python側で解決する。
    if (name.contains(QLatin1Char('.'))) return false;
    if (prefix) *prefix=name;
    return true;
}

QByteArray completionItems(const QSet<QString>& names, const QString& prefix, bool pending) {
    QStringList matched;
    const bool privateNames=prefix.startsWith(QLatin1Char('_'));
    for (const QString& name: names)
        if (name.startsWith(prefix) && (privateNames || !name.startsWith(QLatin1Char('_')))) matched.append(name);
    std::sort(matched.begin(),matched.end());
    QJsonArray items;
    for (const QString& name: matched.mid(0,250)) items.append(QJsonObject{{"name",name},{"detail",""}});
    return QJsonDocument(QJsonObject{{"items",items},{"pending",pending}}).toJson(QJsonDocument::Compact);
}

ModuleScanner::ModuleScanner(int minimumInterval) : interval(minimumInterval) {}

ModuleScanner::~ModuleScanner() { stop(); }

void ModuleScanner::refresh(const QStringList& paths) {
    std::lock_guard<std::mutex> lock(mutex);
    if (running || (started.isValid() && started.elapsed()<interval)) return;
    // 前回の走査は終わっている(running=false)ので、合流してから次を始める。
    if (worker.joinable()) worker.join();
    running=true;
    cancel=false;
    started.restart();
    worker=std::thread(&ModuleScanner::run,this,paths);
}

bool ModuleScanner::waitForFirst(int milliseconds) {
    std::unique_lock<std::mutex> lock(mutex);
    return finished.wait_for(lock,std::chrono::milliseconds(milliseconds),[this] { return completed || !running; })
        && completed;
}

QSet<QString> ModuleScanner::names(bool* pending) const {
    std::lock_guard<std::mutex> lock(mutex);
    if (pending) *pending=running;
    return scanned;
}

void ModuleScanner::stop() {
    cancel=true;
    if (worker.joinable()) worker.join();
    std::lock_guard<std::mutex> lock(mutex);
    running=false;
}

void ModuleScanner::run(QStringList paths) {
    QSet<QString> result=scanTopLevel(paths,&cancel);
    {
        std::lock_guard<std::mutex> lock(mutex);
        // 中断した走査の途中結果で、前回の完全な結果を置き換えない。
        if (!cancel) { scanned=std::move(result); completed=true; }
        running=false;
    }
    finished.notify_all();
}
}
