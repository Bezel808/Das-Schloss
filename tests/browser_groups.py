"""Read-only integration check of the live group portrait; never starts collection."""
import json
import os
import re
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('SCHOLARTRACE_TEST_URL','http://127.0.0.1:8000')
OUT=Path('data/research/group-browser-qa');OUT.mkdir(parents=True,exist_ok=True)
with httpx.Client(trust_env=False,timeout=90) as client:
    jobs=[j for j in client.get(BASE+'/api/jobs').raise_for_status().json() if j['status']=='complete']
first=next((j for j in jobs if j['id']=='A5091518548'),jobs[0])
second=next(j for j in jobs if j['id']!=first['id'])
with sync_playwright() as p:
    executable=os.environ.get('SCHOLARTRACE_BROWSER_EXECUTABLE','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    browser=p.chromium.launch(executable_path=executable,headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    # Calculation now acquires missing histories automatically. Keep this
    # regression read-only, including alternate scopes with missing members.
    page.route('**/api/groups/*/auto',lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"Read-only UI regression: collection is intercepted"}'))
    page.goto(BASE+'?author='+first['id'])
    expect(page.locator('#name')).to_have_text(first['author']['display_name'],timeout=60000)
    page.locator('[data-tab="groups"]').click();page.locator('#groupRun').click()
    expect(page.locator('#groupStatus')).to_contain_text('已完成',timeout=90000)
    expect(page.locator('#groupResults')).to_be_visible()
    assert page.locator('#groupAnnual tbody tr').count()==10
    assert 'NaN' not in page.locator('#groups').inner_text()
    with page.expect_download() as download:page.locator('#groupExport').click()
    download.value.save_as(OUT/'portrait.json')
    exported=json.loads((OUT/'portrait.json').read_text())
    assert exported['focal']=='https://openalex.org/'+first['id']
    assert len(exported['annual'])==10 and exported['version']=='group-cohorts-2'
    # Exercise one-click completion without launching network collection.
    page.route('**/api/groups/'+first['id']+'/auto',lambda route:route.fulfill(status=200,content_type='application/json',body='{"mode":"automatic","total":0}'))
    page.route('**/api/groups/'+first['id']+'/collection',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps({'status':'complete','mode':'automatic','completed':0,'total':0,'updated_at':'test-auto-completion','plan':{'parameters':exported['parameters']}})))
    expect(page.locator('#groupRun')).to_be_enabled()
    with page.expect_response('**/api/compute/groups/'+first['id']):
        page.locator('#groupRun').click()
    expect(page.locator('#groupStatus')).to_contain_text('已完成',timeout=90000)
    page.unroute('**/api/groups/'+first['id']+'/auto')
    page.unroute('**/api/groups/'+first['id']+'/collection')
    page.locator('#groupSummary').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'groups-desktop.png'))
    # Evidence comes from the portrait union, including papers without the focal.
    cohorts=[r for r in exported['cohorts'] if r['assessment']=='assessed' and set(r['early_work_ids'])-set(r['focal_work_ids'])]
    if cohorts:
        row=cohorts[0]
        buttons=page.locator('#groupCohorts [data-group-evidence]')
        records=buttons.evaluate_all('(bs)=>bs.map(b=>JSON.parse(b.dataset.groupEvidence))')
        index=records.index(row['early_work_ids']);buttons.nth(index).click()
        expect(page.locator('#groupEvidence')).to_contain_text('目标作者未署名')
        page.locator('#groupEvidenceSearch').fill('NO_MATCH_SENTINEL')
        expect(page.locator('#groupEvidence')).to_contain_text('当前筛选没有论文')
        page.locator('#groupEvidenceSearch').fill('')
    page.locator('#groupCohortCategory').select_option('early_career')
    assert page.locator('#groupCohorts tbody tr').count()==exported['summary']['early_career']
    page.locator('#groupMemberSearch').fill('NO_MATCH_SENTINEL')
    assert page.locator('#groupCohorts tbody tr').count()==0
    page.locator('#groupMemberSearch').fill('');page.locator('#groupCohortCategory').select_option('')
    page.locator('.groupParameters > summary').click()
    page.locator('#groupCollectionDetails').evaluate('(e)=>e.open=true')
    page.locator('#groupPlan').click()
    expect(page.locator('#groupPlanInfo')).to_contain_text('位圈内成员',timeout=90000)
    page.locator('#groupLimit').fill('5');expect(page.locator('#groupCollect')).to_be_disabled()
    # Server failure clears old results and permits a successful retry.
    endpoint='**/api/compute/groups/'+first['id']
    page.route(endpoint,lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"temporary test failure"}'))
    page.locator('#groupRun').click();expect(page.locator('#groupStatus')).to_contain_text('未完成')
    expect(page.locator('#groupRun')).to_be_enabled();expect(page.locator('#groupResults')).to_be_hidden()
    page.unroute(endpoint);page.locator('#groupRun').click()
    expect(page.locator('#groupStatus')).to_contain_text('已完成',timeout=90000)
    page.set_viewport_size({'width':390,'height':844});page.locator('#groupSummary').scroll_into_view_if_needed()
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.screenshot(path=str(OUT/'groups-mobile.png'))
    # A delayed response after a parameter change may not resurrect stale output.
    held=[];page.route(endpoint,lambda route:held.append(route))
    with page.expect_request(endpoint):page.locator('#groupRun').click()
    page.locator('#groupStart').fill('2017');expect(page.locator('#groupResults')).to_be_hidden()
    with page.expect_response(endpoint):held.pop().fulfill(status=200,content_type='application/json',body=json.dumps({'status':'complete','result':exported}))
    expect(page.locator('#groupStatus')).to_contain_text('范围已更改')
    expect(page.locator('#groupResults')).to_be_hidden();expect(page.locator('#groupRun')).to_be_enabled()
    # A delayed result cannot enter a different author's profile.
    with page.expect_request(endpoint):page.locator('#groupRun').click()
    page.locator('#profileHeader [data-open-dialog="settingsDialog"]').click()
    page.locator('#settingsDialog summary').click()
    page.locator(f'[data-job="{second["id"]}"]').click()
    expect(page.locator('#name')).to_have_text(second['author']['display_name'],timeout=60000)
    with page.expect_response(endpoint):held.pop().fulfill(status=200,content_type='application/json',body=json.dumps({'status':'complete','result':exported}))
    expect(page.locator('#groupResults')).to_be_hidden();expect(page.locator('#groupExport')).to_be_disabled()
    assert not errors,errors
    browser.close()
result={'status':'passed','desktop_mobile_export':True,'non_focal_evidence_checked':bool(cohorts),
        'filters':True,'error_retry':True,'parameter_and_profile_isolation':True,'collection_preview':True}
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
