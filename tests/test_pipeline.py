import io
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pipeline import render

def fixture_image():
    im=Image.new('RGB',(640,240),'#f4f5fb')
    d=ImageDraw.Draw(im)
    d.rectangle((25,25,615,215),outline='#344c84',width=3)
    d.line((25,150,615,150),fill='#c9d2e6',width=2)
    d.text((80,65),'Secure Access Layer',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',28),fill='#253359')
    box=list(d.textbbox((80,65),'Secure Access Layer',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',28)))
    x,y,x2,y2=box
    regions=[{'id':0,'text':'Secure Access Layer','translation':'طبقة الوصول الآمن','confidence':.99,'box':box,
              'polygons':[[[x,y],[x2,y],[x2,y2],[x,y2]]],'line_height':y2-y,'angle':0,'warnings':[]}]
    return im,regions

def test_pixels_outside_text_are_identical():
    im,regions=fixture_image()
    out,mask,verification=render(im,regions)
    a,b,m=np.asarray(im),np.asarray(out),np.asarray(mask)
    assert out.size==im.size
    assert np.any(a!=b)
    assert np.array_equal(a[m==0],b[m==0])
    assert np.array_equal(a[150:153],b[150:153])
    assert verification['outside_regions_unchanged']
    assert regions[0]['rendered']

def test_alpha_is_preserved():
    im,regions=fixture_image()
    im=im.convert('RGBA')
    im.putalpha(Image.new('L',im.size,160))
    out,_,_=render(im,regions)
    assert np.array_equal(np.asarray(out)[:,:,3],np.asarray(im)[:,:,3])

def test_unchanged_brand_is_not_erased():
    im,regions=fixture_image()
    regions[0]['translation']=regions[0]['text']
    out,mask,_=render(im,regions)
    assert np.array_equal(np.asarray(out),np.asarray(im))
    assert not np.any(np.asarray(mask))

def test_overflow_keeps_original_and_flags_review():
    im,regions=fixture_image()
    regions[0]['translation']='كلمةطويلةجدا'*100
    out,_,_=render(im,regions)
    assert not regions[0]['rendered']
    assert any('does not fit' in w for w in regions[0]['warnings'])
    assert np.array_equal(np.asarray(out),np.asarray(im))

def test_detected_regions_are_json_serializable(monkeypatch):
    import json
    import pipeline
    im,regions=fixture_image()
    class FakeEngine:
        def predict(self,image):
            return [{'rec_texts':['Secure Access Layer'],'rec_scores':[np.float32(.99)],'rec_polys':[np.asarray(regions[0]['polygons'][0])]}]
    monkeypatch.setattr(pipeline,'get_engine',lambda lang='en':FakeEngine())
    result=pipeline.detect(im)
    assert len(result)==1
    assert json.loads(json.dumps(result))[0]['text']=='Secure Access Layer'

def test_rendered_text_is_rtl_and_right_aligned():
    im,regions=fixture_image()
    regions[0]['translation']='أمان'
    out,_,_=render(im,regions)
    assert regions[0]['direction']=='rtl'
    assert regions[0]['alignment']=='right'
    # The short Arabic word should sit at the right end of the original text box.
    x1,y1,x2,y2=regions[0]['box']
    crop=np.asarray(out)[y1-3:y2+3,x1:x2+4]
    ink=(crop[:,:,0]<100)&(crop[:,:,1]<100)&(crop[:,:,2]<140)
    xs=np.where(ink)[1]
    assert xs.size and xs.mean() > (x2-x1)*.7


def test_translation_retries_latin_and_ignores_legacy_preserve_flag(monkeypatch):
    import json
    import pipeline
    responses=[{'translations':[{'id':0,'text':'Redis ذاكرة'}]},
               {'translations':[{'id':0,'text':'ذاكرة ريديس المؤقتة'}]}]
    calls=[]
    class FakeResponse:
        status_code=200
        def __init__(self,payload):self.payload=payload
        def json(self):return {'choices':[{'message':{'content':json.dumps(self.payload)}}]}
    class FakeClient:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**kw):
            calls.append(kw['json'])
            return FakeResponse(responses.pop(0))
    monkeypatch.setenv('LLM_API_KEY','test-key')
    monkeypatch.setenv('LLM_BASE_URL','https://example.invalid/v1')
    monkeypatch.setattr(pipeline.httpx,'Client',FakeClient)
    regions=[{'id':0,'text':'Redis Cache'}]
    pipeline.translate(regions,preserve_terms=True)
    assert len(calls)==2
    assert regions[0]['translation']=='ذاكرة ريديس المؤقتة'


def label_image(neighbour_gap=None):
    """A centred one-word label in open space, optionally with English text close to its left."""
    im=Image.new('RGB',(400,80),'#ffffff')
    d=ImageDraw.Draw(im)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',12)
    d.text((188,30),'Mail',font=font,fill='#1a5fb4')
    x,y,x2,y2=d.textbbox((188,30),'Mail',font=font)
    regions=[{'id':0,'text':'Mail','translation':'البريد الإلكتروني','confidence':.99,'box':[x,y,x2,y2],
              'polygons':[[[x,y],[x2,y],[x2,y2],[x,y2]]],'line_height':y2-y,'angle':0,'warnings':[]}]
    if neighbour_gap is not None:
        nx2=x-neighbour_gap
        d.text((nx2-50,30),'Note',font=font,fill='#1a5fb4')
        a,b,c,e=d.textbbox((nx2-50,30),'Note',font=font)
        # Same text as the source, so it is left in place and its pixels must not change.
        regions.append({'id':1,'text':'Note','translation':'Note','confidence':.99,'box':[a,b,c,e],
                        'polygons':[[[a,b],[c,b],[c,e],[a,e]]],'line_height':e-b,'angle':0,'warnings':[]})
    return im,regions

def test_tight_label_extends_into_free_background():
    im,regions=label_image()
    out,mask,verification=render(im,regions)
    r=regions[0]
    assert r['rendered'] and r['alignment']=='center'
    assert not any('Small' in w for w in r['warnings'])
    assert verification['outside_regions_unchanged']
    # The Arabic stays centred on the original label.
    x1,_,x2,_=r['box']
    xs=np.where(np.asarray(mask)>0)[1]
    assert xs.min()<x1 and xs.max()>x2
    assert abs((xs.min()+xs.max())/2-(x1+x2)/2)<4

def test_extension_stops_before_neighbouring_text():
    im,regions=label_image(neighbour_gap=12)
    out,mask,_=render(im,regions)
    a,b,c,e=regions[1]['box']
    assert np.array_equal(np.asarray(out)[b-2:e+2,a-2:c+2],np.asarray(im)[b-2:e+2,a-2:c+2])
    assert regions[0]['rendered']

def fake_llm(monkeypatch,responses):
    import json
    import pipeline
    calls=[]
    class FakeResponse:
        status_code=200
        def __init__(self,payload):self.payload=payload
        def json(self):return {'choices':[{'message':{'content':json.dumps(self.payload)}}]}
    class FakeClient:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**kw):
            calls.append(kw['json'])
            return FakeResponse(responses.pop(0))
    monkeypatch.setenv('LLM_API_KEY','test-key')
    monkeypatch.setenv('LLM_BASE_URL','https://example.invalid/v1')
    monkeypatch.setattr(pipeline.httpx,'Client',FakeClient)
    return calls

def test_translation_sends_box_size_and_budget(monkeypatch):
    import json
    import pipeline
    calls=fake_llm(monkeypatch,[{'translations':[{'id':0,'text':'بريد'}]}])
    regions=[{'id':0,'text':'Mail','box':[161,1110,185,1125],'polygons':[[]],'line_height':15}]
    pipeline.translate(regions)
    entry=json.loads(calls[0]['messages'][1]['content'])['entries'][0]
    assert (entry['width_px'],entry['height_px'],entry['lines'])==(24,15,1)
    assert 2<=entry['max_chars']<=6
    assert regions[0]['translation']=='بريد'

def test_shorten_keeps_only_shorter_replies_and_flags_review(monkeypatch):
    import pipeline
    fake_llm(monkeypatch,[{'translations':[{'id':0,'text':'بريد'},{'id':1,'text':'ملاحظة طويلة جدا'}]}])
    im,regions=label_image()
    regions.append({**regions[0],'id':1,'text':'Note','translation':'ملاحظة'})
    changed=pipeline.shorten(regions,'Mail Note')
    assert changed==[regions[0]]
    assert regions[0]['translation']=='بريد'
    assert regions[0]['original_translation']=='البريد الإلكتروني'
    assert regions[1]['translation']=='ملاحظة' and not regions[1].get('shortened')
    render(im,regions[:1])
    assert pipeline.SHORTENED in regions[0]['warnings']

def test_shorten_failure_leaves_translation(monkeypatch):
    import pipeline
    same={'translations':[{'id':0,'text':'البريد الإلكتروني'}]}
    fake_llm(monkeypatch,[same,same,same])
    _,regions=label_image()
    assert pipeline.shorten(regions,'Mail')==[]
    assert regions[0]['translation']=='البريد الإلكتروني' and not regions[0].get('shortened')


def big_title(jpeg_quality=None):
    """Large heavy lettering whose stems are longer than the diagram-line filter."""
    im=Image.new('RGB',(620,180),(251,242,226))
    d=ImageDraw.Draw(im)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',90)
    d.text((30,30),'WATERFALL',font=font,fill=(5,1,3))
    if jpeg_quality:
        buffer=io.BytesIO(); im.save(buffer,'JPEG',quality=jpeg_quality); im=Image.open(buffer).convert('RGB')
    x,y,x2,y2=d.textbbox((30,30),'WATERFALL',font=font)
    regions=[{'id':0,'text':'WATERFALL','translation':'الشلال','confidence':.99,'box':[x,y,x2,y2],
              'polygons':[[[x,y],[x2,y],[x2,y2],[x,y2]]],'line_height':y2-y,'angle':0,'warnings':[]}]
    return im,regions

def test_tall_letter_stems_are_erased_not_protected_as_lines():
    im,regions=big_title()
    _,mask,_=render(im,regions)
    x1,y1,x2,y2=regions[0]['box']
    dark=np.asarray(im)[y1:y2,x1:x2].max(axis=2)<80
    # Every pixel of the English lettering must be inside the edited area.
    assert np.all(np.asarray(mask)[y1:y2,x1:x2][dark]>0)

def test_no_letter_ghost_on_jpeg_background():
    im,regions=big_title(jpeg_quality=60)
    regions[0]['translation']='أ'
    out,_,_=render(im,regions)
    x1,y1,x2,y2=regions[0]['box']
    # The short Arabic sits at the right; the left half must be plain background again.
    left=np.asarray(out)[y1:y2,x1:(x1+x2)//2].astype(float)
    dist=np.linalg.norm(left-np.array([251,242,226]),axis=2)
    assert np.count_nonzero(dist>25)<0.002*dist.size

def test_stacked_label_lines_do_not_cut_each_other():
    """Two overlapping OCR lines of one label: the later erase must not cut the earlier Arabic."""
    im=Image.new('RGB',(300,120),(0,120,200))
    d=ImageDraw.Draw(im)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
    regions=[]
    for i,(word,y) in enumerate((('Communication',40),('Established',54))):
        d.text((150,y),word,font=font,fill='white',anchor='mt')
        x,y1,x2,y2=d.textbbox((150,y),word,font=font,anchor='mt')
        regions.append({'id':i,'text':word,'translation':['اتصال','منشأ'][i],'confidence':.99,'box':[x,y1-2,x2,y2+2],
                        'polygons':[[[x,y1-2],[x2,y1-2],[x2,y2+2],[x,y2+2]]],'line_height':y2-y1+4,'angle':0,'warnings':[]})
    import copy
    alone,_,_=render(im,copy.deepcopy(regions[:1]))
    out,_,_=render(im,regions)
    assert all(r['rendered'] for r in regions)
    assert not any('Textured' in w for r in regions for w in r['warnings'])
    # The first word's Arabic survives processing of the second, overlapping line.
    x1,y1,x2,y2=regions[0]['box']
    first=np.asarray(alone)[y1:y2,x1:x2].min(axis=2)>170
    kept=np.asarray(out)[y1:y2,x1:x2].min(axis=2)>170
    assert first.sum()>15 and (first&kept).sum()>=0.95*first.sum()


def uml_class():
    """A class box: header, divider, then two attribute lines."""
    im=Image.new('RGB',(260,140),'white')
    d=ImageDraw.Draw(im)
    d.rectangle((20,10,240,130),fill=(46,162,247))
    d.line((20,46,240,46),fill=(20,110,200),width=2)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
    boxes=[]
    for text,y in (('Customer',22),('+name',52),('+address',68)):
        d.text((30,y),text,font=font,fill='white')
        boxes.append((text,d.textbbox((30,y),text,font=font)))
    return im,boxes

def test_lines_are_not_grouped_across_a_divider(monkeypatch):
    import pipeline
    im,boxes=uml_class()
    class FakeEngine:
        def predict(self,image):
            polys=[np.array([[x,y-1],[x2,y-1],[x2,y2+1],[x,y2+1]],float) for _,(x,y,x2,y2) in boxes]
            return [{'rec_texts':[t for t,_ in boxes],'rec_scores':[.99]*3,'rec_polys':polys}]
    monkeypatch.setattr(pipeline,'get_engine',lambda lang='en':FakeEngine())
    regions=pipeline.detect(im)
    assert [r['text'] for r in regions]==['Customer','+name +address']
    assert regions[1]['lines']==['+name','+address']

def test_list_lines_stay_in_their_slots_below_the_divider():
    im,boxes=uml_class()
    (_,a),(_,b)=boxes[1],boxes[2]
    polys=[[[a[0],a[1]-1],[a[2],a[1]-1],[a[2],a[3]+1],[a[0],a[3]+1]],[[b[0],b[1]-1],[b[2],b[1]-1],[b[2],b[3]+1],[b[0],b[3]+1]]]
    regions=[{'id':0,'text':'+name +address','lines':['+name','+address'],'translation':'+الاسم\n+العنوان','confidence':.99,
              'box':[min(a[0],b[0]),a[1]-1,max(a[2],b[2]),b[3]+1],'polygons':polys,'line_height':a[3]-a[1]+2,'angle':0,'warnings':[]}]
    out,mask,_=render(im,regions)
    assert regions[0]['rendered']
    o=np.asarray(out)
    # The divider is intact and nothing was drawn on or above it.
    assert np.array_equal(o[:49],np.asarray(im)[:49])
    # Each slot holds its own line of lettering.
    lettering=np.linalg.norm(o.astype(float)-[46,162,247],axis=2)>60
    middle=(a[3]+b[1])//2
    assert lettering[a[1]-1:middle,30:240].sum()>20 and lettering[middle:b[3]+3,30:240].sum()>20

def test_translation_survives_unescaped_quotes_from_source(monkeypatch):
    import json
    import pipeline
    raw='{"translations":[{"id":0,"text":"(يجب أن يظهر "في الوقت الفعلي")"}]}'
    class FakeResponse:
        status_code=200
        def json(self):return {'choices':[{'message':{'content':raw}}]}
    class FakeClient:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**kw):return FakeResponse()
    monkeypatch.setenv('LLM_API_KEY','test-key')
    monkeypatch.setenv('LLM_BASE_URL','https://example.invalid/v1')
    monkeypatch.setattr(pipeline.httpx,'Client',FakeClient)
    regions=[{'id':0,'text':'(should appear "real-time")'}]
    pipeline.translate(regions)
    assert regions[0]['translation']=='(يجب أن يظهر "في الوقت الفعلي")'

def test_wrapped_sentences_are_not_lists():
    from pipeline import _wrapped
    assert _wrapped(['Step 1: Send Account, Product,','and Price details to Avalara'])
    assert _wrapped(['(should appear','"real-time")'])
    assert not _wrapped(['+code','+address'])
    assert not _wrapped(['Payment Amount','Payment Date','Invoice #'])


def arabic_fixture():
    """An Arabic heading in a framed box, drawn right to left, as Arabic-to-English input."""
    im=Image.new('RGB',(640,240),'#f4f5fb')
    d=ImageDraw.Draw(im)
    d.rectangle((25,25,615,215),outline='#344c84',width=3)
    font=ImageFont.truetype('static/fonts/NotoSansArabic.ttf',30)
    text='طبقة الوصول الآمنة'
    box=list(d.textbbox((300,60),text,font=font,direction='rtl',language='ar'))
    d.text((300,60),text,font=font,fill='#253359',direction='rtl',language='ar')
    x,y,x2,y2=box
    regions=[{'id':0,'text':text,'translation':'Secure Access Layer','confidence':.99,'box':box,
              'polygons':[[[x,y],[x2,y],[x2,y2],[x,y2]]],'line_height':y2-y,'angle':0,'warnings':[]}]
    return im,regions

def test_arabic_reading_order_keeps_numbers_and_latin_runs():
    from pipeline import logical_order
    # The Arabic recognizer returns lines in visual order, left to right.
    assert logical_order('هيلع ةعرقلا') == 'القرعة عليه'
    assert logical_order('120 تافلملا') == 'الملفات 120'
    assert logical_order('٣٠ اضر') == 'رضا ٣٠'
    assert logical_order('KPI ةيسيئرلا تارشؤملا') == 'المؤشرات الرئيسية KPI'

def test_arabic_detection_reads_arabic_only(monkeypatch):
    import pipeline
    im,regions=arabic_fixture()
    poly=np.asarray(regions[0]['polygons'][0])
    used=[]
    class FakeEngine:
        def predict(self,image):
            return [{'rec_texts':['ةنمآلا لوصولا ةقبط','Logo'],'rec_scores':[np.float32(.8),np.float32(.99)],
                     'rec_polys':[poly,poly+[0,100]]}]
    class FakeDigits:
        def predict(self,crops,batch_size=1):
            return [{'rec_text':'Logo'} for _ in crops]
    monkeypatch.setattr(pipeline,'get_engine',lambda lang='en':used.append(lang) or FakeEngine())
    monkeypatch.setattr(pipeline,'get_digit_reader',lambda:FakeDigits())
    result=pipeline.detect(im,'ar')
    assert used==['ar']
    assert [r['text'] for r in result]==['طبقة الوصول الآمنة']
    assert result[0]['warnings']==['Check the Arabic reading']

def test_english_translation_rejects_arabic_and_uses_western_digits(monkeypatch):
    import json
    import pipeline
    calls=fake_llm(monkeypatch,[{'translations':[{'id':0,'text':'Riyadh الرياض'}]},
                                {'translations':[{'id':0,'text':'٣٠ Users، Riyadh'}]}])
    regions=[{'id':0,'text':'٣٠ مستخدم، الرياض','box':[10,10,200,30],'polygons':[[]],'line_height':20}]
    pipeline.translate(regions,target='en')
    assert len(calls)==2
    assert 'Arabic to English' in calls[0]['messages'][0]['content']
    assert 'Arabic letters remain' in calls[1]['messages'][-1]['content']
    assert regions[0]['translation']=='30 Users, Riyadh'
    entry=json.loads(calls[0]['messages'][1]['content'])['entries'][0]
    # The budget is measured in English characters, which are wider than connected Arabic letters.
    assert entry['max_chars']==pipeline.capacity(regions[0],'en')<pipeline.capacity(regions[0],'ar')

def test_rendered_english_is_ltr_and_left_aligned():
    im,regions=arabic_fixture()
    regions[0]['translation']='Security'
    out,mask,verification=render(im,regions,'en')
    assert regions[0]['rendered'] and regions[0]['direction']=='ltr' and regions[0]['alignment']=='left'
    a,b,m=np.asarray(im),np.asarray(out),np.asarray(mask)
    assert np.array_equal(a[m==0],b[m==0]) and verification['outside_regions_unchanged']
    # The short English word should start at the left end of the original Arabic box.
    x1,y1,x2,y2=regions[0]['box']
    crop=b[y1-3:y2+3,x1:x2+4]
    ink=(crop[:,:,0]<100)&(crop[:,:,1]<100)&(crop[:,:,2]<140)
    xs=np.where(ink)[1]
    assert xs.size and xs.mean() < (x2-x1)*.4
    # No Arabic lettering is left inside the box.
    assert not ((crop[:,int((x2-x1)*.7):,0]<100)&(crop[:,int((x2-x1)*.7):,2]<140)).any()

def test_arabic_indic_numbers_come_from_the_digit_reader(monkeypatch):
    import pipeline
    bgr=np.zeros((100,300,3),np.uint8)
    polys=[np.asarray([[10,10],[200,10],[200,40],[10,40]])]*3
    class FakeDigits:
        def predict(self,crops,batch_size=1):
            return [{'rec_text':t} for t in ['٣٤٨ طلبا','طلب رقم']][:len(crops)]
    monkeypatch.setattr(pipeline,'get_digit_reader',lambda:FakeDigits())
    # Lines with only Arabic words are not re-read; a reading without Arabic-Indic digits is not used.
    texts=pipeline._arabic_lines(bgr,['Nع٣ طلبا','طلب رقم I٠f٢','أحدث الطلبات'],polys)
    assert texts==['٣٤٨ طلبا','طلب رقم I٠f٢','أحدث الطلبات']
