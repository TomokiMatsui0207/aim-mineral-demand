"""Explicit, conditional solar capacity-basis sensitivity after metadata audit.
The reference remains v5. Ratios are REMPD design transfers, not AIM estimates
or statistical bounds. All retained solar coefficients are hypothetically treated
as DC-normalized in the transfer cases; their pooled original bases are unresolved.
"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent.parent
INPUT=ROOT/'output/solar_overlap_v5'
OUT=ROOT/'output/solar_capacity_basis_scenarios'
CASES={
 'nominal_matched_reference':1.0,
 'AIM_AC_Wei_as_DC_REMPD_rooftop_design_transfer':1.15,
 'AIM_AC_Wei_as_DC_REMPD_utility_design_transfer':1.28,
}

def run(input_dir=INPUT,output_dir=OUT):
    INPUT=Path(input_dir)
    OUT=Path(output_dir)
    OUT.mkdir(exist_ok=True)
    co=pd.read_csv(INPUT/'coefficients.csv');co=co.loc[co.technology.eq('SolarPV')]
    pa=pd.read_csv(INPUT/'power_activity.csv');pa=pa.loc[pa.technology.eq('SolarPV')]
    solar=pa.merge(co,on='technology',validate='many_to_many')
    solar['reference_solar_t_year']=solar.addition_GW_year*solar.intensity
    keys=['Sc','statistic','mineral','year']
    solar=solar[keys+['reference_solar_t_year']]
    osd=pd.read_csv(INPUT/'other_complement_annual_CONDITIONAL.csv')
    base=pd.read_csv(INPUT/'baseline2020_recalibration.csv')
    frames=[]
    for name,ratio in CASES.items():
        d=solar.copy();d['capacity_basis_case']=name;d['assumed_DC_AC_ratio']=ratio
        d['alternative_solar_t_year']=d.reference_solar_t_year*ratio
        d['solar_delta_t_year']=d.alternative_solar_t_year-d.reference_solar_t_year
        initial=d.loc[d.year.eq(2020),['Sc','statistic','mineral','solar_delta_t_year']].rename(columns={'solar_delta_t_year':'base_solar_delta_t_year'})
        d=osd.merge(d,on=keys,validate='many_to_one').merge(initial,on=['Sc','statistic','mineral'],validate='many_to_one')
        d['other_delta_t_year']=-d.base_solar_delta_t_year*d.growth_factor
        d['alternative_other_low_t_year']=d.raw_other_low_t_year+d.other_delta_t_year
        d['alternative_other_high_t_year']=d.raw_other_high_t_year+d.other_delta_t_year
        d['valid_nonnegative_reference_and_alternative_residual']=(~d.negative_base)&d.alternative_other_low_t_year.ge(0)
        d['conditional_total_delta_t_year']=(d.solar_delta_t_year+d.other_delta_t_year).where(d.valid_nonnegative_reference_and_alternative_residual)
        groups=['Sc','statistic','grid_case','mineral','capacity_basis_case']
        d=d.sort_values(groups+['year'])
        d['cumulative_conditional_total_delta_t']=d.groupby(groups).conditional_total_delta_t_year.transform(lambda s:s.cumsum(skipna=False))
        d['cumulative_solar_t']=d.groupby(groups).alternative_solar_t_year.cumsum()
        d['all_Wei_solar_coefficients_as_DC_is_hypothesis']=True
        d['constant_ratio_2020_2100_is_design_transfer']=True
        frames.append(d)
    results=pd.concat(frames,ignore_index=True)
    results.to_csv(OUT/'annual_solar_and_residual_basis_cases.csv.gz',index=False,compression='gzip')
    results.loc[results.year.eq(2100)].to_csv(OUT/'2100_cumulative_basis_cases.csv',index=False)
    assumptions=pd.DataFrame([{'case':name,'ratio':ratio,'AIM_capacity_basis':'unresolved; AC hypothesized for transfer cases','intensity_basis':'pooled Wei coefficient bases unresolved; DC hypothesized for transfer cases','ratio_source':'https://apps.openei.org/REMPD/overview/solar','not_observed_AIM_ratio':True,'not_statistical_bound':True} for name,ratio in CASES.items()])
    assumptions.to_csv(OUT/'case_assumptions.csv',index=False)
    with pd.ExcelWriter(OUT/'solar_capacity_basis_cases.xlsx') as w:
        assumptions.to_excel(w,sheet_name='ケースの前提と限界',index=False)
        results.loc[results.year.eq(2100)].to_excel(w,sheet_name='2100累積_残余再校正済',index=False)
        results.loc[results.year.isin([2020,2050,2100])].to_excel(w,sheet_name='主要年_年次需要と差分',index=False)
    source=ROOT/'originals/winsol_symbols.txt'
    meta={'reference_input':str(INPUT.relative_to(ROOT)),'symbol_metadata_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'winsol_cap_description':'Capacity in GW','DC_AC_explicit_in_symbol_metadata':False,'reference_overwritten':False,'actual_AIM_basis_resolved':False,'source_design_ratios_used_as_scenarios_only':[1.15,1.28],'all_solar_intensity_bases_verified':False,'residual_recalibration_applied':True,'case_probabilities_assigned':False}
    (OUT/'manifest.json').write_text(json.dumps(meta,indent=2))
    show=results.loc[results.year.eq(2100)&results.statistic.eq('average')&results.grid_case.eq('APS')&results.mineral.isin(['Al','Ag','Cu'])].copy()
    show['solar_Mt']=show.cumulative_solar_t/1e6;show['all_sector_delta_Mt']=show.cumulative_conditional_total_delta_t/1e6
    print(show[['Sc','mineral','assumed_DC_AC_ratio','solar_Mt','all_sector_delta_Mt']].to_string(index=False))
if __name__=='__main__':run()
