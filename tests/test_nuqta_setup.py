"""Asset downloads must never replace a model with unverified bytes."""
import hashlib
import importlib.util
import io
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('nuqta_setup', Path(__file__).parents[1] / 'scripts/nuqta.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_corrupt_download_preserves_existing_file_and_cleans_temporary(tmp_path, monkeypatch):
    target = tmp_path / 'model.gguf'
    target.write_bytes(b'existing model')
    monkeypatch.setattr(setup.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(b'corrupt download'))
    with pytest.raises(RuntimeError, match='Checksum mismatch'):
        setup.download('https://example.invalid/model', target, hashlib.sha256(b'expected').hexdigest())
    assert target.read_bytes() == b'existing model'
    assert list(tmp_path.iterdir()) == [target]


def test_verified_download_is_reused_without_network(tmp_path, monkeypatch):
    target = tmp_path / 'model.gguf'
    content = b'verified model'
    checksum = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(setup.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(content))
    setup.download('https://example.invalid/model', target, checksum)
    assert target.read_bytes() == content

    def unexpected_network(*args, **kwargs):
        pytest.fail('A verified local asset should not be downloaded again')

    monkeypatch.setattr(setup.urllib.request, 'urlopen', unexpected_network)
    setup.download('https://example.invalid/model', target, checksum)
    assert list(tmp_path.iterdir()) == [target]
