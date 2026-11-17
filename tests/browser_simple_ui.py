"""Search, dialogs, back navigation and layout with controlled API responses."""
import gzip
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from tests.browser_ui_helpers import mock_profile

BASE='http://127.0.0.1:8000';A='A5091518548'
OUT=Path('data/research/simple-ui-qa');OUT.mkdir(parents=True,exist_ok=True)
portrait=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/group-portrait.json.gz').read_bytes()))
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
 page=b.new_page(viewport={'width':1440,'height':1000});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)));mock_profile(page)
 removed_requests=[];page.on('request',lambda r:removed_requests.append(r.url) if '/api/mining/' in r.url else None)
 page.route('**/api/groups/*/collection',lambda r:r.fulfill(json={'status':'not_started'}))
 page.route('**/api/compute/groups/*',lambda r:r.fulfill(json={'status':'complete','result':portrait}))
 page.route('**/api/groups/*/auto',lambda r:r.abort())
 page.goto(BASE)
 expect(page.locator('#search')).to_be_visible();expect(page.locator('#profileHeader')).to_be_hidden()
 assert page.locator('aside').count()==0
 expect(page.get_by_text('TRACE THE WORK. UNDERSTAND THE JOURNEY.')).to_be_hidden()
 page.screenshot(path=str(OUT/'search-desktop.png'))
 page.locator('#landingNav [data-open-dialog="aboutDialog"]').click()
 expect(page.locator('#aboutDialog')).to_be_visible()
 page.keyboard.press('Escape');expect(page.locator('#aboutDialog')).to_be_hidden()
 expect(page.locator('#landingNav [data-open-dialog="aboutDialog"]')).to_be_focused()
 page.locator('#landingNav [data-open-dialog="settingsDialog"]').click()
 expect(page.locator('#key')).to_be_visible();page.keyboard.press('Escape')
 page.locator('#query').fill('Chao Huang');page.locator('#search button').click()
 expect(page.locator('#results .card')).to_have_count(1)
 page.locator('[data-pick="0"]').click();expect(page.locator('#profile')).to_be_visible();expect(page.locator('#name')).to_have_text('Chao Huang')
 expect(page.locator('#landingNav')).to_be_hidden()
 assert page.locator('#profileHeader').bounding_box()['y']<2
 expect(page.locator('#home')).to_be_visible()
 page.screenshot(path=str(OUT/'profile-desktop.png'))
 page.locator('[data-tab="groups"]').click()
 expect(page.locator('#groupResults')).to_be_hidden()
 expect(page.locator('#groupCollection')).to_be_hidden()
 expect(page.locator('#groupAuto')).to_have_count(0)
 page.screenshot(path=str(OUT/'groups-before.png'))
 page.locator('#groupRun').click();expect(page.locator('#groupResults')).to_be_visible(timeout=15000)
 expect(page.locator('#groupGraph .subgroupNode')).to_have_count(len(portrait['structure']['nodes']))
 page.locator('#home').click();expect(page.locator('#searchView')).to_be_visible()
 expect(page.locator('#query')).to_have_value('Chao Huang')
 expect(page.locator('#results .card')).to_have_count(1)
 assert '?author=' not in page.url
 # Small screens also begin with the profile header, never settings/history.
 page.set_viewport_size({'width':390,'height':844})
 page.screenshot(path=str(OUT/'search-mobile.png'))
 page.locator('[data-pick="0"]').click();expect(page.locator('#profile')).to_be_visible();expect(page.locator('#name')).to_have_text('Chao Huang')
 assert page.locator('#profileHeader').bounding_box()['y']<2
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 page.screenshot(path=str(OUT/'profile-mobile.png'))
 page.locator('[data-tab="groups"]').click()
 page.screenshot(path=str(OUT/'groups-mobile.png'))
 # A computation returning after Back cannot reopen or populate the profile.
 held=[];page.route('**/api/compute/groups/*',lambda r:held.append(r))
 with page.expect_request('**/api/compute/groups/*'):page.locator('#groupRun').click()
 expect(page.locator('#groupResults')).to_be_hidden()
 page.locator('#home').click()
 with page.expect_response('**/api/compute/groups/*'):
  held.pop().fulfill(json={'status':'complete','result':portrait})
 expect(page.locator('#profile')).to_be_hidden();expect(page.locator('#groupResults')).to_be_hidden()
 assert page.locator('[data-tab="mining"],#mining').count()==0
 assert not removed_requests,removed_requests
 assert not errors,errors
 b.close()
print('PASS: search-first home; About/settings dialogs and focus; header-first desktop/mobile; back retains search; results gated; late response isolation')
