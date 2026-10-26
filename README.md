# Coda Image Translator

Image localization, mounted at `/ocr/`, with an English↔Arabic translation endpoint. English uses PP-OCRv6 Medium detection and recognition. Arabic uses PP-OCRv6 Medium detection plus Nuqta Arabic OCR 0.8B Q8_0 on the local CPU. Extracted text is translated through the configured Coda API and composited into the original image.

## Run

Use Python 3.12+. Set your translation endpoint/model in `.env.example` (or the privately supplied `.env.remote.example`).

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python configure.py
.venv/bin/python scripts/nuqta.py setup
# Start in a separate terminal; keep it running:
.venv/bin/python scripts/nuqta.py serve
# Then start the web app in another terminal:
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8115 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
```

`configure.py` reads endpoint and model settings from `.env.remote.example` if supplied, otherwise `.env.example` and prompts privately for the API key. Runtime secrets are stored in `.env` with mode 0600 and are never served to browsers. The supplied remote template may contain credentials; do not publish it. Fonts and their OFL license are in `static/fonts/`.

Open `http://127.0.0.1:8115/ocr/`. Nuqta setup downloads pinned model/vision files (about 1.08 GB) and a pinned Linux x86-64 llama.cpp runtime, verifies SHA256 checksums, and does not start any service. Paddle models are cached in `models/` on first use. Use one web worker; the image worker serializes jobs and uses four CPU threads. PaddlePaddle remains pinned to 3.2.2 for the tested oneDNN compatibility.

See [Nuqta setup and operations](docs/nuqta-setup.md) for model provisioning, runtime overrides, resource limits, and validation. The app's initial readiness check consumes the Paddle predictions and waits for the configured Nuqta model to be available.

## Workflow

1. Upload PNG, JPEG, or WebP (50 MB, 16 megapixels, maximum side 6000 px).
2. Detect text polygons and group stacked lines of one label (left-, centre- or right-aligned, even when OCR boxes overlap) with compatible size and color. Lines are never grouped across a horizontal rule, so UML class compartments stay separate. Centred labels stay centred in Arabic.
3. Translate groups with whole-image text context through Coda-V2. Lists (attributes, methods, stacked labels) come back one Arabic line per original line and are drawn in evenly spaced slots between dividers; wrapped sentences are re-wrapped as one paragraph. Arabic size is capped to match the English, estimated from line widths because OCR boxes are taller than the lettering. Each entry carries its box size and an Arabic character budget, so short labels get the short interface term.
4. Remove lettering: on plain backgrounds the whole text area is cleared and refilled with background grain sampled around it, so JPEG fringes leave no letter ghosts; textured backgrounds use OpenCV inpainting. Long diagram lines are preserved, but long strokes lying entirely inside a text box (stems of large letters) are erased as lettering.
5. Shape and fit Arabic using Pillow/libraqm and Noto Sans Arabic. All English is erased before any Arabic is drawn, so neighbouring regions never cut into each other. Text that does not fit at a readable size may extend into plain background around it (sideways, and a little up and down inside shapes), stopping at other text, lines and artwork.
6. As a last resort before shrinking below a readable size, Arabic may be condensed horizontally to 85% (flagged for review). Regions that still do not fit, or fit only as small text, are sent back to Coda once or twice for shorter Arabic with the same meaning and flagged for review. Translations edited by the user are never rewritten.
7. Compare the original and Arabic images, edit translations, apply, and download a PNG.

Available OCR confidence and visual-fit warnings are displayed for review. Nuqta has no calibrated confidence score: Arabic readings carry `confidence: null` and a review warning. All detected English must be converted into Arabic script, including brands and technical acronyms. Latin letters trigger translation retries; edits containing Latin letters are rejected. Arabic is shaped RTL and aligned right within the existing text regions. The image layout and artwork are not mirrored. A region that cannot fit blocks completion and is shown for text correction instead of exporting an image with retained English. The website is Arabic and RTL. Re-upload images processed before this policy change.

## Translation endpoint

`POST /ocr-endpoint` translates an image in one synchronous request, English to Arabic by default or Arabic to English with `direction=ar-en`. Send a multipart form with an `image` field (same PNG/JPEG/WebP limits as uploads); the response is the translated PNG. Full reference: [docs/ocr-endpoint.md](docs/ocr-endpoint.md). Swagger UI is at `/ocr/docs` (schema at `/ocr/openapi.json`, listing only this endpoint).

```bash
curl --fail-with-body -F image=@diagram.png -o diagram-arabic.png https://<host>/ocr-endpoint
```

It runs the shared detection, translation, fitting and source-script check without saving endpoint uploads. For `ar-en`, PP-OCRv6 Medium detects at 2× size on images up to 1600 px per side, maps boxes to the original image, removes nested duplicate boxes, and sends padded crops to the local Nuqta server. Nuqta's logical reading order is preserved; the previous small Arabic recognizer, reversal and digit fallback are no longer used. English output uses Noto Sans.

Response headers report `X-Text-Regions`, `X-Review-Count` and `X-Processing-Seconds`. Requests share the app's rate limits and queue of four images, and time out after 170 seconds. Arabic recognition is bounded separately: 64 detected crops and a 120-second image budget by default. Model failures and truncated readings fail the request rather than returning partially recognized output.

## Files and retention

Uploaded images and results are stored under `data/<random-id>/`, accessible only to the browser session that uploaded them. The session cookie is HttpOnly, SameSite=Strict, and Secure over HTTPS. Files expire 24 hours after the last processing update and are swept every ten minutes. The local Nuqta server receives Arabic image crops; Coda receives extracted text. If `NUQTA_BASE_URL` points elsewhere, those crops are sent to that configured host. Rate limits default to 12 images per IP per hour, 100 globally per day, and four active/queued jobs. Limits are in memory and reset on restart.

## Deployment

`deploy/coda-nuqta.service` runs the local model on loopback port 8116. `deploy/coda-ocr.service` depends on it and runs as `bassem`, binds only 127.0.0.1:8115, restarts on failure, caps the service at 4 CPU cores and 8 GB RAM, and limits filesystem writes. `deploy/coda-ocr.conf` mounts `/ocr/` without stripping the path. Install the snippet in the selected Coda TLS vhosts, validate with `nginx -t`, then reload nginx. Keep existing domain routes intact.

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

Flat diagrams and screenshots give the most predictable results. Textured backgrounds use local inpainting, which reconstructs rather than recovers occluded detail. Tiny text, unusual perspective, curved lettering, mixed scripts, and long translations may require review. Arabic fonts and line wrapping approximate the original styling. Numeric-only labels are preserved. English mode selects Latin-script text; Arabic mode selects predominantly Arabic text. OCR does not identify the language of every Latin-script word. No generative image model redraws the image.

## Hybrid OCR validation

The PP-OCRv6 + Nuqta trial read three of four synthetic Arabic fixtures without character errors. With enlarged detection and duplicate-box cleanup, the compressed circle fixture retained one extra Arabic letter. OCR took about 9–16 seconds per image in that trial. These were recreated test images, not original user uploads. Nuqta used about 1.3 GiB RSS; detector memory was measured separately.

Image composition still has known limitations with tilted boxes, faint text and shortening in tight labels. Better recognition does not guarantee a correct final translation layout. This repository change does not imply that an existing hosted deployment has been updated.
