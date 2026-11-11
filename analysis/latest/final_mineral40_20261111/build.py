"""As-of collection of conditional all-sector demand and reserve references.
No new model result is invented; period/accounting differences stay explicit.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import hashlib, json, shutil
import numpy as np
import pandas as pd
O = Path(__file__).resolve().parent
R = Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'mineral2100'))
V = Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'vehicle_allsector_extension_20261111'))
T = Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'technology_substitution_20261111'))
MINERALS = 'Ag Al B C Cd Ce Co Cr Cu Dy Fe Ga Ge Hf In Ir La Li Mg Mn Mo Nb Nd Ni Pb Pr Pt Sc Se Si Sn Ta Tb Te Ti V W Y Zn Zr'.split()
key = ['Sc', 'case_id', 'mineral', 'year']
sector = ['power_t_year', 'stationary_battery_t_year', 'hydrogen_t_year', 'grid_t_year', 'vehicles_t_year', 'other_low_t_year']
refs = pd.read_csv(R / 'reserve40_complete_20261111/40鉱物_埋蔵量と推計参照値.csv')
assert len(refs) == 40 and set(refs.mineral) == set(MINERALS)
refs['unit'] = 't element reference; scope qualified'
refs['constraint_group'] = np.where(refs.extended_assumption, '条件付き7・最適化制約には未使用', '世界参照33・条件付き最適化に使用')
base = pd.read_csv(V / 'all_sectors_extended_CONDITIONAL.csv.gz')
frames = []
cases = []
for case, g in base.groupby('case', sort=False):
    a = g[['Sc', 'mineral', 'year', 'power', 'stationary_battery', 'hydrogen', 'grid_CuAl_t_year', 'vehicles_explicit_t_year', 'other_low_t_year', 'other_high_t_year', 'conditional_total_low_t_year', 'conditional_total_high_t_year']].rename(columns={'power': 'power_t_year', 'stationary_battery': 'stationary_battery_t_year', 'hydrogen': 'hydrogen_t_year', 'grid_CuAl_t_year': 'grid_t_year', 'vehicles_explicit_t_year': 'vehicles_t_year', 'conditional_total_low_t_year': 'total_low_t_year', 'conditional_total_high_t_year': 'total_high_t_year'}).copy()
    a['case_id'] = case
    a['case_group'] = '車両拡張・非最適化'
    a['reference_vehicle_case'] = case
    frames.append(a)
    cases.append(dict(case_id=case, case_group='車両拡張・非最適化', meaning={'A_day_NMC622_known_subtotal': '代表A：地域配送Class8、NMC622、既知部品小計', 'B_day_NMC622_mixed_material_endpoints': 'B：AのCu/Brass・Graphite/Carbonを全量Cu/黒鉛とする端点', 'C_sleeper_NMC811_known_subtotal': 'C：長距離Class8、NMC811', 'D_day_NMC622_alternative_LDV_blocks': 'D：別HEV部品系列・SUV/FCV/Pt参照', 'E_Pt_power_and_FCV_auxiliary_transfer': 'E：A＋FCVのPt出力比例・補機電池配分転用', 'F_E_plus_steel_Fe_proxy': 'F：E＋一部鋼材Fe代理換算。代替最適化の入力ケース'}[case], optimization_horizon='なし'))
alt = pd.read_csv(T / 'all_sectors_with_substitution_CONDITIONAL.csv.gz')
for solution, pol, cid, meaning in [('reference', 'allow_Na_after2035', 'TECH_reference_F', '代替候補と同源の未最適化基準。前回Fとの原単位変更効果を含む。'), ('optimized', 'allow_Na_after2035', 'TECH_optimized_Na_allowed', '代替最適化：2035年以降Na-ion追加可'), ('optimized', 'no_additional_Na', 'TECH_optimized_no_extra_Na', '代替最適化：既定混合以外のNa-ion追加なし')]:
    g = alt[alt.solution.eq(solution) & alt.policy.eq(pol)].copy()
    a = g[['Sc', 'mineral', 'year', 'alternative_power_t_year', 'alternative_stationary_battery_t_year', 'alternative_hydrogen_t_year', 'alternative_grid_t_year', 'alternative_vehicles_t_year', 'other_low_t_year', 'other_high_t_year', 'alternative_total_low_t_year', 'alternative_total_high_t_year']].rename(columns={c: c.replace('alternative_', '') for c in g.columns if c.startswith('alternative_')}).copy()
    a['case_id'] = cid
    a['case_group'] = '代替技術参照' if solution == 'reference' else '代替技術最適化'
    a['reference_vehicle_case'] = 'F_E_plus_steel_Fe_proxy'
    frames.append(a)
    cases.append(dict(case_id=cid, case_group=a.case_group.iloc[0], meaning=meaning, optimization_horizon='2026–2100。2050値はこの解の途中切出しで2050再最適化ではない'))
annual = pd.concat(frames, ignore_index=True).sort_values(key).reset_index(drop=True)
annual['unit'] = 't/year'
annual['full40_observed_complete'] = False
assert len(annual) == 58320 and (not annual.duplicated(key).any())
assert annual.groupby(['Sc', 'case_id']).mineral.nunique().eq(40).all()
for _, g in annual.groupby(['Sc', 'case_id', 'mineral']):
    assert set(g.year) == set(range(2020, 2101))
np.testing.assert_allclose(annual[sector].sum(axis=1), annual.total_low_t_year, rtol=1e-10, atol=1e-05)
np.testing.assert_allclose(annual.total_high_t_year - annual.total_low_t_year, annual.other_high_t_year - annual.other_low_t_year, rtol=1e-09, atol=1e-05)
assert annual[['total_low_t_year', 'total_high_t_year']].notna().all().all()
annual.to_csv(O / '全部門_40鉱物_年次需要.csv.gz', index=False)
caseframe = pd.DataFrame(cases)
cums = []
metrics = sector + ['other_high_t_year', 'total_low_t_year', 'total_high_t_year']
for start, end in [(2020, 2050), (2020, 2100), (2026, 2050), (2026, 2100)]:
    a = annual[annual.year.between(start, end)].groupby(['Sc', 'case_id', 'case_group', 'mineral'], as_index=False)[metrics].sum(min_count=end - start + 1)
    a = a.rename(columns={c: c.replace('_t_year', '_cumulative_t') for c in metrics})
    a['start_year'] = start
    a['end_year'] = end
    a['year_count'] = end - start + 1
    a['unit'] = 't cumulative; annual discrete sum'
    a = a.merge(refs, on='mineral', validate='many_to_one', suffixes=('', '_reserve'))
    a['gross_reference_ratio_low'] = a.total_low_cumulative_t / a.comparison_reference_t_element
    a['gross_reference_ratio_high'] = a.total_high_cumulative_t / a.comparison_reference_t_element
    a['interpretation'] = '総含有量・材料代理の条件付き需要対参照量。一次採掘不足判定ではない'
    a['reoptimized_for_2050'] = False
    cums.append(a)
cumulative = pd.concat(cums, ignore_index=True)
assert len(cumulative) == 2880
cumulative.to_csv(O / '全部門_40鉱物_累積需要と埋蔵量参照比.csv', index=False)
refs.to_csv(O / '40鉱物_埋蔵量と条件付き参照値.csv', index=False)
wide = refs.copy()
for cid, short in [('A_day_NMC622_known_subtotal', '代表A'), ('F_E_plus_steel_Fe_proxy', '非最適化F'), ('TECH_reference_F', '同源参照'), ('TECH_optimized_Na_allowed', '最適化Na追加可'), ('TECH_optimized_no_extra_Na', '最適化Na追加なし')]:
    for end in [2050, 2100]:
        a = cumulative[cumulative.case_id.eq(cid) & cumulative.start_year.eq(2020) & cumulative.end_year.eq(end)][['Sc', 'mineral', 'total_low_cumulative_t', 'total_high_cumulative_t']].rename(columns={'total_low_cumulative_t': f'{short}_2020_{end}_low_t', 'total_high_cumulative_t': f'{short}_2020_{end}_high_t'})
        if 'Sc' not in wide:
            wide = wide.merge(a, on='mineral', validate='one_to_many')
        else:
            wide = wide.merge(a, on=['Sc', 'mineral'], validate='one_to_one')
assert len(wide) == 80
wide.to_csv(O / '40鉱物_主要結果一覧.csv', index=False)
name = dict(zip(MINERALS, ['Silver', 'Aluminum', 'Boron', 'Graphite', 'Cadmium', 'Cerium', 'Cobalt', 'Chromium', 'Copper', 'Dysprosium', 'Iron', 'Gallium', 'Germanium', 'Hafnium', 'Indium', 'Iridium', 'Lanthanum', 'Lithium', 'Magnesium', 'Manganese', 'Molybdenum', 'Niobium', 'Neodymium', 'Nickel', 'Lead', 'Praesodymium', 'Platinum', 'Scandium', 'Selenium', 'Silicon', 'Tin', 'Tantalum', 'Terbium', 'Tellurium', 'Titanium', 'Vanadium', 'Tungsten', 'Yttrium', 'Zinc', 'Zirconium']))
pen = next((R / 'originals').glob('Pelotte*/Data'))
scope = pd.read_excel(pen / 'Scope of the study.xlsx', sheet_name='metals', index_col=0).iloc[:, 0].tolist()
res = pd.read_excel(pen / 'Prod&Demand_Other_Sectors.xlsx', sheet_name='Reserves_Resources', index_col=0)
rr = pd.read_excel(pen / 'Prod&Demand_Other_Sectors.xlsx', sheet_name='Recovery_Rates', index_col=0)
common = []
for m, n in name.items():
    if n in scope:
        common.append(dict(mineral=m, Penelope_name=n, Penelope_Reserves_t=res.loc[n, 'Reserves'], Penelope_Resources_t=res.loc[n, 'Resources'], Penelope_RR_Reserve=rr.loc[n, 'RR_Reserve']))
common = pd.DataFrame(common)
assert len(common) == 32
common2050 = cumulative[cumulative.start_year.eq(2020) & cumulative.end_year.eq(2050)].merge(common, on='mineral', validate='many_to_one')
common2050['accounting_matched_to_Penelope'] = False
common2050['comparison_status'] = '2050年・共通32鉱物の参考集計のみ。回収/歩留まり/部門範囲未整合。Pénélopeの不足3種類との同会計比較は未完了。'
common2050.to_csv(O / '2050_共通32鉱物_参考集計_会計整合未完.csv', index=False)
notes = pd.DataFrame([('更新日', '2026-11-11。最新の条件付き集計。40鉱物すべての実測・完全確定値ではない。'), ('地域とシナリオ', '世界・Baseline/300C、2020–2100年。AIM更新実行2611091342。'), ('最初に見る表', '40鉱物主要一覧：代表A、非最適化F、代替候補同源reference、Na追加可/なしの最適化を横に比較。'), ('期間', '累積は2020–2050の31年、2020–2100の81年。参照比用に2026–2050/2100も収録。開始年を混同しない。'), ('全部門', '発電・定置蓄電池・水素製造・送配電網・車両・その他経済部門。エネルギーaverage、網SPS。'), ('原単位と欠損', '未収録材料は使用量0ではない。既知部品小計とGDP延長残余による条件付き総量。車体鋼種、FCV等の未確定部分が残る。'), ('埋蔵量', '33世界参照＋条件付き7。出典年・物質範囲が混在。7鉱物を世界確認埋蔵量と呼ばない。'), ('条件付き7', 'C、Ge、Hf、Mg、Sc、Ta、Si。天然黒鉛/合成黒鉛、特定国Sc/世界需要等の違いを確認。'), ('参照比', '総含有量・材料代理需要/埋蔵量参照。回収・加工・在庫の会計が未整合なので不足や充足の確定判定ではない。'), ('ケースA–F', '車両原単位・代表車種・混合材料の別ケース。合算禁止。FはPt転用・鋼材Fe代理を含む最適化入力。'), ('代替最適化', 'AIMの電源別導入量・車種別台数固定。候補原単位でそろえたreferenceからの変化が技術シフト効果。'), ('最適化の未実装', '年間採掘上限、回収控除、電源間転換、費用・普及速度等。Na全面採用などは実現予測ではない。'), ('2050比較の注意', '最適化の2050値は2100目的の解を途中で切り出したもの。2050再最適化・Pénélopeと同じ会計での再集計は未完了。'), ('会計', '本ファイルは元データをそのまま1/RR_Reserveした一次量ではない。その他部門の会計境界を揃えず一律換算しない。'), ('単位', '年次はt/年、累積はt。参照量は出典の元素量換算又は範囲限定の代理量。Al等には材料量代理が残る。'), ('再現性', '入力SHA256と集計スクリプトを同梱。元の計算結果は上書きしていない。')], columns=['項目', '説明'])
source = pd.DataFrame([('AIM出力', '更新実行2611091342', '今回の活動量。旧2608261554と区別'), ('Wei', 'https://doi.org/10.1038/s41558-025-02373-3', 'エネルギー原単位等の基礎。全原単位の物質範囲を再構築したわけではない'), ('Pénélope', 'https://doi.org/10.5281/zenodo.15319014', '配布モデル・原単位・送配電・その他部門の考え方'), ('貨物車', 'https://publications.anl.gov/anlpubs/2021/10/171707.pdf', '米国Class6/Class8からの代表設計転用'), ('バス', 'https://www.mdpi.com/2071-1050/17/21/9786', '12m都市型の参照。AIM世界車種構成と同一とは未確認'), ('方法の詳細', str(_SnapshotPath(__file__).resolve().parents[1] / 'method_comparison_20261111/教授説明用_方法の継承と変更.docx'), '継承・変更の理由')], columns=['資料', 'URL又は識別子', '適用範囲'])
book = O / '最新版_全部門40鉱物需要と埋蔵量_条件付き_20261111.xlsx'
with pd.ExcelWriter(book, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_urls': False}}) as w:
    notes.to_excel(w, sheet_name='00_最初に読む', index=False)
    wide.to_excel(w, sheet_name='01_40鉱物主要一覧', index=False)
    refs.to_excel(w, sheet_name='02_埋蔵量と条件付き参照', index=False)
    cumulative.to_excel(w, sheet_name='03_全部門累積と参照比', index=False)
    for sc in ['Baseline', '300C']:
        annual[annual.Sc.eq(sc)].to_excel(w, sheet_name='04_年次_' + sc, index=False)
    caseframe.to_excel(w, sheet_name='05_ケース定義', index=False)
    coverage = pd.read_csv(V / 'active_inventory_coverage.csv')
    coverage.to_excel(w, sheet_name='06_車両原単位不足', index=False)
    vc = base[['Sc', 'case', 'year', 'mineral', 'LDV', 'BUS', 'TRUCK_SMALL', 'TRUCK_LARGE', 'unknown_active_class_powertrain_count']]
    vc.to_excel(w, sheet_name='07_非最適化車両内訳', index=False)
    common2050.to_excel(w, sheet_name='08_2050共通_会計未整合', index=False)
    source.to_excel(w, sheet_name='09_資料と出典', index=False)
    pd.read_csv(T / 'solver_summary.csv').to_excel(w, sheet_name='10_代替最適化の求解', index=False)
    pd.read_csv(T / 'technology_shares_before_after.csv').to_excel(w, sheet_name='11_代替技術シェア', index=False)
    wrap = w.book.add_format({'text_wrap': True, 'valign': 'top'})
    num = w.book.add_format({'num_format': '#,##0.000000'})
    for n, ws in w.sheets.items():
        ws.freeze_panes(1, 3)
        ws.autofilter(0, 0, ws.dim_rowmax, ws.dim_colmax)
        ws.set_column(0, ws.dim_colmax, 19)
        if n in ['00_最初に読む', '05_ケース定義', '09_資料と出典']:
            ws.set_column(0, 0, 25)
            ws.set_column(1, ws.dim_colmax, 70, wrap)
        if n == '02_埋蔵量と条件付き参照':
            ws.set_column(4, 14, 45, wrap)
        if n.startswith('04_'):
            ws.set_column(4, 12, 21, num)
paths = [V / 'all_sectors_extended_CONDITIONAL.csv.gz', T / 'all_sectors_with_substitution_CONDITIONAL.csv.gz', R / 'reserve40_complete_20261111/40鉱物_埋蔵量と推計参照値.csv', pen / 'Scope of the study.xlsx', pen / 'Prod&Demand_Other_Sectors.xlsx', Path(__file__)]
manifest = {'as_of': '2026-11-11 Asia/Tokyo', 'annual_rows': len(annual), 'cumulative_rows': len(cumulative), 'minerals': 40, 'cases': len(caseframe), 'scenarios': 2, 'world_reference_count': int((~refs.extended_assumption).sum()), 'conditional_reference_count': int(refs.extended_assumption.sum()), 'complete40_observed': False, 'primary_mining_demand': False, 'Penelope_2050_accounting_fully_matched': False, 'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(O / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
(O / '読む順番.txt').write_text('1. Excelの00_最初に読む→01_40鉱物主要一覧→02_埋蔵量と条件付き参照。\n2. 03は各期間の全部門累積、04は全ケースの年次需要。\n3. A–Fは車両の別ケース。代替最適化はFを入力にした別計算。合算しない。\n4. 08の2050共通集計は会計整合未完の参考表。Pénélopeの不足3種類と同じ条件の比較ではない。\n5. 表の0は明示部品小計の0を含み、物理的使用なしを意味しない。\n')
print(json.dumps({k: v for k, v in manifest.items() if k != 'inputs'}, ensure_ascii=False))
print(book)
