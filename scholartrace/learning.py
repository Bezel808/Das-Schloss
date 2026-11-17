"""Small supervised linear models, exported as JSON, without unsafe pickle loading.

Training rows must supply features, gold label, people IDs, source, and cutoff.
Unlabeled pairs must not be converted to negative examples.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import networkx as nx
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler

DEGREE_FEATURES = ['observed_years','paper_count_log','active_years','recent_first_rate','recent_leading_rate',
                   'recent_solo_rate','recent_collaborators_log','early_anchor_recent_share','institution_changes']


def degree_features(profile):
    from .inference import entry
    from collections import Counter
    works=profile['works'];aid=profile['id'];last=max(w['publication_year'] for w in works)
    recent=[w for w in works if w['publication_year']>=last-2]
    first=profile['first']
    collaborators={a['author']['id'] for w in recent for a in w['authorships'] if a.get('author',{}).get('id') and a['author']['id']!=aid}
    anchor_counts=Counter(a['author']['id'] for w in profile['early'] for a in w['authorships'] if a.get('author',{}).get('id') and a['author']['id']!=aid)
    anchor=anchor_counts.most_common(1)[0][0] if anchor_counts else None
    institutions=[{i['id'] for i in entry(w,aid).get('institutions',[])} for w in works]
    values=[last-first+1,np.log1p(len(works)),len({w['publication_year'] for w in works}),
            sum(entry(w,aid).get('author_position')=='first' for w in recent)/len(recent),
            sum(entry(w,aid).get('author_position')=='last' or entry(w,aid).get('is_corresponding') is True for w in recent)/len(recent),
            sum(len(w['authorships'])==1 for w in recent)/len(recent),np.log1p(len(collaborators)),
            sum(bool(entry(w,anchor)) for w in recent)/len(recent) if anchor else 0,
            sum(bool(a and b and not a&b) for a,b in zip(institutions,institutions[1:]))]
    return {k:float(v) for k,v in zip(DEGREE_FEATURES,values)}


def predict(model, features):
    x=np.array([features[k] for k in model['features']], dtype=float)
    if not np.isfinite(x).all():raise ValueError('Nonfinite feature')
    z=(x-np.array(model['mean']))/np.array(model['scale'])
    logits=np.array(model['coef'])@z+np.array(model['intercept'])
    if len(model['classes'])==2:logits=np.array([0.,float(logits[0])])
    probs=softmax(logits/model['temperature'])
    index=int(np.argmax(probs))
    # Decline extrapolation far outside the observed feature ranges.
    outside=any(v<lo or v>hi for v,lo,hi in zip(x,model['feature_min'],model['feature_max']))
    return {'label':None if outside else model['classes'][index],
            'probabilities':dict(zip(model['classes'],map(float,probs))),
            'status':'out_of_training_range' if outside else 'prediction',
            'model_id':model['model_id'], 'validated_metrics':model['metrics'],
            'calibration':'temperature fitted on person-disjoint validation data; not guaranteed out of domain'}


def train(rows, features, task):
    if len(rows)<30:raise ValueError('Need at least 30 genuinely labeled examples')
    people_graph=nx.Graph()
    for row in rows:
        if not row.get('people') or not row.get('source') or not row.get('cutoff'):
            raise ValueError('Every label needs people IDs, a source, and feature cutoff')
        people_graph.add_nodes_from(row['people'])
        for person in row['people'][1:]:people_graph.add_edge(row['people'][0],person)
    components={p:i for i,c in enumerate(nx.connected_components(people_graph)) for p in c}
    groups=[components[row['people'][0]] for row in rows]
    if len(set(groups))<6:raise ValueError('Need at least 6 disconnected person groups for leakage-free splits')
    x=np.array([[r['features'][k] for k in features] for r in rows],dtype=float)
    if not np.isfinite(x).all():raise ValueError('Features must be finite')
    y=np.array([str(r['label']) for r in rows]);classes=set(y)
    if len(classes)<2:raise ValueError('Need at least two labeled classes')
    split=None
    for seed in range(42,142):
        trainval,test=next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=seed).split(x,y,groups))
        tr,va=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=seed).split(x[trainval],y[trainval],np.array(groups)[trainval]))
        train_idx,val_idx=trainval[tr],trainval[va]
        if all(set(y[idx])==classes for idx in [train_idx,val_idx,test]):
            split=(train_idx,val_idx,test);break
    if split is None:raise ValueError('Cannot make person-disjoint splits containing every class')
    train_idx,val_idx,test=split
    scaler=StandardScaler().fit(x[train_idx]);clf=LogisticRegression(max_iter=2000,random_state=42).fit(scaler.transform(x[train_idx]),y[train_idx])
    def logits(indices):
        z=clf.decision_function(scaler.transform(x[indices]))
        return np.column_stack([np.zeros(len(z)),z]) if z.ndim==1 else z
    validation=logits(val_idx)
    result=minimize_scalar(lambda t:log_loss(y[val_idx],softmax(validation/t,axis=1),labels=clf.classes_),bounds=(.1,10),method='bounded')
    temperature=float(result.x);probs=softmax(logits(test)/temperature,axis=1)
    pred=clf.classes_[probs.argmax(axis=1)]
    onehot=np.array([[label==c for c in clf.classes_] for label in y[test]],dtype=float)
    model={'task':task,'features':features,'classes':clf.classes_.tolist(),'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),
           'coef':clf.coef_.tolist(),'intercept':clf.intercept_.tolist(),'temperature':temperature,
           'feature_min':x[train_idx].min(axis=0).tolist(),'feature_max':x[train_idx].max(axis=0).tolist(),
           'metrics':{'test_accuracy':float(accuracy_score(y[test],pred)),'test_log_loss':float(log_loss(y[test],probs,labels=clf.classes_)),
                      'test_multiclass_brier':float(np.mean(np.sum((probs-onehot)**2,axis=1))),
                      'n_train':len(train_idx),'n_validation':len(val_idx),'n_test':len(test)},
           'sources':sorted({r['source'] for r in rows}), 'split':'person-connected-component disjoint 60/20/20',
           'training_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}
    model['model_id']=hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest()[:16]
    return model


def main():
    parser=argparse.ArgumentParser(description='Train a small classifier from independently labeled feature rows')
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--task',choices=['advisor','degree'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from .inference import FEATURES
    rows=json.loads(args.input.read_text())
    model=train(rows,FEATURES if args.task=='advisor' else DEGREE_FEATURES,args.task)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(model,indent=2)+'\n')
    print(json.dumps(model['metrics'],indent=2))


if __name__=='__main__':main()
