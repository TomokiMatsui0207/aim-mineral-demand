# 最新版コードの収録範囲（2026-11-11）

公開版に分析時点のソース35ファイルを追加した。初期版analysis直下は履歴として保持。
最新スナップショットはanalysis/latest/。絶対パスをこのフォルダに相対化したほか、鉱物名対応に集計結果CSVを要求する依存を公開の名称辞書へ置き換えた。計算式・係数は変更していない。
SNAPSHOT.jsonに元ソースと公開ソースのSHA256、変更内容を記録。

## 収録した工程

|stage|内容|
|---|---|
|updated|更新版AIMのnative/IAMCを使う再集計と旧新比較|
|vehicle-components|HEV・FCVの部品別既知原単位と重複排除|
|road-units|単位定義、VR+VPと期間、新設台数への変換|
|vehicles|乗用車・バス・小型/大型貨物車のケース別統合と基準年残余の再校正|
|reserves|世界参照33・条件付き7を区別した40枠の台帳作成|
|substitution2100|2026–2100年の部分的代替技術最適化|
|constraints2050|累積資源量と2030/2040/2050年生産能力の制約。PV拡張前の比較版|
|pv-revision|PV方式全体の転換、IEA蓄電置換、2021年からの遡及比較|
|export40|車両A–Fと2100年最適化をまとめる集計版。直近PV比較は別出力|

全工程が生のGDXから一括生成できる完全パイプラインではない。各工程は先行工程の中間表・外部の原単位表を必要とする。必要な準備済み入力の一覧はconfig/latest_stages.json、実装は各entryのファイルを参照。

## 実行方法

Python3.10以上。requirements.txtをインストールする。入力の配置起点はanalysis/latest/。
ここに各自が取得・準備した非公開データを、config/latest_stages.jsonのrequiredに記載の相対パスで配置する。出力もこのスナップショット以下に作成される。公開用GitHubには含めない。

```bash
python scripts/run_latest.py --list
python scripts/run_latest.py --stage vehicles --check
python scripts/run_latest.py --stage pv-revision --check
```

--checkは列挙されたファイルの存在・一意性を調べる。設定JSONがさらに参照する資料や、履歴比較用の中間表まで完全に検証する機能ではない。計算の数値正当性や原典照合の完了も意味しない。
実行時はconfig/run_metadata.example.jsonをconfig/run_metadata.local.jsonにコピーして、実際の入力を生成したAIM/core/dataのcommitとsource_output_idを記入する。古い入力を新しい実行IDと混在させない。

```bash
python scripts/run_latest.py --stage vehicles
python scripts/run_latest.py --stage pv-revision --case pv_only
python scripts/run_latest.py --stage pv-revision --case pv_plus_IEA_storage
python scripts/run_latest.py --stage pv-revision --case pv_plus_IEA_storage_retrospective2021
```

直近PV比較の3ケース：

- pv_only：AIM/WeiのLi-ion蓄電を保持し、PV方式選択を拡張。
- pv_plus_IEA_storage：蓄電部門をIEA既知8元素の需要へ全置換。Baseline=SPS、300C=APSは比較上の仮定。Vだけを加算せず、2020残余を再校正する。AIM容量からVRFB需要を確定したものではない。他材料は未収録の既知小計。
- pv_plus_IEA_storage_retrospective2021：2021年から選択を許す反実仮想。2020–2025固定の主比較と区別。過去に戻って実行できる政策ではない。

実行したコードのGit commit、変更の有無、入力読み込み時のSHA256、メタデータ、コマンドをlocal_run/latest/のJSONに記録する。同フォルダは非公開。元工程が読む中間表も入力としてハッシュを残す。

## 非公開のまま必要なもの

AIM生出力、全原単位/技術シェア表、truck_reference.json等の転記表、HEV/NiMH/FCV設定と原資料、Pénélopeの元ExcelとFuture_Productionを抽出する元コード、既存の基準年台帳、準備済み中間CSV。コードだけを取得しても実データの結果は完全再現できない。
埋蔵量の採用数値台帳と研究結果のExcel/CSV/図も、この更新では公開しない。

## 検証と限界

公開環境では構文・パス・入力不足時の停止・初期版の基本処理テストを実行。別途、手元の非公開入力を同じ相対位置に用意してPV比較の再計算を照合する。
未収録材料を使用量ゼロと断定しない。40枠の条件付き需要・供給参照を全40鉱物の確定需要・世界埋蔵量と呼ばない。
2050最適化は元研究と同一の目的・技術選択・供給データ版を完全再現していない。供給制約の超過数は確定不足数ではない。
