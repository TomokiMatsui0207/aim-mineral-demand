"""Evidence ledger and dimensionally explicit battery alternatives; does not replace v2.

The conversion is a Wei-equivalent normalization, not a claim that every raw
inventory was originally energy-scaled or that AIM storage duration is known.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from harmonize_energy_v2 import coefficient_table
ROOT=Path(__file__).resolve().parent.parent
WEI_HOURS=6.2113

def battery_demand(addition, wei_t_GW, activity_unit, *, duration_hours=None):
    """Return t/year. Refuse implicit capacity units and duplicated duration."""
    if activity_unit=='GWh/year':
        if duration_hours is not None: raise ValueError('Energy already includes duration')
        return addition*wei_t_GW/WEI_HOURS
    if activity_unit=='GW/year':
        if duration_hours is None or not np.isfinite(duration_hours) or duration_hours<=0:
            raise ValueError('Power activity requires an explicit positive duration')
        return addition*duration_hours*wei_t_GW/WEI_HOURS
    raise ValueError('Use an explicit GW/year or GWh/year activity unit')

def run():
    out=ROOT/'output/energy_basis_resolution';out.mkdir(exist_ok=True)
    raw=pd.read_csv(ROOT/'input/imported/wei_intensity_rows.csv')
    carbon=raw.loc[raw.category.eq('Energy storage')&raw.material.eq('C')&raw.reported_average.notna()]
    assert len(carbon)>0
    np.testing.assert_allclose(carbon.reported_average/WEI_HOURS/1000,1.2,atol=1e-10)
    co=pd.concat([coefficient_table(s) for s in ['average','minimum']],ignore_index=True)
    b=co.loc[co.sector.eq('stationary_battery')].copy()
    b['Wei_equivalent_t_GWh']=b.intensity/WEI_HOURS
    b['Wei_equivalent_kg_kWh']=b.Wei_equivalent_t_GWh/1000
    b['normalization_status']='conditional_Wei_equivalent; graphite independently crosschecked; other materials not individually source-rebuilt'
    b.to_csv(out/'battery_coefficients_explicit_units.csv',index=False)
    reference=pd.read_csv(ROOT/'output/harmonized_energy_v2/explicit_sector_annual.csv')
    b=reference.loc[reference.sector.eq('stationary_battery')].copy()
    b=b.rename(columns={'explicit_t_year':'v2_assumed_GW_Wei_duration_t_year'})
    b['if_native_is_GWh_t_year']=b.v2_assumed_GW_Wei_duration_t_year/WEI_HOURS
    b['delta_t_year']=b.if_native_is_GWh_t_year-b.v2_assumed_GW_Wei_duration_t_year
    base_delta=b.loc[b.year.eq(2020),['Sc','statistic','mineral','delta_t_year']].rename(columns={'delta_t_year':'base_delta'})
    growth=pd.read_csv(ROOT/'output/harmonized_energy_v2/other_complement_annual_CONDITIONAL.csv')
    d=growth.merge(b,on=['Sc','statistic','year','mineral'],validate='many_to_one').merge(base_delta,on=['Sc','statistic','mineral'],validate='many_to_one')
    d['recalibrated_other_low_t_year']=d.raw_other_low_t_year-d.base_delta*d.growth_factor
    d['recalibrated_other_high_t_year']=d.raw_other_high_t_year-d.base_delta*d.growth_factor
    d['valid_nonnegative_residual']=(d.recalibrated_other_low_t_year>=0)&~d.negative_base
    d['conditional_total_delta_t_year']=(d.delta_t_year-d.base_delta*d.growth_factor).where(d.valid_nonnegative_residual)
    d.to_csv(out/'battery_GWh_hypothesis_with_residual_recalibration.csv',index=False)
    c=b.groupby(['Sc','statistic','mineral'],as_index=False)[['v2_assumed_GW_Wei_duration_t_year','if_native_is_GWh_t_year','delta_t_year']].sum()
    c.to_csv(out/'battery_cumulative_comparison.csv',index=False)
    ledger=[
      dict(topic='battery graphite',status='numerical_crosscheck_confirmed',finding='7453.56/6.2113=1200 t/GWh=1.2 kg/kWh; JRC Table4 PDF page66 supports energy intensity for NMC. Extension to all chemistries remains Wei assumption.',source='https://publications.jrc.ec.europa.eu/repository/bitstream/JRC113360/kjna29440enn.pdf',applied='Explicit-unit converter, no repeated duration, GWh alternative with residual recalibration'),
      dict(topic='PV component scope',status='overlap_risk_confirmed; exact_Wei_rows_pending',finding='REMPD covers modules, inverters, cabling, transformers, racking and structural BOS, in kg/kW module capacity (DC). Cannot universally add all subtype inventory to generic PV.',source='https://apps.openei.org/REMPD/overview/solar',applied='Do not promote additive v2 assumption to confirmed reference; preserve replacement comparator'),
      dict(topic='PV steel provenance',status='source_value_located; averaging_scope_pending',finding='Wang public material_intensities_7.0.csv lists CSI_PV Steel73000 attributed to Jean2015; also distinct whole-technology categories for Coal and CoalCCS. These are not enough to classify pooled Wei CCS as incremental.',source='https://zenodo.org/records/7023703',applied='CCS increment remains conditional; do not treat Wang CoalCCS whole-technology labels as additional capture mass'),
      dict(topic='Wei turnover',status='source_algorithm_verified',finding='Public Global Metal Demand.py calculates additions and retirement before material demand. It also uses changing intensities. Missing Input_data.xlsx prevents exact matrix reconstruction.',source='https://zenodo.org/records/17195662',applied='Retain AIM native additions; do not add another Wei replacement flow'),
    ]
    pd.DataFrame(ledger).to_csv(out/'source_decision_ledger.csv',index=False)
    meta={'AIM_native_battery_unit_confirmed':False,'Wei_reference_hours':WEI_HOURS,'v2_reference_totals_overwritten':False,'GWh_alternative_is_confirmed_AIM_result':False,'source_checks_not_equal_all_inventory_validation':True}
    (out/'manifest.json').write_text(json.dumps(meta,indent=2))
    with pd.ExcelWriter(out/'energy_basis_resolution.xlsx') as w:
        pd.DataFrame(ledger).to_excel(w,sheet_name='出典と反映判断',index=False)
        co.loc[co.sector.eq('stationary_battery')].assign(Wei_equivalent_t_GWh=lambda x:x.intensity/WEI_HOURS).to_excel(w,sheet_name='蓄電池_単位換算',index=False)
        c.to_excel(w,sheet_name='累積_単位仮説の影響',index=False)
    print(c.loc[c.statistic.eq('average')&c.mineral.isin(['C','Li','Cu','Al'])].to_string(index=False))
if __name__=='__main__':run()
