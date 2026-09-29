/** @file user_paths.cpp
 * @brief heditのファイルを置く場所の決定。
 */
#include "plugin/user_paths.h"
#include "plugin/mel.h"
#include <QDir>

namespace hedit {

QString userFolder() {
    // 関数の中のstatic変数は、最初に呼ばれたときに1回だけ初期化される。Mayaの起動中は変わらない値なので覚えておく。
    static const QString folder = [] {
        const QString prefs = mel("internalVar -userPrefDir");
        return prefs.isEmpty() ? QString() : QDir::cleanPath(prefs + "/hedit");
    }();
    return folder;
}

QString sessionFilePath() {
    // 環境変数は毎回読む(テストが途中で変えることがあるため)。読むのは軽い処理。
    const QString override = qEnvironmentVariable("HEDIT_SESSION_FILE");
    if (!override.isEmpty()) {
        return override;
    }
    return QDir::toNativeSeparators(QDir(userFolder()).filePath("tabs.json"));
}

}  // namespace hedit
