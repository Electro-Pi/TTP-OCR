# Coda Image Translator

English-to-Arabic image localization, mounted at `/ocr/`. Runs PP-OCRv6 medium detection and recognition on the local CPU, translates extracted text through the configured Coda API, and composites Arabic into the original image.

## Run

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python configure.py
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8115 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
```

`configure.py` reads endpoint and model settings from the supplied `.env.remote.example` and prompts privately for the API key. Runtime secrets are stored in `.env` with mode 0600 and are never served to browsers. The supplied remote template may contain credentials; do not publish it. Fonts and their OFL license are in `static/fonts/`.

Open `http://127.0.0.1:8115/ocr/`. Initial startup downloads about 140 MB of model files into `models/`. Use one web worker: a separate single processing worker serializes OCR jobs and keeps the web process responsive. Four CPU threads are used by default. PaddlePaddle is pinned to 3.2.2: 3.3.1 failed on these v6 models with an unsupported oneDNN PIR attribute. With 3.2.2 and oneDNN enabled, the 1600×900 test diagram took about 4.9 seconds for OCR alone.

## Workflow

1. Upload PNG, JPEG, or WebP (50 MB, 16 megapixels, maximum side 6000 px).
2. Detect text polygons and group stacked lines of one label (left-, centre- or right-aligned, even when OCR boxes overlap) with compatible size and color. Lines are never grouped across a horizontal rule, so UML class compartments stay separate. Centred labels stay centred in Arabic.
3. Translate groups with whole-image text context through Coda-V2. Lists (attributes, methods, stacked labels) come back one Arabic line per original line and are drawn in evenly spaced slots between dividers; wrapped sentences are re-wrapped as one paragraph. Arabic size is capped to match the English, estimated from line widths because OCR boxes are taller than the lettering. Each entry carries its box size and an Arabic character budget, so short labels get the short interface term.
4. Remove lettering: on plain backgrounds the whole text area is cleared and refilled with background grain sampled around it, so JPEG fringes leave no letter ghosts; textured backgrounds use OpenCV inpainting. Long diagram lines are preserved, but long strokes lying entirely inside a text box (stems of large letters) are erased as lettering.
5. Shape and fit Arabic using Pillow/libraqm and Noto Sans Arabic. All English is erased before any Arabic is drawn, so neighbouring regions never cut into each other. Text that does not fit at a readable size may extend into plain background around it (sideways, and a little up and down inside shapes), stopping at other text, lines and artwork.
6. As a last resort before shrinking below a readable size, Arabic may be condensed horizontally to 85% (flagged for review). Regions that still do not fit, or fit only as small text, are sent back to Coda once or twice for shorter Arabic with the same meaning and flagged for review. Translations edited by the user are never rewritten.
7. Compare the original and Arabic images, edit translations, apply, and download a PNG.

Raw OCR confidence and visual-fit warnings are displayed for review. All detected English must be converted into Arabic script, including brands and technical acronyms. Latin letters trigger translation retries; edits containing Latin letters are rejected. Arabic is shaped RTL and aligned right within the existing text regions. The image layout and artwork are not mirrored. A region that cannot fit blocks completion and is shown for text correction instead of exporting an image with retained English. The website is Arabic and RTL. Re-upload images processed before this policy change.

## Translation endpoint

`POST /ocr-endpoint` translates an image in one synchronous request, English to Arabic by default or Arabic to English with `direction=ar-en`. Send a multipart form with an `image` field (same PNG/JPEG/WebP limits as uploads); the response is the Arabic PNG. Full reference: [docs/ocr-endpoint.md](docs/ocr-endpoint.md). Swagger UI is at `/ocr/docs` (schema at `/ocr/openapi.json`, listing only this endpoint).

```bash
curl --fail-with-body -F image=@diagram.png -o diagram-arabic.png https://<host>/ocr-endpoint
```

It runs the same detection, translation, fitting and Arabic-only check as web jobs, without saving anything to disk. Arabic is read with the community model `arabic_PP-OCRv6_small_rec` (vendored in `models/`, chosen by benchmark over the official Arabic model), with the official `arabic_PP-OCRv5_mobile_rec` re-reading lines that contain digits; English is drawn in Noto Sans, left-aligned. Response headers report `X-Text-Regions`, `X-Review-Count` and `X-Processing-Seconds`. Requests share the web app's rate limits and its queue of four images, and time out with 504 after 170 seconds (nginx allows 180).

## Files and retention

Uploaded images and results are stored under `data/<random-id>/`, accessible only to the browser session that uploaded them. The session cookie is HttpOnly, SameSite=Strict, and Secure over HTTPS. Files expire 24 hours after the last processing update and are swept every ten minutes. The server receives the image; Coda receives extracted text. Rate limits default to 12 images per IP per hour, 100 globally per day, and four active/queued jobs. Limits are in memory and reset on restart.

## Deployment

`deploy/coda-ocr.service` runs as `bassem`, binds only 127.0.0.1:8115, restarts on failure, caps the service at 4 CPU cores and 8 GB RAM, and limits filesystem writes. `deploy/coda-ocr.conf` mounts `/ocr/` without stripping the path. Install the snippet in the selected Coda TLS vhosts, validate with `nginx -t`, then reload nginx. Keep existing domain routes intact.

```bash
sudo systemctl status coda-ocr
sudo journalctl -u coda-ocr -n 80 --no-pager
sudo systemctl restart coda-ocr
```

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/python tests/make_fixture.py
.venv/bin/python tests/smoke.py
.venv/bin/python tests/browser_check.py
```

The smoke and browser tests use live Coda translation and require the local server. Browser QA uses Playwright and the existing Chromium executable; adjust its path for another machine. Generated screenshots and test output are ignored under `test-results/`.

The synthetic 1600×900 architecture diagram is a test fixture, not the user's original image. Unit tests verify pixels outside edit masks, preservation of borders, alpha handling, unchanged labels, and overflow behavior. End-to-end checks cover actual OCR, translation, export, access isolation, invalid uploads, and browser interactions.

## Practical limits

Flat diagrams and screenshots give the most predictable results. Textured backgrounds use local inpainting, which reconstructs rather than recovers occluded detail. Tiny text, unusual perspective, curved lettering, mixed scripts, and long translations may require review. Arabic fonts and line wrapping approximate the original styling. Numeric-only labels are preserved; text without Latin letters is not translated. OCR does not identify the language of every Latin-script word. No generative image model redraws the image.

## Verified deployment results

The complete synthetic 1600×900 diagram processed in 9.2 seconds (38 grouped text regions), including translation and rendering, on this host with four OCR threads. Five unit tests pass. Browser tests passed for desktop/mobile layout, upload, comparison, text editing, PNG download, and session restoration with no JavaScript errors. Timings vary by image and translation latency.
