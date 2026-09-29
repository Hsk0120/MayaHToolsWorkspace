/** @file user_paths.cpp
 * @brief heditのファイルを置く場所の決定。
 */
#include "plugin/user_paths.h"
#include "plugin/mel.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>

namespace hedit {
namespace {

/** @brief Mayaのユーザー設定フォルダー。 @return ``internalVar -userPrefDir``の結果。 */
QString userPrefDir() {
    return mel("internalVar -userPrefDir");
}

/** @brief 旧名heditorのフォルダーから、まだ無いファイルだけをコピーする。
 * @param base Mayaのユーザー設定フォルダー。
 */
void copyLegacyFiles(const QDir& base) {
    const QDir destination(base.filePath("hedit"));
    const QDir legacy(base.filePath("heditor"));
    for (const char* name : {"tabs.json", "ui.json", "preferences.ini"}) {
        const QString source = legacy.filePath(name);
        const QString target = destination.filePath(name);
        if (QFileInfo(source).isFile() && !QFileInfo::exists(target)) {
            QDir().mkpath(destination.path());
            QFile::copy(source, target);
        }
    }
}

}  // namespace

QString userFolder() {
    const QString prefs = userPrefDir();
    if (prefs.isEmpty()) {
        return QString();
    }
    return QDir::cleanPath(prefs + "/hedit");
}

QString sessionFilePath() {
    const QString override = qEnvironmentVariable("HEDIT_SESSION_FILE");
    if (!override.isEmpty()) {
        return override;
    }
    const QDir base(userPrefDir());
    copyLegacyFiles(base);
    return QDir::toNativeSeparators(QDir(base.filePath("hedit")).filePath("tabs.json"));
}

}  // namespace hedit
