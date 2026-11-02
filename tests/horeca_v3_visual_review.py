"""Browser visual review of actual HoReCa One ERP screens; fake offline data only."""
from __future__ import annotations

import os
import json
import runpy
import sys
import time
import zipfile
import subprocess
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
runpy.run_path(str(ROOT/'installer'/'horeca_v3_preview_hook.py'))
idx=sys.argv.index('--data')
DATA_DIR=Path(sys.argv[idx+1])
PORT=8163
URL=f'http://127.0.0.1:{PORT}/hotel_erp.html'
shots=ROOT/'horeca-v3-visual-review'
shots.mkdir(exist_ok=True)
routes=[
 ('01_dashboard','gateway'),('02_billing','bill'),('03_bill_history','bills'),
 ('04_cashier_shifts','sessions'),('05_zomato_swiggy','online'),
 ('06_qr_orders','qr'),('07_captain','captain'),('08_kitchen','kitchen'),
 ('09_tokens','tokens'),('10_reservations','reservations'),
 ('11_purchase','purchase'),('12_stock','stock'),('13_suppliers','suppliers'),
 ('14_expenses','expense'),('15_cash_counter','cash'),('16_day_book','daybook'),
 ('17_gst','gst'),('18_analytics','analytics'),('19_whatsapp','wa-reports'),
 ('20_settings','settings'),('21_user_guide','guide'),('22_setu_ai','ai')
]
server=subprocess.Popen(
    [sys.executable,str(ROOT/'app_main.py'),'--server','--port',str(PORT),'--data',str(DATA_DIR)],
    stdout=(shots/'server.log').open('w',encoding='utf-8'),
    stderr=subprocess.STDOUT,
    env=os.environ.copy()
)
try:
    ready=False
    for _ in range(70):
        try:
            urllib.request.urlopen(URL,timeout=3).read(256)
            ready=True
            break
        except Exception:
            if server.poll() is not None:
                raise RuntimeError('Server exited before startup')
            time.sleep(.5)
    if not ready:
        raise RuntimeError('Preview server did not start')
    result={'url':URL,'views':[],'login':None}
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1536,'height':950},device_scale_factor=1)
        page=context.new_page()
        page.goto(URL,wait_until='domcontentloaded',timeout=45000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(shots/'00_initial_login.png'),full_page=True)
        page.evaluate("showLoginView('existing')")
        page.locator('#exist_hotel_id').fill('DEMOLOCAL')
        page.locator('#exist_username').fill('owner')
        page.locator('#exist_password').fill('Preview@2026')
        page.locator('#btn-exist-pull').click()
        page.wait_for_timeout(3500)
        info=page.evaluate("""() => ({
            authHidden:getComputedStyle(document.querySelector('#login-screen')).display==='none',
            authError:document.querySelector('#exist_pull_err')?.textContent||'',
            lockHidden:getComputedStyle(document.querySelector('#lock-screen')).display==='none'
        })""")
        result['login']=info
        page.screenshot(path=str(shots/'00_after_login.png'),full_page=True)
        if not info['authHidden'] or not info['lockHidden']:
            (shots/'review-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            raise RuntimeError('Demo login did not complete: '+str(info))
        for label,route in routes:
            error=''
            try:
                page.evaluate('(route)=>go(route)',route)
                page.wait_for_timeout(550)
                main=page.locator('#main')
                text=main.inner_text(timeout=8000)
                if 'This screen could not open' in text:
                    error='ERP screen renderer returned an error'
                width=page.evaluate("""() => ({
                    document:document.documentElement.scrollWidth,
                    viewport:document.documentElement.clientWidth,
                    panel:document.querySelector('#main')?.scrollWidth||0
                })""")
                page.screenshot(path=str(shots/(label+'.png')),full_page=False,timeout=15000)
                result['views'].append({'route':route,'status':'error' if error else 'rendered',
                                        'error':error,'widths':width,'characters':len(text)})
            except Exception as e:
                result['views'].append({'route':route,'status':'exception','error':str(e)[:500]})
        browser.close()
    (shots/'review-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    with zipfile.ZipFile(ROOT/'HoReCa-One-V3-Actual-Screen-Review.zip','w',
                         compression=zipfile.ZIP_DEFLATED) as bundle:
        for file in shots.iterdir():
            if file.is_file() and file.name!='server.log':
                bundle.write(file,arcname=file.name)
    bad=[v for v in result['views'] if v['status']!='rendered']
    print('Screen count',len(result['views']),'issues',len(bad))
    if bad:
        print(json.dumps(bad,indent=2))
        raise RuntimeError('One or more screens have errors')
finally:
    server.terminate()
    try:server.wait(timeout=10)
    except subprocess.TimeoutExpired:server.kill()
