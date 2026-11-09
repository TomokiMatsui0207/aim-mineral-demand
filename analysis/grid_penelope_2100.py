"""Penelope grid Cu/Al anchors plus explicitly assumed post-2050 AIM scaling."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from model import MINERALS
ROOT=Path(__file__).resolve().parent.parent

def calculate(anchors,aim):
    anchors=anchors.copy()
    if set(anchors.mineral)!={'Cu','Al'} or set(anchors.Unit)!={'t/yr'}:
        raise ValueError('Expected Cu/Al annual tonnes only')
    if anchors.duplicated(['Scenario','mineral']).any():raise ValueError('Duplicate anchors')
    if set(anchors.Scenario)!={'SPS','APS','NZE'} or len(anchors)!=6:raise ValueError('Incomplete anchors')
    a=aim.loc[aim.Sr.eq('World') & aim.Sv.eq('Fin_Ene_Ele')].copy()
    if a.duplicated(['Sc','Y5']).any():raise ValueError('Duplicate electricity driver')
    if not np.isfinite(a.value).all() or (a.value<=0).any():raise ValueError('Invalid electricity driver')
    rows=[]
    anchor_years=np.array([2022,2025,2030,2035,2040,2045,2050])
    for sc,g in a.groupby('Sc'):
        g=g.sort_values('Y5')
        if g.Y5.min()>2020 or g.Y5.max()<2100 or 2050 not in set(g.Y5):raise ValueError('Insufficient electricity coverage')
        driver=np.interp(np.arange(2020,2101),g.Y5,g.value)
        e2050=float(g.loc[g.Y5.eq(2050),'value'].iloc[0])
        for _,r in anchors.iterrows():
            vals=np.array([r[str(y)] for y in anchor_years],dtype=float)
            if not np.isfinite(vals).all() or (vals<0).any():raise ValueError('Invalid anchors')
            # Correct year-spacing extrapolation: 2020 is 2 years before2022,
            # while2025 is 3 years after2022. Legacy code used a different rule.
            v2020=max(0.,vals[0]-2*(vals[1]-vals[0])/3)
            ys=np.r_[2020,anchor_years]; vs=np.r_[v2020,vals]
            for case in ['AIM_electricity_ratio','hold_2050_comparator']:
                for year in range(2020,2101):
                    demand=float(np.interp(year,ys,vs)) if year<=2050 else float(vals[-1]*(driver[year-2020]/e2050 if case=='AIM_electricity_ratio' else 1))
                    rows.append(dict(Sc=sc,region='World',source_scenario=r.Scenario,extension_case=case,mineral=r.mineral,year=year,demand_t_year=demand,electricity_ratio_to_2050=driver[year-2020]/e2050,status='source_anchor' if year in anchor_years else 'backcast_corrected_year_spacing' if year<2022 else 'interpolated' if year<=2050 else 'post2050_ASSUMPTION',accounting='IEA_network_demand_as_transcribed_not_verified_primary_or_gross',aggregation_rule='replace_other_grid_CuAl_estimate_do_not_add'))
    result=pd.DataFrame(rows)
    if result.empty:raise ValueError('No World electricity driver')
    return result

def main():
    out=ROOT/'output/grid_penelope_2100';out.mkdir(parents=True,exist_ok=True)
    anchors=pd.read_csv(ROOT/'input/imported/penelope_Demand_Network.csv')
    aim=pd.read_csv(ROOT/'input/AIM_World.csv.gz')
    result=calculate(anchors,aim)
    keys=['Sc','region','source_scenario','extension_case','mineral']
    result['cumulative_discrete_2020_inclusive_t']=result.groupby(keys).demand_t_year.cumsum()
    grid40=result.drop(columns=['cumulative_discrete_2020_inclusive_t']).set_index(keys+['year'])
    slots=pd.MultiIndex.from_product([sorted(result.Sc.unique()),['World'],['APS','NZE','SPS'],sorted(result.extension_case.unique()),MINERALS,range(2020,2101)],names=keys+['year'])
    grid40=grid40.reindex(slots).reset_index()
    grid40['coverage']=np.where(grid40.mineral.isin(['Cu','Al']),'CuAl_direct_demand_method','unquantified_NOT_ZERO')
    endpoints=result[result.year.isin([2020,2022,2050,2100])]
    result.to_csv(out/'grid_CuAl_annual_2020_2100.csv',index=False)
    grid40.to_csv(out/'grid_40_slots_with_unknowns.csv',index=False)
    endpoints.to_csv(out/'checkpoints.csv',index=False)
    baseline_path=ROOT/'output/reconciled40_CONDITIONAL/baseline_40_CONDITIONAL.csv'
    if baseline_path.exists():
        baseline=pd.read_csv(baseline_path)
        now=result.loc[result.year.eq(2020)&result.extension_case.eq('AIM_electricity_ratio'),['Sc','mineral','source_scenario','demand_t_year']]
        audit=baseline.loc[baseline.mineral.isin(['Cu','Al'])].merge(now,left_on=['Sc','mineral','grid_case'],right_on=['Sc','mineral','source_scenario'],validate='many_to_one')
        if len(audit)!=len(baseline.loc[baseline.mineral.isin(['Cu','Al'])]):raise ValueError('Unmatched baseline grid deductions')
        audit['difference_t_year']=audit.network_t_year-audit.demand_t_year
        if audit.difference_t_year.abs().max()>1e-6:raise ValueError('Baseline residual recalibration required')
        audit.to_csv(out/'baseline_alignment_audit.csv',index=False)
    with pd.ExcelWriter(out/'grid_penelope_2100.xlsx') as w:
        result.to_excel(w,sheet_name='CuAl_annual',index=False)
        grid40.to_excel(w,sheet_name='40_mineral_coverage',index=False)
        endpoints.to_excel(w,sheet_name='checkpoints',index=False)
        anchors.to_excel(w,sheet_name='original_anchors',index=False)
    manifest={'driver':'Fin_Ene_Ele, World; linear interpolation between AIM years','main_extension':'D(y)=D(2050)*E(y)/E(2050), y>2050; assumed not Penelope original','scenario_mapping':'all3 IEA cases crossed with all AIM scenarios; no asserted equivalence','2020_rule':'2022-2/3*(2025-2022), clip at0; corrected backcast not observation','cumulative':'sum annual values2020 through year inclusive; not trapezoid convention','other38':'NA, not zero; equipment supplementation still unquantified','replacement':'not decomposed; source IEA scope inherited; do not add generic stock/lifetime replacement','existing_results':'not overwritten; replace previous grid CuAl rows when integrating; no automatic OSD change','rows':len(result)}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(endpoints.loc[endpoints.year.eq(2100),['Sc','source_scenario','extension_case','mineral','demand_t_year']].to_string(index=False))
if __name__=='__main__':main()
