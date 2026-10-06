import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright
# Run against a local server with Playwright installed. All auth state is browser-only.
BASE=os.environ.get('CINEMA_PREVIEW_URL','http://127.0.0.1:8002')
async def main():
 Path('.local').mkdir(exist_ok=True)
 async with async_playwright() as p:
  browser=await p.chromium.launch()
  for width in [1536,390,320]:
   ctx=await browser.new_context(viewport={'width':width,'height':900},service_workers='block');page=await ctx.new_page()
   cdp=await ctx.new_cdp_session(page);await cdp.send('Network.enable');await cdp.send('Network.setCacheDisabled',{'cacheDisabled':True});await cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':120,'downloadThroughput':150000,'uploadThroughput':75000})
   images=asyncio.Event();fonts=asyncio.Event();auth=asyncio.Event();week_gate=asyncio.Event();pending={'image':0,'font':0}
   await page.add_init_script("localStorage.setItem('cinema_club_token','browser-only')")
   async def route(r):
    typ=r.request.resource_type
    if typ in ['font','image']:
     pending[typ]+=1;await (images if typ=='image' else fonts).wait();await r.continue_()
    elif r.request.url.endswith('/auth/me'):
     await auth.wait();await r.fulfill(json={'id':999,'username':'browser_admin','is_admin':True,'letterboxd_username':'browser_admin','letterboxd_avatar_url':'https://image.tmdb.org/t/p/w92/tisNLcMkxryU2zxhi0PiyDFqhm0.jpg'})
    elif r.request.url.endswith('/weeks/current'):
     await week_gate.wait();await r.continue_()
    else:await r.continue_()
   await page.route('**/*',route)
   await page.goto(BASE+'/preview',wait_until='domcontentloaded')
   await page.evaluate("window.hits=[];window.record=e=>{let b=e.target.closest('button,[role=button]');if(b){hits.push(b.id);e.preventDefault();e.stopImmediatePropagation()}};document.addEventListener('click',record,true)")
   initial={}
   async def check(stage):
    for selector in ['#btnLogin','#btnLogout','#btnChat','#btnTheme','#btnLetterboxd','#authAvatarPill']:
     e=page.locator(selector)
     if not await e.is_visible():continue
     box=await e.bounding_box();assert box['width']>=44 and box['height']>=44,(width,selector,box)
     if selector in initial:assert box==initial[selector],(stage,selector,initial[selector],box)
     else:initial[selector]=box
     for x,y in [(.5,.5),(.01,.5),(.99,.5),(.5,.01),(.5,.99)]:
      await page.mouse.move(0,0);await page.mouse.move(box['x']+max(1.5,min(box['width']-1.5,box['width']*x)),box['y']+max(1.5,min(box['height']-1.5,box['height']*y)));await page.wait_for_timeout(30)
      target=await page.evaluate('([x,y])=>{let e=document.elementFromPoint(x,y);return[e.closest("button,[role=button]")?.id,getComputedStyle(e).cursor]}',[box['x']+max(1.5,min(box['width']-1.5,box['width']*x)),box['y']+max(1.5,min(box['height']-1.5,box['height']*y))]);assert target==[selector[1:],'pointer'],(stage,selector,x,y,target,await page.evaluate('Object.fromEntries(["btnLogin","btnLogout","btnChat","btnTheme"].map(id=>{let e=document.getElementById(id),r=e.getBoundingClientRect();return[id,[r.x,r.y,r.width,r.height,getComputedStyle(e).gridColumn,getComputedStyle(e).display]]}))'))
      before=await page.evaluate('hits.length');await page.mouse.click(box['x']+max(1.5,min(box['width']-1.5,box['width']*x)),box['y']+max(1.5,min(box['height']-1.5,box['height']*y)));assert await page.evaluate('hits.length')==before+1
    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
    print(width,stage,'stable centres/edges',dict(pending),flush=True)
   await check('before authentication')
   auth.set();await page.locator('#btnLogout').wait_for();await check('images/fonts held, auth ready')
   week_gate.set();await page.locator('#btnChat').wait_for();await check('images loading, week ready')
   fonts.set();await page.evaluate('document.fonts.ready');await check('fonts loaded, images still held')
   images.set();await page.wait_for_function('Array.from(document.images).filter(i=>{const r=i.getBoundingClientRect();return r.top<innerHeight && r.bottom>0}).every(i=>i.complete)',timeout=45000);await check('images released')
   await page.evaluate('document.documentElement.dataset.theme="dark"');await check('dark theme')
   await page.screenshot(path=f'.local/loading-header-{width}.png')
   await page.evaluate("document.removeEventListener('click',record,true)")
   old=await page.locator('html').get_attribute('data-theme');await page.locator('#btnTheme').click();assert await page.locator('html').get_attribute('data-theme')!=old
   await page.locator('#btnChat').click();await page.locator('.chat-panel--open').wait_for();await page.locator('#chatClose').click()
   await ctx.close()
  await browser.close()
asyncio.run(main())
