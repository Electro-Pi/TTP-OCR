'use strict';
const $ = id => document.getElementById(id);
const state = {file:null, url:null, job:null, busy:false, polling:null, view:'translated', ready:false};
const show=(id,visible=true)=>$(id).classList.toggle('hidden',!visible);
const message=(text,success=false)=>{ $('message').textContent=text; $('message').classList.toggle('success',success); show('message',!!text); };

async function api(path,options={}){
  const response=await fetch('/ocr/api/'+path,{credentials:'same-origin',...options});
  const data=await response.json().catch(()=>({detail:'تعذّر الاتصال بالخادم. حاول مرة أخرى.'}));
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'تحقّق من الصورة وحاول مرة أخرى.');
  return data;
}

function setBusy(busy){
  state.busy=busy;
  $('translate-button').disabled=busy||!state.file||!state.ready;
  $('file-input').disabled=busy;
  $('clear-file').disabled=busy;
  $('apply-button').disabled=busy;
  $('download-button').disabled=busy;
  $('dropzone').setAttribute('aria-disabled',String(busy));
  $('translate-button').querySelector('span').textContent=busy?'جارٍ تعريب الصورة…':'ترجم الصورة';
}

async function health(){
  try{
    const info=await api('health');
    state.ready=info.status==='ready';
    $('server-status').classList.toggle('error',info.status==='error');
    $('server-status').querySelector('span:last-child').textContent=state.ready?'خدمة الترجمة جاهزة':(info.status==='loading'?'جارٍ تجهيز نماذج قراءة النصوص…':'تعذّر تشغيل الخدمة، حاول لاحقًا.');
    setBusy(state.busy);
    if(info.status==='loading')setTimeout(health,5000);
  }catch{
    $('server-status').classList.add('error');
    $('server-status').querySelector('span:last-child').textContent='جارٍ إعادة الاتصال بالخدمة…';
    state.ready=false;setBusy(state.busy);setTimeout(health,10000);
  }
}

function resetResult(){
  clearTimeout(state.polling);state.job=null;sessionStorage.removeItem('coda-ocr-job');
  ['view-tabs','review-panel','download-button','compare-control','compare-overlay','compare-line','processing-overlay'].forEach(id=>show(id,false));
  show('canvas-dots');$('preview-badge').textContent='معاينة';
}

async function selectFile(file){
  if(state.busy||!file)return;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)){message('اختر صورة بصيغة بي إن جي أو جي بي جي أو ويب بي.');return;}
  if(file.size>50*1024*1024){message('الصورة كبيرة جدًا. الحد الأقصى ٥٠ ميغابايت.');return;}
  const url=URL.createObjectURL(file), img=new Image();
  try{await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=url;});}
  catch{URL.revokeObjectURL(url);message('تعذّر فتح الصورة. جرّب ملفًا آخر.');return;}
  if(img.width*img.height>16000000||Math.max(img.width,img.height)>6000||Math.min(img.width,img.height)<32){URL.revokeObjectURL(url);message('اختر صورة بأبعاد بين ٣٢ و٦٠٠٠ بكسل، بحد أقصى ١٦ ميغابكسل.');return;}
  if(state.url)URL.revokeObjectURL(state.url);
  resetResult();message('');state.file=file;state.url=url;
  $('file-thumb').src=url;$('main-image').src=url;
  $('file-name').textContent=file.name;
  $('file-meta').textContent=`${img.width} × ${img.height} بكسل · ${(file.size/1024/1024).toFixed(1)} ميغابايت`;
  $('canvas-caption').textContent=`${img.width} × ${img.height} · جاهزة للترجمة`;
  show('selected-file');show('empty-state',false);show('image-stage');
  setBusy(false);
}

$('file-input').addEventListener('change',e=>selectFile(e.target.files[0]));
$('dropzone').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&!state.busy){e.preventDefault();$('file-input').click();}});
for(const event of ['dragenter','dragover'])$('dropzone').addEventListener(event,e=>{e.preventDefault();if(!state.busy)$('dropzone').classList.add('dragover');});
for(const event of ['dragleave','drop'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.remove('dragover');});
$('dropzone').addEventListener('drop',e=>selectFile(e.dataTransfer.files[0]));
window.addEventListener('paste',e=>{if(e.target.tagName==='TEXTAREA'||e.target.tagName==='INPUT')return;const item=[...(e.clipboardData?.items||[])].find(x=>x.type.startsWith('image/'));if(item)selectFile(item.getAsFile());});
$('clear-file').addEventListener('click',()=>{if(state.busy)return;resetResult();state.file=null;if(state.url)URL.revokeObjectURL(state.url);state.url=null;$('file-input').value='';show('selected-file',false);show('image-stage',false);show('empty-state');$('canvas-caption').textContent='صورتك تعبر إلى جمهور جديد.';message('');setBusy(false);});
$('how-button').addEventListener('click',()=>$('how-it-works').scrollIntoView({behavior:'smooth',block:'center'}));

const stageText={queued:['صورتك في قائمة الانتظار','ستبدأ المعالجة فور توفّر مكان.'],detect:['جارٍ قراءة الصورة','نحدّد النصوص وأماكنها في الصورة.'],translate:['نختار الكلمات المناسبة','نعرّب جميع النصوص والأسماء والاختصارات.'],render:['جارٍ تنسيق الصورة','نستعيد الخلفية ونضع النصوص بمحاذاة إلى اليمين.']};
function progress(job){
  show('processing-overlay');
  const [title,description]=stageText[job.stage]||stageText.queued;
  $('progress-title').textContent=title;$('progress-description').textContent=description;
  $('progress-bar').style.width=(job.progress||5)+'%';
  const stages=['detect','translate','render'], index=stages.indexOf(job.stage);
  document.querySelectorAll('[data-step]').forEach(el=>{const n=stages.indexOf(el.dataset.step);el.classList.toggle('current',n===index);el.classList.toggle('complete',n<index);});
}

$('translate-button').addEventListener('click',async()=>{
  if(!state.file||state.busy)return;
  message('');resetResult();setBusy(true);progress({stage:'queued',progress:3});
  const form=new FormData();form.append('image',state.file);form.append('preserve_terms','false');
  try{const job=await api('jobs',{method:'POST',body:form});state.job=job;sessionStorage.setItem('coda-ocr-job',job.id);poll(job.id);}
  catch(error){show('processing-overlay',false);setBusy(false);message(error.message);}
});

async function poll(id,failures=0){
  try{
    const job=await api('jobs/'+id);state.job=job;
    if(job.status==='done'){finish(job);return;}
    if(job.status==='error'){show('download-button',false);show('processing-overlay',false);setBusy(false);message(job.error||'حدث خطأ. حاول مرة أخرى.');if(job.regions.some(r=>r.translation))buildReview(job);return;}
    progress(job);state.polling=setTimeout(()=>poll(id),1500);
  }catch(error){
    if(failures<5){state.polling=setTimeout(()=>poll(id,failures+1),3000);return;}
    show('processing-overlay',false);setBusy(false);message(error.message+' حدّث الصفحة للعودة إلى آخر صورة.');
  }
}

function imageURL(kind){return `/ocr/api/jobs/${state.job.id}/${kind}?v=${state.job.version||0}`;}
function switchView(view){
  state.view=view;
  document.querySelectorAll('[data-view]').forEach(button=>{const active=button.dataset.view===view;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active));});
  $('main-image').src=imageURL(view==='original'?'original':'translated');
  $('main-image').alt=view==='original'?'الصورة الأصلية':'الصورة المترجمة إلى العربية';
  for(const id of ['compare-overlay','compare-line','compare-control'])show(id,view==='compare');
  if(view==='compare'){$('compare-image').src=imageURL('original');updateCompare();}
}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>switchView(button.dataset.view)));
function updateCompare(){const value=$('compare-range').value;$('compare-overlay').style.clipPath=`inset(0 0 0 ${value}%)`;$('compare-line').style.left=value+'%';}
$('compare-range').addEventListener('input',updateCompare);

function finish(job){
  state.job=job;show('processing-overlay',false);setBusy(false);
  show('empty-state',false);show('image-stage');show('view-tabs');show('download-button');show('canvas-dots',false);
  $('preview-badge').textContent='مكتملة';
  $('canvas-caption').textContent=`${job.width} × ${job.height} · ${job.regions.length} منطقة نصية · ${job.seconds} ثانية`;
  switchView('translated');buildReview(job);
  if(job.review_count)message(`تحتاج ${job.review_count} منطقة نصية إلى مراجعة. تحقّق من الملاحظات أدناه قبل التنزيل.`);
  else message('صورتك العربية جاهزة. راجع النصوص أو نزّل الصورة.',true);
}

function buildReview(job){
  const container=$('review-rows');container.replaceChildren();
  for(const region of job.regions){
    const row=document.createElement('div');row.className='review-row';
    const source=document.createElement('div');source.className='source';source.textContent=region.text;
    const input=document.createElement('textarea');input.value=region.translation;input.dataset.region=region.id;input.lang='ar';input.dir='rtl';input.rows=Math.max(1,region.translation.split('\n').length);input.maxLength=2000;input.setAttribute('aria-label','الترجمة العربية للنص: '+region.text);
    const status=document.createElement('div');status.className='review-status'+(region.warnings.length?' warning':'');
    status.textContent=region.warnings.length?region.warnings.map(localizeWarning).join(' · '):'✓ جاهز';
    const confidence=document.createElement('small');confidence.textContent=`دقة قراءة النص ${Math.round(region.confidence*100)}%`;status.append(confidence);
    row.append(source,input,status);container.append(row);
  }
  show('review-panel');
}

$('apply-button').addEventListener('click',async()=>{
  if(state.busy||!state.job)return;
  const translations=[...document.querySelectorAll('[data-region]')].map(input=>({id:Number(input.dataset.region),translation:input.value.trim()}));
  if(translations.some(t=>!t.translation)){message('اكتب ترجمة عربية لكل منطقة نصية.');return;}
  if(translations.some(t=>/[A-Za-z]/.test(t.translation))){message('اكتب جميع الأسماء والاختصارات بالعربية. لا يمكن إبقاء أحرف إنجليزية.');return;}
  message('');setBusy(true);progress({stage:'render',progress:80});
  try{await api(`jobs/${state.job.id}/render`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({translations})});poll(state.job.id);$('canvas').scrollIntoView({behavior:'smooth',block:'center'});}
  catch(error){show('processing-overlay',false);setBusy(false);message(error.message);}
});

$('download-button').addEventListener('click',()=>{if(!state.job||state.busy)return;const a=document.createElement('a');a.href=imageURL('translated')+'&download=true';a.download='image-arabic.png';document.body.append(a);a.click();a.remove();});

async function restore(){
  const id=sessionStorage.getItem('coda-ocr-job');
  if(!id||!/^[a-f0-9]{32}$/.test(id))return;
  try{
    const job=await api('jobs/'+id);
    if(state.file)return;
    if(job.localization_policy!=='arabic-rtl-v2'){sessionStorage.removeItem('coda-ocr-job');message('ارفع الصورة مجددًا لتطبيق التعريب الكامل والمحاذاة من اليمين إلى اليسار.');return;}
    state.job=job;
    $('main-image').src=imageURL('original');show('empty-state',false);show('image-stage');
    if(job.status==='done')finish(job);
    else if(job.status==='queued'||job.status==='processing'){setBusy(true);poll(id);}
    else message(job.error||'تعذّرت معالجة الصورة السابقة. ارفعها للمحاولة مجددًا.');
  }catch{sessionStorage.removeItem('coda-ocr-job');}
}
function localizeWarning(text){
  return ({'Check the English reading':'راجع قراءة النص الأصلي',
    'Textured background: check the restored area':'خلفية معقدة: راجع المنطقة المعدّلة',
    'Arabic does not fit: shorten the translation and apply again':'الترجمة أطول من المساحة: اختصرها ثم طبّق التعديلات',
    'Small Arabic text: consider a shorter translation':'الخط العربي صغير: جرّب ترجمة أقصر',
    'Shortened automatically to fit: check the meaning':'اختُصرت الترجمة تلقائيًا لتتسع: راجع المعنى',
    'Condensed Arabic text: consider a shorter translation':'الخط العربي مضغوط أفقيًا: جرّب ترجمة أقصر'})[text]||text;
}
health();restore();
