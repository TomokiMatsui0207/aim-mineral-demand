"""Source-backed glider materials and HEV NiMH electrode subinventories.

Raw measured compositions, conditional reconstruction and pack extrapolation
are deliberately separate. No complete vehicle or pack elemental claim.
"""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import json
import numpy as np
import pandas as pd
from model import MINERALS
ROOT = Path(__file__).resolve().parent

def body_materials(cfg):
    records = []
    summary = []
    for c in cfg['body_cases']:
        if not np.isclose(sum((p['share'] for p in c['parts'])), 1):
            raise ValueError('Bad glider shares')
        glider = c['vehicle_weight_lb'] * 0.45359237 * c['glider_share']
        selected = 0.0
        for part in c['parts']:
            if not 0 <= part['share'] <= 1:
                raise ValueError('Invalid part share')
            fractions = [part[m] for m in cfg['body_material_columns']]
            if any((f < 0 for f in fractions)) or sum(fractions) > 1:
                raise ValueError('Invalid material composition')
            for material in cfg['body_material_columns']:
                kg = glider * part['share'] * part[material]
                selected += kg
                records.append([c['case'], part['part'], material, part['share'], part[material], kg])
        summary.append([c['case'], glider, selected, glider - selected, 'published_model_glider_not_measured_specific_vehicle'])
    return (pd.DataFrame(records, columns=['case', 'part', 'material', 'part_share', 'material_fraction_in_part', 'kg_per_glider']), pd.DataFrame(summary, columns=['case', 'glider_kg', 'selected_material_kg', 'other_materials_not_extracted_kg', 'evidence']))

def electrode_masses(cfg):
    r = cfg['anode_mesh_to_active_ratio_from_Table2']
    if r < 0:
        raise ValueError('Invalid mesh ratio')
    cath = cfg['cells_per_module'] * cfg['cathode_plates_per_cell'] * cfg['cathode_plate_with_mesh_g'] / 1000
    anode_with = cfg['cells_per_module'] * cfg['anode_plates_per_cell'] * cfg['anode_plate_with_mesh_g'] / 1000
    active = anode_with / (1 + r)
    mesh = anode_with - active
    if cath + anode_with > cfg['module_mass_kg']:
        raise ValueError('Electrodes exceed module mass')
    return (cath, active, mesh)

def elemental_inventory(cfg, body):
    records = []
    raw = []
    for c, g in body.groupby('case'):
        material = g.groupby('material').kg_per_glider.sum()
        values = {'Al': material.Wrought_Al + material.Cast_Al, 'Cu': material.Cu}
        for m in MINERALS:
            records.append([c, 'glider', 'published_material_model_Al_proxy_and_Cu_only', m, values.get(m, np.nan), False])
    t = cfg['table6_mass_percent']
    for electrode, values in t.items():
        for m, value in values.items():
            raw.append([electrode, m, value, 'not_detected_not_zero' if value is None else 'measured_mass_percent', value * 10 if value is not None else np.nan])
        for m in MINERALS:
            v = values.get(m)
            records.append(['Korkmaz2018_' + electrode + '_per_kg', electrode, 'measured_composition_per_kg', m, v / 100 if v is not None else np.nan, False])
    cath, active, _ = electrode_masses(cfg)
    for scale, label, evidence in [(1, 'module', 'Table2_interpretation_electrode_subtotal'), (cfg['reference_pack_modules'], f"reference_{cfg['reference_pack_modules']}_modules", 'module_count_transfer_electrode_subtotal')]:
        for m in MINERALS:
            terms = []
            for name, mass in [('cathode_with_mesh', cath), ('anode_active_only', active)]:
                v = t[name].get(m)
                if v is not None:
                    terms.append(mass * v / 100)
            kg = sum(terms) * scale if terms else np.nan
            records.append(['Korkmaz2018_' + label + '_electrodes', 'electrode_subtotal', evidence, m, kg, False])
    result = pd.DataFrame(records, columns=['case', 'scope', 'evidence', 'mineral', 'quantified_kg_per_reference_unit', 'whole_vehicle_or_pack_complete'])
    return (result, pd.DataFrame(raw, columns=['electrode', 'element', 'mass_percent', 'status', 'g_per_kg_electrode']))

def run():
    cfg = json.loads((ROOT / 'input/hev_body_nimh_v3.json').read_text())
    body, summary = body_materials(cfg)
    elements, raw = elemental_inventory(cfg, body)
    cath, active, mesh = electrode_masses(cfg)
    audit = pd.DataFrame([['cathode_including_mesh_kg_per_module', cath, 'plate counts times plate mass'], ['anode_active_kg_per_module', active, 'conditional on mesh/active=0.28 from Table2'], ['anode_mesh_kg_per_module', mesh, 'composition excluded'], ['other_module_mass_kg', cfg['module_mass_kg'] - cath - active - mesh, 'casing/connectors/electrolyte; not elementally allocated']], columns=['quantity', 'kg', 'note'])
    sources = pd.read_csv(ROOT / 'input/hev_body_nimh_v3_sources.csv')
    out = ROOT / 'output/hev_body_nimh_v3'
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in [('body_materials', body), ('body_mass_audit', summary), ('NiMH_measured_electrode_composition', raw), ('NiMH_reconstruction_audit', audit), ('elemental_inventory_40_slots_PARTIAL', elements)]:
        frame.to_csv(out / f'{name}.csv', index=False)
    with pd.ExcelWriter(out / 'HEV_body_NiMH_checked.xlsx') as writer:
        for name, frame in [('出典と確認状況', sources), ('車体_材料kg', body), ('車体_質量範囲', summary), ('NiMH_実測組成', raw), ('NiMH_電極質量の再構成', audit), ('鉱物40枠_範囲限定', elements)]:
            frame.to_excel(writer, sheet_name=name, index=False)
    print(summary.to_string(index=False))
    print(elements.loc[elements.case.eq('Korkmaz2018_reference_28_modules_electrodes') & elements.mineral.isin(['Ni', 'Co', 'La', 'Ce', 'Nd', 'Pr']), ['mineral', 'quantified_kg_per_reference_unit']].to_string(index=False))
if __name__ == '__main__':
    run()
