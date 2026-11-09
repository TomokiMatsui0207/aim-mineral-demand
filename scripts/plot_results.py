"""Plot one explicitly selected conditional case; attach figure provenance."""
from pathlib import Path
import argparse,hashlib,json,subprocess,os
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'output/.matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME',str(ROOT/'output/.cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--grid-case',required=True)
    p.add_argument('--case',required=True)
    p.add_argument('--statistic',default='average')
    p.add_argument('--model-version',required=True,help='Version that produced these inputs; use SYNTHETIC for demo.')
    p.add_argument('--out',type=Path,default=ROOT/'figures/cumulative')
    a=p.parse_args();d=pd.read_csv(a.input)
    if a.out.suffix:raise ValueError('--out must be a filename stem without extension')
    d=d.loc[d.statistic.eq(a.statistic)&d.grid_case.eq(a.grid_case)&d.case.eq(a.case)].copy()
    if d.empty:raise ValueError('Selected case has no rows')
    if d.duplicated(['Sc','mineral','year']).any():raise ValueError('Ambiguous figure series')
    synthetic='data_kind' in d and d.data_kind.eq('SYNTHETIC_NOT_RESEARCH_RESULTS').any()
    if synthetic and a.model_version!='SYNTHETIC':raise ValueError('Synthetic inputs must be labelled SYNTHETIC')
    if not synthetic and a.model_version=='SYNTHETIC':raise ValueError('Research inputs cannot be labelled as demo')
    minerals=sorted(d.mineral.unique());cols=4;rows=(len(minerals)+cols-1)//cols
    fig,axes=plt.subplots(rows,cols,figsize=(15,2.4*rows),squeeze=False,layout='constrained')
    for ax,m in zip(axes.flat,minerals):
        q=d[d.mineral.eq(m)];vals=q.cumulative_conditional_high_t.dropna()
        scale=1e6 if len(vals) and vals.max()>=1e6 else 1e3;unit='Mt' if scale==1e6 else 'kt'
        for sc,color in [('Baseline','#00a6b2'),('300C','#ef7064')]:
            v=q[q.Sc.eq(sc)].sort_values('year')
            if v.empty:continue
            ax.plot(v.year,v.cumulative_conditional_low_t/scale,label=sc,color=color)
            ax.fill_between(v.year.to_numpy(),v.cumulative_conditional_low_t.to_numpy()/scale,v.cumulative_conditional_high_t.to_numpy()/scale,color=color,alpha=.15)
        if vals.empty:ax.text(.5,.5,'Unresolved baseline',transform=ax.transAxes,ha='center')
        ax.set_title(f'{m} ({unit})');ax.grid(alpha=.2)
    for ax in list(axes.flat)[len(minerals):]:ax.set_visible(False)
    title='SYNTHETIC DEMONSTRATION - NOT RESEARCH RESULTS' if synthetic else 'Conditional cumulative mineral demand - inventory coverage incomplete'
    fig.suptitle(f'{title}\n{a.model_version} | {a.statistic} | {a.grid_case} | {a.case}',fontsize=11)
    handles,labels=axes.flat[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=2)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    for ext in ['png','pdf']:fig.savefig(a.out.with_suffix('.'+ext),dpi=150)
    plt.close(fig)
    commit=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True)
    dirty=subprocess.run(['git','-C',str(ROOT),'status','--porcelain'],capture_output=True,text=True)
    meta={'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'analysis_commit':commit.stdout.strip() if commit.returncode==0 else 'uncommitted','analysis_worktree_dirty':bool(dirty.stdout.strip()) if dirty.returncode==0 else True,'model_version':a.model_version,'case':a.case,'grid_case':a.grid_case,'statistic':a.statistic,'synthetic':bool(synthetic),'command_args':__import__('sys').argv[1:]}
    a.out.with_suffix('.json').write_text(json.dumps(meta,indent=2))
    print('Saved PNG, PDF and provenance JSON:',a.out)
if __name__=='__main__':main()
