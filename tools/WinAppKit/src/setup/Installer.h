/**
 * @file Installer.h
 * @brief アプリのインストール・更新・アンインストールの本体(画面は持たない)。
 *
 * インストールは、このユーザーだけ(HKEY_CURRENT_USER と %LOCALAPPDATA%)に行うので、管理者権限は要らない。
 * 作ったファイル・フォルダ・レジストリはすべて、インストール先の「uninstall.wak」に記録する。
 * アンインストールは、この記録を逆順にたどって、記録したものだけを消す(フォルダごと消すことはしない。
 * フォルダは空になったときだけ消す)。ほかのアプリと共有する場所(拡張子の OpenWithProgids など)は、
 * 自分が足した値だけを消す。
 */
#pragma once

#include "setup/Manifest.h"
#include "setup/Package.h"

#include <functional>
#include <string>
#include <vector>

namespace wak {

/** @brief インストールの指定。 */
struct InstallOptions {
    std::wstring installDir;  ///< インストール先(正規の形)。
    bool fileTypes = true;    ///< 関連付け(右クリック・「プログラムから開く」・既定のアプリの候補)を登録するか。
};

/** @brief 既にインストールされている同じアプリの情報。 */
struct ExistingInstall {
    bool found = false;     ///< 見つかったか。
    std::wstring dir;       ///< インストール先。
    std::wstring version;   ///< バージョン。
};

/** @brief 進み具合を知らせる関数。引数は 0〜100 の割合と、今の作業の説明。 */
using ProgressCallback = std::function<void(int percent, const std::wstring& step)>;

/**
 * @brief 既定のインストール先を返す。
 * @param manifest アプリの説明。
 * @return インストール先(正規の形)。
 */
std::wstring defaultInstallDir(const Manifest& manifest);

/**
 * @brief 同じアプリが既にインストールされているかを調べる(「アプリ」一覧の登録と、記録のファイルで確かめる)。
 * @param id アプリの識別名。
 * @return 見つかった情報。
 */
ExistingInstall findExistingInstall(const std::wstring& id);

/**
 * @brief インストール先として安全かを確かめる。
 * @param dir インストール先(正規の形)。
 * @param error 安全でない理由の格納先。
 * @return 安全ならtrue。ドライブの直下・Windowsやユーザーの大事なフォルダ(とその親)・ほかのファイルが入った
 *         フォルダ(このインストーラーの記録が無いもの)は拒否する。
 */
bool checkInstallDir(const std::wstring& dir, std::wstring& error);

/**
 * @brief ファイルを使っている(起動中の)アプリの名前を返す。Windows標準のRestart Managerで調べる。
 * @param files 調べるファイル(あるものだけ渡す)。
 * @return アプリの名前。使われていなければ空。
 */
std::vector<std::wstring> findRunningApps(const std::vector<std::wstring>& files);

/**
 * @brief ファイルを使っているアプリを閉じる(応じなければ終了させる)。
 * @param files 対象のファイル。
 * @return 閉じられたらtrue。
 */
bool closeRunningApps(const std::vector<std::wstring>& files);

/**
 * @brief インストールに関わる、既にあるファイル(起動中か調べる対象)を返す。
 * @param manifest アプリの説明。
 * @param installDir インストール先。
 * @return パス。
 */
std::vector<std::wstring> installedFiles(const Manifest& manifest, const std::wstring& installDir);

/**
 * @brief インストールする(同じアプリがあれば上書きして更新する)。
 * @param manifest アプリの説明。
 * @param files 中身(manifest.filesと同じ順)。
 * @param options 指定。
 * @param progress 進み具合を知らせる関数(空でもよい)。
 * @param error 失敗した理由の格納先。
 * @return 成功ならtrue。失敗したときは、置き換えたファイルを戻し、新しく作ったものを消す。
 * @note 自分自身(セットアップのexe)を、インストール先へ「Uninstall.exe」として写す(「アプリ」一覧から
 *       アンインストールするときに使う)。
 */
bool install(const Manifest& manifest, const std::vector<PackageFile>& files, const InstallOptions& options,
             const ProgressCallback& progress, std::wstring& error);

/** @brief 記録から読んだ、インストール済みのアプリの情報(アンインストールの画面用)。 */
struct RecordInfo {
    std::wstring id;          ///< 識別名。
    std::wstring name;        ///< 表示名。
    std::wstring version;     ///< バージョン。
    std::wstring executable;  ///< 本体のexe(インストール先からの相対パス)。
    bool hasUserData = false; ///< 「データも削除」で消すものがあるか。
};

/**
 * @brief インストール先の記録から、アプリの情報を読む。
 * @param installDir インストール先。
 * @param info 情報の格納先。
 * @return 記録があり読めたらtrue。
 */
bool readRecordInfo(const std::wstring& installDir, RecordInfo& info);

/**
 * @brief アンインストールする(記録したものだけを消す)。
 * @param installDir インストール先。
 * @param removeUserData 設定などのデータ(設定ファイルの [UserData])も消すか。
 * @param error 失敗した理由の格納先。
 * @return 記録を読めて、消し終えたらtrue(消せなかったものがあっても続け、記録に書く)。
 */
bool uninstall(const std::wstring& installDir, bool removeUserData, std::wstring& error);

}  // namespace wak
