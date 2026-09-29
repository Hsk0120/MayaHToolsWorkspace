/** @file session_data.cpp
 * @brief tabs.jsonとSessionDataの変換。
 */
#include "core/session_data.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

namespace hedit {
namespace {

/// tabs.jsonの形式の版。形を変えるときは上げ、古い版の読み込みを考える。
constexpr int kSessionFormatVersion = 1;

}  // namespace

QByteArray sessionToJson(const SessionData& data) {
    QJsonArray tabs;
    for (const TabState& tab : data.tabs) {
        tabs.append(QJsonObject{
            {"text", tab.text},
            {"path", tab.path},
            {"language", tab.language},
            {"modified", tab.modified},
            {"position", tab.position},
            {"anchor", tab.anchor},
        });
    }
    const QJsonObject root{
        {"version", kSessionFormatVersion},
        {"active", data.activeTab},
        {"tabs", tabs},
        {"folders", QJsonArray::fromStringList(data.folders)},
        {"explorerVisible", data.explorerVisible},
    };
    return QJsonDocument(root).toJson();
}

bool sessionFromJson(const QByteArray& bytes, SessionData* data) {
    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(bytes, &error);
    if (error.error != QJsonParseError::NoError) {
        return false;
    }
    const QJsonObject root = document.object();
    const QJsonArray entries = root.value("tabs").toArray();
    if (root.value("version").toInt() != kSessionFormatVersion || entries.isEmpty()) {
        return false;
    }

    SessionData result;
    for (const QJsonValue& entry : entries) {
        const QJsonObject object = entry.toObject();
        // 必須の項目の型が違えば、壊れたファイルとして全体を読まない(元のファイルは残す)。
        const bool valid = object.value("text").isString() && object.value("path").isString()
                           && object.value("modified").isBool();
        if (!valid) {
            return false;
        }
        TabState tab;
        tab.text = object.value("text").toString();
        tab.path = object.value("path").toString();
        tab.language = object.value("language").toString("python");
        tab.modified = object.value("modified").toBool();
        tab.position = object.value("position").toInt();
        tab.anchor = object.value("anchor").toInt();
        result.tabs.append(tab);
    }
    for (const QJsonValue& folder : root.value("folders").toArray()) {
        if (folder.isString()) {
            result.folders.append(folder.toString());
        }
    }
    result.explorerVisible = root.value("explorerVisible").toBool();
    result.activeTab = root.value("active").toInt();
    *data = result;
    return true;
}

}  // namespace hedit
