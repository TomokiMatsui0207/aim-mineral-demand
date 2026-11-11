# AIM mineral demand analysis

Repository: https://github.com/TomokiMatsui0207/aim-mineral-demand

AIM-Technologyの出力を用いて、2020–2100年・40鉱物の条件付き需要を集計・作図する研究用コードです。発電、水素製造、定置蓄電池、車両、送配電網、その他経済部門を対象とします。

**AIM本体・モデル出力・文献原本・実測入力データは同梱していません。** 公開対象は分析コード、作図コード、入力仕様、再現手順と人工データのデモです。コードが公開されていることと、実データが公開されていることは別です。

## 最新追加版（2026-11-11）

更新版AIMへの対応、HEV/FCV・バス・貨物車、埋蔵量台帳の作成処理、2050年制約最適化、PV方式・IEA蓄電比較のコードを`analysis/latest/`に追加しました。[収録範囲と実行手順](docs/LATEST.md)を参照してください。

```bash
python scripts/run_latest.py --list
python scripts/run_latest.py --stage pv-revision --check
```

初期版の`run_analysis.py`は保持しています。最新工程には`run_latest.py`を使用してください。
実データ・中間表・研究結果は同梱せず、コードのみでは最新数値の完全再現はできません。

## 初期公開版の位置付け

- 統合処理は`reconcile_wind_ree_v6`の参照ケースを収録しています。
- 元の解析はAIM更新前の出力で検討したもので、更新版AIMの再計算結果による検証は未完了です。最新モデルの計算が終わっただけで、このコードの入力が自動更新されることはありません。
- 全40鉱物の物理的需要を完全に同定したモデルではありません。未収録部材・物質範囲・供給基準等の仮定を含みます。
- 現在の実データ用入口は、準備済みの車両需要・基準年供給等の中間表を入力とします。生のGDXから全入力を生成する工程は、この公開版では一体化していません。

## データなしで動作を確認する

Python 3.10以上を使用してください。実行例はリポジトリのルートから入力します。

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShellの場合: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/demo.py
python scripts/plot_results.py --input output/demo/synthetic_results.csv --grid-case SYNTHETIC --case SYNTHETIC --model-version SYNTHETIC --out figures/demo
```

`figures/demo.png`・`demo.pdf`と作図情報`demo.json`を作成します。**人工データのデモであり、研究結果ではありません。** 出力はGit管理対象外です。

## 実データを使う

1. [入力仕様](docs/INPUTS.md)に従って、各自で取得したデータ・準備済み中間表を配置します。
2. `config/run_metadata.example.json`を`config/run_metadata.local.json`へコピーし、入力を実際に生成したAIM・core・データのコミット番号と出力IDを記録します。
3. `python scripts/run_analysis.py --check`で不足入力を確認します。
4. `python scripts/run_analysis.py`で統合集計を再実行します。
5. [再現手順](docs/REPRODUCIBILITY.md)に従い、表示する条件を指定して作図します。

`analysis/`には履歴処理の依存モジュールも含みます。各モジュールの古い実行入口を順不同で実行せず、通常は`run_analysis.py`を使用します。掲載した過去版比較の関数には、別途その履歴出力が必要です。

## 方法上の主な仮定

- 製造需要は原則として新設量に原単位を掛けます。容量ストックの出力点和を新設需要とはみなしません。
- 蓄電池はAIMの放電時間設定12hに合わせた等価容量の参照条件です。実際のパックの実測容量を確定した意味ではありません。
- 風力のDy・Tb・Nd・Prには、Penelope資料の方式別原単位と2020年容量構成を使用するケースを収録。ストック構成を新設構成へ移転し、2100年まで固定する仮定があります。
- 太陽光は鉱物別に共通PVと種類別の重複を整理。DC/AC基準と一部部品範囲は未確定です。
- 欠損を物理的な使用量ゼロとは解釈しません。表示する既知小計と完全需要は区別してください。
- その他部門は基準年の供給−明示需要の残余から推計します。原単位を変えたときは残余も再校正します。

## ゼミ資料での記載

[記載用テンプレート](docs/SEMINAR_TEMPLATE.md)を使用してください。リポジトリURL、分析コードのコミット番号、AIM等の版、入力出力ID、図のコマンドと条件を記載します。作図時のJSONにも解析版・入力ハッシュ・条件を保存します。

## 公開範囲・出典

`.gitignore`で入力・モデル出力・文献ファイル・ローカル設定を除外しています。これは未追跡ファイルの誤追加を防ぐ設定で、既にコミットしたファイルや履歴を消す機能ではありません。

参考資料と取得先は[出典](docs/SOURCES.md)、公開版への整理内容は[ソース対応表](docs/source_manifest.json)を参照してください。第三者の元プログラム・論文・補足データは再配布していません。参考にしたPenelopeプログラムのBSD-3-Clause通知を`third_party/`に保持します。

本プロジェクト独自部分のライセンスは未選択です。公開と再利用の許諾条件は別なので、研究室の方針に従って決定してください。
