# GitHubへ公開する手順

## 別リポジトリを使う

AIMEnduseやAIMTechnology_coreの既存フォークをPublicへ変更せず、分析・作図用の新しい`aim-mineral-demand`を作成する。モデル本体の公開権限と分析コードの公開は分けて扱う。

## 新規作成画面

1. GitHubへログインし、右上`+`→`New repository`。
2. Repository name：`aim-mineral-demand`。
3. Description：`Critical mineral demand analysis and plotting for AIM-Technology outputs`。
4. Visibility：`Public`。
5. この準備済み一式にREADME・.gitignoreがあるため、GitHub側の初期ファイル追加は選ばない。
6. `Create repository`。表示されたリポジトリURLを作業記録とゼミ資料へ記載する。

## 初回アップロード前に確認する対象

このフォルダはコード専用の新規履歴。`input/`、`originals/`、`output/`、`figures/`、モデルのGDX・Excel原本を入れない。`git status --short`と`git diff --cached --stat`で実際の追加対象を確認する。既存AIMフォルダで`git add .`を実行する手順ではない。

リモートへpushする操作は、URLを確定し、公開する内容を確認してから行う。入力データは公開用リポジトリと別に管理する。

## ゼミ資料

mainブランチのURLに加えて、使用したコミットに固定したURLを載せる。資料の図にはモデル出力ID・AIM各リポジトリのコミット・条件・作図コマンドも記載する。公開リポジトリが作成されていない間は、URLを推測して実在する公開先として記載しない。

ライセンスは研究室の方針に沿って選択する。未選択でも閲覧はできるが、自由な再利用の許諾が付くわけではない。
