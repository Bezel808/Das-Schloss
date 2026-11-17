"""Fetch author-published temporal coauthorship data; keep raw files out of Git."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]/'data/research/temporal'
SOURCES={
 'coauth-DBLP':('15YpIK8vvzQJXyQC4bt-Sz951e4eb0rc_','https://www.cs.cornell.edu/~arb/data/coauth-DBLP/'),
 'coauth-MAG-History':('1LDjyK72GvI7iJfWMP4O9tq0_kIg_xrEW','https://www.cs.cornell.edu/~arb/data/coauth-MAG-History/')}

class DownloadForm(HTMLParser):
 def __init__(self):super().__init__();self.action=None;self.fields={}
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='form' and a.get('id')=='download-form':self.action=a['action']
  if tag=='input' and a.get('name'):self.fields[a['name']]=a.get('value','')

def file_sha256(path):
 digest=hashlib.sha256()
 with path.open('rb') as source:
  for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
 return digest.hexdigest()

def fetch(name,fileid,source):
 ROOT.mkdir(parents=True,exist_ok=True);dest=ROOT/(name+'.tar.gz');manifest=dest.with_suffix('.json')
 if dest.exists() and manifest.exists():
  expected=json.loads(manifest.read_text())['sha256']
  if file_sha256(dest)==expected:
   print(name,'verified cached',flush=True);return
 with httpx.Client(follow_redirects=True,timeout=120) as c:
  url='https://drive.usercontent.google.com/download';params={'id':fileid,'export':'download'}
  with c.stream('GET',url,params=params) as r:
   r.raise_for_status()
   if 'text/html' in r.headers.get('content-type',''):
    form=DownloadForm();form.feed(r.read().decode())
    if form.action!='https://drive.usercontent.google.com/download':raise ValueError('Unexpected download form')
    params=form.fields
  with c.stream('GET',url,params=params) as r:
   r.raise_for_status()
   if 'text/html' in r.headers.get('content-type',''):raise ValueError('Expected archive, got HTML')
   digest=hashlib.sha256();count=0;next_log=20_000_000
   with dest.with_suffix('.part').open('wb') as f:
    for chunk in r.iter_bytes():
     f.write(chunk);digest.update(chunk);count+=len(chunk)
     if count>=next_log:print(name,count,'bytes',flush=True);next_log+=20_000_000
   dest.with_suffix('.part').replace(dest)
 manifest.write_text(json.dumps({'source':source,'file_id':fileid,'bytes':count,'sha256':digest.hexdigest(),
  'retrieved_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
  'reference':'https://www.cs.cornell.edu/~arb/papers/ScHoLP-PNAS-2018.pdf',
  'scope':'Author-published temporal hypergraph, restricted to at most 25 authors per paper. No invented author disambiguation or dates.'},indent=2))
 print(name,'complete',count,flush=True)

if __name__=='__main__':
 for name,(identity,source) in SOURCES.items():
  for attempt in range(3):
   try:fetch(name,identity,source);break
   except httpx.HTTPError:
    if attempt==2:raise
    print(name,'network retry',attempt+1,flush=True);time.sleep(2**attempt)
