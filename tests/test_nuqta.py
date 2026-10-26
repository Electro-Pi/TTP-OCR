import base64
import io
import json
from types import SimpleNamespace

import httpx
import numpy as np
from PIL import Image
import pytest

import nuqta_ocr as ocr


def rectangle(x1,y1,x2,y2):
    return np.asarray([[x1,y1],[x2,y1],[x2,y2],[x1,y2]],np.float32)


def reply(text='إجمالي المبيعات ١٢٥٬٠٠٠',finish='stop'):
    return {'choices':[{'finish_reason':finish,'message':{'content':text}}]}


def engine(monkeypatch, polygons, handler=None, scale=2, max_regions=64):
    calls=[]
    def respond(request):
        calls.append(request)
        return handler(request) if handler else httpx.Response(200,json=reply())
    real_client=httpx.Client
    monkeypatch.setattr(ocr.httpx,'Client',lambda **kw:real_client(**kw,transport=httpx.MockTransport(respond)))
    obj=ocr.PaddleNuqtaOCR.__new__(ocr.PaddleNuqtaOCR)
    obj.scale=scale;obj.max_regions=max_regions;obj.image_timeout=120
    obj.reader=ocr.NuqtaClient()
    images=[]
    def predict(image):
        images.append(image)
        return [{'dt_polys':polygons}]
    obj.detector=SimpleNamespace(predict=predict)
    return obj,calls,images


def test_nested_detection_removed_without_removing_neighbor():
    outer=rectangle(20,20,80,100);inner=rectangle(25,15,75,40);neighbor=rectangle(90,20,130,40)
    result=ocr.suppress_nested([inner,outer,neighbor])
    assert len(result)==2
    assert np.array_equal(result[0],outer) and np.array_equal(result[1],neighbor)


def test_scaled_coordinates_original_crop_and_unknown_confidence(monkeypatch):
    obj,calls,images=engine(monkeypatch,[rectangle(20,20,60,40)])
    bgr=np.full((50,80,3),[10,20,30],dtype=np.uint8)
    result=obj.predict(bgr)[0]
    assert images[0].shape==(100,160,3)
    assert np.array_equal(result['rec_polys'][0],rectangle(10,10,30,20))
    assert result['rec_scores']==[None]
    assert result['rec_texts']==['إجمالي المبيعات ١٢٥٬٠٠٠']
    body=json.loads(calls[0].content)
    assert body['temperature']==0 and body['chat_template_kwargs']['enable_thinking'] is False
    assert body['model']=='nuqta-arabic'
    url=body['messages'][0]['content'][0]['image_url']['url']
    crop=Image.open(io.BytesIO(base64.b64decode(url.split(',')[1])))
    assert crop.size==(26,16)
    assert crop.getpixel((0,0))==(30,20,10)


def test_duplicate_is_removed_before_any_recognition(monkeypatch):
    obj,calls,_=engine(monkeypatch,[rectangle(20,20,80,100),rectangle(25,15,75,40)])
    result=obj.predict(np.zeros((100,100,3),np.uint8))[0]
    assert len(calls)==len(result['rec_texts'])==1


def test_large_upload_is_not_enlarged(monkeypatch):
    obj,calls,images=engine(monkeypatch,[])
    result=obj.predict(np.zeros((30,2000,3),np.uint8))[0]
    assert images[0].shape==(30,2000,3)
    assert not calls and result['rec_texts']==[]


def test_region_limit_precedes_recognition(monkeypatch):
    obj,calls,_=engine(monkeypatch,[rectangle(0,0,20,20),rectangle(40,0,60,20)],max_regions=1)
    with pytest.raises(ocr.OCRInputLimit,match='more than 1'):
        obj.predict(np.zeros((50,80,3),np.uint8))
    assert not calls


@pytest.mark.parametrize('response',[
    httpx.Response(503,json={'error':'unavailable'}),
    httpx.Response(200,json={}),
    httpx.Response(200,json=reply(finish='length')),
    httpx.Response(200,json=reply(text=None)),
    httpx.Response(200,json=reply(text='<think>unfinished')),
])
def test_failed_or_truncated_read_is_not_silently_accepted(monkeypatch,response):
    obj,_,_=engine(monkeypatch,[rectangle(20,20,60,40)],lambda _:response)
    with pytest.raises(RuntimeError):obj.predict(np.zeros((50,80,3),np.uint8))


def test_inference_timeout_is_actionable(monkeypatch):
    def fail(request):raise httpx.ReadTimeout('timed out',request=request)
    obj,_,_=engine(monkeypatch,[rectangle(20,20,60,40)],fail)
    with pytest.raises(ocr.OCRDeadlineExceeded,match='crop'):
        obj.predict(np.zeros((50,80,3),np.uint8))


def test_image_deadline_stops_before_next_crop(monkeypatch):
    obj,calls,_=engine(monkeypatch,[rectangle(0,0,20,20),rectangle(40,0,60,20)])
    ticks=iter([0,1,121])
    monkeypatch.setattr(ocr,'time',SimpleNamespace(monotonic=lambda:next(ticks)))
    with pytest.raises(ocr.OCRDeadlineExceeded):obj.predict(np.zeros((50,80,3),np.uint8))
    assert len(calls)==1


def test_backend_failure_returns_no_partial_image_read(monkeypatch):
    responses=iter([httpx.Response(200,json=reply()),httpx.Response(500)])
    obj,calls,_=engine(monkeypatch,[rectangle(0,0,20,20),rectangle(40,0,60,20)],lambda _:next(responses))
    with pytest.raises(RuntimeError):obj.predict(np.zeros((50,80,3),np.uint8))
    assert len(calls)==2


def test_reasoning_wrapper_removed_but_arabic_is_not_rewritten(monkeypatch):
    obj,_,_=engine(monkeypatch,[rectangle(20,20,60,40)],lambda _:httpx.Response(200,json=reply('<think></think>رسم بيانتي')))
    assert obj.predict(np.zeros((50,80,3),np.uint8))[0]['rec_texts']==['رسم بيانتي']


def test_ready_checks_model_identity(monkeypatch):
    obj,_,_=engine(monkeypatch,[],lambda r:httpx.Response(200,json={'data':[{'id':'wrong-model'}]}))
    with pytest.raises(RuntimeError,match='alias'):obj.reader.check_ready(timeout=0)


def test_unavailable_backend_cannot_report_ready(monkeypatch):
    obj,_,_=engine(monkeypatch,[],lambda r:httpx.Response(503))
    with pytest.raises(RuntimeError,match='unavailable'):obj.reader.check_ready(timeout=0)


def test_language_routes_use_medium_detector_and_nuqta(monkeypatch):
    import sys,pipeline
    calls=[]
    monkeypatch.setitem(sys.modules,'paddleocr',SimpleNamespace(
        PaddleOCR=lambda **kw:calls.append(('en',kw)) or object(),
        TextDetection=lambda **kw:calls.append(('ar',kw)) or object()))
    monkeypatch.setattr(pipeline,'_engines',{})
    english=pipeline.get_engine('en');arabic=pipeline.get_engine('ar')
    assert isinstance(arabic,ocr.PaddleNuqtaOCR)
    assert pipeline.get_engine('en') is english and pipeline.get_engine('ar') is arabic
    assert calls[0][1]['text_recognition_model_name']=='PP-OCRv6_medium_rec'
    assert calls[1][1]['model_name']=='PP-OCRv6_medium_det'


def test_warmup_consumes_predictions_and_checks_nuqta(monkeypatch):
    import app
    calls=[]
    class Engine:
        def __init__(self,lang):self.lang=lang
        def check_ready(self):calls.append('ready-'+self.lang)
        def predict(self,image):
            calls.append('predict-'+self.lang)
            yield {}
    monkeypatch.setattr(app,'get_engine',Engine)
    assert app.warmup()['status']=='ready'
    assert calls==['predict-en','ready-ar','predict-ar']


def test_arabic_input_limit_maps_to_unprocessable(monkeypatch):
    import app
    def fail(*a):raise ocr.OCRInputLimit('Please crop it')
    monkeypatch.setattr(app,'detect',fail)
    with pytest.raises(app.Unprocessable,match='crop'):app.find_text(Image.new('RGB',(50,50)),'ar')


def test_endpoint_maps_ocr_deadline_to_504(monkeypatch):
    import app
    from concurrent.futures import Future
    from fastapi.testclient import TestClient
    def submit(*a):
        future=Future();future.set_exception(ocr.OCRDeadlineExceeded('Please crop the image'))
        return future
    monkeypatch.setattr(app,'pool',SimpleNamespace(submit=submit))
    monkeypatch.setattr(app,'engine_state',{'status':'ready','message':'ready'})
    image=io.BytesIO();Image.new('RGB',(64,64)).save(image,format='PNG')
    client=TestClient(app.app)
    try:
        response=client.post('/ocr-endpoint',files={'image':('a.png',image.getvalue(),'image/png')},data={'direction':'ar-en'})
    finally:client.close()
    assert response.status_code==504
    assert response.json()['detail']=='Please crop the image'
