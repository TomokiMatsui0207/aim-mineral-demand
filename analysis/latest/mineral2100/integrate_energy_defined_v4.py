"""Model-defined 12-hour storage-equivalent reference, following source inspection.
This adopts AIM's declared discharge-time parameter for the mineral conversion;
it is not a claim about observed packs, SOC modeling or empirical fleet duration.
"""
from pathlib import Path as _SnapshotPath
import hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
import integrate_all_sectors_conditional as legacy
import integrate_energy_native_v3 as v3
import harmonize_energy_v2 as v2
from resolve_energy_basis import WEI_HOURS
ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'input/power_definition_complete'
OUT = ROOT / 'output/harmonized_energy_defined_v4'

def validate_sources():
    main = (SOURCE / 'power/power.gms').read_text()
    data = (SOURCE / 'GLOBAL/data_power.gms').read_text()
    mapping = (SOURCE / 'power/power_set.py').read_text()
    assert "'discharge time of electricity storage in hours'" in main
    assert "t_disc(R,'BAT')         =12;" in data
    assert "eff_in(R,'BAT')         =0.85;" in data
    assert 'hourslice*eff_H2' in main
    assert "R_S+'.H_H.H2CAP_ELE'" in mapping
    d = pd.read_csv(v3.OUT / 'battery_duration_constraint_audit.csv.gz')
    assert set(d.Sc) == {'Baseline', '300C'}
    np.testing.assert_allclose(d.inferred_storage_hours, 12, atol=1e-08)
    return len(d)

def coefficients(stat):
    c = v2.coefficient_table(stat)
    b = c.sector.eq('stationary_battery')
    for col in ['intensity', 'elemental_component_t_GW', 'steel_material_part_t_GW']:
        c.loc[b, col] *= 12 / WEI_HOURS
    c.loc[b, 'scope_assumption'] = 'AIM_declared_12h_discharge_time_equivalent; native_constraint_ratio_verified; pack_energy_convention_Wei_equivalent'
    c.loc[b, 'unit'] = 't/GW_at_AIM_12h_equivalent'
    c['energy_intensity_t_GWh'] = np.where(b, c.intensity / 12, np.nan)
    return c

def run():
    OUT.mkdir(exist_ok=True)
    n = validate_sources()
    tables = legacy.build(coefficients, v2.power_activity, lambda aim: v3.activities(aim, audit_dir=OUT))
    names = ['all_sectors_CONDITIONAL', 'explicit_sector_annual', 'explicit_sector_detail', 'grid_CuAl_annual', 'other_complement_annual_CONDITIONAL', 'baseline2020_recalibration', 'coefficients', 'power_activity', 'power_activity_audit', 'hydrogen_native_activity', 'battery_native_activity']
    for name, frame in zip(names, tables):
        compressed = name in ['all_sectors_CONDITIONAL', 'explicit_sector_detail']
        frame.to_csv(OUT / (name + ('.csv.gz' if compressed else '.csv')), index=False, compression='gzip' if compressed else None)
    before = pd.read_csv(v3.OUT / 'explicit_sector_annual.csv').groupby(['Sc', 'statistic', 'sector', 'mineral'], as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year': 'v3_cumulative_t'})
    after = tables[1].groupby(['Sc', 'statistic', 'sector', 'mineral'], as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year': 'v4_cumulative_t'})
    cmp = before.merge(after, on=['Sc', 'statistic', 'sector', 'mineral'], validate='one_to_one')
    cmp['change_t'] = cmp.v4_cumulative_t - cmp.v3_cumulative_t
    cmp.to_csv(OUT / 'cumulative_change_vs_v3.csv', index=False)
    old = pd.read_csv(v3.OUT / 'all_sectors_CONDITIONAL.csv.gz')
    keys = ['Sc', 'statistic', 'grid_case', 'case', 'year', 'mineral']
    delta = tables[0][keys + ['conditional_total_low_t_year', 'conditional_total_high_t_year']].merge(old[keys + ['conditional_total_low_t_year', 'conditional_total_high_t_year']], on=keys, suffixes=('_v4', '_v3'), validate='one_to_one')
    delta['total_change_low_t_year'] = delta.conditional_total_low_t_year_v4 - delta.conditional_total_low_t_year_v3
    delta['total_change_high_t_year'] = delta.conditional_total_high_t_year_v4 - delta.conditional_total_high_t_year_v3
    delta.to_csv(OUT / 'all_sectors_change_vs_v3.csv.gz', index=False, compression='gzip')
    hashes = [{'source': str(p.relative_to(SOURCE)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(SOURCE.rglob('*')) if p.is_file() and p.suffix in ['.gms', '.py', '.map']]
    pd.DataFrame(hashes).to_csv(OUT / 'definition_source_hashes.csv', index=False)
    meta = {'reference': 'AIM_declared_discharge_time_equivalent', 'storage_discharge_time_model_hours': 12, 'Wei_embedded_reference_hours': WEI_HOURS, 'battery_scale_vs_v3': 12 / WEI_HOURS, 'native_ratio_pairs_verified': n, 'AIM_H2_capacity_basis': 'electricity_input_power', 'Wei_each_electrolyser_MI_basis_rebuilt': False, 'PV_DC_AC_confirmed': False, 'efficiency_multiplier_applied_to_mineral_mass': False, 'all40_inventory_complete': False, 'original_v2_v3_overwritten': False}
    (OUT / 'manifest.json').write_text(json.dumps(meta, indent=2))
    notes = pd.DataFrame({'説明': ['AIMで放電時間と定義されたt_disc=12hを参照条件として容量換算へ採用。両実行のnative係数比でも12を照合。', '製造需要=新設GW/年×12h×Wei表原単位/6.2113h。充放電効率0.85を材料量へ重ね掛けしない。', 'SOCや実際の電池パックの実測蓄電時間が判明したという意味ではない。モデル設定に整合させた12h等価ケース。', '水素容量は電力入力基準。水素原単位の個別出典の基準確認までは終わっていない。', '太陽光DC/AC、PV部品重複、CCS部品範囲などは継続課題。', 'その他部門残余を再校正。負残余Dy/Tbをゼロ補完して完全な合計としない。']})
    with pd.ExcelWriter(OUT / 'energy_defined_revision_v4.xlsx') as w:
        notes.to_excel(w, sheet_name='定義と計算上の扱い', index=False)
        cmp.to_excel(w, sheet_name='累積需要_前回との差', index=False)
        tables[1].to_excel(w, sheet_name='エネルギー設備_年次', index=False)
        tables[5].to_excel(w, sheet_name='2020残余再校正', index=False)
        tables[0].loc[tables[0].year.isin([2020, 2050, 2100])].to_excel(w, sheet_name='全部門_主要年_条件付き', index=False)
    print(cmp.loc[cmp.statistic.eq('average') & cmp.sector.eq('stationary_battery') & cmp.mineral.isin(['C', 'Li', 'Cu', 'Al'])].to_string(index=False))
if __name__ == '__main__':
    run()
