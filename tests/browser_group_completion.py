"""Exercise the real browser orchestration with controlled source progress.

Mocks API responses; never launches a live collection. Only the local web
server is required. Checks that partial results stay hidden until completion.
"""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from scholartrace.groups import portrait
from tests.test_group_api import paper
from tests.browser_ui_helpers import mock_profile

BASE=os.environ.get('SCHOLARTRACE_TEST_URL','http://127.0.0.1:8000')
A='A5091518548';F='https://openalex.org/'+A
own=[paper(1,2018,[A,'A2','A3']),paper(2,2019,[A,'A2'])]
corpora={F:own};coverage={F:{'complete':True,'through':2025}}
names={F:'Chao Huang'}
initial=portrait(corpora,F,coverage,names)
corpora['https://openalex.org/A2']=[own[0],own[1]];coverage['https://openalex.org/A2']={'complete':True,'through':2025}
partial=portrait(corpora,F,coverage,names)
corpora['https://openalex.org/A3']=[paper(3,2010,['A3']),own[0]];coverage['https://openalex.org/A3']={'complete':True,'through':2025}
complete=portrait(corpora,F,coverage,names)
params=complete['parameters']
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
 page=b.new_page(accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 mock_profile(page)
 state={'phase':'not_started','completed':0,'starts':0,'fail':False}
 def respond(route,value,status=200):route.fulfill(status=status,content_type='application/json',body=json.dumps(value))
 def current():return complete if state['phase']=='complete' else partial if state['completed'] else initial
 def collection(route):respond(route,{'status':state['phase'],'mode':'automatic','completed':state['completed'],'total':2,'updated_at':state['phase']+str(state['starts']),'plan':{'parameters':params}})
 def auto(route):
  state['starts']+=1
  if state['fail']:respond(route,{'detail':'source temporarily unavailable'},503);return
  state['phase']='running';respond(route,{'total':2,'mode':'automatic'})
 page.route('**/api/groups/'+A+'/collection',collection)
 page.route('**/api/groups/'+A+'/auto',auto)
 page.route('**/api/groups/'+A+'?*',lambda route:respond(route,current()))
 page.route('**/api/compute/groups/'+A,lambda route:respond(route,{'status':'complete','result':current()}))
 page.goto(BASE+'?author='+A);expect(page.locator('#name')).to_have_text('Chao Huang',timeout=60000)
 page.locator('[data-tab="groups"]').click();page.locator('#groupRun').click()
 expect(page.locator('#groupCollectionStatus')).to_contain_text('正在获取论文',timeout=15000)
 assert state['starts']==1
 expect(page.locator('#groupResults')).to_be_hidden()
 expect(page.locator('#groupRun')).to_be_disabled()
 expect(page.locator('#groupExport')).to_be_hidden()
 # Status polling reuses the running collection; partial snapshots stay hidden.
 page.locator('#groupCollectionRefresh').click();assert state['starts']==1
 state['completed']=1
 expect(page.locator('#groupCollectionStatus')).to_contain_text('1/2',timeout=15000)
 expect(page.locator('#groupResults')).to_be_hidden()
 state['phase']='complete';state['completed']=2
 expect(page.locator('#groupStatus')).to_contain_text('已完成',timeout=15000)
 expect(page.locator('#groupResults')).to_be_visible()
 expect(page.locator('#groupCollection')).to_be_hidden()
 assert state['starts']==1
 with page.expect_download() as downloaded:page.locator('#groupExport').click()
 result=json.loads(Path(downloaded.value.path()).read_text());assert result['data_readiness']['pending']==0
 assert result['summary']['early_career']==1 and result['summary']['experienced']==1
 # Failure clears results; one primary button retries.
 state.update(phase='not_started',completed=0,fail=True)
 page.locator('#groupRun').click()
 expect(page.locator('#groupStatus')).to_contain_text('未完成')
 expect(page.locator('#groupResults')).to_be_hidden();assert state['starts']==2
 state['fail']=False;page.locator('#groupRun').click()
 expect(page.locator('#groupCollectionStatus')).to_contain_text('正在获取论文');assert state['starts']==3
 # Pausing does not silently restart collection on subsequent status refreshes.
 state['phase']='paused';page.locator('#groupCollectionRefresh').click()
 expect(page.locator('#groupCollectionStatus')).to_contain_text('已暂停');assert state['starts']==3
 expect(page.locator('#groupRun')).to_be_enabled()
 expect(page.locator('#groupResults')).to_be_hidden()
 # A response arriving after parameter changes must not start a new collection.
 state['phase']='not_started';held=[]
 page.route('**/api/compute/groups/'+A,lambda route:held.append(route))
 with page.expect_request('**/api/compute/groups/'+A):page.locator('#groupRun').click()
 page.locator('#groupStart').fill('2017')
 respond(held.pop(),{'status':'complete','result':initial})
 expect(page.locator('#groupStatus')).to_contain_text('范围已更改');assert state['starts']==3
 expect(page.locator('#groupResults')).to_be_hidden()
 assert not errors,errors
 b.close()
print('PASS: automatic missing-history acquisition, running-job reuse, partial-result gating, final refresh, readiness export, failure/retry, paused state, stale-parameter isolation')
