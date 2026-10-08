/** @file module_scanner.cpp
 * @brief トップレベル名の補完(importの行)と、sys.pathの別スレッド走査。
 * @details Pythonの旧実装(Index.complete/scan_top)と同じ候補・並び順・件数上限を返す。
 */
#include "core/module_scanner.h"
#include <QDirIterator>
#include <QFileInfo>
#include <QRegularExpression>
#include <QVector>
#include <algorithm>
#include <chrono>

namespace hedit {

bool isIdentifier(const QString& name) {
    if (name.isEmpty()) {
        return false;
    }
    const QChar first = name.at(0);
    if (!first.isLetter() && first != QLatin1Char('_')) {
        return false;
    }
    for (const QChar character : name) {
        const bool allowed = character.isLetterOrNumber() || character == QLatin1Char('_') || character.isMark();
        if (!allowed) {
            return false;
        }
    }
    return true;
}

QSet<QString> scanTopLevel(const QStringList& paths, const std::atomic_bool* cancel) {
    QSet<QString> result;
    for (const QString& path : paths) {
        if (cancel && *cancel) {
            break;
        }
        QDirIterator entries(path, QDir::AllEntries | QDir::NoDotAndDotDot);
        while (entries.hasNext()) {
            entries.next();
            const QString name = entries.fileName();
            // importできる名前だけを集める(どれもPythonの識別子でなければimportできない)。
            // - name.py: 拡張子を除いた名前(my-tool.py のような識別子でない名前は除く)。
            // - 拡張モジュール name.pyd・name.cp311-win_amd64.pyd: 最初の点より前の名前。
            // - フォルダー: 識別子の名前のもの(パッケージ・名前空間パッケージ)。
            if (name.endsWith(QLatin1String(".py"))) {
                const QString stem = name.left(name.size() - 3);
                if (isIdentifier(stem)) {
                    result.insert(stem);
                }
            } else if (name.endsWith(QLatin1String(".pyd")) && !entries.fileInfo().isDir()) {
                const QString stem = name.left(name.indexOf(QLatin1Char('.')));
                if (isIdentifier(stem)) {
                    result.insert(stem);
                }
            } else if (entries.fileInfo().isDir() && isIdentifier(name)) {
                result.insert(name);
            }
        }
    }
    return result;
}

bool topLevelImportPrefix(const QString& source, QString* prefix) {
    // 正規表現の作成は重いので、static(初回だけ作って使い回す)にする。
    static const QRegularExpression importLine(QStringLiteral("^\\s*(import|from)\\s+[\\w.]*$"),
                                               QRegularExpression::UseUnicodePropertiesOption);
    static const QRegularExpression token(QStringLiteral("[A-Za-z_][\\w.]*$|(?<=\\.)$"),
                                          QRegularExpression::UseUnicodePropertiesOption);
    const QString lastLine = source.mid(source.lastIndexOf(QLatin1Char('\n')) + 1);
    if (!importLine.match(lastLine).hasMatch()) {
        return false;
    }
    const QString name = token.match(source).captured(0);
    // import maya.cm のようなドット付きはモジュールの中身の補完なので、Python側で解決する。
    if (name.contains(QLatin1Char('.'))) {
        return false;
    }
    if (prefix) {
        *prefix = name;
    }
    return true;
}

CompletionResult completionItems(const QSet<QString>& names, const QString& prefix, bool pending) {
    const bool wantsPrivateNames = prefix.startsWith(QLatin1Char('_'));
    constexpr int kMaximumNames = 250;
    QVector<QString> matched;
    for (const QString& name : names) {
        if (!name.startsWith(prefix)) {
            continue;
        }
        if (!wantsPrivateNames && name.startsWith(QLatin1Char('_'))) {
            continue;
        }
        matched.append(name);
    }
    // 使うのは名前順の先頭250件だけなので、全体を並べ替えずに先頭だけを並べる(partial_sort)。
    const int count = qMin(int(matched.size()), kMaximumNames);
    std::partial_sort(matched.begin(), matched.begin() + count, matched.end());

    CompletionResult result;
    result.items.reserve(count);
    for (int i = 0; i < count; ++i) {
        result.items.append({matched[i], QString(), QString()});
    }
    result.pending = pending;
    return result;
}

ModuleScanner::ModuleScanner(int minimumInterval) : interval_(minimumInterval) {}

ModuleScanner::~ModuleScanner() {
    stop();
}

void ModuleScanner::refresh(const QStringList& paths) {
    std::lock_guard<std::mutex> lock(mutex_);
    const bool tooSoon = started_.isValid() && started_.elapsed() < interval_;
    if (running_ || tooSoon) {
        return;
    }
    // 前回の走査は終わっている(running_=false)ので、合流してから次を始める。
    if (worker_.joinable()) {
        worker_.join();
    }
    running_ = true;
    cancel_ = false;
    started_.restart();
    worker_ = std::thread(&ModuleScanner::run, this, paths);
}

bool ModuleScanner::waitForFirst(int milliseconds) {
    std::unique_lock<std::mutex> lock(mutex_);
    // wait_forは、条件が満たされるか時間切れまで待つ。待っている間は鍵を手放す。
    const bool finishedWaiting = finished_.wait_for(lock, std::chrono::milliseconds(milliseconds),
                                                    [this] { return completed_ || !running_; });
    return finishedWaiting && completed_;
}

QSet<QString> ModuleScanner::names(bool* pending) const {
    std::lock_guard<std::mutex> lock(mutex_);
    if (pending) {
        *pending = running_;
    }
    return scanned_;
}

void ModuleScanner::stop() {
    cancel_ = true;
    if (worker_.joinable()) {
        worker_.join();
    }
    std::lock_guard<std::mutex> lock(mutex_);
    running_ = false;
}

void ModuleScanner::run(QStringList paths) {
    QSet<QString> result = scanTopLevel(paths, &cancel_);
    {
        std::lock_guard<std::mutex> lock(mutex_);
        // 中断した走査の途中結果で、前回の完全な結果を置き換えない。
        if (!cancel_) {
            scanned_ = std::move(result);
            completed_ = true;
        }
        running_ = false;
    }
    finished_.notify_all();
}

}  // namespace hedit
