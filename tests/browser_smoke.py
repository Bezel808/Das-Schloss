"""Read-only UI regression against a running local app with collected authors.

Requires Playwright and Chromium/Chrome. Never starts collection or sends a key.
"""
import argparse
import json
import os
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect


def check(url, output):
    with httpx.Client(trust_env=False, timeout=60) as client:
        jobs=client.get(url+'/api/jobs').raise_for_status().json()
    jobs=[j for j in jobs if j['status']=='complete' and j['received']>0]
    if len(jobs)<2:raise ValueError('Collect at least two authors before this cross-profile regression')
    first=next((j for j in jobs if 50<=j['received']<=500),jobs[0])
    second=next(j for j in jobs if j['id']!=first['id'])
    output.mkdir(parents=True,exist_ok=True)
    executable=os.environ.get('SCHOLARTRACE_BROWSER_EXECUTABLE')
    default=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    if not executable and default.exists():executable=str(default)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(**({'executable_path':executable} if executable else {}),headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(url+'?author='+first['id'])
        page.locator(f'[data-job="{first["id"]}"]').click()
        expect(page.locator('#name')).to_have_text(first['author']['display_name'],timeout=60000)
        page.locator('[data-tab="network"]').click()
        assert page.locator('#graph circle').count()>0
        assert page.evaluate("window.open.toString().includes('[native code]')")
        page.locator('[data-tab="experiments"]').click();page.locator('#experimentLoad').click()
        expect(page.locator('#experimentDataset option')).to_have_count(8)
        for dataset in range(8):
            page.locator('#experimentDataset').select_option(str(dataset))
            for task in ['new','repeat']:
                page.locator('#experimentTask').select_option(task)
                for score in page.locator('#experimentScore option').evaluate_all('(options)=>options.map(x=>x.value)'):
                    page.locator('#experimentScore').select_option(score)
                    assert page.locator('#experimentResults tbody').first.locator('tr').count()==7
                    assert 'NaN' not in page.locator('#experiments').inner_text()
        page.locator('#experimentTask').select_option('new')
        page.screenshot(path=str(output/'experiments-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.screenshot(path=str(output/'experiments-mobile.png'),full_page=True)
        with page.expect_download() as download:page.locator('#experimentExport').click()
        download.value.save_as(output/'evidence-export.json')
        exported=json.loads((output/'evidence-export.json').read_text())
        assert len(exported['holdout']['reports'])==10
        assert exported['independent_replay']['recomputed_target_years']==5120
        # A delayed retrieval response must not contaminate another profile.
        held=[];page.route('**/api/retrieve/**',lambda route:held.append(route))
        page.locator('[data-tab="retrieve"]').click();page.locator('#retrieveQuery').fill('network')
        with page.expect_request('**/api/retrieve/**'):page.locator('#retrieveForm button').click()
        expect(page.locator('#retrieveForm')).to_be_visible()
        assert held
        pending_reports=[];page.route('**/api/report/**',lambda route:pending_reports.append(route))
        page.locator(f'[data-job="{second["id"]}"]').click()
        expect(page.locator('#name')).to_have_text(second['id'])
        assert page.locator('#graph circle').count()==0
        with page.expect_response('**/api/retrieve/**'):
            held[0].fulfill(status=200,content_type='application/json',body=json.dumps({'corpus_size':1,'results':[
                {'id':'https://openalex.org/W1','title':'STALE_PROFILE_SENTINEL','year':2000,'score':1,'matched_terms':[],'excerpt':''}]}))
        page.unroute('**/api/retrieve/**');page.unroute('**/api/report/**')
        for route in pending_reports:route.continue_()
        expect(page.locator('#name')).to_have_text(second['author']['display_name'],timeout=60000)
        assert page.locator('#retrieved').inner_text()==''
        # Errors must leave an actionable retry state, with no stale panel.
        page.locator('[data-tab="insights"]').click()
        page.route('**/api/compute/insights/**',lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"test unavailable"}'))
        page.locator('#insightRun').click();expect(page.locator('#insightStatus')).to_contain_text('计算未完成')
        expect(page.locator('#insightRun')).to_be_enabled()
        page.unroute('**/api/compute/insights/**');page.locator('#insightRun').click()
        expect(page.locator('#insightStatus')).to_contain_text('10 个年度截面',timeout=60000)
        assert not errors,errors
        browser.close()
    result={'status':'passed','experiment_combinations':72,'cross_profile_delayed_response':'isolated',
            'insights_error_and_retry':'passed','desktop_mobile_export':'passed'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=Path('data/research/browser-qa'))
    args=parser.parse_args();check(args.url.rstrip('/'),args.output)
