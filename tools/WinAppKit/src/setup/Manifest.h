/**
 * @file Manifest.h
 * @brief インストールするアプリの説明(アプリ名・ファイル・関連付けなど)を、INI形式の設定ファイルから読む。
 *
 * 設定ファイルの例(詳しくは tools/WinAppKit/README.md):
 * @code
 * [App]
 * Id=FramePlayer
 * Name=FramePlayer
 * Publisher=...
 * Executable=FramePlayer.exe
 * InstallDir={LocalPrograms}\FramePlayer
 * StartMenuShortcut=yes
 * SetupIcon=../resources/icon/FramePlayer.ico
 *
 * [Files]
 * ../FramePlayer.exe=FramePlayer.exe
 *
 * [FileTypes]
 * ProgId=FramePlayer.Video
 * Description=動画 (FramePlayer)
 * Extensions=.mp4;.mov
 * ContextMenu=FramePlayerで開く
 *
 * [UserData]
 * Registry=HKCU\Software\FramePlayer
 * Folder={LocalAppData}\FramePlayer
 * @endcode
 */
#pragma once

#include <string>
#include <vector>

namespace wak {

/** @brief インストールする1つのファイル。 */
struct FileEntry {
    std::wstring source;  ///< 元のファイル(設定ファイルのフォルダからの相対パス)。作るときだけ使う。
    std::wstring target;  ///< インストール先のフォルダからの相対パス。
};

/** @brief インストールするアプリの説明。 */
struct Manifest {
    std::wstring id;           ///< 識別名(英数字と . _ -)。「アプリ」一覧の登録名・記録の名前に使う。
    std::wstring name;         ///< 表示名。
    std::wstring version;      ///< バージョン(空なら、作るときに本体のexeのバージョン情報から読む)。
    std::wstring publisher;    ///< 発行元。
    std::wstring description;  ///< 説明(関連付けの画面などに出る)。
    std::wstring url;          ///< ホームページ(「アプリ」一覧のサポート情報)。
    std::wstring executable;   ///< 本体のexe(インストール先からの相対パス)。
    std::wstring installDir;   ///< 既定のインストール先(置き換え文字を含む)。
    bool startMenuShortcut = true;  ///< スタートメニューにショートカットを作るか。
    std::wstring setupIcon;    ///< セットアップのexeに付けるアイコン(.ico、設定ファイルからの相対パス)。作るときだけ使う。
    std::vector<FileEntry> files;  ///< インストールするファイル。

    // 関連付け(ProgIdが空なら行わない)。
    std::wstring progId;                   ///< 関連付けの名前(例: FramePlayer.Video)。
    std::wstring typeDescription;          ///< ファイルの種類の表示名。
    std::vector<std::wstring> extensions;  ///< 拡張子(「.mp4」の形)。
    std::wstring contextMenu;              ///< 右クリックに出す文字(空なら右クリックには出さない)。
    bool fileTypesOptional = true;         ///< インストール時に関連付けをしないことも選べるか。

    std::vector<std::wstring> userDataRegistry;  ///< アンインストールで「データも削除」を選んだときに消すレジストリ。
    std::vector<std::wstring> userDataFolders;   ///< 同じく消すフォルダ(置き換え文字を含む)。

    /**
     * @brief INI形式の文字列から読む。
     * @param text 設定ファイルの中身。
     * @param manifest 読んだ結果の格納先。
     * @param error 読めなかった理由の格納先。
     * @return 必要な項目がそろい、正しい形ならtrue。
     */
    static bool parse(const std::wstring& text, Manifest& manifest, std::wstring& error);

    /**
     * @brief インストールに必要な項目だけを、INI形式の文字列にする(セットアップのexeに埋め込む用)。
     * @return INI形式の文字列。parse()で読み戻せる。
     */
    std::wstring serialize() const;
};

/**
 * @brief パスの置き換え文字を、このユーザーの実際のフォルダにする。
 * @param text 置き換え文字を含むパス。{LocalAppData} {AppData} {LocalPrograms}(=LocalAppData\Programs)
 *             {InstallDir} を置き換える。
 * @param installDir {InstallDir} に入れるパス。
 * @return 置き換えたパス。
 */
std::wstring expandPath(const std::wstring& text, const std::wstring& installDir);

}  // namespace wak
