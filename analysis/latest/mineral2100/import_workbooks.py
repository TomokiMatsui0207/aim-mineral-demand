"""Extract source workbooks without silently completing unreported minerals."""
from pathlib import Path as _SnapshotPath
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
from model import MINERALS
NAMES = dict(zip('Silver Aluminum Boron Carbon Cadmium Cerium Cobalt Chromium Copper Dysprosium Iron Gallium Germanium Hafnium Indium Iridium Lanthanum Lithium Magnesium Manganese Molybdenum Niobium Neodymium Nickel Lead Praseodymium Platinum Scandium Selenium Silicon Tin Tantalum Terbium Tellurium Titanium Vanadium Tungsten Yttrium Zinc Zirconium'.split(), MINERALS))
NAMES['Praesodymium'] = 'Pr'

def extract(data, wei, out):
    out.mkdir(parents=True, exist_ok=True)
    ev = data / 'EV_MI_MS_Recycling.xlsx'
    prod = data / 'Prod&Demand_Other_Sectors.xlsx'
    rows = []
    for sheet, component, unit in [('MI_Vehicle', 'vehicle_body', 'vehicle'), ('MI_Battery', 'vehicle_battery', 'kWh'), ('MI_Motor', 'vehicle_motor', 'vehicle')]:
        table = pd.read_excel(ev, sheet)
        techcols = list(table.columns[1:table.columns.get_loc('Unit')])
        for _, r in table.iterrows():
            name = str(r.iloc[0]).strip()
            if name not in NAMES:
                raise ValueError(f'Unknown mineral: {name}')
            for tech in techcols:
                value = pd.to_numeric(r[tech], errors='raise')
                rows.append([component, tech, NAMES[name], unit, value / 1000000.0 if pd.notna(value) else np.nan, 'explicit_source_zero' if value == 0 else 'reported', sheet, str(r.get('Ref', r.get('Ref1', '')))])
    ints = pd.DataFrame(rows, columns=['component', 'technology', 'mineral', 'activity_unit', 't_per_unit', 'status', 'sheet', 'reference'])
    ints.to_csv(out / 'penelope_intensities_long.csv', index=False)
    coverage = []
    for component, sub in ints.groupby('component'):
        found = set(sub.loc[sub.t_per_unit.notna(), 'mineral'])
        for m in MINERALS:
            coverage.append([component, m, m in found, 'reported (including explicit zeros)' if m in found else 'unreported; not zero'])
    pd.DataFrame(coverage, columns=['component', 'mineral', 'has_reported_coefficient', 'status']).to_csv(out / 'ev_40_mineral_coverage.csv', index=False)
    for sheet in ['Demand_Network', 'Demand_Storage', 'OSD_litt', 'Prod_2020_Beta', 'Recovery_Rates', 'Metal_Intensity_Reduction']:
        table = pd.read_excel(prod, sheet)
        if table.columns[0] == 'Metal':
            table.insert(1, 'mineral', table.Metal.map(NAMES))
        table.to_csv(out / ('penelope_' + sheet + '.csv'), index=False)
    for sheet in ['Vehicle_Stat', 'MS_Motor', 'MS_Battery', 'MS_Vehicle', 'Vehicle_Stock', 'Recycling_2020_Rates', 'Recycling_Evolution']:
        pd.read_excel(ev, sheet).to_csv(out / ('penelope_' + sheet + '.csv'), index=False)
    raw = pd.read_excel(wei, 'S5. Mineral_intensity')
    raw.insert(0, 'excel_row', raw.index + 2)
    raw.to_csv(out / 'wei_S5_all_rows.csv', index=False)
    tidy = raw.loc[raw.iloc[:, 5].astype(str).str.strip().isin(MINERALS + ['Steel'])].copy()
    tidy = pd.DataFrame({'excel_row': tidy.excel_row, 'category': tidy.iloc[:, 2], 'technology': tidy.iloc[:, 3], 'material': tidy.iloc[:, 5].astype(str).str.strip(), 'reported_average': pd.to_numeric(tidy.iloc[:, 7], errors='coerce'), 'reported_minimum': pd.to_numeric(tidy.iloc[:, 8], errors='coerce'), 'reference': tidy.iloc[:, 9]})
    tidy['status'] = np.where(tidy.reported_average.notna(), 'reported_average', 'no_average_in_this_row')
    tidy['warning'] = 'No averaging across rows; no zero fill; Steel retained separately; verify category units'
    tidy.to_csv(out / 'wei_intensity_rows.csv', index=False)
    for sheet in ['S4. life_year', 'S6. recycle_rate', 'S7. proportion in energy system', 'S11 Market share']:
        pd.read_excel(wei, sheet).to_csv(out / ('wei_' + sheet.split('.')[0].replace(' ', '_') + '.csv'), index=False)
    ms = pd.read_excel(ev, 'MS_Battery')
    years = [c for c in ms if isinstance(c, (int, float)) and 1900 <= c <= 2100]
    a = ms.set_index('Battery_type')[years]
    a.columns = a.columns.astype(int)
    a = a.reindex(columns=range(2020, 2101)).interpolate(axis=1, limit_area='inside')
    a.loc[:, 2051:2100] = np.repeat(a[[2050]].to_numpy(), 50, axis=1)
    long = a.rename_axis(columns='year').stack().rename('share').reset_index()
    long['status'] = np.where(long.year > 2050, '2050_share_held_constant_ASSUMPTION', 'source_or_linear_interpolation')
    long.to_csv(out / 'battery_chemistry_shares_2020_2100_ASSUMPTION.csv', index=False)
    totals = long.groupby('year', as_index=False).share.sum()
    totals['deviation_from_one'] = totals.share - 1
    totals['normalized'] = False
    totals.to_csv(out / 'battery_share_sum_audit.csv', index=False)
    osd = pd.read_excel(prod, 'OSD_litt')
    project = []
    for rowid, r in osd.iterrows():
        anchors = pd.Series({int(y): float(r.loc[y]) for y in osd.columns if str(y).isdigit() and pd.notna(r.loc[y])})
        for year in range(2020, 2051):
            value = np.interp(year, anchors.index, anchors.values) if len(anchors) and anchors.index.min() <= year <= anchors.index.max() else np.nan
            project.append([rowid, NAMES.get(str(r.Metal)), r.Scenario, year, value, 'source_or_interpolation_no_AIM_scenario_assignment'])
    hist = pd.DataFrame(project, columns=['source_row', 'mineral', 'source_scenario', 'year', 'demand_t_year', 'status'])
    hist.to_csv(out / 'other_sector_literature_annual_2020_2050.csv', index=False)
    drivers_path = Path(__file__).parent / 'output' / 'annual_drivers.csv'
    if drivers_path.exists():
        drivers = pd.read_csv(drivers_path)
        projections = []
        network = []
        for sc, d in drivers.groupby('Sc'):
            d = d.set_index('year')
            for _, r in hist.loc[hist.year.eq(2050) & hist.demand_t_year.notna()].iterrows():
                for reduction in [0.0, 0.005, 0.01]:
                    for year in range(2051, 2101):
                        demand = r.demand_t_year * d.loc[year, 'GDP_PPP_billion_2010USD'] / d.loc[2050, 'GDP_PPP_billion_2010USD'] * (1 - reduction) ** (year - 2050)
                        projections.append([sc, r.source_row, r.mineral, r.source_scenario, year, reduction, demand, 'literature_2050_times_AIM_GDP_ASSUMPTION; scenarios_not_matched'])
            for _, r in pd.read_excel(prod, 'Demand_Network').iterrows():
                yearcols = {int(c): c for c in r.index if str(c).isdigit()}
                if 2050 not in yearcols:
                    raise ValueError('Missing 2050 grid anchor')
                for elasticity in [0.5, 1.0]:
                    for year in range(2051, 2101):
                        demand = float(r.loc[yearcols[2050]]) * (d.loc[year, 'electricity_original_unit'] / d.loc[2050, 'electricity_original_unit']) ** elasticity
                        network.append([sc, NAMES[str(r.Metal)], r.Scenario, year, elasticity, demand, 'annual_demand_scaled_after_2050_ASSUMPTION; do_not_add_equipment_based_grid_case'])
        pd.DataFrame(projections, columns=['Sc', 'source_row', 'mineral', 'source_scenario', 'year', 'annual_intensity_reduction_assumption', 'demand_t_year', 'status']).to_csv(out / 'other_sector_2051_2100_SENSITIVITY.csv', index=False)
        pd.DataFrame(network, columns=['Sc', 'mineral', 'source_scenario', 'year', 'electricity_elasticity_assumption', 'demand_t_year', 'status']).to_csv(out / 'grid_Cu_Al_2051_2100_SENSITIVITY.csv', index=False)
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--wei', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path(__file__).parent / 'input' / 'imported')
    a = p.parse_args()
    extract(a.data, a.wei, a.out)
