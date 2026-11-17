"""Read-only regression of the unified real-data collaboration graph."""
import json
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
BASE='http://127.0.0.1:8000';A='A5091518548'
OUT=Path('data/research/group-unified-qa');OUT.mkdir(parents=True,exist_ok=True)
with httpx.Client(trust_env=False,timeout=60) as c:
 data=c.get(BASE+'/api/groups/'+A).raise_for_status().json()
nodes=data['structure']['nodes'];edges=data['structure']['edges'];groups=data['structure']['observed_subgroups']
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
 page=b.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/api/groups/*/auto',lambda r:r.abort())
 page.goto(BASE+'?author='+A);expect(page.locator('#name')).to_have_text(data['name'],timeout=60000)
 page.locator('[data-tab="groups"]').click();expect(page.locator('#groupResults')).to_be_visible(timeout=60000)
 expect(page.locator('#groupGraph .subgroupNode')).to_have_count(len(nodes))
 expect(page.locator('#groupGraph .groupNetworkEdges line')).to_have_count(len(edges))
 assert page.locator('#groupGraph .subgroupArea').count()==0
 assert page.locator('#groupGraph [data-community="unassigned"]').count()==data['structure']['isolates']
 assert page.locator('#groupShowBridges').is_checked()
 actual=page.locator('#groupGraph .groupNetworkEdges line').evaluate_all('(xs)=>xs.map(x=>[x.dataset.source,x.dataset.target])')
 assert sorted(actual)==sorted([[e['source'],e['target']] for e in edges])
 coordinates=lambda:page.locator('#groupGraph .subgroupNode').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("transform"))')
 expect(page.locator('#groupGraph')).to_have_attribute('data-motion','settled',timeout=15000)
 before=coordinates()
 page.locator('#groupFocus').select_option('0')
 expect(page.locator('#groupGraph .subgroupNode')).to_have_count(len(nodes))
 assert coordinates()==before
 expect(page.locator('#groupSelection')).to_contain_text('完整网络')
 page.locator('#groupResetFocus').click()
 person=nodes[0]
 page.locator('#groupFindPerson').fill(person['name']);assert coordinates()==before
 page.locator('#groupFindPerson').fill('')
 # Edge evidence remains tied to the actual source papers.
 edge=page.locator('#groupGraph .groupNetworkEdges line').first
 edge.focus();edge.press('Enter');expect(page.locator('#groupEvidencePanel')).to_be_visible()
 # Selecting an isolated member keeps all nodes and locates the real grey node.
 isolate=page.locator('#groupGraph [data-community="unassigned"]').first
 isolate.focus();isolate.press('Enter');expect(page.locator('#groupGraph .memberSelected')).to_have_count(1)
 expect(page.locator('#groupGraph .subgroupNode')).to_have_count(len(nodes))
 page.locator('#groupResetFocus').click()
 # Drag an actual connected node: neighbors follow, then it springs back.
 graph=page.locator('#groupGraph');graph.scroll_into_view_if_needed()
 node_id=edges[0]['source'];neighbor_id=edges[0]['target']
 node=page.locator('#groupGraph [data-author="'+node_id+'"]')
 neighbor=page.locator('#groupGraph [data-author="'+neighbor_id+'"]')
 xy=lambda element:element.evaluate('(e)=>[e.__data__.x,e.__data__.y]')
 distance=lambda a,b:((a[0]-b[0])**2+(a[1]-b[1])**2)**.5
 old=xy(node);neighbor_old=xy(neighbor);box=node.locator('circle').bounding_box()
 page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down()
 page.mouse.move(box['x']+box['width']/2+110,box['y']+box['height']/2+65,steps=12)
 page.wait_for_timeout(500)
 pulled=xy(node);neighbor_movement=distance(xy(neighbor),neighbor_old)
 assert distance(pulled,old)>70
 assert neighbor_movement>2,neighbor_movement
 page.mouse.up()
 expect(graph).to_have_attribute('data-motion','settled',timeout=15000)
 springback=distance(xy(node),old)
 assert springback<distance(pulled,old)*.35,(springback,old,pulled,xy(node))
 assert node.evaluate('(e)=>e.__data__.fx==null&&e.__data__.fy==null')
 assert page.locator('#groupGraph .groupNetworkEdges line').count()==len(edges)
 # Switching tabs pauses movement; returning resumes without changing topology.
 box=node.locator('circle').bounding_box()
 page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down()
 page.mouse.move(box['x']+box['width']/2+80,box['y']+box['height']/2,steps=5);page.mouse.up()
 page.locator('[data-tab="papers"]').click();page.wait_for_timeout(100)
 paused=coordinates();page.wait_for_timeout(200);assert coordinates()==paused
 page.locator('[data-tab="groups"]').click()
 expect(graph).to_have_attribute('data-motion','settled',timeout=15000)
 page.locator('#groupFitGraph').click()
 page.locator('#groupShowBridges').uncheck();assert page.locator('#groupGraph .subgroupNode').count()==len(nodes)
 page.locator('#groupShowBridges').check()
 page.locator('#groupGraphLegend').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'desktop.png'))
 page.set_viewport_size({'width':390,'height':844});page.locator('#groupFitGraph').click()
 page.locator('#groupGraph').scroll_into_view_if_needed();assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 page.screenshot(path=str(OUT/'mobile.png'))
 # Reduced-motion preference suppresses initial animation but keeps graph usable.
 page.emulate_media(reduced_motion='reduce');page.reload()
 expect(page.locator('#name')).to_have_text(data['name'],timeout=60000)
 page.locator('[data-tab="groups"]').click();expect(page.locator('#groupResults')).to_be_visible(timeout=60000)
 expect(page.locator('#groupGraph')).to_have_attribute('data-motion','settled')
 expect(page.locator('#groupGraph .subgroupNode')).to_have_count(len(nodes))
 assert not errors,errors;b.close()
print(json.dumps({'status':'passed','nodes':len(nodes),'edges':len(edges),'isolates':data['structure']['isolates'],'groups':len(groups),'neighbor_movement':round(neighbor_movement,2),'return_distance':round(springback,2),'coverage':'all real edges; stable highlighting; neighbor motion and spring return; tab pause/resume; reduced motion; search, evidence, resize'}))
