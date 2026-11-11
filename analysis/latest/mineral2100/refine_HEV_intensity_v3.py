"""Conditional HEV reference update; retained material, not manufacturing inputs.

No historical whole-PCU recipe is combined with its modeled power-module children.
Only selected subparts are resolved: all totals remain partial vehicle inventories.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import json
import numpy as np
import pandas as pd
from model import MINERALS
from refine_HEV_intensity_v2 import build as build_v2
from integrate_HEV_vehicle import check_disjoint_scopes, central_sales, map_to_sales
ROOT = Path(__file__).resolve().parent

def module_materials(power, cfg):
    low, high = cfg['module_power_range_kW']
    if not np.isfinite(power) or not low <= power <= high:
        raise ValueError('Power outside published model range')
    return {m: (base + slope * (power - 20)) / 1000 for m, (base, slope) in cfg['power_module_materials_base_g_and_slope_g_per_kW'].items()}

def module_elements(materials, cfg):
    aw = cfg['atomic_weights']
    values = {m: materials[m] for m in ['Cu', 'Ni', 'Zn']}
    values['Si'] = materials['doped_Si']
    values['Al'] = materials['Al2O3'] * (2 * aw['Al']) / (2 * aw['Al'] + 3 * aw['O'])
    for m, f in cfg['solder_mass_fractions'].items():
        values[m] = values.get(m, 0) + materials['solder'] * f
    return values

def coated_magnet(mass, cfg):
    f = cfg['magnet_uncoated_body_fractions']
    coat = cfg['magnet_Ni_coating_fraction_of_finished_mass']
    if not np.isclose(sum(f.values()), 1) or not 0 <= coat < 1:
        raise ValueError('Invalid finished magnet recipe')
    out = {m: mass * (1 - coat) * v for m, v in f.items()}
    out['Ni'] = mass * coat
    return out

def build(root=ROOT):
    cfg = json.loads((root / 'input/hev_refinement_v3/reference.json').read_text())
    old, total2, cases2, _, _, _, _, cfg2 = build_v2(root)
    frames = []
    audit = []
    cases = []
    for body in ['sedan', 'smallSUV']:
        basecase = f'HEV2_{body}_NiMH2010_unresolved_electrical'
        baseline = old.loc[old.case.eq(basecase)].copy()
        for enabled in [False, True]:
            case = f'HEV3_{body}_' + ('Nordelof_reference' if enabled else 'unresolved_reference')
            p = baseline.copy()
            p['case'] = case

            def contribute(scope, values, source, evidence):
                nonlocal p
                if scope not in set(p.scope):
                    p = pd.concat([p, pd.DataFrame([{'case': case, 'scope': scope, 'mineral': m, 'quantified_kg_per_vehicle': np.nan, 'source': source, 'evidence': evidence, 'physical_component_count_per_vehicle': 1, 'full_component_element_coverage_confirmed': False} for m in MINERALS])], ignore_index=True)
                for m, value in values.items():
                    mask = p.scope.eq(scope) & p.mineral.eq(m)
                    if mask.sum() != 1:
                        raise ValueError('Invalid ownership')
                    previous = p.loc[mask, 'quantified_kg_per_vehicle'].iloc[0]
                    p.loc[mask, 'quantified_kg_per_vehicle'] = (0 if pd.isna(previous) else previous) + value
                    p.loc[mask, 'source'] = source
                    p.loc[mask, 'evidence'] = evidence
            if enabled:
                p = p.loc[~p.scope.eq('vehicle.power_electronics')].copy()
                for machine, power in cfg['module_power_reference_kW'].items():
                    materials = module_materials(power, cfg)
                    values = module_elements(materials, cfg)
                    contribute('vehicle.power_electronics.' + machine + '_power_module', values, 'Nordelof_2018_report_Table1_Eq1', 'generic_module_design_transfer; not_Prius_assay; Si_material_proxy; other_material_elements_unresolved')
                    for material, mass in materials.items():
                        audit.append({'case': case, 'subpart': machine + '_power_module', 'material': material, 'mass_kg': mass, 'power_kW': power, 'meaning': 'retained modeled material; not whole inverter'})
                    if sum(values.values()) > sum(materials.values()) + 1e-12:
                        raise ValueError('Element mass exceeds module mass')
                contribute('vehicle.power_electronics.unresolved_remainder', {}, 'ORNL_PCU_boundary', 'busbars;capacitor;boards;housing;boost_DC_DC;12V_converter;other_parts_unknown_not_zero')
                for scope, machine in [('vehicle.traction_motor', 'MG2'), ('vehicle.generator', 'MG1')]:
                    mass = cfg2['ORNL2010_' + machine]['magnet_kg']
                    values = coated_magnet(mass, cfg)
                    contribute(scope, values, 'ORNL_magnet_mass_x_Nordelof_2017_sections3.4', 'generic_finished_magnet_recipe_transfer; body99percent_plus_Ni_coating1percent; not_Prius_assay')
                    audit.append({'case': case, 'subpart': machine + '_magnet', 'material': 'finished_magnet', 'mass_kg': mass, 'power_kW': np.nan, 'meaning': 'already inside rotor; all recipe elements sum to this mass'})
                steel = cfg2['ORNL2010_MG2']['stator_core_laminations_kg']
                contribute('vehicle.traction_motor', {m: steel * f for m, f in cfg['electrical_steel_known_fractions'].items()}, 'ORNL10.36kg_x_Nordelof_2017_Si2percent_Al0.4percent', 'generic_electrical_steel_transfer; only_MG2_stator; remaining97.6percent_not_pure_Fe')
                audit.append({'case': case, 'subpart': 'MG2_stator_core', 'material': 'unresolved_steel_balance', 'mass_kg': steel * (1 - sum(cfg['electrical_steel_known_fractions'].values())), 'power_kW': np.nan, 'meaning': 'includes_Fe_and_other_unresolved_elements; not additional material'})
            check_disjoint_scopes(p)
            frames.append(p)
            cases.append({'case': case, 'new_reference_enabled': enabled, 'body_type': body, 'whole_HEV_complete': False, 'historical_whole_PCU_recipe_used': False, 'confidence_interval': False, 'future_technology_prediction': False})
    parts = pd.concat(frames, ignore_index=True)
    check_disjoint_scopes(parts)
    total = parts.groupby(['case', 'mineral'], as_index=False).agg(quantified_subtotal_kg_per_vehicle=('quantified_kg_per_vehicle', lambda x: x.sum(min_count=1)))
    total['whole_HEV_kg_per_vehicle'] = np.nan
    total['whole_HEV_complete'] = False
    total['interpretation'] = 'PARTIAL contained-material proxy subtotal; unknown contributions remain; not primary supply demand'
    total.loc[total.mineral.eq('Fe'), 'interpretation'] = 'PARTIAL battery Fe proxy plus conditional magnet Fe ONLY; vehicle steel Fe unresolved'
    return (parts, total, pd.DataFrame(cases), pd.DataFrame(audit), cfg)

def run(root=ROOT):
    parts, total, cases, audit, cfg = build(root)
    out = root / 'output/HEV_refinement_v3'
    out.mkdir(parents=True, exist_ok=True)
    annual = map_to_sales(central_sales(root), total)
    summary = total.pivot(index='case', columns='mineral', values='quantified_subtotal_kg_per_vehicle').reset_index()
    note = pd.DataFrame({'説明': ['全てkg/新車1台の部分小計。40鉱物の全量確定ではない。空欄は不明。', 'Nordelof_referenceは公開された汎用部品設計の転用。Prius実測組成ではない。', '未確認を残す参照との比較であり、上下限ではない。旧v2転用ケースを足さない。', 'Feは電池と条件付き磁石のみ。車体鋼材・鋳鉄のFeを含まず、全車両Feとして使わない。', 'Ag/Snは2つのモデル化パワーモジュールのはんだのみ。他の電子部品は未計上。', '製造ロス、再生材控除、補修交換、将来技術構成は含まない。AIM台数は未校正。']})
    tables = {'最初に読む': note, '１台部分小計kg': summary, '40鉱物_部分原単位': total, '部品寄与': parts, 'ケース定義': cases, '材料収支_入れ子非加算': audit, 'AIM2100累積_条件付き': annual.loc[annual.year.eq(2100)]}
    for name, frame in [('component_inventory', parts), ('inventory_40_PARTIAL', total), ('cases', cases), ('material_audit', audit), ('annual_demand_CONDITIONAL', annual)]:
        frame.to_csv(out / (name + '.csv'), index=False)
    with pd.ExcelWriter(out / 'HEV_reference_v3.xlsx', engine='openpyxl') as writer:
        for name, frame in tables.items():
            frame.to_excel(writer, sheet_name=name, index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = 'B2'
            ws.auto_filter.ref = ws.dimensions
    print(summary[['case', 'Cu', 'Al', 'Ni', 'Nd', 'Dy', 'B', 'Si', 'Ag', 'Sn', 'Fe']].to_string(index=False))
if __name__ == '__main__':
    run()
