"""Reporting-only equal-year contrasts; never changes a frozen model or score."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def analyze():
    path=ROOT/'research/results/frozen-forecast-v1.json';report=json.loads(path.read_text())
    protocol=report['protocol'];folder=ROOT/'data/research/temporal/holdout'/report['protocol_sha256'][:16]
    results=[]
    for dataset in protocol['datasets']:
        years=protocol['stages']['final_test'];by_year=[];population=set()
        for year in years:
            rows=sorted((json.loads(p.read_text()) for p in (folder/f'{dataset}-{year}').glob('author-*.json')),key=lambda r:r['author'])
            assert len(rows)==protocol['targets']
            by_year.append(rows);population.update(r['author'] for r in rows)
        authors=sorted(population);index={a:i for i,a in enumerate(authors)}
        differences=np.zeros((len(authors),len(years)));gold=np.zeros_like(differences)
        stratified=[];values=[];primary=[];baseline=[]
        for column,(year,rows) in enumerate(zip(years,by_year)):
            a=np.array([r['metrics'][protocol['primary_method']]['tie_expected']['hits_at_10'] for r in rows])
            b=np.array([r['metrics'][protocol['primary_baseline']]['tie_expected']['hits_at_10'] for r in rows])
            g=np.array([r['gold_new_seen'] for r in rows],dtype=float)
            for r,delta,denominator in zip(rows,a-b,g):differences[index[r['author']],column]=delta;gold[index[r['author']],column]=denominator
            sample=np.random.default_rng(813+year).integers(0,len(rows),size=(5000,len(rows)))
            den=g[sample].sum(axis=1)
            stratified.append(np.divide((a-b)[sample].sum(axis=1),den,out=np.full(5000,np.nan),where=den>0))
            values.append(float((a-b).sum()/g.sum()));primary.append(float(a.sum()/g.sum()));baseline.append(float(b.sum()/g.sum()))
        draws=np.mean(np.asarray(stratified),axis=0);valid=np.isfinite(draws)
        # Sensitivity: draw unique people as clusters, retaining all their years.
        rng=np.random.default_rng(1813);cluster=[]
        for _ in range(5000):
            weight=np.bincount(rng.integers(0,len(authors),size=len(authors)),minlength=len(authors))
            den=weight@gold
            if np.all(den>0):cluster.append(float(np.mean((weight@differences)/den)))
        results.append({'dataset':dataset,'years':years,'target_years':sum(len(r) for r in by_year),'unique_authors':len(authors),
                        'primary_mean_recall':float(np.mean(primary)),'baseline_mean_recall':float(np.mean(baseline)),
                        'equal_year_difference':float(np.mean(values)),
                        'year_stratified_paired_95':np.quantile(draws[valid],[.025,.975]).tolist(),
                        'year_stratified_valid_replicates':int(valid.sum()),
                        'author_cluster_paired_95_sensitivity':np.quantile(cluster,[.025,.975]).tolist(),
                        'author_cluster_valid_replicates':len(cluster)})
    result={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'protocol_sha256':report['protocol_sha256'],
            'rows':results,'bootstrap_replicates':5000,'year_stratified_seed':'813 + cutoff year','author_cluster_seed':1813,
            'scope':'Conditional on the fixed three final years, source graphs and sampled historical-activity populations. Years are not resampled; these are not intervals for future-year generalization. History was seen during development, not an untouched domain.',
            'analysis':'Predeclared equal-year mean contrast, with reporting-only bootstrap and repeated-author cluster sensitivity; no model or query changes.'}
    (ROOT/'research/results/frozen-forecast-aggregate.json').write_text(json.dumps(result,indent=2)+'\n')
    for r in results:print(json.dumps(r))


if __name__=='__main__':analyze()
