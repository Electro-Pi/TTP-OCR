import httpx,time,json,pathlib,os,re
base=os.getenv('OCR_TEST_BASE_URL','http://127.0.0.1:8115')+'/ocr/api/'
with httpx.Client(timeout=30) as c:
 print('health',c.get(base+'health').json(),flush=True)
 with open('test-results/diagram.png','rb') as f:
  r=c.post(base+'jobs',files={'image':('diagram.png',f,'image/png')},data={'preserve_terms':'true'})
 print('upload',r.status_code,r.text,flush=True)
 r.raise_for_status();jid=r.json()['id']
 pathlib.Path('test-results/smoke-session.json').write_text(json.dumps({'id':jid,'cookies':dict(c.cookies)}))
 for i in range(150):
  j=c.get(base+'jobs/'+jid).json()
  if i%5==0:print(j['status'],j.get('stage'),flush=True)
  if j['status'] in ['done','error']:
   pathlib.Path('test-results/smoke-job.json').write_text(json.dumps(j,ensure_ascii=False,indent=2))
   print(json.dumps({k:v for k,v in j.items() if k!='regions'},ensure_ascii=False,indent=2))
   print([(r['text'],r['translation'],r['warnings']) for r in j['regions']])
   if j['status']=='done':
    assert j['preserve_terms'] is False
    assert not any(re.search('[A-Za-z]',r['translation']) for r in j['regions'])
    assert all(r.get('direction')=='rtl' and r.get('alignment')=='right' for r in j['regions'])
    pathlib.Path('test-results/translated.png').write_bytes(c.get(base+'jobs/'+jid+'/translated').content)
    assert c.get(base+'jobs/'+jid+'/translated?download=true').headers['content-type']=='image/png'
    assert httpx.get(base+'jobs/'+jid).status_code==404
    assert c.post(base+'jobs',headers={'Origin':'https://example.com'},files={'image':('test.png',b'bad','image/png')}).status_code==403
    assert c.post(base+'jobs',files={'image':('test.png',b'bad','image/png')}).status_code==400
   else:raise RuntimeError(j.get('error'))
   break
  time.sleep(2)
 else:raise RuntimeError('Timed out')
