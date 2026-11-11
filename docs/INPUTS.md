最新追加版の入力は`config/latest_stages.json`および[LATEST.md](LATEST.md)を参照。以下は初期公開版の入力仕様です。

# 入力仕様

実データは各自で用意します。下記は現在の統合入口が必要とするパスです。`run_analysis.py --check`はファイル存在と一意性を確認し、数値・単位・収支は計算側で検証します。

| パス | 内容 |
|---|---|
| `input/AIM_World.csv.gz` | WorldのIAMC出力。`Sc,Sr,Sv,Y5,value`。両シナリオ、GDP_PPP、Fin_Ene_Ele、技術別容量・新設量等を使用 |
| `input/units_and_time_basis.csv` | `variable,declared_unit,time_basis,definition_found`。GW/yrと期間平均の確認表 |
| `input/imported/wei_intensity_rows.csv` | Wei原単位の転記表。`category,technology,material,reported_average,reported_minimum`等 |
| `input/imported/wei_S11_Market_share.csv` | Wei技術シェアの転記表 |
| `input/imported/penelope_Demand_Network.csv` | Cu/AlのIEA系統需要アンカー。`Scenario,mineral,Unit`と年列 |
| `input/imported/penelope_Metal_Intensity_Reduction.csv` | その他部門の金属原単位変化。2030/2040/2050年列 |
| `input/energy_unit_check/energy_drivers_Baseline.csv`・`energy_drivers_300C.csv` | native設備量・新設率・更新率。`Sc,region,sector,technology,year,stock_native,new_rate_native,replacement_rate_native,model_time_interval,lifetime_tn_years,stock_inflow_over_interval_native` |
| `output/native_vehicle_demand_two_scenarios/alternative_HEV_combined_partial_demand.csv` | 準備済み車両需要表。`Sc,year,mineral,case,known_partial_vehicle_demand_t_year,any_reported_coefficient_in_selected_inventory` |
| `output/reconciled40_CONDITIONAL/baseline_40_CONDITIONAL.csv` | 準備済み基準年供給表。`Sc,statistic,grid_case,mineral,supply_low_t_year,supply_high_t_year`等 |
| `output/solar_overlap_v5/baseline2020_recalibration.csv` | 変更前後比較用の基準年収支表 |
| `output/solar_overlap_v5/explicit_sector_annual.csv` | 変更前後比較用のエネルギー設備需要表 |
| `originals/Pelotte*/Data/PowerCap_MI_MS_CF.xlsx` | 自分で取得したPenelope方式別原単位ブック。`MI`シート |
| `originals/Pelotte*/Data/Market Share in time - Disag.xlsx` | 同、技術構成ブック。`2020`シート |

`output/`の一部が入力になっているのは、現在の統合処理が先行する準備工程の成果を読むためです。これらの中間表も公開しません。新しいAIM実行へ切り替える際は、AIM依存の中間表を新出力から再生成して版をそろえてください。新しいAIM CSVと古い車両表を混ぜるだけでは、最新版の再現にはなりません。

太陽光DC/ACの追加比較には`originals/winsol_symbols.txt`等が必要です。本文のv6統合入口では使わない補助資料なので、上の必須一覧には含めていません。
