"""Read-only live edge filter, meaning, evidence and export regression."""
import itertools,json,os
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('SCHOLARTRACE_TEST_URL','http://127.0.0.1:8000')
OUT=Path('data/research/edge-browser-qa');OUT.mkdir(parents=True,exist_ok=True)
with httpx.Client(trust_env=False,timeout=90) as client:
 jobs=client.get(BASE+'/api/jobs').raise_for_status().json()
 job=next(j for j in jobs if j['id']=='A5091518548')
 report=client.get(BASE+'/api/report/'+job['id']).raise_for_status().json()
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=os.environ.get('SCHOLARTRACE_BROWSER_EXECUTABLE','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'?author='+job['id']);expect(page.locator('#name')).to_have_text(job['author']['display_name'],timeout=60000)
 expect(page.locator('#name')).to_have_text(job['author']['display_name'],timeout=90000)
 page.locator('[data-tab="network"]').click()
 for kind,inst,repeat in itertools.product(['all','focal_coauthor','coauthors_on_focal_papers'],['all','shared','disjoint','unknown'],['all','single','multiple','cross_year']):
  page.locator('#edgeKind').select_option(kind);page.locator('#edgeInstitution').select_option(inst);page.locator('#edgeRepeat').select_option(repeat)
  matches=[e for e in report['graph']['edges'] if (kind=='all' or e['semantics']['kind']==kind) and (inst=='all' or e['semantics']['institution_work_ids'][inst]) and (repeat=='all' or repeat=='single' and e['weight_raw']==1 or repeat=='multiple' and e['weight_raw']>=2 or repeat=='cross_year' and len(e['active_years'])>=2)]
  expect(page.locator('#graphSummary')).to_contain_text('条件匹配 '+str(len(matches))+' 条')
  rendered=page.locator('.network-edge').evaluate_all('(xs)=>xs.map(x=>({source:x.__data__.source.id,target:x.__data__.target.id}))')
  allowed={frozenset([e['source'],e['target']]) for e in matches}
  assert all(frozenset([e['source'],e['target']]) in allowed for e in rendered)
 for id in ['edgeKind','edgeInstitution','edgeRepeat']:page.locator('#'+id).select_option('all')
 page.locator('#edgeKind').select_option('coauthors_on_focal_papers')
 edge=page.locator('.network-edge').first
 edge.evaluate('(e)=>e.focus()');edge.press('Enter')
 expect(page.locator('#nodeDetail')).to_contain_text('灰色虚线')
 expect(page.locator('#nodeDetail')).to_contain_text('不证明')
 with page.expect_download() as event:page.locator('#exportFilteredGraph').click()
 event.value.save_as(OUT/'filtered-edges.json')
 result=json.loads((OUT/'filtered-edges.json').read_text())
 assert result['edges'] and all(e['semantics']['kind']=='coauthors_on_focal_papers' for e in result['edges'])
 assert all(isinstance(e['source'],str) for e in result['edges'])
 page.locator('#nodeDetail').get_by_role('button',name='全部共同论文',exact=False).click()
 expect(page.locator('#papers')).to_be_visible();assert page.locator('#paperList .paper').count()>0
 page.locator('[data-tab="network"]').click()
 page.locator('#edgeKind').select_option('focal_coauthor')
 edge=page.locator('.network-edge').first;edge.evaluate('(e)=>e.focus()');edge.press('Enter')
 expect(page.locator('#nodeDetail')).to_contain_text('绿色实线')
 with page.expect_download() as download:page.locator('#exportGraph').click()
 download.value.save_as(OUT/'network.svg')
 from xml.etree import ElementTree
 exported_svg=ElementTree.parse(OUT/'network.svg').getroot()
 assert exported_svg.find('{http://www.w3.org/2000/svg}rect').attrib['fill']=='#f5f8f2'
 assert any('rgb(41, 68, 56)' in n.attrib.get('style','') for n in exported_svg.iter('{http://www.w3.org/2000/svg}text'))
 page.locator('.networkControls').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'desktop.png'))
 page.set_viewport_size({'width':390,'height':844});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 page.locator('.networkControls').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'mobile.png'))
 page.locator('#minShared').fill('99999');page.locator('#minShared').dispatch_event('change')
 expect(page.locator('.network-edge')).to_have_count(0)
 expect(page.locator('#nodeDetail')).to_contain_text('没有满足')
 assert not errors,errors
 browser.close()
print(json.dumps({'status':'passed','filter_combinations':48,'keyboard_edge_inspection':True,'paper_evidence':True,'filtered_json_export':True,'desktop_mobile':True,'empty_state':True}))
