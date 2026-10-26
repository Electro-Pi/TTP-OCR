"""PP-OCRv6 detection and local Nuqta Arabic recognition.

Nuqta emits logical-order text and no calibrated recognition confidence.
The local llama.cpp server is provisioned separately with scripts/nuqta.py.
"""
from __future__ import annotations

import base64
import io
import os
import re
import time

import cv2
import httpx
import numpy as np
from PIL import Image

PROMPT = ('Transcribe the Arabic text in this image exactly as written. '
          'Include only the diacritics (tashkeel) that are visible in the image.')
MODEL_ALIAS = 'nuqta-arabic'


class OCRInputLimit(RuntimeError):
    """An image exceeds the bounded CPU recognition workload."""


class OCRDeadlineExceeded(RuntimeError):
    """The Arabic OCR budget expired before the image was fully read."""


def suppress_nested(polygons):
    """Keep the larger region when a detector returns a block and its child line."""
    polygons = [np.asarray(p, dtype=np.float32) for p in polygons]
    areas = [abs(cv2.contourArea(p)) for p in polygons]
    return [p for i, p in enumerate(polygons) if areas[i] > 0 and not any(
        i != j and areas[j] >= 2 * areas[i]
        and cv2.intersectConvexConvex(p, other)[0] / areas[i] >= 0.65
        for j, other in enumerate(polygons))]


class NuqtaClient:
    def __init__(self):
        self.url = os.getenv('NUQTA_BASE_URL', 'http://127.0.0.1:8116').rstrip('/')
        self.request_timeout = float(os.getenv('NUQTA_REQUEST_TIMEOUT', '30'))
        if self.request_timeout <= 0:
            raise ValueError('NUQTA_REQUEST_TIMEOUT must be positive')

    def check_ready(self, timeout=120):
        """Wait for the configured model, not merely an open TCP port."""
        deadline = time.monotonic() + timeout
        with httpx.Client(base_url=self.url, trust_env=False) as client:
            while True:
                try:
                    remaining = max(0.1, deadline - time.monotonic())
                    response = client.get('/health', timeout=min(2, remaining))
                    response.raise_for_status()
                    response = client.get('/v1/models', timeout=min(2, remaining))
                    response.raise_for_status()
                    if MODEL_ALIAS not in [m['id'] for m in response.json()['data']]:
                        raise RuntimeError('The OCR backend is not serving the nuqta-arabic model alias.')
                    return
                except (httpx.HTTPError, KeyError, ValueError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Nuqta OCR is unavailable. Check the local model service.') from None
                    time.sleep(min(0.5, max(0, deadline - time.monotonic())))

    def read(self, image, client, remaining):
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
        payload = {
            'model': MODEL_ALIAS,
            'messages': [{'role': 'user', 'content': [
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}},
                {'type': 'text', 'text': PROMPT},
            ]}],
            'temperature': 0, 'top_k': 1, 'max_tokens': 256,
            'repeat_penalty': 1.0, 'frequency_penalty': 0, 'presence_penalty': 0,
            'cache_prompt': False, 'chat_template_kwargs': {'enable_thinking': False},
        }
        try:
            response = client.post('/v1/chat/completions', json=payload,
                                   timeout=min(self.request_timeout, remaining))
            response.raise_for_status()
            choice = response.json()['choices'][0]
            if choice['finish_reason'] != 'stop':
                raise RuntimeError('Nuqta could not finish reading a text region. Try a smaller crop.')
            text = choice['message']['content']
            if not isinstance(text, str):
                raise ValueError('Missing OCR text')
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
            if '<think>' in text or '</think>' in text:
                raise ValueError('Incomplete reasoning block')
            return text
        except httpx.TimeoutException:
            raise OCRDeadlineExceeded('Arabic OCR took too long. Please crop the image into smaller parts.') from None
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            raise RuntimeError('Nuqta OCR returned an invalid response or is unavailable.') from None


class PaddleNuqtaOCR:
    """Paddle-compatible predict interface used only by the Arabic route."""
    def __init__(self):
        from paddleocr import TextDetection
        self.scale = int(os.getenv('ARABIC_DETECTION_SCALE', '2'))
        self.max_regions = int(os.getenv('NUQTA_MAX_REGIONS', '64'))
        self.image_timeout = float(os.getenv('NUQTA_IMAGE_TIMEOUT', '120'))
        if self.scale not in (1, 2) or self.max_regions < 1 or self.image_timeout <= 0:
            raise ValueError('Invalid Arabic OCR scale, region limit, or time budget')
        self.detector = TextDetection(
            model_name=os.getenv('OCR_DETECTION_MODEL', 'PP-OCRv6_medium_det'),
            device='cpu', enable_mkldnn=True, cpu_threads=int(os.getenv('OCR_CPU_THREADS', '4')),
            limit_side_len=1600, limit_type='max', thresh=0.25, box_thresh=0.5,
        )
        self.reader = NuqtaClient()

    def check_ready(self):
        self.reader.check_ready(timeout=float(os.getenv('NUQTA_STARTUP_TIMEOUT', '120')))

    def predict(self, bgr):
        deadline = time.monotonic() + self.image_timeout
        image = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        # Upscale screenshots, but avoid allocating a 4x copy of large uploads.
        scale = self.scale if max(image.size) <= 1600 else 1
        enlarged = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS) if scale != 1 else image
        result = next(iter(self.detector.predict(cv2.cvtColor(np.asarray(enlarged), cv2.COLOR_RGB2BGR))))
        polygons = suppress_nested([np.asarray(p, dtype=float) / scale for p in result['dt_polys']])
        if len(polygons) > self.max_regions:
            raise OCRInputLimit(f'This image has more than {self.max_regions} Arabic text regions. Please crop it into smaller images.')
        readings = []
        used = []
        with httpx.Client(base_url=self.reader.url, trust_env=False) as client:
            for polygon in polygons:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise OCRDeadlineExceeded('Arabic OCR took too long. Please crop the image into smaller parts.')
                lo = np.maximum(np.floor(polygon.min(axis=0)).astype(int) - 3, 0)
                hi = np.minimum(np.ceil(polygon.max(axis=0)).astype(int) + 3, image.size)
                if np.any(hi <= lo):
                    continue
                crop = image.crop(tuple(int(x) for x in (*lo, *hi)))
                text = self.reader.read(crop, client, remaining)
                if time.monotonic() > deadline:
                    raise OCRDeadlineExceeded('Arabic OCR took too long. Please crop the image into smaller parts.')
                readings.append(text)
                used.append(polygon)
        return [{'rec_texts': readings, 'rec_scores': [None] * len(readings), 'rec_polys': used}]
