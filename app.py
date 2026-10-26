from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import secrets
import re
import shutil
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parent
load_dotenv(ROOT/'.env')
os.environ.setdefault('PADDLE_PDX_CACHE_HOME',str(ROOT/'models'))
os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK','True')
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from pipeline import LETTERS, WARNINGS, detect, get_digit_reader, get_engine, render, shorten, translate

Image.MAX_IMAGE_PIXELS=16_000_000
DATA=ROOT/'data'
DATA.mkdir(exist_ok=True,mode=0o700)
log=logging.getLogger('ocr')
pool=ProcessPoolExecutor(max_workers=1,mp_context=get_context('spawn'))
lock=threading.RLock()
jobs={}
rates=defaultdict(deque)
global_rate=deque()
engine_state={'status':'loading','message':'Preparing the OCR models'}
MAX_UPLOAD_MB=50
MAX_UPLOAD=MAX_UPLOAD_MB*1024*1024
API_TIMEOUT=170
api_active=[0]


class Unprocessable(RuntimeError):
    """The image itself cannot be localized; the message is shown to the user."""


def save_job(job):
    with lock:
        job['updated']=time.time()
        path=DATA/job['id']/'job.json'
        temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(job,ensure_ascii=False))
        temp.replace(path)


def update(job, **fields):
    with lock:
        job.update(fields)
        save_job(job)


def warmup():
    try:
        blank=__import__('numpy').full((64,192,3),255,dtype='uint8')
        for lang in ('en','ar'):
            get_engine(lang).predict(blank)
        get_digit_reader().predict([blank])
        return {'status':'ready','message':'CPU OCR is ready'}
    except Exception:
        log.exception('OCR initialization failed')
        return {'status':'error','message':'OCR models could not be loaded. Check the server configuration.'}


def sync_jobs():
    with lock:
        for jid, job in list(jobs.items()):
            if job['status'] in ('queued','processing'):
                try:
                    jobs[jid]=json.loads((DATA/jid/'job.json').read_text())
                except (OSError,ValueError):
                    pass


def worker_ready(future):
    try:
        engine_state.update(future.result())
    except Exception:
        log.exception('Worker startup failed')
        engine_state.update(status='error',message='The OCR worker could not start.')


def cleanup():
    sync_jobs()
    cutoff=time.time()-int(os.getenv('DATA_RETENTION_HOURS','24'))*3600
    with lock:
        expired=[jid for jid,j in jobs.items() if j['updated']<cutoff and j['status'] not in ('queued','processing')]
        for jid in expired:
            shutil.rmtree(DATA/jid,ignore_errors=True)
            jobs.pop(jid,None)
        for ip in list(rates):
            while rates[ip] and rates[ip][0] < time.time()-3600:
                rates[ip].popleft()
            if not rates[ip]:
                del rates[ip]


@asynccontextmanager
async def lifespan(app):
    for p in DATA.glob('*/job.json'):
        try:
            job=json.loads(p.read_text())
            if job['status'] in ('queued','processing'):
                job.update(status='error',error='The service restarted. Please upload the image again.')
            jobs[job['id']]=job
        except (ValueError,KeyError):
            continue
    cleanup()
    pool.submit(warmup).add_done_callback(worker_ready)
    import asyncio
    async def sweep():
        while True:
            await asyncio.sleep(600)
            cleanup()
    task=asyncio.create_task(sweep())
    yield
    task.cancel()
    pool.shutdown(wait=False)


app=FastAPI(title='Coda Image Translator',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)


@app.middleware('http')
async def session_and_security(request:Request,call_next):
    sid=request.cookies.get('coda_ocr_session','')
    new_session=len(sid)!=64 or any(c not in '0123456789abcdef' for c in sid)
    if new_session:
        sid=secrets.token_hex(32)
    request.state.owner=hashlib.sha256(sid.encode()).hexdigest()
    if request.method in ('POST','PUT','PATCH','DELETE'):
        origin=request.headers.get('origin')
        expected=f'{request.url.scheme}://{request.headers.get("host","")}'
        if request.headers.get('sec-fetch-site')=='cross-site' or (origin and origin!=expected):
            return JSONResponse({'detail':'Requests must come from this website.'},status_code=403)
        length=request.headers.get('content-length','0')
        if not length.isdigit() or int(length)>MAX_UPLOAD+1024*1024:
            return JSONResponse({'detail':f'Maximum upload size is {MAX_UPLOAD_MB} MB.'},status_code=413)
    response=await call_next(request)
    if new_session:
        response.set_cookie('coda_ocr_session',sid,max_age=86400,httponly=True,secure=request.url.scheme=='https',samesite='strict',path='/ocr')
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='SAMEORIGIN'
    # Swagger UI loads its bundle from jsdelivr and starts it with an inline script.
    docs=request.url.path=='/ocr/docs'
    scripts="'self' 'unsafe-inline' https://cdn.jsdelivr.net" if docs else "'self'"
    styles="'self' 'unsafe-inline' https://cdn.jsdelivr.net" if docs else "'self' 'unsafe-inline'"
    response.headers['Content-Security-Policy']=f"default-src 'self'; img-src 'self' blob: data:; style-src {styles}; script-src {scripts}; font-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
    if '/api/' in request.url.path or request.url.path=='/ocr-endpoint':
        response.headers['Cache-Control']='no-store'
    return response


@app.get('/')
def root():
    return RedirectResponse('/ocr/')


@app.get('/ocr')
@app.get('/ocr/')
def index():
    return FileResponse(ROOT/'static/index.html',headers={'Cache-Control':'no-cache'})


app.mount('/ocr/static',StaticFiles(directory=ROOT/'static'),name='static')


@app.get('/ocr/api/health')
def health():
    return {'status':engine_state['status'],'message':engine_state['message'],
            'ocr':'PP-OCRv6 medium','device':'CPU','translation':'Coda-V2',
            'retention_hours':int(os.getenv('DATA_RETENTION_HOURS','24'))}


def own_job(jid,request):
    sync_jobs()
    with lock:
        job=jobs.get(jid)
        if not job or job['owner']!=request.state.owner:
            raise HTTPException(404,'Image not found or session expired. Upload it again.')
        return job


def submit_job(job, rerender=False):
    future=pool.submit(process,job,rerender)
    def completed(future):
        try:
            future.result()
        except Exception:
            log.exception('Worker failed for %s',job['id'])
            update(job,status='error',stage='error',error='The image worker stopped. Please upload the image again.')
    future.add_done_callback(completed)


LANGUAGE={'en':'English','ar':'Arabic'}
NOT_FITTED={'ar':'تعذّر وضع كل النصوص بالعربية. راجع الترجمات واختصر النصوص التي لا تتسع، ثم طبّق التعديلات.',
            'en':'Some English text could not fit in its space, even after shortening. Crop the image or give the text more room.'}


def find_text(image, source='en'):
    regions=detect(image,source)
    if len(regions)>300:
        raise Unprocessable('This image has too many text regions. Please crop it into smaller images.')
    if not regions:
        raise Unprocessable(f'No readable {LANGUAGE[source]} text was found. Try a clearer or higher-resolution image.')
    return regions


def compose(image, regions, target='ar'):
    """Draw the translation, shortening text that does not fit; refuse to return source-language text."""
    output,mask,verification=render(image,regions,target)
    context='\n'.join(r['text'] for r in regions)
    small=WARNINGS[target]['small']
    for attempt in range(2):
        # Ask for shorter text where it does not fit legibly; never rewrite the user's own edits.
        unfitted=[r for r in regions if r.get('translation') and not r.get('edited')
                  and (not r.get('rendered') or small in r['warnings'])]
        if not unfitted or not shorten(unfitted,context,attempt,target):
            break
        output,mask,verification=render(image,regions,target)
    source='en' if target=='ar' else 'ar'
    if any(LETTERS[source].search(r.get('translation','')) or not r.get('rendered') for r in regions):
        raise Unprocessable(NOT_FITTED[target])
    verification[f'{LANGUAGE[target].lower()}_only_translations']=True
    verification['text_direction']='rtl' if target=='ar' else 'ltr'
    return output,mask,verification


def translate_image(image, direction='en-ar'):
    """Endpoint worker: image in, translated PNG bytes and a short summary out."""
    source,target=direction.split('-')
    regions=find_text(image,source)
    translate(regions,target=target)
    output,_,_=compose(image,regions,target)
    buffer=io.BytesIO()
    output.save(buffer,format='PNG')
    return buffer.getvalue(),{'regions':len(regions),'review':sum(bool(r['warnings']) for r in regions)}


def process(job, rerender=False):
    began=time.monotonic()
    try:
        path=DATA/job['id']
        image=Image.open(path/'original.png')
        if not rerender:
            update(job,status='processing',stage='detect',progress=15)
            regions=find_text(image)
            update(job,regions=regions,stage='translate',progress=55)
            translate(regions,job['preserve_terms'])
        else:
            regions=job['regions']
        update(job,stage='render',progress=85)
        output,mask,verification=compose(image,regions)
        output.save(path/'translated.tmp',format='PNG')
        (path/'translated.tmp').replace(path/'translated.png')
        mask.save(path/'mask.png')
        review=sum(bool(r['warnings']) for r in regions)
        update(job,status='done',stage='done',progress=100,regions=regions,verification=verification,
               seconds=round(time.monotonic()-began,1),review_count=review,version=job.get('version',0)+1,error=None)
    except Exception as e:
        log.exception('Image processing failed for %s',job['id'])
        message=str(e) if isinstance(e,RuntimeError) else 'Processing failed. Please try again with a clearer image.'
        update(job,status='error',stage='error',error=message)


async def load_upload(image:UploadFile):
    raw=await image.read(MAX_UPLOAD+1)
    await image.close()
    if len(raw)>MAX_UPLOAD:
        raise HTTPException(413,f'Maximum upload size is {MAX_UPLOAD_MB} MB.')
    try:
        source=Image.open(io.BytesIO(raw))
        if source.format not in ('JPEG','PNG','WEBP'):
            raise HTTPException(415,'Please upload a PNG, JPG, or WebP image.')
        if source.width*source.height>16_000_000 or max(source.size)>6000 or min(source.size)<32:
            raise HTTPException(400,'Use an image between 32 and 6000 pixels per side, up to 16 megapixels.')
        source.load()
        source=ImageOps.exif_transpose(source)
        source=source.convert('RGBA' if 'A' in source.getbands() or 'transparency' in source.info else 'RGB')
    except HTTPException:
        raise
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(400,'This file is not a valid supported image.')
    return source


def take_slot(ip,now):
    """Apply the queue cap and the translation rate limits shared with the web app."""
    sync_jobs()
    with lock:
        active=sum(j['status'] in ('queued','processing') for j in jobs.values())+api_active[0]
        if active>=4:
            raise HTTPException(429,'The image queue is full. Please try again in a minute.')
        while rates[ip] and rates[ip][0]<now-3600:
            rates[ip].popleft()
        while global_rate and global_rate[0]<now-86400:
            global_rate.popleft()
        if len(rates[ip])>=int(os.getenv('MAX_JOBS_PER_IP_HOUR','12')) or len(global_rate)>=int(os.getenv('MAX_JOBS_PER_DAY','100')):
            raise HTTPException(429,'The translation limit has been reached. Please try again later.')
        rates[ip].append(now)
        global_rate.append(now)


def error(description):
    return {'description':description,'content':{'application/json':{'example':{'detail':'…'}}}}


@app.post('/ocr-endpoint',response_class=Response,tags=['Translation'],summary='Translate the text in an image',
          description='Upload an image and receive the same image as a PNG with its text translated in place. '
                      '`direction` chooses `en-ar` (English to Arabic, the default) or `ar-en` (Arabic to English). '
                      'Synchronous: typically 5–25 seconds, up to 170. '
                      f'Limits: PNG, JPEG or WebP, {MAX_UPLOAD_MB} MB, 32–6000 px per side, 16 megapixels; '
                      '12 images per IP per hour. Full guide: docs/ocr-endpoint.md.',
          responses={200:{'description':'The translated image. Headers `X-Text-Regions`, `X-Review-Count` and '
                                        '`X-Processing-Seconds` summarize the result.',
                          'content':{'image/png':{'schema':{'type':'string','format':'binary'}}}},
                     400:error('Not a valid image, or dimensions out of range.'),
                     413:error(f'File larger than {MAX_UPLOAD_MB} MB.'),
                     415:error('Format other than PNG, JPEG or WebP.'),
                     422:error('No source-language text found, too many text regions, or the translation could not fit.'),
                     429:error('Queue full or rate limit reached.'),
                     502:error('The translation service failed.'),
                     504:error('Processing took longer than 170 seconds.')})
async def ocr_endpoint(request:Request,image:UploadFile=File(...,description='PNG, JPEG or WebP image containing text to translate.'),
                       direction:Literal['en-ar','ar-en']=Form('en-ar',description='`en-ar`: English text to Arabic. `ar-en`: Arabic text to English.')):
    """Synchronous translation: upload an image, get the translated PNG back."""
    if engine_state['status']=='error':
        raise HTTPException(503,engine_state['message'])
    source=await load_upload(image)
    take_slot(request.client.host if request.client else 'unknown',time.time())
    began=time.monotonic()
    with lock:
        api_active[0]+=1
    future=pool.submit(translate_image,source,direction)
    def finished(_):
        with lock:
            api_active[0]-=1
    # Release the queue slot when the worker finishes. On timeout a queued request is cancelled;
    # one already running completes and is discarded.
    future.add_done_callback(finished)
    try:
        png,summary=await asyncio.wait_for(asyncio.wrap_future(future),timeout=API_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(504,'Translation is taking too long. Please try again shortly.')
    except Unprocessable as e:
        raise HTTPException(422,str(e))
    except RuntimeError as e:
        log.warning('Translation endpoint failed: %s',e)
        raise HTTPException(502,str(e))
    except Exception:
        log.exception('Translation endpoint failed')
        raise HTTPException(500,'Processing failed. Please try again with a clearer image.')
    stem=re.sub(r'[^A-Za-z0-9._-]+','_',Path(image.filename or '').stem)[:80] or 'image'
    return Response(png,media_type='image/png',headers={
        'Content-Disposition':f'inline; filename="{stem}-{LANGUAGE[direction[-2:]].lower()}.png"',
        'X-Translation-Direction':direction,'X-Text-Regions':str(summary['regions']),'X-Review-Count':str(summary['review']),
        'X-Processing-Seconds':str(round(time.monotonic()-began,1))})


@app.get('/ocr/openapi.json',include_in_schema=False)
def openapi_schema():
    # Document only the public endpoint, not the web app's session API.
    schema=get_openapi(title='Coda Image Translation API',version='1.0',
                       routes=[r for r in app.routes if getattr(r,'path','')=='/ocr-endpoint'])
    # Swagger UI shows a file picker for `format: binary`, not for OpenAPI 3.1's contentMediaType.
    for body in schema.get('components',{}).get('schemas',{}).values():
        for field in body.get('properties',{}).values():
            if field.pop('contentMediaType',None)=='application/octet-stream':
                field['format']='binary'
    return schema


@app.get('/ocr/docs',include_in_schema=False)
def swagger():
    return get_swagger_ui_html(openapi_url='/ocr/openapi.json',title='Coda Image Translation API',
                               swagger_js_url='https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js',
                               swagger_css_url='https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css',
                               swagger_favicon_url='/ocr/static/favicon.svg')


@app.post('/ocr/api/jobs',status_code=202)
async def create_job(request:Request,image:UploadFile=File(...),preserve_terms:bool=Form(False)):
    if engine_state['status']=='error':
        raise HTTPException(503,engine_state['message'])
    source=await load_upload(image)
    now=time.time()
    with lock:
        take_slot(request.client.host if request.client else 'unknown',now)
        jid=secrets.token_hex(16)
        job={'id':jid,'owner':request.state.owner,'status':'queued','stage':'queued','progress':5,
             'created':now,'updated':now,'name':Path(image.filename or 'image').name[:120],
             'width':source.width,'height':source.height,'preserve_terms':False,'localization_policy':'arabic-rtl-v2','regions':[]}
        folder=DATA/jid
        folder.mkdir(mode=0o700)
        source.save(folder/'original.png')
        jobs[jid]=job
        save_job(job)
        submit_job(job)
    return {'id':jid,'status':'queued'}


@app.get('/ocr/api/jobs/{jid}')
def get_job(jid:str,request:Request):
    job=own_job(jid,request)
    with lock:
        return {k:v for k,v in job.items() if k!='owner'}


class TranslationEdit(BaseModel):
    id:int
    translation:str=Field(min_length=1,max_length=2000)


class EditRequest(BaseModel):
    translations:list[TranslationEdit]=Field(max_length=300,min_length=1)


@app.post('/ocr/api/jobs/{jid}/render',status_code=202)
def edit_job(jid:str,body:EditRequest,request:Request):
    job=own_job(jid,request)
    with lock:
        if job['status'] not in ('done','error') or not job['regions']:
            raise HTTPException(409,'Wait for the current image to finish.')
        if sum(j['status'] in ('queued','processing') for j in jobs.values())>=4:
            raise HTTPException(429,'The queue is full. Try again shortly.')
        edits={e.id:e.translation.strip() for e in body.translations}
        ids={r['id'] for r in job['regions']}
        if len(edits)!=len(body.translations) or not set(edits)<=ids or any(not t for t in edits.values()):
            raise HTTPException(400,'Invalid translation edits.')
        if any(re.search('[A-Za-z]',text) for text in edits.values()):
            raise HTTPException(400,'اكتب جميع الترجمات بالعربية، بما فيها الأسماء والاختصارات.')
        for region in job['regions']:
            if region['id'] in edits and edits[region['id']]!=region['translation']:
                region['translation']=edits[region['id']]
                region['edited']=True
                region.pop('shortened',None)
        update(job,status='processing',stage='render',progress=80)
        submit_job(job,True)
    return {'id':jid,'status':'processing'}


@app.get('/ocr/api/jobs/{jid}/{kind}')
def image_file(jid:str,kind:str,request:Request,download:bool=False):
    job=own_job(jid,request)
    if kind not in ('original','translated','mask'):
        raise HTTPException(404)
    path=DATA/jid/(kind+'.png')
    if not path.exists():
        raise HTTPException(404,'The image is still processing.')
    name=(Path(job['name']).stem+'-arabic.png') if download else None
    return FileResponse(path,media_type='image/png',filename=name,headers={'Cache-Control':'private, no-store'})
