"""Old merged 5-year IAMC vs new raw IAMC. Do not conflate reporting conventions.
Power and grid rerun with fixed v6 methods; battery/H2 are explicitly VR-only pending VP.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import sys, json, hashlib, re
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harmonize_energy_v2 as v2
import reconcile_wind_ree_v6 as v6
from grid_penelope_2100 import calculate as grid
ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / 'results_received_IAMC'
YEARS = list(range(2005, 2051)) + list(range(2055, 2101, 5))
POINTS = list(range(2005, 2101, 5))

def merge_like_old(raw):
    """Reproduce relevant average5.gms behavior: annual2016..2020 mean; after2050 rate*5/5."""
    f = raw.copy()
    if f.duplicated(['Sc', 'Sr', 'Sv', 'Y5']).any():
        raise ValueError('Duplicate raw IAMC keys')
    for sc, g in f.groupby('Sc'):
        gd = g.loc[g.Sv.eq('Cap_Ele')]
        if set(gd.Y5) != set(YEARS):
            raise ValueError('Unexpected actual year coverage')
    rows = []
    for (sc, region, var), g in f.groupby(['Sc', 'Sr', 'Sv']):
        values = g.set_index('Y5').value
        average = var.startswith('Cap_Add_Ele_') and var not in ['Cap_Add_Ele_Sto_Cap']
        for y in POINTS:
            if average:
                labels = [t for t in YEARS if max(2005, y - 4) <= t <= y]
                val = sum((float(values.get(t, 0)) * (1 if t <= 2050 else 5) for t in labels)) / (1 if y == 2005 else 5)
                rows.append(dict(Sc=sc, Sr=region, Sv=var, Y5=y, value=val))
            elif y in values.index:
                rows.append(dict(Sc=sc, Sr=region, Sv=var, Y5=y, value=float(values[y])))
    return pd.DataFrame(rows)

def compare_frames(old, new, keys, value):
    if old.duplicated(keys).any() or new.duplicated(keys).any():
        raise ValueError('Duplicate comparison keys')
    d = old[keys + [value]].merge(new[keys + [value]], on=keys, how='outer', suffixes=('_old', '_new'), indicator=True, validate='one_to_one')
    a, b = (d[value + '_old'], d[value + '_new'])
    d['change'] = b - a
    valid = a.notna() & b.notna()
    den = valid & a.ne(0)
    d['change_percent'] = np.where(den, 100 * d.change / a.where(den), np.nan)
    d['comparison_status'] = np.select([~valid, valid & a.eq(0) & b.ne(0), valid & a.eq(0) & b.eq(0)], ['unpaired_or_unknown', 'zero_to_nonzero', 'both_zero'], default='comparable')
    return d.drop(columns='_merge')

def activity_rate(raw, variable):
    rows = []
    for sc, g in raw.groupby('Sc'):
        g = g.loc[g.Sv.eq(variable)]
        if g.empty:
            raise ValueError('Variable wholly missing: ' + variable)
        values = g.set_index('Y5').value
        for year in YEARS:
            dt = 1 if year <= 2050 else 5
            rate = float(values.get(year, 0))
            if rate < -1e-07 or not np.isfinite(rate):
                raise ValueError('Invalid rate')
            rate = max(0, rate)
            for annual in range(max(2020, year - dt + 1), min(2100, year) + 1):
                rows.append(dict(Sc=sc, year=annual, addition_GW_year=rate))
    return pd.DataFrame(rows)

def run():
    OUT.mkdir(exist_ok=True)
    old = pd.read_csv(ROOT / 'input/AIM_World.csv.gz')
    old = old.loc[old.Sr.eq('World')]
    raw = pd.read_csv(ROOT / 'input/updated_2611091342/AIM_World.csv.gz')
    new = merge_like_old(raw)
    new.to_csv(OUT / 'updated_World_old_merge_convention.csv.gz', index=False, compression='gzip')
    rawcmp = compare_frames(old, new, ['Sc', 'Sr', 'Sv', 'Y5'], 'value')
    rawcmp.to_csv(OUT / 'all_reported_World_variable_comparison.csv.gz', index=False, compression='gzip')
    pa0, au0 = v2.power_activity(old)
    pa1, au1 = v2.power_activity(new)
    pdiff = compare_frames(pa0, pa1, ['Sc', 'year', 'technology'], 'addition_GW_year')
    pdiff.to_csv(OUT / 'power_annual_activity_comparison.csv', index=False)
    pows = []
    for version, a in [('old', pa0), ('new', pa1)]:
        for stat in ['average', 'minimum']:
            co = v6.coefficients(stat)
            co = co.loc[co.sector.eq('power')]
            d = a.merge(co, on='technology')
            d['demand_t_year'] = d.addition_GW_year * d.intensity
            d['version'] = version
            pows.append(d)
    pows = pd.concat(pows, ignore_index=True)
    pows.to_csv(OUT / 'power_detail_same_v6_intensities.csv.gz', index=False, compression='gzip')
    q = pows.groupby(['version', 'Sc', 'statistic', 'year', 'mineral'], as_index=False).demand_t_year.sum()
    power = compare_frames(q.loc[q.version.eq('old')], q.loc[q.version.eq('new')], ['Sc', 'statistic', 'year', 'mineral'], 'demand_t_year')
    power.to_csv(OUT / 'power_mineral_annual_comparison.csv', index=False)
    ref = pd.read_csv(ROOT / 'output/wind_ree_reconciliation_v6/explicit_sector_annual.csv')
    ref = ref.loc[ref.sector.eq('power')].rename(columns={'explicit_t_year': 'saved_t'})
    check = q.loc[q.version.eq('old')].merge(ref, on=['Sc', 'statistic', 'year', 'mineral'], validate='one_to_one')
    if len(check) != len(ref):
        raise ValueError('Old power reconstruction missing rows')
    np.testing.assert_allclose(check.demand_t_year, check.saved_t, rtol=1e-12, atol=1e-06)
    summary = []
    for end in [2050, 2100]:
        c = q.loc[q.year.le(end)].groupby(['version', 'Sc', 'statistic', 'mineral'], as_index=False).demand_t_year.sum()
        x = compare_frames(c.loc[c.version.eq('old')], c.loc[c.version.eq('new')], ['Sc', 'statistic', 'mineral'], 'demand_t_year')
        x = x.rename(columns={'demand_t_year_old': 'old_cumulative_t', 'demand_t_year_new': 'new_cumulative_t'})
        x['end_year'] = end
        summary.append(x)
    pc = pd.concat(summary, ignore_index=True)
    pc.to_csv(OUT / 'power_mineral_cumulative_comparison.csv', index=False)
    anchor = pd.read_csv(ROOT / 'input/imported/penelope_Demand_Network.csv')
    grids = []
    for ver, a in [('old', old), ('new', new)]:
        d = grid(anchor, a)
        d = d.loc[d.extension_case.eq('AIM_electricity_ratio')].copy()
        d['version'] = ver
        grids.append(d)
    grids = pd.concat(grids, ignore_index=True)
    gc = compare_frames(grids.loc[grids.version.eq('old')], grids.loc[grids.version.eq('new')], ['Sc', 'source_scenario', 'mineral', 'year'], 'demand_t_year')
    gc.to_csv(OUT / 'grid_annual_comparison.csv', index=False)
    gcc = []
    for end in [2050, 2100]:
        d = grids.loc[grids.year.le(end)].groupby(['version', 'Sc', 'source_scenario', 'mineral'], as_index=False).demand_t_year.sum()
        c = compare_frames(d.loc[d.version.eq('old')], d.loc[d.version.eq('new')], ['Sc', 'source_scenario', 'mineral'], 'demand_t_year')
        c['end_year'] = end
        gcc.append(c)
    gcc = pd.concat(gcc, ignore_index=True).rename(columns={'demand_t_year_old': 'old_cumulative_t', 'demand_t_year_new': 'new_cumulative_t'})
    gcc.to_csv(OUT / 'grid_cumulative_comparison.csv', index=False)
    provisional = []
    equipment = []
    for sec, tech, var in [('stationary_battery', 'ELECAP_BAT', 'Cap_Add_Ele_Sto_Cap'), ('hydrogen', 'H2CAP_ELE', 'Cap_Add_Hyd_Ele')]:
        a1 = activity_rate(raw, var)
        oldrows = []
        replacements = []
        for sc in ['Baseline', '300C']:
            d = pd.read_csv(ROOT / f'input/energy_unit_check/energy_drivers_{sc}.csv')
            d = d.loc[d.technology.eq(tech)]
            replacements.append(float(d.replacement_rate_native.abs().max()))
            for yr, g in d.groupby('year'):
                dt = int(g.model_time_interval.iloc[0])
                rate = g.new_rate_native.clip(lower=0).sum()
                for y in range(max(2020, int(yr) - dt + 1), min(2100, int(yr)) + 1):
                    oldrows.append(dict(Sc=sc, year=y, addition_GW_year=rate))
        a0 = pd.DataFrame(oldrows)
        x = compare_frames(a0, a1, ['Sc', 'year'], 'addition_GW_year')
        x['sector'] = sec
        x['status'] = 'VR_only; updated_VP_not_retrieved; fixed_old_12h_capacity_interpretation_for_battery; declaration_mismatch_not_resolved'
        x['old_max_abs_VP'] = max(replacements)
        equipment.append(x)
        for ver, a in [('old', a0), ('new', a1)]:
            for stat in ['average', 'minimum']:
                co = v6.coefficients(stat)
                co = co.loc[co.sector.eq(sec)]
                d = a.merge(co, how='cross')
                d['demand_t_year'] = d.addition_GW_year * d.intensity
                d['version'] = ver
                provisional.append(d)
    eq = pd.concat(equipment, ignore_index=True)
    eq.to_csv(OUT / 'equipment_VR_only_activity_comparison_PROVISIONAL.csv', index=False)
    pr = pd.concat(provisional, ignore_index=True)
    pr = pr.groupby(['version', 'Sc', 'statistic', 'sector', 'year', 'mineral'], as_index=False).demand_t_year.sum()
    prov = []
    for end in [2050, 2100]:
        d = pr.loc[pr.year.le(end)].groupby(['version', 'Sc', 'statistic', 'sector', 'mineral'], as_index=False).demand_t_year.sum()
        c = compare_frames(d.loc[d.version.eq('old')], d.loc[d.version.eq('new')], ['Sc', 'statistic', 'sector', 'mineral'], 'demand_t_year')
        c['end_year'] = end
        c['status'] = 'VR_ONLY_PROVISIONAL_NOT_FINAL_GROSS_OR_ALL_SECTOR_TOTAL'
        prov.append(c)
    prov = pd.concat(prov, ignore_index=True).rename(columns={'demand_t_year_old': 'old_cumulative_t', 'demand_t_year_new': 'new_cumulative_t'})
    prov.to_csv(OUT / 'battery_H2_mineral_cumulative_VR_ONLY_PROVISIONAL.csv', index=False)
    old_ldv = pd.read_csv(ROOT / 'output/verified_exports/LDV_verified_model_years.csv')
    declared = set(pd.read_csv(ROOT / 'input/updated_2611091342/updated_units_Baseline.csv.gz').VAR)
    mapping = {'ICE_including_HEV': (['TP_ICE', 'TP_HEV'], 'Ene_Ser_Tra_Pss_Roa_Lig_Veh_Int_Com'), 'PHEV': (['TP_PHV'], 'Ene_Ser_Tra_Pss_Roa_Lig_Veh_Plu_Hyb'), 'BEV': (['TP_BEV'], 'Ene_Ser_Tra_Pss_Roa_Lig_Veh_Bat'), 'FCV': (['TP_FCV'], 'Ene_Ser_Tra_Pss_Roa_Lig_Veh_Fue')}
    ldvrows = []
    for sc in ['Baseline', '300C']:
        for year in [2020, 2030, 2050, 2100]:
            for typ, (groups, var) in mapping.items():
                if var not in declared:
                    raise ValueError('Cannot assume absent new vehicle variable is zero')
                a = float(old_ldv.loc[old_ldv.Sc.eq(sc) & old_ldv.year.eq(year) & old_ldv.technology.isin(groups), 'service_bn_pkm_year'].sum())
                q = raw.loc[raw.Sc.eq(sc) & raw.Y5.eq(year) & raw.Sv.eq(var), 'value']
                b = float(q.sum())
                ldvrows.append({'Sc': sc, 'year': year, 'drive_type': typ, 'old_service_bn_pkm_year': a, 'new_service_bn_pkm_year': b, 'change_percent': 100 * (b - a) / a if a != 0 else np.nan, 'new_zero_from_sparse_declared_variable': q.empty, 'interpretation': 'service only; HEV included in ICE; not sales or stock; reporting-method differences may contribute'})
    ldvcompare = pd.DataFrame(ldvrows)
    ldvcompare.to_csv(OUT / 'LDV_drive_service_comparison_NOT_sales.csv', index=False)
    selected = ['GDP_PPP', 'Fin_Ene_Ele', 'Cap_Ele_SolarPV', 'Cap_Ele_Win_Ons', 'Cap_Ele_Win_Off', 'Cap_Ele_Sto_Cap', 'Cap_Hyd_Ele', 'Ene_Ser_Tra_Pss_Roa_LDV', 'Ene_Ser_Tra_Pss_Roa_Bus', 'Ene_Ser_Tra_Fre_Roa', 'Ene_Ser_Tra_Pss_Roa', 'Ene_Ser_Tra_Pss_Rai', 'Ene_Ser_Tra_Pss_Avi']
    checkpoints = rawcmp.loc[rawcmp.Sv.isin(selected) & rawcmp.Y5.isin([2020, 2030, 2050, 2100])].copy()
    checkpoints.to_csv(OUT / 'driver_checkpoints.csv', index=False)
    gd = rawcmp.loc[rawcmp.Sv.eq('GDP_PPP')]
    notes = pd.DataFrame({'項目': ['時間基準', '確定して再計算', '蓄電池・水素', '車両', 'その他部門', '単位表', '因果の限界'], '説明': ['旧CSVは5年集約。新rawは2050まで年次、以後5年。発電新設は旧mergeと同じ5年平均へ整形。', '旧v6と同じ係数で発電を再計算。送配電Cu/Alも同じIEA固定系列＋AIM延長で再計算。', '追加IAMC変数はVRのみ。旧nativeのVRだけと比較した暫定表。新VP未取得。電池GWh/yrという単位宣言とnative直接出力の実装に不整合があるため旧GW・12h解釈固定の参照計算。', 'サービスは比較可能。新設台数未取得のため、新鉱物需要は未確定。サービスシェアを販売シェアにしない。', 'GDP差は比較。新2020車両等の差引が未確認のためその他部門・全部門総需要を更新完了としない。', '受領unitsCSVは変数名のみで単位文字列なし。対応する公式コミットのunit.gmsと報告式を別途取得。実行時ソース同一性はまだ未照合。', '新旧にはサービス不具合以外のコード・データ更新もあり、差を単独のバグ修正効果と断定しない。']})
    with pd.ExcelWriter(OUT / 'updated_vs_old_first_comparison.xlsx', engine='openpyxl') as w:
        for name, d in [('最初に読む', notes), ('AIM主要指標', checkpoints), ('車両駆動別サービス_台数でない', ldvcompare), ('発電鉱物_累積', pc), ('発電鉱物_主要年', power.loc[power.year.isin([2020, 2030, 2050, 2100])]), ('送配電_累積', gcc), ('送配電_主要年', gc.loc[gc.year.isin([2020, 2050, 2100])]), ('暫定_電池水素_累積', prov), ('暫定_電池水素_新設', eq.loc[eq.year.isin([2020, 2050, 2100])])]:
            d.to_excel(w, sheet_name=name, index=False)
            ws = w.book[name]
            ws.freeze_panes = 'B2'
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(65, max(15, max((len(str(c.value or '')) for c in col[:50])) + 1))
    used = [ROOT / 'input/AIM_World.csv.gz', ROOT / 'input/updated_2611091342/AIM_World.csv.gz', ROOT / 'output/wind_ree_reconciliation_v6/coefficients.csv', ROOT / 'input/imported/penelope_Demand_Network.csv', Path(__file__)]
    (OUT / 'manifest.json').write_text(json.dumps({'old_run': '2608261554', 'new_run': '2611091342', 'old_power_reproduction_rows': len(check), 'old_power_max_abs_error_t_year': float((check.demand_t_year - check.saved_t).abs().max()), 'GDP_max_abs_change': float(gd.change.abs().max()), 'new_vehicle_mineral_demand_recomputed': False, 'other_sector_full_residual_recomputed': False, 'new_VP_retrieved': False, 'all_sector_new_total_ready': False, 'new_power_time_convention': 'old_average5_from_raw; after2050 model interval weighted', 'unit_text_absent_in_received_unit_CSVs': True, 'hashes': {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in used}}, indent=2))
    print('DRIVERS\n', checkpoints.loc[checkpoints.Y5.eq(2100), ['Sc', 'Sv', 'value_old', 'value_new', 'change_percent']].to_string(index=False))
    print('POWER\n', pc.loc[pc.statistic.eq('average') & pc.end_year.eq(2100) & pc.mineral.isin(['Cu', 'Al', 'Fe', 'Dy', 'Tb', 'Li'])].to_string(index=False))
    print('PROVISIONAL\n', prov.loc[prov.statistic.eq('average') & prov.end_year.eq(2100) & prov.mineral.isin(['Li', 'Ir', 'Pt', 'Sc'])].to_string(index=False))
if __name__ == '__main__':
    run()
