"""Real browser regression: cursor navigation, races, retry, and profile return."""
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect
from tests.browser_ui_helpers import mock_profile

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
    page = browser.new_page(reduced_motion='reduce')
    mock_profile(page, author_id='A13', name='Author 13')
    calls, held, errors = [], [], []
    fail_next = [False]
    page.on('pageerror', lambda e: errors.append(str(e)))

    def search(route):
        params = parse_qs(urlparse(route.request.url).query)
        query, cursor = params['q'][0], params['cursor'][0]
        calls.append((query, cursor))
        if query == 'Slow':
            held.append(route)
            return
        if fail_next[0]:
            fail_next[0] = False
            route.fulfill(status=502, json={'detail': 'temporary upstream failure'})
            return
        if query == 'Empty':
            route.fulfill(json={'results': [], 'meta': {'count': 0, 'next_cursor': None}})
            return
        start = 1 if cursor == '*' else 13
        rows = [{'id': 'https://openalex.org/A'+str(i), 'display_name': 'Author '+str(i)} for i in range(start, start+12)]
        # OpenAlex may send a cursor at the end: total still prevents an empty extra page.
        route.fulfill(json={'results': rows, 'meta': {'count': 24, 'next_cursor': 'next+/=&?'}})

    page.route('**/api/authors?*', search)
    page.goto('http://127.0.0.1:8000')
    page.locator('#query').fill('Huang');page.locator('#search button').click()
    expect(page.locator('#results .card')).to_have_count(12)
    expect(page.locator('#searchPageStatus')).to_have_text('第 1 页 · 1–12 / 24 位')
    expect(page.locator('#searchPrev')).to_be_disabled()
    fail_next[0] = True
    page.locator('#searchNext').click()
    expect(page.locator('#notice')).to_contain_text('temporary upstream failure')
    expect(page.locator('#results h3').first).to_have_text('Author 1')
    page.locator('#searchNext').click()
    expect(page.locator('#searchPageStatus')).to_have_text('第 2 页 · 13–24 / 24 位')
    expect(page.locator('#searchNext')).to_be_disabled()
    assert calls[-1] == ('Huang', 'next+/=&?')
    page.locator('[data-pick="0"]').click()
    expect(page.locator('#name')).to_have_text('Author 13')
    page.locator('#home').click()
    expect(page.locator('#searchPageStatus')).to_have_text('第 2 页 · 13–24 / 24 位')
    page.locator('#searchPrev').click()
    expect(page.locator('#results h3').first).to_have_text('Author 1')
    assert calls[-1] == ('Huang', '*')
    page.locator('#query').fill('Changed')
    expect(page.locator('#searchNext')).to_be_disabled()
    page.locator('#query').fill('Slow');page.locator('#search button').click()
    page.wait_for_function('document.getElementById("search").getAttribute("aria-busy")==="true"')
    page.locator('#query').fill('New');page.locator('#search button').click()
    expect(page.locator('#results .card')).to_have_count(12)
    assert held
    held.pop().fulfill(json={'results': [{'display_name': 'Stale'}], 'meta': {'count': 1}})
    page.wait_for_timeout(150)
    expect(page.locator('#results h3').first).to_have_text('Author 1')
    expect(page.locator('#searchPageStatus')).to_have_text('第 1 页 · 1–12 / 24 位')
    page.locator('#query').fill('Empty');page.locator('#search button').click()
    expect(page.locator('#searchPagination')).to_be_hidden()
    expect(page.locator('#results')).to_contain_text('没有匹配')
    assert not errors, errors
    browser.close()
print('PASS: cursor encoding, totals, next/previous, terminal page, retry, query reset, stale response isolation, profile return')
