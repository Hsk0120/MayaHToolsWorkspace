---
applyTo: "maya/inhouse/mlib/**"
---

# mlib を編集するときの指示

- `maya/inhouse/mlib` は別リポジトリ `Hsk0120/mlib` の submodule。コードを書くときのルールの正本は `maya/inhouse/mlib/.github/copilot-instructions.md` なので、編集前に必ず読んで従う。
- mlib のコード・docstring・文書・テストに、HTools・mlrig・このワークスペースの情報(パス・ツール名・作業ログ)を書かない。
- 設計の検討・経緯は `docs/mlib-api-design.md`(ワークスペース側)に書き、mlib のリポジトリへは入れない。
- 版番号は mlib の `_version.py` だけに書く。
- 変更は mlib のリポジトリでコミット・push してから、ワークスペースで submodule の参照を更新する。
