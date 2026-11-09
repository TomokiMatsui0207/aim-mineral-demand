"""Mineral-specific PV overlap policy; nominal capacity basis still conditional.
Technology-specific Al/Steel/Ag/Sn replace the corresponding common estimate.
CIGS absorber Cu is additional to common wiring/BOS Cu. This is a harmonization
policy supported by component descriptions, not reconstruction of all source LCIs.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
import integrate_all_sectors_conditional as legacy
import harmonize_energy_v2 as v2
import integrate_energy_defined_v4 as v4
import integrate_energy_native_v3 as v3
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'output/solar_overlap_v5'
REPLACE={'Al','Fe','Ag','Sn'}

def convert_capacity(value,from_basis,to_basis,dc_ac_ratio=None):
    """Convert only explicitly declared bases; no silent AC/DC equality."""
    if from_basis not in {'DC','AC'} or to_basis not in {'DC','AC'}:
        raise ValueError('Capacity basis is unresolved')
    if from_basis==to_basis:return value
    if dc_ac_ratio is None or not np.isfinite(dc_ac_ratio) or dc_ac_ratio<=0:
        raise ValueError('Cross-basis conversion requires a documented DC/AC ratio')
    return value*dc_ac_ratio if from_basis=='AC' else value/dc_ac_ratio

def coefficients(stat):
    c=v4.coefficients(stat)
    replacement=v2.coefficient_table(stat,solar_mode='replacement_comparator')
    mask=c.sector.eq('power')&c.technology.eq('SolarPV')&c.mineral.isin(REPLACE)
    keys=['sector','technology','mineral']
    for idx,row in c.loc[mask].iterrows():
        source=replacement.loc[(replacement[keys]==row[keys]).all(axis=1)].iloc[0]
        for col in ['intensity','elemental_component_t_GW','steel_material_part_t_GW']:
            c.at[idx,col]=source[col]
        c.at[idx,'scope_assumption']='specific_replaces_common_for_same_material; missing_subtype_falls_back_to_common; harmonization_not_full_LCI_rebuild'
    solar=c.sector.eq('power')&c.technology.eq('SolarPV')
    c.loc[solar&c.mineral.eq('Cu'),'scope_assumption']='common_wiring_BOS_Cu_plus_CIGS_absorber_Cu; not_universal_replacement'
    c['capacity_basis_status']='unchanged_non_solar'
    c.loc[solar,'capacity_basis_status']='AIM_DC_AC_unresolved; Wei_averages_mix_sources; no_universal_ILR_applied'
    return c

def run():
    OUT.mkdir(exist_ok=True)
    tables=legacy.build(coefficients,v2.power_activity,lambda aim:v3.activities(aim,audit_dir=OUT))
    names=['all_sectors_CONDITIONAL','explicit_sector_annual','explicit_sector_detail','grid_CuAl_annual','other_complement_annual_CONDITIONAL','baseline2020_recalibration','coefficients','power_activity','power_activity_audit','hydrogen_native_activity','battery_native_activity']
    for name,frame in zip(names,tables):
        compressed=name in ['all_sectors_CONDITIONAL','explicit_sector_detail']
        frame.to_csv(OUT/(name+('.csv.gz' if compressed else '.csv')),index=False,compression='gzip' if compressed else None)
    before=pd.read_csv(v4.OUT/'explicit_sector_annual.csv').groupby(['Sc','statistic','sector','mineral'],as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year':'v4_cumulative_t'})
    after=tables[1].groupby(['Sc','statistic','sector','mineral'],as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year':'v5_cumulative_t'})
    cmp=before.merge(after,on=['Sc','statistic','sector','mineral'],validate='one_to_one');cmp['change_t']=cmp.v5_cumulative_t-cmp.v4_cumulative_t
    cmp.to_csv(OUT/'energy_cumulative_change_vs_v4.csv',index=False)
    base_old=pd.read_csv(v4.OUT/'baseline2020_recalibration.csv')
    base_new=tables[5].merge(base_old,on=['Sc','statistic','grid_case','mineral','year'],suffixes=('_v5','_v4'),validate='one_to_one')
    base_new['other_base_change_low_t_year']=base_new.raw_residual_low_t_year_v5-base_new.raw_residual_low_t_year_v4
    base_new.to_csv(OUT/'other_base_recalibration_change.csv',index=False)
    keys=['Sc','statistic','grid_case','case','year','mineral']
    old=pd.read_csv(v4.OUT/'all_sectors_CONDITIONAL.csv.gz')
    delta=tables[0][keys+['conditional_total_low_t_year']].merge(old[keys+['conditional_total_low_t_year']],on=keys,suffixes=('_v5','_v4'),validate='one_to_one')
    delta['total_delta_t_year']=delta.conditional_total_low_t_year_v5-delta.conditional_total_low_t_year_v4
    delta=delta.sort_values(keys)
    delta['cumulative_delta_t']=delta.groupby([k for k in keys if k!='year']).total_delta_t_year.transform(lambda s:s.cumsum(skipna=False))
    delta.to_csv(OUT/'all_sectors_change_with_recalibration.csv.gz',index=False,compression='gzip')
    meta={'overlap_policy':'specific_replaces_common_Al_Fe_Ag_Sn; additive_common_plus_absorber_Cu','technology_specific_coverage_complete':False,'AIM_PV_DC_AC_confirmed':False,'universal_DC_AC_ratio_applied':False,'REMPD_reference_basis':'module_rated_DC; applies_to_that_source_not_all_Wei_means','Sn_scope_verified_in_each_underlying_reference':False,'all40_inventory_complete':False,'historical_results_overwritten':False}
    (OUT/'manifest.json').write_text(json.dumps(meta,indent=2))
    ledger=pd.DataFrame([
      {'topic':'Al/steel','decision':'replace for subtype with reported value; common fallback otherwise','evidence':'REMPD includes frames/racking/transformers/BOS; JRC lists Al/steel structural roles. Potential same-component overlap; exact pooled-source LCI not rebuilt.','source':'https://apps.openei.org/REMPD/overview/solar'},
      {'topic':'Ag','decision':'technology-specific estimate replaces common estimate','evidence':'JRC lists Ag as c-Si cell material. Treat generic and subtype as alternative estimates, not different components; nominal source basis remains conditional.','source':'https://publications.jrc.ec.europa.eu/repository/bitstream/JRC119941/rms_for_wind_and_solar_published_v2.pdf'},
      {'topic':'Cu','decision':'common plus CIGS absorber','evidence':'JRC distinguishes general wiring/cabling/inverters/transformers/ribbons from CIGS-specific Cu. Other Cu omissions are not proven physical zeros.','source':'https://publications.jrc.ec.europa.eu/repository/bitstream/JRC119941/rms_for_wind_and_solar_published_v2.pdf'},
      {'topic':'Sn','decision':'conditional specific-over-common policy','evidence':'REMPD includes interconnects and electronics. Exact scope of every Wei Sn reference not confirmed, so retain old additive output for sensitivity.','source':'https://apps.openei.org/REMPD/overview/solar'},
      {'topic':'DC/AC','decision':'no automatic conversion; explicit converter rejects unknown basis','evidence':'REMPD module-rated DC; utility ILR1.28, commercial/residential1.15 are source design examples, not AIM world estimates. AIM loads winsolpotential2.gdx; producer definitions not available.','source':'https://apps.openei.org/REMPD/overview/solar'}
    ])
    ledger.to_csv(OUT/'source_scope_decisions.csv',index=False)
    with pd.ExcelWriter(OUT/'solar_overlap_revision_v5.xlsx') as w:
        ledger.to_excel(w,sheet_name='出典と重複処理',index=False)
        cmp.to_excel(w,sheet_name='エネルギー累積_変更前後',index=False)
        tables[6].loc[tables[6].technology.eq('SolarPV')].to_excel(w,sheet_name='PV原単位_修正後',index=False)
        base_new.to_excel(w,sheet_name='その他部門_基準年変更',index=False)
        delta.loc[delta.year.eq(2100)].to_excel(w,sheet_name='全部門累積差_残余再校正済',index=False)
    print(cmp.loc[cmp.statistic.eq('average')&cmp.sector.eq('power')&cmp.mineral.isin(['Al','Fe','Ag','Sn','Cu'])].to_string(index=False))
if __name__=='__main__':run()
