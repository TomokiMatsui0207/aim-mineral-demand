"""Generate synthetic data to demonstrate plotting; no AIM results are used."""
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'analysis'))
from model import MINERALS
def main():
    rows=[]
    for sc,factor in [('Baseline',1.),('300C',1.4)]:
        for i,m in enumerate(MINERALS,1):
            cumulative=0.
            for year in range(2020,2101):
                demand=100*i*factor*(1+(year-2020)/80)
                cumulative+=demand
                rows.append(dict(Sc=sc,year=year,mineral=m,statistic='average',grid_case='SYNTHETIC',case='SYNTHETIC',conditional_total_low_t_year=demand,conditional_total_high_t_year=demand,cumulative_conditional_low_t=cumulative,cumulative_conditional_high_t=cumulative,full40_observed_total_ready=False,data_kind='SYNTHETIC_NOT_RESEARCH_RESULTS'))
    out=ROOT/'output/demo';out.mkdir(parents=True,exist_ok=True)
    path=out/'synthetic_results.csv';pd.DataFrame(rows).to_csv(path,index=False)
    print(path)
if __name__=='__main__':main()
