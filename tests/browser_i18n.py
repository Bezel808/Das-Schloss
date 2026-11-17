"""Bilingual UI integration, including source preservation and async updates.
Synthetic papers exercise UI behavior; no external retrieval or keys are used.
"""
import gzip
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from tests.browser_ui_helpers import mock_profile
from scholartrace import analyze
from scholartrace.network import decorate_graph

OUT=Path('data/research/i18n-qa');OUT.mkdir(parents=True,exist_ok=True)
works=json.loads(Path('examples/synthetic.json').read_text())
works[0]['title']='合作网络'
works[0]['abstract_inverted_index']={'科研早期':[0],'论文证据':[1]}
author={'id':'https://openalex.org/A1','display_name':'张三','last_known_institutions':[{'display_name':'科研早期'}]}
report=analyze(author['id'],works);decorate_graph(report['graph'],works,author['id'])
report.update(author=author,papers=works,omitted=[],missing_year_count=0,status='complete',retrieved_at='test',
              time_axis={'minimum_year':2020,'maximum_year':2022,'available_years':[2020,2021,2022]})
portrait=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/group-portrait.json.gz').read_bytes()))
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
 page=b.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce',accept_downloads=True)
 errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda r:requests.append(r.url) if '/api/' in r.url else None)
 mock_profile(page,author_id='A1',name='张三')
 page.route('**/api/report/A1?*',lambda r:r.fulfill(json=report))
 page.route('**/api/groups/*/collection',lambda r:r.fulfill(json={'status':'not_started'}))
 page.route('**/api/compute/groups/*',lambda r:r.fulfill(json={'status':'complete','result':portrait}))
 page.route('**/api/compute/insights/*',lambda r:r.fulfill(json={'status':'complete','result':{'panel':{'rows':[{'year':2020}]},'corpus':{'scope':'当前学者与直接合作者已完成的论文历史；指标限于这个观察范围。','author_corpora':[{'id':'A1'}]}}}))
 page.route('**/api/retrieve/A1?*',lambda r:r.fulfill(json={'corpus_size':3,'results':[{'id':works[0]['id'],'title':'合作网络','year':2020,'score':1.2,'matched_terms':['科研早期'],'excerpt':'科研早期 论文证据'}]}))
 page.goto('http://127.0.0.1:8000')
 expect(page.locator('html')).to_have_attribute('lang','zh-CN')
 page.locator('#query').fill('Chao Huang')
 page.locator('#landingNav [data-language-switch]').click()
 expect(page.locator('#search button')).to_have_text('Search')
 expect(page.locator('#query')).to_have_value('Chao Huang')
 expect(page.locator('#query')).to_have_attribute('placeholder','Search name, ORCID or OpenAlex ID')
 page.screenshot(path=str(OUT/'home-en.png'))
 # Locale survives refresh; only a language preference is stored.
 page.reload();expect(page.locator('html')).to_have_attribute('lang','en')
 assert page.evaluate('sessionStorage.getItem("schloss-language")')=='en'
 page.locator('#landingNav [data-open-dialog="settingsDialog"]').click()
 page.locator('#key').fill('test-value-never-sent')
 page.evaluate('i18n.setLanguage("zh")');expect(page.locator('#key')).to_have_value('test-value-never-sent')
 page.evaluate('i18n.setLanguage("en")');expect(page.locator('#settingsTitle')).to_have_text('Settings')
 page.locator('#key').fill('');page.keyboard.press('Escape')
 page.locator('#query').fill('Chao Huang');page.locator('#search button').click()
 expect(page.locator('[data-pick="0"]')).to_have_text('Open profile')
 page.locator('[data-pick="0"]').click();expect(page.locator('#name')).to_have_text('张三')
 expect(page.locator('#bio')).to_have_text('科研早期 · Latest affiliation')
 expect(page.locator('[data-tab="groups"]')).to_have_text('Teams & newcomers')
 page.locator('[data-tab="papers"]').click()
 expect(page.locator('#paperList .paper>a').last).to_contain_text('合作网络')
 page.locator('#paperList details').last.locator('summary').click()
 expect(page.locator('#paperList details').last).to_contain_text('科研早期 论文证据')
 # Source JSON remains untouched by a presentation-language change.
 with page.expect_download() as download:
  page.locator('.profileFilters').evaluate('(el)=>el.open=true');page.locator('#export').click()
 download.value.save_as(OUT/'report.json')
 assert json.loads((OUT/'report.json').read_text())['papers']==works
 page.locator('[data-tab="network"]').click()
 page.locator('#edgeKind').select_option('focal_coauthor')
 edge=page.locator('.network-edge').first;edge.focus();edge.press('Enter')
 expect(page.locator('#nodeDetail')).to_contain_text('Green solid link')
 # Switching does not refetch, reset filters, or recreate SVG nodes.
 page.evaluate('window.savedNetworkNode=document.querySelector(".network-edge")')
 before=len(requests)
 page.locator('#profileHeader [data-language-switch]').click()
 expect(page.locator('#nodeDetail')).to_contain_text('绿色实线')
 assert page.evaluate('window.savedNetworkNode===document.querySelector(".network-edge")')
 expect(page.locator('#edgeKind')).to_have_value('focal_coauthor')
 page.locator('#profileHeader [data-language-switch]').click()
 expect(page.locator('#nodeDetail')).to_contain_text('Green solid link')
 assert len(requests)==before
 page.locator('[data-tab="insights"]').click();page.locator('#insightRun').click()
 expect(page.locator('#insightPanel h3')).to_have_text('Researcher–year panel')
 expect(page.locator('#insightStatus')).to_contain_text('Completed publication histories')
 page.locator('[data-tab="retrieve"]').click();page.locator('#retrieveQuery').fill('collaboration')
 page.locator('#retrieveForm button').click()
 expect(page.locator('#retrieved .paper')).to_have_count(1)
 expect(page.locator('#retrieved')).to_contain_text('科研早期 论文证据')
 expect(page.locator('#retrieved button')).to_contain_text('View source paper')
 page.locator('[data-tab="groups"]').click();page.locator('#groupRun').click()
 expect(page.locator('#groupResults')).to_be_visible()
 expect(page.locator('#groupStatus')).to_contain_text('Complete')
 page.locator('#groupFocus').select_option('0')
 page.locator('#profileHeader [data-language-switch]').click()
 expect(page.locator('#groupFocus')).to_have_value('0');expect(page.locator('#groupRun')).to_have_text('重新分析')
 page.locator('#profileHeader [data-language-switch]').click()
 expect(page.locator('#groupRun')).to_have_text('Analyze again')
 page.locator('#groupGraphLegend').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'groups-en.png'))
 # Dynamic experiment text, tables and SVG labels are localized as they arrive.
 page.locator('[data-tab="experiments"]').click();page.locator('#experimentLoad').click()
 expect(page.locator('#experimentResults table').first).to_be_visible()
 page.locator('#experimentTask').select_option('repeat')
 expect(page.locator('#experimentChart')).to_have_attribute('aria-label','Tie-expected recall for repeat collaborations')
 page.wait_for_timeout(100)
 assert not page.evaluate('[...i18n.missing]'),page.evaluate('[...i18n.missing]')
 # Async backend error after switching language uses the current presentation locale.
 page.locator('#home').click()
 held=[];page.route('**/api/authors?*',lambda r:held.append(r))
 page.locator('#search button').click();page.wait_for_timeout(80)
 page.locator('#landingNav [data-language-switch]').click()
 assert held
 held.pop().fulfill(status=502,json={'detail':'OpenAlex 连接失败，请检查网络后继续。'})
 expect(page.locator('#notice')).to_contain_text('OpenAlex 连接失败')
 page.locator('#landingNav [data-language-switch]').click()
 expect(page.locator('#notice')).to_contain_text('Could not connect to OpenAlex')
 # Keyboard-accessible switch, mobile layout, About and native form labels.
 page.set_viewport_size({'width':390,'height':844})
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 page.screenshot(path=str(OUT/'home-en-mobile.png'))
 page.locator('#landingNav [data-open-dialog="aboutDialog"]').click()
 page.locator('#aboutDialog details').evaluate_all('(xs)=>xs.forEach(x=>x.open=true)')
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 assert 'How to use' in page.locator('#aboutDialog').inner_text()
 page.keyboard.press('Escape')
 switch=page.locator('#landingNav [data-language-switch]');switch.focus();page.keyboard.press('Enter')
 expect(page.locator('html')).to_have_attribute('lang','zh-CN')
 assert not errors,errors
 b.close()
print('PASS: bilingual navigation and dynamic data; reversible live switching; no refetch; filters and graph preserved; source records unchanged; refresh preference; async errors; keyboard and mobile')
