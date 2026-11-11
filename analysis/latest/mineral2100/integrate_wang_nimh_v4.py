"""Audit uploaded Wang S1/S2; do not equate LCA substitute mass with elements."""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import pandas as pd
import numpy as np
from model import MINERALS
ROOT = Path(__file__).resolve().parent
ATOMIC = {'Ni': 58.6934, 'Co': 58.933194, 'Zn': 65.38, 'O': 15.999, 'H': 1.008}

def calculations(s1, s2):
    if s1.component.duplicated().any() or len(s1) != 24:
        raise ValueError('Unexpected S1 table')
    if len(s2) != 9 or s2.shipment_category.duplicated().any():
        raise ValueError('Unexpected S2 table')
    if not np.isfinite(s1.mass_kg).all() or (s1.mass_kg < 0).any():
        raise ValueError('Invalid S1 masses')
    if not np.isfinite(s2.mass_kg).all() or (s2.mass_kg < 0).any():
        raise ValueError('Invalid S2 masses')
    m = s1.set_index('component').mass_kg
    masses = s1.groupby('scope').mass_kg.sum()
    if not np.isclose(masses['module'], 29.12) or not np.isclose(masses['case'], 9.95):
        raise ValueError('S1 totals disagree')
    if not np.isclose(s2.mass_kg.sum(), 39.07):
        raise ValueError('S2 total disagrees')
    details = []
    for component, element, denominator in [('Positive electrode active material Ni', 'Ni', ATOMIC['Ni'] + 2 * (ATOMIC['O'] + ATOMIC['H'])), ('Positive electrode active material Co', 'Co', ATOMIC['Co'] + 2 * (ATOMIC['O'] + ATOMIC['H'])), ('Positive electrode active material Zn', 'Zn', ATOMIC['Zn'] + ATOMIC['O'])]:
        fraction = ATOMIC[element] / denominator
        details.append([component, element, m[component], fraction, m[component] * fraction, 'chemical_formula_reconstruction_assuming_S1_material_mass'])
    for component in ['Negative electrode plate', 'Positive electrode collector', 'Plate for positive electrode']:
        details.append([component, 'Ni', m[component], 1.0, m[component], 'reported_Ni_material_as_Ni_proxy; no_x3_mass_multiplier'])
    for component, element in [('Backing plate', 'Fe'), ('Battery case cover upper part', 'Fe'), ('Battery case cover side part', 'Fe'), ('Reinforcing materials', 'Al')]:
        details.append([component, element, m[component], 1.0, m[component], 'reported_metal_material_as_element_proxy_not_purity_assay'])
    details = pd.DataFrame(details, columns=['component', 'mineral', 'source_material_kg', 'element_mass_fraction_assumed', 'quantified_element_kg', 'evidence'])
    values = details.groupby('mineral').quantified_element_kg.sum()
    inventory = pd.DataFrame({'mineral': MINERALS})
    inventory['quantified_subtotal_kg_per_source_pack'] = inventory.mineral.map(values)
    inventory['whole_pack_kg_per_element'] = np.nan
    inventory['whole_pack_complete'] = False
    inventory['scope'] = 'S1_stoichiometric_and_reported_metal_proxy_subtotal; unallocated_parts_remain'
    audit = [['module_total', masses['module'], 29.12, True, 'S1 modules as a set, not a single module'], ['case_total', masses['case'], 9.95, True, 'S1 case assembly'], ['pack_total', s1.mass_kg.sum(), 39.07, True, 'source recipe; no extra x28'], ['S2_shipment_total', s2.mass_kg.sum(), 39.07, True, 'shipment categories, not elemental assay']]
    s2map = s2.set_index('shipment_category').mass_kg
    ni_proxy = m['Positive electrode active material Ni'] + m['Negative electrode plate'] + m['Positive electrode collector'] + m['Plate for positive electrode']
    audit.append(['S2_Nickel_aggregation', ni_proxy, s2map['Nickel'], np.isclose(ni_proxy, s2map['Nickel']), 'includes full Ni(OH)2 row mass; not elemental Ni'])
    fe_named = s1.loc[s1.material.isin(['Fe-Ni plating', 'Fe']) & s1.scope.eq('module')].mass_kg.sum()
    audit.append(['S2_steel_vs_S1_module_Fe_named', fe_named, s2map['Steel component'], False, 'difference equals 0.33kg ZnO row; cause not documented; do not reclassify Zn as Fe'])
    unresolved = s1.loc[~s1.component.isin(details.component.unique())].copy()
    return (inventory, details, pd.DataFrame(audit, columns=['check', 'reconstructed_kg', 'source_comparison_kg', 'matches', 'note']), unresolved)

def run():
    inp = ROOT / 'input'
    out = ROOT / 'output/wang_nimh_v4'
    out.mkdir(parents=True, exist_ok=True)
    s1 = pd.read_csv(inp / 'wang2021_S1_transcribed.csv')
    s2 = pd.read_csv(inp / 'wang2021_S2_transcribed.csv')
    inventory, details, audit, unresolved = calculations(s1, s2)
    sources = pd.read_csv(inp / 'wang2021_uploaded_sources.csv')
    for name, frame in [('elemental_40_slots_PARTIAL', inventory), ('element_conversion_details', details), ('S1_S2_mass_and_category_audit', audit), ('unallocated_material_components', unresolved)]:
        frame.to_csv(out / f'{name}.csv', index=False)
    with pd.ExcelWriter(out / 'Wang_NiMH_source_checked.xlsx') as writer:
        for name, frame in [('S1_材料とLCA代替材', s1), ('S2_出荷カテゴリ', s2), ('質量とカテゴリ整合確認', audit), ('元素換算の内訳', details), ('40鉱物_未完全部分計', inventory), ('未配分の構成材料', unresolved), ('原本とSHA256', sources)]:
            frame.to_excel(writer, sheet_name=name, index=False)
    print(inventory.dropna(subset=['quantified_subtotal_kg_per_source_pack']).to_string(index=False))
    print(audit.to_string(index=False))
if __name__ == '__main__':
    run()
