import copy
from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:8013'
with sync_playwright() as p:
 browser=p.chromium.launch()
 ctx=browser.new_context(viewport={'width':390,'height':844},service_workers='block')
 ctx.add_init_script("localStorage.setItem('cinema_club_token','browser-test-only')")
 page=ctx.new_page()
 week=page.request.get(BASE+'/preview/data?path=/weeks/current&stage=voting').json()
 week.update(is_open=True,phase='voting',winner_film_id=None,voting_open=True,submissions_open=False,is_ready=True,submission_deadline=None,voting_deadline=None)
 state={'week':week,'chat':[]}
 posts=[]
 user={'id':999,'username':'browser_test','is_admin':False,'letterboxd_username':'browser_test'}
 page.route('**/auth/me',lambda r:r.fulfill(json=user))
 page.route('**/weeks/current',lambda r:r.fulfill(json=state['week']))
 page.route('**/letterboxd/members',lambda r:r.fulfill(json=[]))
 page.route('**/films/*/reactions',lambda r:r.fulfill(json=[]))
 def vote(r):
  posts.append(r.request.post_data_json)
  state['week']['films'][0]['votes']=1
  r.fulfill(json=state['week'])
 page.route('**/weeks/*/vote',vote)
 page.goto(BASE+'/preview?theme=halloween&demo=0',wait_until='networkidle')
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 page.locator('.film-actions button').first.click()
 page.wait_for_function("localStorage.getItem('cinema_club_voted_week_-670')!==null")
 assert posts[-1]=={'film_id':week['films'][0]['id']}
 assert 'voto' in page.locator('.film-actions button').first.inner_text().lower()
 state['week'].update(phase='submissions',voting_open=False,submissions_open=True,is_ready=False)
 page.evaluate('(w)=>render(w)',state['week'])
 def submit(r):
  posts.append(r.request.post_data_json)
  state['week']['films'].append(dict(state['week']['films'][0],id=999,title='Browser test submission',votes=0))
  r.fulfill(json=state['week'])
 page.route('**/weeks/*/submissions',submit)
 page.locator('#openSubmission').click()
 page.locator('#subTitle').fill('Browser test submission')
 page.locator('#subYear').fill('2001')
 page.locator('#subDirector').fill('Browser test director')
 page.locator('#subBtn').click()
 page.wait_for_function('!document.getElementById("submissionDialog").open')
 assert posts[-1]=={'title':'Browser test submission','year':2001,'director':'Browser test director'}
 assert page.locator('#films .film-card').count()==5
 def chat(r):
  if r.request.method=='POST':
   posts.append(r.request.post_data_json)
   state['chat'].append({'id':1,'user':user,'content':posts[-1]['content'],'created_at':1791300000})
   r.fulfill(json=state['chat'][0])
  else:r.fulfill(json=state['chat'])
 page.route('**/weeks/*/chat*',chat)
 page.locator('#btnChat').click()
 page.locator('#chatInput').fill('Browser-only chat check')
 page.locator('#chatSend').click()
 page.wait_for_selector('.chat-msg')
 assert posts[-1]=={'content':'Browser-only chat check'}
 assert 'Browser-only chat check' in page.locator('.chat-msg').inner_text()
 page.keyboard.press('Escape')
 assert page.locator('#chatPanel').evaluate('e=>e.inert')
 page.wait_for_function('getComputedStyle(document.getElementById("chatOverlay")).opacity==="0"')
 page.screenshot(path='.local/halloween/authenticated-mobile.png',full_page=True)
 print('Authenticated voting, submission and chat passed; all writes intercepted in browser, database unchanged.')
 browser.close()
