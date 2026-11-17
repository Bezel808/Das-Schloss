"""Exercise actual GLSL compilation/rendering and GPU lifecycle in Chrome."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from tests.browser_ui_helpers import mock_profile

OUT = Path('data/research/landing-qa');OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True,
                                args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width': 1440, 'height': 960})
    errors = [];page.on('pageerror', lambda e: errors.append(str(e)))
    mock_profile(page)
    page.goto('http://127.0.0.1:8000')
    canvas = page.locator('#landingShader')
    expect(canvas).to_have_attribute('data-renderer', 'webgl')
    frame = lambda: int(canvas.get_attribute('data-frame'))
    start = frame()
    page.wait_for_function('(n)=>+document.getElementById("landingShader").dataset.frame>n', arg=start)
    page.locator('#backgroundMotion').click()
    expect(page.locator('#backgroundMotion')).to_have_attribute('aria-pressed', 'true')
    start = frame();page.wait_for_timeout(200);assert frame() == start
    page.screenshot(path=str(OUT/'home-desktop.png'))
    assert canvas.evaluate('(c)=>c.width<=1280 && c.height<=1280')
    page.locator('#backgroundMotion').click()
    page.locator('#landingNav [data-open-dialog="aboutDialog"]').click()
    start = frame();page.wait_for_timeout(150);assert frame() == start
    page.keyboard.press('Escape')
    page.wait_for_function('(n)=>+document.getElementById("landingShader").dataset.frame>n', arg=start)
    page.locator('#query').fill('Chao Huang');page.locator('#search button').click()
    page.locator('[data-pick="0"]').click();expect(page.locator('#profile')).to_be_visible()
    start = frame();page.wait_for_timeout(200);assert frame() == start
    page.locator('#home').click()
    page.wait_for_function('(n)=>+document.getElementById("landingShader").dataset.frame>n', arg=start)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    # Context loss must retain a usable search page, then restore the renderer.
    page.evaluate('window.lose=document.getElementById("landingShader").getContext("webgl").getExtension("WEBGL_lose_context");window.lose.loseContext()')
    expect(canvas).to_have_attribute('data-renderer', 'fallback')
    expect(page.locator('#search')).to_be_visible()
    page.evaluate('window.lose.restoreContext()')
    expect(canvas).to_have_attribute('data-renderer', 'webgl')
    page.emulate_media(reduced_motion='reduce')
    # Manual choice overrides system changes for this page; a new page honours reduction.
    reduced = browser.new_page(reduced_motion='reduce', viewport={'width':390,'height':844})
    mock_profile(reduced);reduced.goto('http://127.0.0.1:8000')
    expect(reduced.locator('#backgroundMotion')).to_have_attribute('aria-pressed', 'true')
    start = reduced.locator('#landingShader').get_attribute('data-frame')
    reduced.wait_for_timeout(200);assert reduced.locator('#landingShader').get_attribute('data-frame') == start
    reduced.screenshot(path=str(OUT/'home-mobile.png'))
    fallback = browser.new_page()
    mock_profile(fallback)
    fallback.add_init_script('const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return type==="webgl"?null:original.call(this,type,...args)}')
    fallback.on('pageerror', lambda e: errors.append(str(e)))
    fallback.goto('http://127.0.0.1:8000')
    expect(fallback.locator('#landingShader')).to_have_attribute('data-renderer', 'fallback')
    expect(fallback.locator('#backgroundMotion')).to_be_enabled()
    expect(fallback.locator('#landingBackdrop')).to_have_attribute('data-motion', 'running')
    fog=fallback.locator('.fogFallback i').first
    assert fog.evaluate('(e)=>getComputedStyle(e).animationPlayState')=='running'
    before=fog.evaluate('(e)=>getComputedStyle(e).transform')
    fallback.wait_for_timeout(200)
    assert fog.evaluate('(e)=>getComputedStyle(e).transform')!=before
    fallback.locator('#backgroundMotion').click()
    expect(fallback.locator('#landingBackdrop')).to_have_attribute('data-motion', 'paused')
    before=fog.evaluate('(e)=>getComputedStyle(e).transform');fallback.wait_for_timeout(150)
    assert fog.evaluate('(e)=>getComputedStyle(e).transform')==before
    fallback.locator('#backgroundMotion').click()
    fallback.locator('#query').fill('Chao Huang');fallback.locator('#search button').click()
    expect(fallback.locator('#results .card')).to_have_count(1)
    fallback.screenshot(path=str(OUT/'fallback.png'))
    fallback.locator('[data-pick="0"]').click()
    expect(fallback.locator('#profile')).to_be_visible()
    expect(fallback.locator('#landingBackdrop')).to_have_attribute('data-motion', 'paused')
    fallback.locator('#home').click()
    expect(fallback.locator('#landingBackdrop')).to_have_attribute('data-motion', 'running')
    fallback.locator('#landingNav [data-open-dialog="aboutDialog"]').click()
    expect(fallback.locator('#landingBackdrop')).to_have_attribute('data-motion', 'paused')
    fallback.keyboard.press('Escape')
    expect(fallback.locator('#landingBackdrop')).to_have_attribute('data-motion', 'running')
    assert not errors, errors
    browser.close()
print('PASS: real WebGL passes, capped resolution, animation/pause, dialogs/profile idle, resume, mobile, context restoration, reduced motion, animated no-WebGL fallback')
