from pathlib import Path
import os
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/home/bassem/.cache/ms-playwright/chromium-1193/chrome-linux/chrome',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(os.getenv('OCR_TEST_BASE_URL','http://127.0.0.1:8115')+'/ocr/',wait_until='networkidle')
    page.screenshot(path=str(ROOT/'test-results/desktop.png'),full_page=True)
    assert page.locator('html').get_attribute('dir')=='rtl'
    assert page.locator('html').get_attribute('lang')=='ar'
    assert page.locator('#preserve-terms').count()==0
    print('Title:',page.title(),'Errors:',errors,flush=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(ROOT/'test-results/mobile.png'),full_page=True)
    assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth'),'Mobile overflow'
    page.set_viewport_size({'width':1440,'height':1100})
    page.locator('#file-input').set_input_files(str(ROOT/'test-results/diagram.png'))
    page.locator('#translate-button').click(timeout=60000)
    page.locator('#download-button').wait_for(state='visible',timeout=240000)
    assert page.locator('#review-rows textarea').count()>15
    assert page.locator('#review-rows textarea').evaluate_all("els => els.every(el => !/[A-Za-z]/.test(el.value))")
    page.locator('[data-view="compare"]').click()
    page.locator('#compare-range').fill('35')
    page.screenshot(path=str(ROOT/'test-results/comparison.png'),full_page=True)
    page.locator('[data-view="translated"]').click()
    textarea=page.locator('#review-rows textarea').first
    textarea.fill('طبقة الوصول الآمن')
    page.locator('#apply-button').click()
    page.locator('#processing-overlay').wait_for(state='hidden',timeout=60000)
    with page.expect_download() as info:
        page.locator('#download-button').click()
    download=info.value
    download.save_as(str(ROOT/'test-results/browser-download.png'))
    assert Path(ROOT/'test-results/browser-download.png').read_bytes().startswith(b'\x89PNG')
    page.reload(wait_until='networkidle')
    page.locator('#download-button').wait_for(state='visible',timeout=15000)
    page.screenshot(path=str(ROOT/'test-results/result.png'),full_page=True)
    assert not errors,errors
    print('PASS: desktop, mobile, upload, comparison, Arabic editing, download, session restore; no JS errors',flush=True)
    browser.close()
