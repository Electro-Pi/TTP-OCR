"""Provision or run the pinned CPU Nuqta server; never installs/starts systemd units."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import tarfile
import tempfile
import urllib.request

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
ASSETS = json.loads((ROOT / 'nuqta-assets.json').read_text())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, target, checksum):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and digest(target) == checksum:
        print('Verified', target.name, flush=True)
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as dest:
            temporary = Path(dest.name)
            print('Downloading', target.name, flush=True)
            with urllib.request.urlopen(url, timeout=120) as response:
                while chunk := response.read(4 * 1024 * 1024):
                    dest.write(chunk)
        if digest(temporary) != checksum:
            raise RuntimeError(f'Checksum mismatch for {target.name}')
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'verify', 'serve'])
    args = parser.parse_args()
    model_dir = Path(os.getenv('NUQTA_MODEL_DIR', str(ROOT / 'models/nuqta'))).resolve()
    runtime = ASSETS['runtime']
    binary = Path(os.getenv('NUQTA_LLAMA_SERVER', str(model_dir / 'runtime' / runtime['binary']))).resolve()
    if args.command == 'setup':
        for name, meta in ASSETS['files'].items():
            download(f'https://huggingface.co/{ASSETS["repo"]}/resolve/{ASSETS["revision"]}/{name}',
                     model_dir / name, meta['sha256'])
        if not os.getenv('NUQTA_LLAMA_SERVER'):
            if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
                raise SystemExit('Set NUQTA_LLAMA_SERVER to a compatible llama.cpp binary on this platform.')
            archive = model_dir / 'runtime.tar.gz'
            download(runtime['url'], archive, runtime['sha256'])
            with tarfile.open(archive) as bundle:
                bundle.extractall(model_dir / 'runtime', filter='data')
    for name, meta in ASSETS['files'].items():
        path = model_dir / name
        if not path.is_file() or digest(path) != meta['sha256']:
            raise SystemExit(f'Missing or corrupt {name}; run scripts/nuqta.py setup.')
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise SystemExit('Missing llama-server. Run setup or set NUQTA_LLAMA_SERVER.')
    if args.command != 'serve':
        print('Nuqta assets verified. No service was started.')
        return
    threads = os.getenv('OCR_CPU_THREADS', '4')
    port = os.getenv('NUQTA_PORT', '8116')
    command = [str(binary), '-m', str(model_dir / 'nuqta-ocr-0.8b-Q8_0.gguf'),
               '--mmproj', str(model_dir / 'nuqta-ocr-0.8b-mmproj-f16.gguf'),
               '-ngl', '0', '--no-mmproj-offload', '--host', '127.0.0.1', '--port', port,
               '--parallel', '1', '-c', '8192', '--threads', threads, '--threads-batch', threads,
               '--image-min-tokens', '64', '--image-max-tokens', '4096', '--cache-ram', '0',
               '--alias', 'nuqta-arabic', '--jinja', '--reasoning', 'off', '--temp', '0']
    os.execv(str(binary), command)


if __name__ == '__main__':
    main()
