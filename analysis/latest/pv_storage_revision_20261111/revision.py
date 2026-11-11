"""Non-destructive PV choice expansion plus separate Penelope-IEA storage replacement.
No claim that global IEA V demand is derived from AIM battery capacity.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import sys, os
import pandas as pd, numpy as np
ROOT = Path(str(_SnapshotPath(__file__).resolve().parents[1] / 'mineral2100'))
OUT = Path(__file__).resolve().parent
VARIANT = os.environ.get('REVISION_CASE', 'pv_only')
from mineral_names import PENELOPE_NAMES as NAMES

def install(old):
    original_load = old.load
    original_build = old.build_problem
    if VARIANT.endswith('_retrospective2021'):
        original_init = old.Problem.__init__

        def init(self, sc, inputs):
            original_init(self, sc, inputs)
            self.before = old.vec(self.total.query('year>=2021').groupby('mineral').conditional_total_low_t_year.sum().to_dict())
            self.fixed = self.before.copy()
        old.Problem.__init__ = init
    raw = pd.read_csv(ROOT / 'input/imported/wei_intensity_rows.csv')
    raw = raw[raw.category.eq('Solar') & raw.reported_average.notna()]

    def elm(tech, m):
        q = raw[raw.technology.eq(tech) & raw.material.eq(m)]
        s = raw[raw.technology.eq(tech) & raw.material.eq('Steel')] if m == 'Fe' else raw.iloc[:0]
        assert len(q) <= 1 and len(s) <= 1
        return ((float(q.reported_average.iloc[0]) if len(q) else 0) + (float(s.reported_average.iloc[0]) * 0.9786 if len(s) else 0), bool(len(q) + len(s)))
    types = ['c-Si', 'c-Si_Cu', 'CdTe', 'CIGS', 'a-Si']
    w = np.array([0.954, 0, 0.024, 0.019, 0.003])
    cv = []
    mi = pd.read_excel(old.PEN / 'PowerCap_MI_MS_CF.xlsx', sheet_name='MI', index_col=0)
    for tech in types:
        v = []
        for m in old.MINERALS:
            generic, _ = elm('PV', m)
            specific, seen = elm('c-Si' if tech == 'c-Si_Cu' else tech, m)
            value = (specific if seen else generic) if m in {'Al', 'Fe', 'Ag', 'Sn'} else generic + specific
            if tech == 'c-Si_Cu' and m == 'Ag':
                value = 0.0
            if tech == 'c-Si_Cu' and m == 'Cu':
                value *= mi.loc['Copper', 'Sol_C-si_Copper'] / mi.loc['Copper', 'Sol_C-si_Silver']
            v.append(value)
        cv.append(v)
    cv = np.array(cv)
    audit = pd.DataFrame(cv, index=types, columns=old.MINERALS)
    audit.to_csv(OUT / 'PV_technology_coefficients_t_per_GW.csv')

    def load():
        z = list(original_load())
        co = z[6]
        sourceco = co[co.sector.eq('power') & co.technology.eq('SolarPV')].set_index('mineral').intensity.reindex(old.MINERALS).to_numpy()
        np.testing.assert_allclose(w @ cv, sourceco, rtol=1e-10, atol=1e-08)
        if VARIANT.startswith('pv_plus_IEA_storage'):
            t = z[-2].copy()
            book = old.PEN / 'Prod&Demand_Other_Sectors.xlsx'
            src = pd.read_excel(book, sheet_name='Demand_Storage', index_col=0)
            mapping = {v: k for k, v in NAMES.items()}
            mapping['Graphite'] = 'C'
            records = []
            for sc, iea in [('Baseline', 'SPS'), ('300C', 'APS')]:
                s = src[src.Scenario.eq(iea)].drop(columns=['Scenario', 'Unit', 'Ref'])
                s.columns = s.columns.astype(int)
                s = s.reindex(columns=range(2020, 2051)).interpolate(axis=1)
                s[2020] = 2 * s[2022] - s[2025]
                s[2021] = (s[2020] + s[2022]) / 2
                s = s.clip(lower=0)
                for mineral, name in mapping.items():
                    if mineral not in s.index:
                        continue
                    for year in range(2020, 2051):
                        records.append(dict(Sc=sc, mineral=name, year=year, IEA_storage_t_year=float(s.loc[mineral, year]), IEA_scenario=iea))
            series = pd.DataFrame(records)
            series.to_csv(OUT / 'IEA_storage_annual_reported.csv', index=False)
            t = t.merge(series[['Sc', 'mineral', 'year', 'IEA_storage_t_year']], on=['Sc', 'mineral', 'year'], how='left', validate='many_to_one')
            t['old_storage_t_year'] = t.stationary_battery
            t['replacement_storage_t_year'] = t.IEA_storage_t_year.fillna(0.0)
            t.loc[t.year.gt(2050), 'replacement_storage_t_year'] = t.loc[t.year.gt(2050), 'old_storage_t_year']
            t['storage_change'] = t.replacement_storage_t_year - t.old_storage_t_year
            base = t[t.year.eq(2020)][['Sc', 'mineral', 'storage_change']].rename(columns={'storage_change': 'storage_base_change'})
            t = t.merge(base, on=['Sc', 'mineral'], validate='many_to_one')
            for bound in ['low', 'high']:
                t['other_' + bound + '_t_year'] -= t.storage_base_change * t.growth_factor
                if t['other_' + bound + '_t_year'].min() < -1e-05:
                    raise RuntimeError('Negative recalibrated OSD')
                t['conditional_total_' + bound + '_t_year'] += t.storage_change - t.storage_base_change * t.growth_factor
            t['stationary_battery'] = t.replacement_storage_t_year
            assert np.allclose(t[t.year.eq(2020)].storage_change - t[t.year.eq(2020)].storage_base_change, 0)
            t[t.year.le(2050)][['Sc', 'mineral', 'year', 'old_storage_t_year', 'replacement_storage_t_year', 'storage_change', 'storage_base_change', 'other_low_t_year', 'IEA_storage_t_year']].to_csv(OUT / 'storage_replacement_and_OSD_audit.csv.gz', index=False)
            z[-2] = t
        return z

    def build(sc, inputs):
        p = original_build(sc, inputs)
        q = old.Problem(sc, inputs)
        for g in p.groups:
            if g['name'] == 'solar_cSi_metallisation':
                continue
            records = p.records[g['offset']:g['offset'] + g['n']]
            q.add(g['name'], (g['start'], g['end']), [r['candidate'] for r in records], g['p'], g['current'], g['options'], g['na_cap'])
        co = inputs[6]
        co = co[co.sector.eq('power') & co.technology.eq('SolarPV')].set_index('mineral').intensity.reindex(old.MINERALS).to_numpy()
        pa = inputs[8]
        pa = pa[pa.Sc.eq(sc) & pa.technology.eq('SolarPV')].set_index('year').addition_GW_year
        for start, end in old.BLOCKS:
            rates = np.array([pa.get(y, 0) for y in range(start, end + 1)])
            if not rates.sum():
                continue
            current = rates[:, None] * co
            options = rates[None, :, None] * cv[:, None, :]
            q.add('solar_PV_whole_technology', (start, end), types, w, current, options)
        return q
    old.load = load
    old.build_problem = build
