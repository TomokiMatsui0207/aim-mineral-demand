"""Technology-resolved REE reference case, not a supply-fitted coefficient.
Transfer Penelope's 2020 installed-capacity technology shares to new equipment
and hold them fixed to 2100. This explicit transfer is an assumption, not observed
sales shares or a forecast. Preserve the unresolved Wei pooled branch unchanged.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd
import integrate_all_sectors_conditional as legacy
import harmonize_energy_v2 as v2
import integrate_energy_native_v3 as v3
import resolve_solar_overlap_v5 as v5
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/wind_ree_reconciliation_v6'
MI_FILE = next((ROOT / 'originals').glob('Pelotte*/Data/PowerCap_MI_MS_CF.xlsx'))
SHARE_FILE = next((ROOT / 'originals').glob('Pelotte*/Data/Market Share in time - Disag.xlsx'))
REE = {'Dy': 'Dysprosium', 'Tb': 'Terbium', 'Nd': 'Neodymium', 'Pr': 'Praesodymium'}

def technology_ledger():
    mi = pd.read_excel(MI_FILE, sheet_name='MI', index_col=0)
    if '[t/GW]' not in str(mi.index.name):
        raise ValueError('Unverified wind intensity unit')
    shares = pd.read_excel(SHARE_FILE, sheet_name='2020', index_col=0)
    rows = []
    for location, suffix in [('Onshore', 'Win_Ons'), ('Offshore', 'Win_Off')]:
        cols = [c for c in mi.columns if c.startswith('Wind_') and c.endswith('_' + location)]
        weights = shares.loc['Capacity..Electricity..Wind..' + location, cols].astype(float)
        if len(cols) != 4 or weights.isna().any() or (weights < 0).any() or (not np.isclose(weights.sum(), 1)):
            raise ValueError('Wind technology shares do not close')
        for element, name in REE.items():
            for technology in cols:
                val = float(mi.loc[name, technology])
                if not np.isfinite(val) or val < 0:
                    raise ValueError('Missing component MI')
                rows.append(dict(technology=suffix, mineral=element, subtechnology=technology, intensity_t_GW=val, capacity_share_2020=weights[technology], weighted_t_GW=val * weights[technology], share_transfer='installed_capacity_mix_to_new_equipment; fixed_2020_mix_through_2100_ASSUMPTION'))
    return pd.DataFrame(rows)

def coefficients(stat):
    c = v5.coefficients(stat)
    mix = technology_ledger().groupby(['technology', 'mineral']).weighted_t_GW.sum()
    for (tech, m), value in mix.items():
        mask = c.sector.eq('power') & c.technology.eq(tech) & c.mineral.eq(m)
        if mask.sum() != 1:
            raise ValueError('Missing wind REE target')
        c.loc[mask, 'intensity'] = value
        c.loc[mask, 'elemental_component_t_GW'] = value
        c.loc[mask, 'steel_material_part_t_GW'] = 0
        c.loc[mask, 'coefficient_reported'] = True
        c.loc[mask, 'scope_assumption'] = 'Penelope_2020_wind_technology_mix_transferred_to_new_capacity_FIXED; same_REE_reference_in_both_Wei_statistic_branches'
    return c

def run():
    OUT.mkdir(exist_ok=True)
    ledger = technology_ledger()
    ledger.to_csv(OUT / 'wind_REE_component_share_ledger.csv', index=False)
    tables = legacy.build(coefficients, v2.power_activity, lambda aim: v3.activities(aim, audit_dir=OUT))
    names = ['all_sectors_CONDITIONAL', 'explicit_sector_annual', 'explicit_sector_detail', 'grid_CuAl_annual', 'other_complement_annual_CONDITIONAL', 'baseline2020_recalibration', 'coefficients', 'power_activity', 'power_activity_audit', 'hydrogen_native_activity', 'battery_native_activity']
    for name, frame in zip(names, tables):
        compressed = name in ['all_sectors_CONDITIONAL', 'explicit_sector_detail']
        frame.to_csv(OUT / (name + ('.csv.gz' if compressed else '.csv')), index=False, compression='gzip' if compressed else None)
    previous = pd.read_csv(v5.OUT / 'baseline2020_recalibration.csv')
    comparison = tables[5].merge(previous, on=['Sc', 'statistic', 'grid_case', 'mineral', 'year'], suffixes=('_v6', '_v5'), validate='one_to_one')
    comparison.to_csv(OUT / 'baseline_before_after.csv', index=False)
    bysector = tables[1].loc[tables[1].year.eq(2020) & tables[1].mineral.isin(REE)].copy()
    bysector.to_csv(OUT / '2020_explicit_energy_sector_breakdown.csv', index=False)
    before = pd.read_csv(v5.OUT / 'explicit_sector_annual.csv').groupby(['Sc', 'statistic', 'sector', 'mineral'], as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year': 'v5_cumulative_t'})
    after = tables[1].groupby(['Sc', 'statistic', 'sector', 'mineral'], as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year': 'v6_cumulative_t'})
    cumul = before.merge(after, on=['Sc', 'statistic', 'sector', 'mineral'], validate='one_to_one')
    cumul.to_csv(OUT / 'cumulative_energy_comparison.csv', index=False)
    negative = sorted(tables[5].loc[tables[5].negative_base, 'mineral'].unique())
    meta = {'reference_case': 'technology_specific_REE_with_Penelope_2020_capacity_mix', 'fit_to_supply': False, 'supply_changed': False, 'negative_residual_clipped_to_zero': False, 'REE_inventory_group_replaced': ['Dy', 'Tb', 'Nd', 'Pr'], '2020_stock_shares_transferred_to_new_equipment': True, 'fixed_2020_mix_to_2100_is_assumption': True, 'wind_REE_values_identical_in_average_and_minimum_branches': True, 'old_Wei_pooled_case_preserved': True, 'negative_base_minerals_after_change': negative, 'all40_observed_total_complete': False, 'sources': [{'file': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in [MI_FILE, SHARE_FILE]]}
    (OUT / 'manifest.json').write_text(json.dumps(meta, indent=2))
    with pd.ExcelWriter(OUT / 'wind_REE_reconciliation_v6.xlsx') as w:
        ledger.to_excel(w, sheet_name='発電機別原単位と構成', index=False)
        comparison.loc[comparison.mineral.isin(REE)].to_excel(w, sheet_name='2020収支_修正前後', index=False)
        bysector.to_excel(w, sheet_name='2020エネルギー部門内訳', index=False)
        cumul.loc[cumul.mineral.isin(REE)].to_excel(w, sheet_name='累積エネルギー需要_比較', index=False)
        tables[0].loc[tables[0].year.isin([2020, 2050, 2100])].to_excel(w, sheet_name='全部門_主要年_条件付き', index=False)
    q = comparison.loc[comparison.statistic.eq('average') & comparison.grid_case.eq('APS') & comparison.mineral.isin(['Dy', 'Tb'])]
    print(q[['Sc', 'mineral', 'supply_low_t_year_v6', 'explicit_deduction_t_year_v5', 'explicit_deduction_t_year_v6', 'raw_residual_low_t_year_v5', 'raw_residual_low_t_year_v6']].to_string(index=False))
    print('Negative base minerals after:', negative)
if __name__ == '__main__':
    run()
