"""Install only the OCR service and mount on the two .ai TLS virtual hosts."""
from pathlib import Path
import datetime,shutil,subprocess

root=Path('/home/bassem/screenshot-ocr')
config=Path('/etc/nginx/sites-available/coda-front.conf')
text=config.read_text()
include='    include /etc/nginx/snippets/coda-ocr.conf;\n'
# Match existing server blocks by brace depth rather than replacing global routes.
lines=text.splitlines(keepends=True)
new=[]
block=[]
depth=0
count=0
for line in lines:
    if not block and line.strip().startswith('server {'):
        block=[line];depth=line.count('{')-line.count('}')
        continue
    if block:
        block.append(line);depth+=line.count('{')-line.count('}')
        if depth==0:
            body=''.join(block)
            if ('server_name www.coda.eracoda.ai;' in body or 'server_name coda.eracoda.ai;' in body) and 'listen 443 ssl' in body:
                count+=1
                if include.strip() not in body:
                    marker='    include /etc/nginx/snippets/coda-tts-api.conf;\n'
                    if marker not in body:raise SystemExit('Expected Coda API include not found')
                    body=body.replace(marker,marker+include,1)
            new.append(body);block=[]
    else:new.append(line)
if block or count!=2:raise SystemExit(f'Expected two Coda .ai TLS blocks, found {count}')
updated=''.join(new)
backup=config.with_name(config.name+'.before-ocr-'+datetime.datetime.now().strftime('%Y%m%d%H%M%S'))
shutil.copy2(config,backup)
shutil.copy2(root/'deploy/coda-ocr.conf','/etc/nginx/snippets/coda-ocr.conf')
shutil.copy2(root/'deploy/coda-ocr.service','/etc/systemd/system/coda-ocr.service')
config.write_text(updated)
try:
    subprocess.run(['nginx','-t'],check=True)
except Exception:
    shutil.copy2(backup,config)
    raise
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','coda-ocr.service'],check=True)
subprocess.run(['systemctl','reload','nginx'],check=True)
print('Installed OCR service and /ocr route on coda.eracoda.ai and www.coda.eracoda.ai')
print('Nginx backup:',backup)
