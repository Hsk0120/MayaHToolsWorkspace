/** @file user_paths.cpp
 * @brief Maya Code Editorのファイルを置く場所の決定。
 */
#include "plugin/user_paths.h"
#include "plugin/mel.h"
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>

namespace mce {
namespace {

/** @brief 旧名(hedit)の保存先から、未保存のタブ・設定・開閉状態を写す(新しい保存先がまだ無いときだけ)。
 * @param prefs Mayaのユーザー設定フォルダー。
 * @param folder 新しい保存先。
 * @details 0.7.0でhedit → Maya Code Editorへ改名した。旧フォルダーは消さずに残す(前の版へ戻しても使えるように)。
 * 写すのは1回だけ(新しいフォルダーができた後は何もしない)。
 */
void copyLegacyFolder(const QString& prefs, const QString& folder) {
    const QString legacy = QDir::cleanPath(prefs + "/hedit");
    if (QFileInfo::exists(folder) || !QFileInfo(legacy).isDir()) {
        return;
    }
    QDir legacyDir(legacy);
    QDirIterator it(legacy, QDir::Files | QDir::Hidden | QDir::NoDotAndDotDot, QDirIterator::Subdirectories);
    while (it.hasNext()) {
        const QString source = it.next();
        const QString target = QDir(folder).filePath(legacyDir.relativeFilePath(source));
        QDir().mkpath(QFileInfo(target).absolutePath());
        QFile::copy(source, target);
    }
}

}  // namespace

QString userFolder() {
    // 関数の中のstatic変数は、最初に呼ばれたときに1回だけ初期化される。Mayaの起動中は変わらない値なので覚えておく。
    static const QString folder = [] {
        const QString prefs = mel("internalVar -userPrefDir");
        if (prefs.isEmpty()) {
            return QString();
        }
        const QString path = QDir::cleanPath(prefs + "/MayaCodeEditor");
        copyLegacyFolder(prefs, path);
        return path;
    }();
    return folder;
}

QString sessionFilePath() {
    // 環境変数は毎回読む(テストが途中で変えることがあるため)。読むのは軽い処理。
    const QString override = qEnvironmentVariable("MCE_SESSION_FILE");
    if (!override.isEmpty()) {
        return override;
    }
    return QDir::toNativeSeparators(QDir(userFolder()).filePath("tabs.json"));
}

}  // namespace mce
