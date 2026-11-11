"""Literature-supported AB5 transfer reference; plated/mixed parts stay unknown."""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import json
import numpy as np
import pandas as pd
from integrate_wang_nimh_v4 import calculations
ROOT = Path(__file__).resolve().parent

def alloy_inventory(cfg):
    n = cfg['molar_coefficients']
    a = cfg['atomic_weights']
    mass = cfg['AB5_mass_from_Wang_S1_kg']
    if set(n) != set(a) or mass <= 0 or any((v <= 0 for v in [*n.values(), *a.values()])):
        raise ValueError('Invalid alloy inputs')
    denominator = sum((n[m] * a[m] for m in n))
    return pd.DataFrame([{'mineral': m, 'molar_coefficient': n[m], 'atomic_weight': a[m], 'mass_fraction': n[m] * a[m] / denominator, 'alloy_contribution_kg': mass * n[m] * a[m] / denominator, 'evidence': 'DOE2011_literature_model_transferred_to_Wang_AB5_mass; not_same_pack_measurement'} for m in n])

def coated_foil_ni_fraction(total_thickness, ni_face1, ni_face2, rho_ni, rho_substrate):
    """Flat uniform foil; total_thickness INCLUDES both coatings.

    Explicit dimensions and densities required, no guessed default values.
    This must not be applied to bolts, pillars, or unknown adopted parts.
    """
    values = np.asarray([total_thickness, ni_face1, ni_face2, rho_ni, rho_substrate], float)
    if not np.isfinite(values).all() or total_thickness <= 0 or min(ni_face1, ni_face2) < 0 or (min(rho_ni, rho_substrate) <= 0):
        raise ValueError('Invalid coating geometry')
    substrate = total_thickness - ni_face1 - ni_face2
    if substrate <= 0:
        raise ValueError('Coatings consume all foil thickness')
    return rho_ni * (ni_face1 + ni_face2) / (rho_ni * (ni_face1 + ni_face2) + rho_substrate * substrate)

def run():
    inp = ROOT / 'input'
    out = ROOT / 'output/nimh_AB5_v5'
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((inp / 'nimh_AB5_v5.json').read_text())
    alloy = alloy_inventory(cfg)
    s1 = pd.read_csv(inp / 'wang2021_S1_transcribed.csv')
    s2 = pd.read_csv(inp / 'wang2021_S2_transcribed.csv')
    base, details, audit, unallocated = calculations(s1, s2)
    actual = s1.loc[s1.material.eq('AB5 alloy'), 'mass_kg'].sum()
    if not np.isclose(actual, cfg['AB5_mass_from_Wang_S1_kg']):
        raise ValueError('Alloy mass inconsistent with S1')
    result = base[['mineral', 'quantified_subtotal_kg_per_source_pack']].rename(columns={'quantified_subtotal_kg_per_source_pack': 'Wang_source_rows_subtotal_kg'})
    result = result.merge(alloy[['mineral', 'alloy_contribution_kg']], on='mineral', how='left', validate='one_to_one')
    result['DOE_AB5_transfer_reference_subtotal_kg'] = result[['Wang_source_rows_subtotal_kg', 'alloy_contribution_kg']].sum(axis=1, min_count=1)
    result['whole_pack_element_kg'] = np.nan
    result['same_pack_composition_confirmed'] = False
    result['world_HEV_representative'] = False
    result['case'] = cfg['case']
    remaining = unallocated.loc[~unallocated.material.eq('AB5 alloy')].copy()
    metals = remaining.loc[remaining.material.isin(['Fe-Ni plating', 'Cu-Ni plating', 'Fe/Plastic', 'Fe/cable', 'Plastic/Cooper [source spelling]'])].copy()
    metals['required_data'] = metals.material.map({'Fe-Ni plating': 'adopted substrate composition and coating mass/thickness for this part', 'Cu-Ni plating': 'adopted Cu substrate and Ni coating mass ratio', 'Fe/Plastic': 'separate metal and polymer masses', 'Fe/cable': 'separate steel,cable conductor,insulation and connectors', 'Plastic/Cooper [source spelling]': 'separate plastic and copper-bearing parts; source spelling Cooper'})
    if not np.isclose(metals.mass_kg.sum(), 9.78):
        raise ValueError('Mixed/plated material mass audit failed')
    decisions = pd.read_csv(inp / 'nimh_v5_research_sources.csv')
    for name, frame in [('AB5_molar_to_mass_reference', alloy), ('source_only_vs_AB5_TRANSFER_40_slots', result), ('remaining_metal_bearing_parts', metals), ('remaining_unallocated_materials', remaining), ('Wang_S1_S2_audit', audit)]:
        frame.to_csv(out / f'{name}.csv', index=False)
    with pd.ExcelWriter(out / 'NiMH_AB5_research_update.xlsx') as writer:
        for name, frame in [('調査結果と出典', decisions), ('AB5_モル比から質量比', alloy), ('原表小計と代用ケース', result), ('未配分金属部材9_78kg', metals), ('その他未配分材料', remaining), ('S1_S2整合確認', audit)]:
            frame.to_excel(writer, sheet_name=name, index=False)
    print(result.loc[result.mineral.isin(['La', 'Ce', 'Pr', 'Nd', 'Ni', 'Co', 'Mn', 'Al']), ['mineral', 'Wang_source_rows_subtotal_kg', 'alloy_contribution_kg', 'DOE_AB5_transfer_reference_subtotal_kg']].to_string(index=False))
    print('Remaining plated/mixed metal-bearing parts:', metals.mass_kg.sum(), 'kg')
if __name__ == '__main__':
    run()
