"""Development-only temporal ML ablation with population-weighted negative sampling."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import log_loss, average_precision_score

from temporal_benchmark import TemporalCorpus, Observation, retrieval, ROOT, PROJECT, METRIC_VERSION
from forecast_features import features, FEATURES, ACTIVITY, NETWORK, COVERAGE


def extract(run):
    protocol=json.loads((run/'protocol.json').read_text())
    corpus=TemporalCorpus(protocol['dataset']); cutoff=protocol['cutoff']
    if protocol.get('normalization')!=corpus.normalization:
        raise ValueError('Feature extraction requires the same normalized data as the query run')
    schema_hash=hashlib.sha256(Path(__file__).with_name('forecast_features.py').read_bytes()+(PROJECT/'scholartrace/acquisition.py').read_bytes()+Path(__file__).with_name('event_data.py').read_bytes()+json.dumps(protocol,sort_keys=True).encode()).hexdigest()
    destination=run/'feature-cache'/schema_hash[:16];destination.mkdir(parents=True,exist_ok=True)
    for path in sorted(run.glob('author-*.json')):
        author=int(path.stem.split('-')[1]);rows=json.loads(path.read_text())
        gold=corpus.future(author,cutoff)['new_seen']
        for row in rows:
            if row['budget'] not in [5,20,40]:continue
            dest=destination/f'{author}-{row["policy"]}-{row["budget"]}.npz'
            if dest.exists():continue
            state=Observation(author,cutoff)
            for query in row['query_log']:state.reveal(query['author'],corpus.query(query['author'],cutoff))
            ids,x=features(state,corpus)
            y=np.array([int(a in gold) for a in ids],dtype=np.int8)
            with dest.with_suffix('.tmp').open('wb') as f:
                np.savez_compressed(f,x=x,y=y,ids=np.asarray(ids,dtype=np.int32),gold=np.asarray(sorted(gold),dtype=np.int32))
            dest.with_suffix('.tmp').replace(dest)
    return destination


def load_train(folders,seed=42):
    xx=[];yy=[];ww=[];metadata=[]
    rng=np.random.default_rng(seed)
    for folder in folders:
        for path in sorted(folder.glob('*.npz')):
            data=np.load(path);x,y=data['x'],data['y']
            if not len(y):continue
            positive=np.flatnonzero(y);negative=np.flatnonzero(y==0)
            # Include all positives; inverse inclusion weights reconstruct the
            # original candidate distribution within each person/state.
            sample=rng.choice(negative,min(100,len(negative)),replace=False)
            take=np.r_[positive,sample]
            weight=np.r_[np.ones(len(positive)),np.full(len(sample),len(negative)/max(1,len(sample)))]/len(y)
            xx.append(x[take]);yy.append(y[take]);ww.append(weight)
            metadata.append({'file':str(path.relative_to(PROJECT)), 'candidates':len(y),'sampled':len(take),'positives':len(positive)})
    return np.vstack(xx),np.concatenate(yy),np.concatenate(ww),metadata


def evaluate(folder,scaler,model,columns):
    rows=[]
    for path in sorted(folder.glob('*.npz')):
        d=np.load(path);x,y,ids,gold=(d[k] for k in ['x','y','ids','gold'])
        parts=path.stem.split('-');author=int(parts[0]);policy=parts[1];budget=int(parts[2])
        score=model.predict_proba(scaler.transform(x[:,columns]))[:,1] if len(x) else np.array([])
        metric=retrieval({int(a):float(s) for a,s in zip(ids,score)},set(gold.tolist()))
        # Complete validation candidate sets, no sampled negatives at evaluation.
        loss=log_loss(y,score,labels=[0,1]) if len(y) else None
        rows.append({'author':author,'policy':policy,'budget':budget,'gold':len(gold),
                     'log_loss':loss,'brier':float(np.mean((score-y)**2)) if len(y) else None,**metric})
    groups={}
    for policy in sorted({r['policy'] for r in rows}):
        for budget in [5,20,40]:
            rr=[r for r in rows if r['policy']==policy and r['budget']==budget]
            positives=sum(r['gold'] for r in rr)
            groups[f'{policy}/{budget}']={'targets':len(rr),'positive_edges':positives,
                'tie_expected_micro_recall_at_10':sum(r['tie_expected']['hits_at_10'] for r in rr)/positives if positives else None,
                'tie_expected_macro_ap_positive_targets':float(np.mean([r['tie_expected']['average_precision'] for r in rr if r['gold']])) if positives else None,
                'micro_recall_at_10':sum(r['hits_at_10'] for r in rr)/positives if positives else None,
                'macro_ap_positive_targets':float(np.mean([r['average_precision'] for r in rr if r['gold']])) if positives else None,
                'mean_candidate_log_loss':float(np.mean([r['log_loss'] for r in rr if r['log_loss'] is not None])),
                'mean_candidate_brier':float(np.mean([r['brier'] for r in rr if r['brier'] is not None]))}
    return rows,groups


def run(train_runs,validation_run):
    protocols=[json.loads((r/'protocol.json').read_text()) for r in train_runs+[validation_run]]
    if max(p['cutoff'] for p in protocols[:-1])>=protocols[-1]['cutoff']:raise ValueError('Training cutoff must strictly precede evaluation')
    if protocols[-1]['cutoff']>2008:raise ValueError('Development evaluator cannot access frozen validation or test years')
    folders=[extract(r) for r in train_runs];validation=extract(validation_run)
    x,y,w,sampling=load_train(folders)
    print('training rows',len(y),'sampled positive labels',int(y.sum()),flush=True)
    results={};models={}
    # Fixed baseline regularization; do not search C against reported outcomes.
    for name,columns in [('activity',ACTIVITY),('activity_network',NETWORK),('activity_network_coverage',COVERAGE)]:
        scaler=StandardScaler().fit(x[:,columns],sample_weight=w)
        model=LogisticRegression(C=1.,max_iter=2000,random_state=42)
        model.fit(scaler.transform(x[:,columns]),y,sample_weight=w)
        rows,summary=evaluate(validation,scaler,model,columns)
        results[name]={'summary':summary,'rows':rows}
        models[name]={'features':[FEATURES[c] for c in columns],'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),
                      'coefficient':model.coef_[0].tolist(),'intercept':float(model.intercept_[0]),
                      'C':1.,'iterations':int(model.n_iter_[0]),'probabilities_calibrated':False}
    report={'stage':'temporal development evaluation, not final holdout','protocols':protocols,
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('forecast_features.py').read_bytes()+(PROJECT/'scholartrace/evaluation.py').read_bytes()+(PROJECT/'scholartrace/acquisition.py').read_bytes()).hexdigest(),
            'metric_version':METRIC_VERSION,
            'preprocessing_sha256':hashlib.sha256(Path(__file__).with_name('event_data.py').read_bytes()).hexdigest(),
            'features':FEATURES,'sampling':sampling,'models':models,'results':results,
            'limitations':['Targets are not guaranteed person-disjoint across years; this is temporal, not new-person generalization.',
                           'Repeated states from each target are correlated; row count is not independent sample size.',
                           'Model scores are development estimates conditional on discovered candidates, not validated global probabilities.']}
    dest=PROJECT/'research/results'/f'forecast-ml-{protocols[-1]["dataset"]}-{protocols[-1]["cutoff"]}-{METRIC_VERSION}.json'
    dest.write_text(json.dumps(report,indent=2)+'\n');print('report',dest,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--train',nargs='+',type=Path,required=True);p.add_argument('--evaluate',type=Path,required=True)
    a=p.parse_args();run([r.resolve() for r in a.train],a.evaluate.resolve())
