最新追加版は[LATEST.md](LATEST.md)を参照。以下は初期公開版の手順です。

# 再現と作図

## 実データ

環境・入力をそろえた後、リポジトリルートで次を実行します。

```bash
python scripts/run_analysis.py --check
python scripts/run_analysis.py
```

結果は`output/wind_ree_reconciliation_v6/`。`run_provenance.json`にAIM等の指定版、分析コミット、未コミット変更の有無、入力ハッシュを記録します。コミット番号は実際の入力を生成した版を記載し、単に今インストールしている最新版を書かないでください。

作図例（モデル版ラベルは実際の入力に合わせて置き換える）：

```bash
python scripts/plot_results.py --input output/wind_ree_reconciliation_v6/all_sectors_CONDITIONAL.csv.gz --statistic average --grid-case SPS --case HEV_sedan_MG2010_WangNiMH_DOE2011_AB5_transfer --model-version ACTUAL_INPUT_VERSION --out figures/cumulative_reference
```

このHEV条件が唯一の推奨・確定値という意味ではありません。表示するシナリオを明示するための使用例です。図のPNG/PDFと一緒に、`.json`を研究記録へ保存してください。

## 追跡する版

- 分析用リポジトリのコミットSHA（未コミット変更がある場合はその差分も）
- AIM本体・core・共通データの各コミットSHA
- AIM出力IDと、読み込んだファイルのハッシュ
- 原単位・技術シェア・基準年供給表の出典・版
- コマンド、条件、作成日

GitHubのコミットに固定したリンクは`https://github.com/OWNER/REPOSITORY/tree/COMMIT_SHA`。ゼミ資料では変化するmainブランチのURLに加え、この固定リンクを載せると追跡しやすくなります。

公開していない入力を持たない人は、人工データでプログラムの動作を確認できますが、研究の数値結果を完全には再現できません。この区別を明記してください。
