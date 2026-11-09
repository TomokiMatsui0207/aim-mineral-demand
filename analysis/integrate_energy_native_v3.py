"""Revision from uploaded native energy coefficients and physical-capacity flows.
12 h is an energy-budget/power ratio; equating it to rated energy capacity
needs cycle, efficiency and SOC definitions. Retain it as an alternative.
"""
import hashlib,json,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import harmonize_energy_v2 as v2
import integrate_all_sectors_conditional as legacy
from resolve_energy_basis import WEI_HOURS
ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'input/energy_unit_check'
ARCHIVE=ROOT/'originals/energy_unit_check.zip'
OUT=ROOT/'output/harmonized_energy_native_v3'

def audit_duration():
    pairs=[]
    with zipfile.ZipFile(ARCHIVE) as z:
        for sc in ['Baseline','300C']:
            with z.open(f'exports/energy_inputs_{sc}.csv') as f:
                inp=pd.read_csv(f)
            with z.open(f'exports/energy_outputs_{sc}.csv') as f:
                out=pd.read_csv(f)
            a=inp.loc[inp.technology.str.startswith('ELEBAT_')&inp.carrier.str.startswith('ESC_BAT')&inp.effective_input_per_activity.abs().gt(1e-9)].copy()
            b=out.loc[out.technology.eq('ELECAP_BAT')&out.service.str.startswith('ESC_BAT')&out.effective_output_per_activity.gt(1e-9)].copy()
            a=a.rename(columns={'carrier':'constraint','effective_input_per_activity':'dispatch_energy_coefficient'})
            b=b.rename(columns={'service':'constraint','effective_output_per_activity':'capacity_energy_coefficient'})
            keys=['Sc','region','year','constraint']
            if b.duplicated(keys).any():raise ValueError('Ambiguous storage capacity constraint')
            d=a[keys+['technology','dispatch_energy_coefficient']].merge(b[keys+['capacity_energy_coefficient']],on=keys,validate='many_to_one')
            if len(d)!=len(a):raise ValueError('Unmatched storage energy constraints')
            d['inferred_storage_hours']=d.capacity_energy_coefficient/-d.dispatch_energy_coefficient
            np.testing.assert_allclose(d.inferred_storage_hours,12,atol=1e-8)
            # Power availability is 1 capacity unit per 1 dispatch unit.
            p=out.loc[out.technology.eq('ELECAP_BAT')&out.service.str.startswith('EE_BAT')&out.effective_output_per_activity.gt(1e-9)]
            q=inp.loc[inp.technology.str.startswith('ELEBAT_')&inp.carrier.str.startswith('EE_BAT')&inp.effective_input_per_activity.abs().gt(1e-9)]
            np.testing.assert_allclose(p.effective_output_per_activity,1,atol=1e-10)
            np.testing.assert_allclose(q.effective_input_per_activity,-1,atol=1e-10)
            pairs.append(d)
    result=pd.concat(pairs,ignore_index=True)
    result.to_csv(OUT/'battery_duration_constraint_audit.csv.gz',index=False,compression='gzip')
    return result

def coefficients(stat,storage_hours=None):
    c=v2.coefficient_table(stat)
    if storage_hours is None:return c
    b=c.sector.eq('stationary_battery')
    c.loc[b,'intensity']*=storage_hours/WEI_HOURS
    c.loc[b,'elemental_component_t_GW']*=storage_hours/WEI_HOURS
    c.loc[b,'steel_material_part_t_GW']*=storage_hours/WEI_HOURS
    c.loc[b,'scope_assumption']='12h_energy_budget_AS_capacity_HYPOTHESIS; cycles_efficiency_SOC_not_confirmed'
    c.loc[b,'unit']='t/GW_at_assumed_12h'
    return c

def activities(aim,audit_dir=OUT):
    result=[];audits=[]
    for tech in ['H2CAP_ELE','ELECAP_BAT']:
        rows=[]
        for sc in ['Baseline','300C']:
            d=pd.read_csv(DATA/f'energy_drivers_{sc}.csv')
            d=d.loc[d.technology.eq(tech)].copy()
            if d.duplicated(['region','year']).any():raise ValueError('Duplicate native equipment')
            # Numerical residuals in the uploaded nonnegative variables are <100 W.
            if d[['new_rate_native','replacement_rate_native']].min().min() < -1e-7:raise ValueError('Negative physical additions exceed 1e-7 GW tolerance')
            np.testing.assert_allclose(d.stock_inflow_over_interval_native,(d.new_rate_native+d.replacement_rate_native)*d.model_time_interval,atol=1e-8)
            # Stock independently crosschecked with the archived IAMC series.
            variable='Cap_Hyd_Ele' if tech=='H2CAP_ELE' else 'Cap_Ele_Sto_Cap'
            for year,g in d.groupby('year'):
                if year<2020:continue
                dt_values=g.model_time_interval.unique()
                if len(dt_values)!=1:raise ValueError('Regional interval disagreement')
                dt=int(dt_values[0]);rate=g.new_rate_native.clip(lower=0).sum()+g.replacement_rate_native.clip(lower=0).sum()
                selected=aim.loc[aim.Sc.eq(sc)&aim.Sv.eq(variable)&aim.Y5.eq(year),'value']
                # IAMC has only 5-year labels; absent annual labels are not zeros.
                diff=np.nan
                if year%5==0:
                    diff=g.stock_native.sum()-selected.sum()
                    if abs(diff)>1e-5:raise ValueError('Native/IAMC capacity mismatch')
                audits.append(dict(Sc=sc,technology=tech,year=year,native_rate=rate,native_stock=g.stock_native.sum(),IAMC_stock_difference=diff,model_interval=dt,negative_rate_removed_GW=-g.new_rate_native.clip(upper=0).sum()-g.replacement_rate_native.clip(upper=0).sum()))
                for y in range(max(2020,year-dt+1),min(2100,year)+1):
                    rows.append(dict(Sc=sc,year=y,addition_GW_year=rate,basis='native_physical_equipment_VR_plus_VP; battery_Wei_duration_reference_pending; H2_GW_input_output_basis_pending'))
        f=pd.DataFrame(rows)
        if f.duplicated(['Sc','year']).any():raise ValueError('Overlapping model intervals')
        for _,g in f.groupby('Sc'):
            if set(g.year)!=set(range(2020,2101)):raise ValueError('Missing years')
        result.append(f)
    pd.DataFrame(audits).to_csv(audit_dir/'native_capacity_activity_audit.csv',index=False)
    return tuple(result)

def run():
    OUT.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    with zipfile.ZipFile(ARCHIVE) as z:
        for sc in ['Baseline','300C']:
            with z.open(f'exports/energy_drivers_{sc}.csv') as f:d=pd.read_csv(f)
            d.loc[d.technology.isin(['H2CAP_ELE','ELECAP_BAT'])].to_csv(DATA/f'energy_drivers_{sc}.csv',index=False)
    duration=audit_duration()
    tables=legacy.build(coefficients,v2.power_activity,activities)
    names=['all_sectors_CONDITIONAL','explicit_sector_annual','explicit_sector_detail','grid_CuAl_annual','other_complement_annual_CONDITIONAL','baseline2020_recalibration','coefficients','power_activity','power_activity_audit','hydrogen_native_activity','battery_native_activity']
    for name,frame in zip(names,tables):
        compressed=name in ['all_sectors_CONDITIONAL','explicit_sector_detail']
        frame.to_csv(OUT/(name+('.csv.gz' if compressed else '.csv')),index=False,compression='gzip' if compressed else None)
    before=pd.read_csv(ROOT/'output/harmonized_energy_v2/explicit_sector_annual.csv')
    before=before.groupby(['Sc','statistic','sector','mineral'],as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year':'v2_cumulative_t'})
    after=tables[1].groupby(['Sc','statistic','sector','mineral'],as_index=False).explicit_t_year.sum().rename(columns={'explicit_t_year':'v3_cumulative_t'})
    cmp=before.merge(after,on=['Sc','statistic','sector','mineral'],validate='one_to_one');cmp['change_t']=cmp.v3_cumulative_t-cmp.v2_cumulative_t
    cmp.to_csv(OUT/'cumulative_change_vs_v2.csv',index=False)
    battery=tables[1].loc[tables[1].sector.eq('stationary_battery')].copy()
    battery['if_12h_budget_equals_rated_capacity_t_year']=battery.explicit_t_year*12/WEI_HOURS
    battery['not_confirmed_physical_capacity']=True
    battery.to_csv(OUT/'battery_12h_budget_capacity_HYPOTHESIS.csv',index=False)
    meta={'source_zip_sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),'storage_energy_budget_power_ratio_hours':12,'rated_storage_duration_confirmed':False,'matched_constraint_rows':len(duration),'battery_reference_multiplier_vs_v2':1,'12h_capacity_hypothesis_multiplier':12/WEI_HOURS,'hydrogen_activity':'native_VR_plus_VP_instead_of_positive_net_stock_change','hydrogen_input_output_basis_confirmed':False,'PV_DC_AC_confirmed':False,'all_40_inventories_complete':False,'previous_outputs_overwritten':False}
    (OUT/'manifest.json').write_text(json.dumps(meta,indent=2))
    with pd.ExcelWriter(OUT/'native_energy_revision_v3.xlsx') as w:
        cmp.to_excel(w,sheet_name='累積需要_前回との差',index=False)
        pd.DataFrame([meta]).to_excel(w,sheet_name='確認事項と未確認事項',index=False)
        tables[5].to_excel(w,sheet_name='基準年残余の再校正',index=False)
        tables[1].to_excel(w,sheet_name='発電_水素_蓄電池_年次',index=False)
    print(json.dumps(meta,indent=2));print(cmp.loc[cmp.statistic.eq('average')&cmp.sector.isin(['hydrogen','stationary_battery'])&cmp.mineral.isin(['C','Li','Al','Pt','Ir','Sc'])].to_string(index=False))
if __name__=='__main__':run()
