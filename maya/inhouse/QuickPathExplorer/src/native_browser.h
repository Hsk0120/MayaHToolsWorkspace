/** @file native_browser.h
 * @brief QPE専用の一覧表示・可視アイコン取得。Mayaの他UIへは登録しない。
 */
#pragma once
#include <QObject>
#include <QString>
#include <QIcon>
class QWidget;
namespace qpe {
/** @brief 実ディスクを照会せずWindowsの標準フォルダー絵柄を共有する。 @return フォルダーアイコン。 */
QIcon nativeFolderIcon();
/** @brief Qt親所有の高速部品を作る。
 * @param kind proxy、delegate、iconsのいずれか。
 * @param parent QPEが所有するウィジェット。
 * @return 作成した部品。不明な種類はnullptr。
 */
QObject* createNative(const QString& kind, QWidget* parent);
/** @brief 全部品の破棄を確認する。生存中はDLLのアンロードを拒否する。
 * @return 破棄済みか。
 */
bool nativeObjectsReleased();
}
