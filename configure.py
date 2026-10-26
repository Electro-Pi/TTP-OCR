"""Create private runtime configuration from the provided remote template."""
import os
from getpass import getpass
from pathlib import Path
from dotenv import dotenv_values

template = Path('.env.remote.example')
if not template.exists():
    template = Path('.env.example')
values = dotenv_values(template)
if not values.get('LLM_BASE_URL') or '.example' in values['LLM_BASE_URL']:
    raise SystemExit(f'Set LLM_BASE_URL and LLM_MODEL in {template} before running configure.py.')
key = getpass('Coda translation API key (hidden): ')
if not key.startswith('coda_sk_'):
    raise SystemExit('Expected a Coda API key')
config = {
    'LLM_BASE_URL': values['LLM_BASE_URL'],
    'LLM_MODEL': values['LLM_MODEL'],
    'LLM_API_KEY': key,
    'OCR_DETECTION_MODEL': 'PP-OCRv6_medium_det',
    'OCR_RECOGNITION_MODEL': 'PP-OCRv6_medium_rec',
    'OCR_CPU_THREADS': '4',
    'NUQTA_BASE_URL': 'http://127.0.0.1:8116',
    'ARABIC_DETECTION_SCALE': '2',
    'NUQTA_MAX_REGIONS': '64',
    'NUQTA_IMAGE_TIMEOUT': '120',
    'DATA_RETENTION_HOURS': '24',
    'MAX_JOBS_PER_IP_HOUR': '12',
    'MAX_JOBS_PER_DAY': '100',
}
fd = os.open('.env', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    for k, v in config.items():
        f.write(f'{k}="{v}"\n')
os.chmod('.env', 0o600)
print('Private runtime configuration saved; credential not displayed.')
