"""Create private runtime configuration from the provided remote template."""
import os
from getpass import getpass
from pathlib import Path
from dotenv import dotenv_values

values = dotenv_values('.env.remote.example')
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
