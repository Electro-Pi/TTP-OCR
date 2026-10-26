# Image Translation Endpoint

Upload an image and get the same image back with its text translated in place. It works in two directions:

- **English → Arabic** (`en-ar`, the default)
- **Arabic → English** (`ar-en`)

One request does the whole job. The server reads the text with OCR, translates it with Coda, erases the original lettering and draws the translation in its place. The layout, colors and artwork stay the same.

```
POST https://www.coda.eracoda.ai/ocr-endpoint
```

English → Arabic runs the same pipeline as the [image translator web app](https://www.coda.eracoda.ai/ocr/), without the review and editing steps. Arabic → English is available only through this endpoint.

**Try it in the browser:** [Swagger UI](https://www.coda.eracoda.ai/ocr/docs). Open **POST /ocr-endpoint**, click **Try it out**, choose an image and click **Execute**. The OpenAPI schema is at [`/ocr/openapi.json`](https://www.coda.eracoda.ai/ocr/openapi.json).

- [Quick start](#quick-start)
- [Request](#request)
- [Response](#response)
- [Errors](#errors)
- [Limits and behavior](#limits-and-behavior)
- [How the translation works](#how-the-translation-works)
- [Code examples](#code-examples)
- [Tips for good results](#tips-for-good-results)
- [Troubleshooting](#troubleshooting)
- [Operations](#operations)

---

## Quick start

```bash
curl -F image=@diagram.png -o diagram-arabic.png https://www.coda.eracoda.ai/ocr-endpoint
```

`diagram-arabic.png` is the translated image. To translate an Arabic image into English, add `-F direction=ar-en`:

```bash
curl -F image=@dashboard.png -F direction=ar-en -o dashboard-english.png https://www.coda.eracoda.ai/ocr-endpoint
```

If something goes wrong, the file contains a JSON error instead of an image. To catch that, use `--fail-with-body` and check the status code:

```bash
curl --fail-with-body -s -F image=@diagram.png -o diagram-arabic.png \
  -w 'HTTP %{http_code}\n' https://www.coda.eracoda.ai/ocr-endpoint
```

> Opening the URL in a browser returns `405 Method Not Allowed`. A browser sends `GET` when you open a URL, but the endpoint only accepts `POST` with an uploaded image.

---

## Request

| | |
|---|---|
| **Method** | `POST` |
| **Path** | `/ocr-endpoint` (exactly, with no trailing slash) |
| **Content type** | `multipart/form-data` |
| **Authentication** | None |

### Form fields

| Field | Type | Required | Description |
|---|---|---|---|
| `image` | file | Yes | The image to translate. Its file name is used to name the result. |
| `direction` | text | No | `en-ar` (default): English text to Arabic. `ar-en`: Arabic text to English. Any other value returns `422`. |

### Image requirements

| Rule | Value |
|---|---|
| Formats | PNG, JPEG, WebP. The server reads the file contents to determine the format; the file name and extension don't matter. |
| Maximum file size | 50 MB |
| Dimensions | 32 to 6000 pixels on each side |
| Maximum pixel count | 16 megapixels (for example 4000 × 4000) |
| Content | At least one line of readable text in the source language (English for `en-ar`, Arabic for `ar-en`), and at most 300 text regions. |

The server applies the EXIF orientation of JPEG files before processing, so photos taken on a phone come out upright.

---

## Response

### Success: `200 OK`

The response body is the translated image as a PNG.

| Header | Example | Meaning |
|---|---|---|
| `Content-Type` | `image/png` | The body is always PNG, whatever format you uploaded. |
| `Content-Disposition` | `inline; filename="diagram-arabic.png"` | Suggested file name: your file's name with `-arabic.png` (for `en-ar`) or `-english.png` (for `ar-en`) appended. Characters other than `A–Z a–z 0–9 . _ -` are replaced with `_`. |
| `X-Translation-Direction` | `en-ar` | The direction that was used. |
| `X-Text-Regions` | `37` | Number of text regions translated. A region is a label or block of text; lines that belong together are grouped. |
| `X-Review-Count` | `0` | Number of regions with a visual warning. These usually fit only at a small size, were condensed, or were shortened to fit. If this is above `0`, look at the image before you use it. |
| `X-Processing-Seconds` | `21.7` | Time spent on the server, including any wait in the queue. |
| `Cache-Control` | `no-store` | Don't cache the response. |

The output image:

- Has the **same width and height** as the input (after the EXIF orientation is applied).
- Keeps **transparency**: a PNG or WebP with an alpha channel comes back with the same alpha channel.
- Contains **no source-language letters** in translated areas: no English letters in an `en-ar` result, no Arabic letters in an `ar-en` result. The server refuses to return a partially translated image (see [`422`](#errors)).
- Isn't mirrored. The artwork stays in place and only the text changes direction: Arabic is drawn right to left and right-aligned, English left to right and left-aligned. Centered labels stay centered.

### Failure

Errors return JSON, not an image. See [Errors](#errors).

---

## Errors

Every error from the application is JSON with a `detail` field. `detail` is a string, except for `422` validation errors on the form, where it is a list.

```json
{"detail": "No readable English text was found. Try a clearer or higher-resolution image."}
```

| Status | `detail` | Cause and what to do |
|---|---|---|
| `400` | `This file is not a valid supported image.` | The file is damaged or isn't an image. |
| `400` | `Use an image between 32 and 6000 pixels per side, up to 16 megapixels.` | Resize the image. |
| `403` | `Requests must come from this website.` | A web page on another domain sent the request from a browser. See [Calling from a browser](#calling-from-a-browser). |
| `405` | `Method Not Allowed` | You used `GET` (for example by opening the URL in a browser). Use `POST`. |
| `413` | `Maximum upload size is 50 MB.` | The file is too large. For uploads over 51 MB, nginx answers with an HTML error page instead of JSON. |
| `415` | `Please upload a PNG, JPG, or WebP image.` | The image is in another format, such as GIF, BMP, TIFF, HEIC or PDF. Convert it first. |
| `422` | *(list)* `Field required` | The form has no `image` field. Check the field name and that the request is `multipart/form-data`. |
| `422` | *(list)* `Input should be 'en-ar' or 'ar-en'` | `direction` has another value. |
| `422` | `No readable English text was found. …` | `en-ar`: the image has no English text the engine can read. It's blank, too blurry, or already Arabic (use `ar-en`). |
| `422` | `No readable Arabic text was found. …` | `ar-en`: the image has no Arabic text the engine can read. It's blank, too blurry, or already English (use `en-ar`). |
| `422` | `This image has too many text regions. …` | The image has more than 300 text regions. Crop it into smaller parts. |
| `422` | `تعذّر وضع كل النصوص بالعربية. …` | `en-ar`: some of the Arabic didn't fit even after shortening. The server doesn't return a partially translated image. Use the [web app](https://www.coda.eracoda.ai/ocr/) to edit the translations by hand, or crop the image. |
| `422` | `Some English text could not fit in its space, even after shortening. …` | `ar-en`: the same, for English. Crop the image or give the text more room. |
| `429` | `The image queue is full. Please try again in a minute.` | Four images are already being processed. Retry shortly. |
| `429` | `The translation limit has been reached. Please try again later.` | Your IP address or the whole service has used its limit. See [Rate limits](#rate-limits). |
| `500` | `Processing failed. Please try again with a clearer image.` | Unexpected processing error. |
| `502` | *(Coda message)*, e.g. `Translation returned an incomplete response. Please try again.` | The Coda translation service failed or returned unusable output. Retry. |
| `502` | *(nginx HTML page)* | The service is down or restarting. Retry after a short wait. |
| `503` | `OCR models could not be loaded. Check the server configuration.` | The server is misconfigured. Contact the operator. |
| `504` | `Translation is taking too long. Please try again shortly.` | The request didn't finish within 170 seconds. Retry later. |

### Retries

- **Retry with backoff:** `429`, `502`, `504`. For example, wait 10, 30, then 60 seconds.
- **Don't retry unchanged:** `400`, `403`, `405`, `413`, `415`, and the `422` errors. Change the image or the request first.
- **Retry once:** `500`.

A `429` for the rate limit won't clear for up to an hour. Don't retry it in a tight loop.

---

## Limits and behavior

### Rate limits

Each translated image uses the paid Coda translation API. Requests to this endpoint therefore share the image translator web app's limits:

| Limit | Default | Setting |
|---|---|---|
| Images per client IP address per hour | 12 | `MAX_JOBS_PER_IP_HOUR` |
| Images for the whole service per day | 100 | `MAX_JOBS_PER_DAY` |
| Images being processed or queued at once | 4 | fixed |

Every request that passes image validation counts toward these limits, even if it later fails (for example with "No readable English text"). Requests rejected earlier, such as invalid files or oversized images, don't count. Counters are kept in memory and reset when the service restarts. Responses don't include rate-limit headers.

### Processing time

The endpoint is **synchronous**: the connection stays open until the translated image is ready.

| Image | Typical time |
|---|---|
| 1600 × 900 diagram with about 40 labels, `en-ar` | about 10–25 seconds |
| 1600 × 900 diagram with about 40 labels, `ar-en` | about 7–15 seconds |
| 1280 × 760 dashboard with about 25 labels, `ar-en` | about 4–6 seconds |
| Small screenshot with a few labels | a few seconds |

Most of the time is spent on OCR and on waiting for Coda. Text that doesn't fit is sent back to Coda once or twice for shorter wording, which adds time.

All OCR and drawing runs in one worker process that handles one image at a time. If other images are ahead of yours, from this endpoint or the web app, your request waits.

- Set your HTTP client timeout to at least **180 seconds**.
- The server gives up after **170 seconds** and returns `504`. A request still waiting in the queue is cancelled. One that has already started finishes in the background and its result is discarded.
- Send images **one at a time** and wait for each response before sending the next. Parallel requests just wait in the queue and use up the limit of four.
- Shortly after a service restart, the OCR models may still be loading. Requests wait for them to finish loading; they are not rejected.

### Languages

| Direction | What is translated | What is left unchanged |
|---|---|---|
| `en-ar` English → Arabic | Every line with Latin letters. All English becomes Arabic script, including brand names and acronyms: "IAM / SSO" becomes Arabic words, not untouched Latin letters. | Lines with no Latin letters: numbers, symbols, existing Arabic. |
| `ar-en` Arabic → English | Every line that is mostly Arabic letters. Arabic names are transliterated (الرياض → Riyadh), and Latin words and acronyms inside Arabic text (`KPI`, `v2.1`) are kept. Arabic-Indic digits become Western digits (٣٤٨ → 348). | Lines that are mostly or entirely Latin text, numbers and symbols. |

#### Arabic OCR accuracy

Arabic is read by a separate recognizer, [`arabic_PP-OCRv6_small_rec`](https://huggingface.co/medyas/arabic_PP-OCRv6_small_rec), behind the same PP-OCRv6 text detector. It was chosen after benchmarks on this server's CPU. On Arabic interface text in 18 common UI fonts (Cairo, Tajawal, Almarai, IBM Plex Sans Arabic, Noto and others), it made about 3% character errors end to end, against about 6% for PaddleOCR's official Arabic model.

Known weak spots:

- **Arabic-Indic numbers** (٠١٢٣٤٥٦٧٨٩) are the least reliable part. In common UI fonts the digit `١` looks exactly like the letter `ا`, and digits are sometimes dropped or misread, for example `١٢٥٬٠٠٠` read as `١٥`. Lines containing digits are read a second time with PaddleOCR's official Arabic model, which handles them better, but **check numbers in the result**. Western digits (0–9) inside Arabic text are read reliably.
- **Very small text** (under about 14 px) and **calligraphic fonts** such as Amiri have higher error rates.
- The recognizer sometimes runs two words together. The translator is told to expect OCR slips and usually translates the intended words.

The OCR output isn't returned. If a translation looks wrong, the source reading is the first thing to suspect.

### Privacy and data handling

- The uploaded image is processed **in memory and not written to disk**. Nothing is kept after the response is sent.
- The image itself stays on the server. Only the **extracted text** is sent to the Coda translation API.
- Responses carry `Cache-Control: no-store`.
- The response also sets a `coda_ocr_session` cookie. That cookie is used by the web app and can be ignored.

### Authentication and CORS

There is no API key. Anyone who can reach the URL can use the endpoint, subject to the [rate limits](#rate-limits).

#### Calling from a browser

The service rejects browser requests sent from web pages on other domains, so you can't call it with `fetch` from your own website's front end. The service blocks those requests with `403` and doesn't send CORS headers. Call the endpoint from your backend, a script or the command line, and pass the image to your front end.

---

## How the translation works

1. **Read:** the PP-OCRv6 detector finds every line of text and its outline, and a recognizer for the source language reads it: PP-OCRv6 medium for English, the Arabic recognizer above for Arabic. Lines not in the source language are skipped. Lines that belong to one label (same alignment, size and color, and not separated by a rule) are grouped together.
2. **Translate:** all labels are sent to Coda together, so each one is translated with the context of the whole image. Each label comes with the number of characters that fit its space, and short labels get short interface terms. Lists keep one translated line per original line.
3. **Erase:** the original lettering is removed. Plain backgrounds are refilled with matching texture, and textured backgrounds are inpainted. Diagram lines and borders are preserved.
4. **Draw:** the translation is drawn in the original text color, at a size that visually matches the original. Arabic is shaped right to left in Noto Sans Arabic and right-aligned; English is set in Noto Sans and left-aligned. Centered labels stay centered.
5. **Fit:** if the text doesn't fit, it can spread into empty space nearby or be condensed slightly. If it still doesn't fit or would be too small, Coda is asked for a shorter translation, up to two more times. Shortening never truncates words into made-up abbreviations. If any text still can't be placed, the request fails with `422` rather than returning a partially translated image.

---

## Code examples

### curl

```bash
# Save the translated image
curl --fail-with-body -s -F image=@diagram.png -o diagram-arabic.png https://www.coda.eracoda.ai/ocr-endpoint

# Also print the status code and the summary headers
curl -s -m 180 -D - -o diagram-arabic.png -F image=@diagram.png https://www.coda.eracoda.ai/ocr-endpoint \
  | grep -iE '^(HTTP|x-text-regions|x-review-count|x-processing-seconds)'

# Arabic image to English
curl --fail-with-body -s -F image=@dashboard.png -F direction=ar-en -o dashboard-english.png https://www.coda.eracoda.ai/ocr-endpoint

# Translate every PNG in a folder, one at a time
for f in images/*.png; do
  curl --fail-with-body -s -m 180 -F "image=@$f" -o "out/$(basename "${f%.*}")-arabic.png" \
    https://www.coda.eracoda.ai/ocr-endpoint || echo "failed: $f"
done
```

### Python (requests)

```python
import requests

URL = "https://www.coda.eracoda.ai/ocr-endpoint"

with open("diagram.png", "rb") as f:
    response = requests.post(URL, files={"image": ("diagram.png", f, "image/png")}, timeout=180)

if response.ok:
    with open("diagram-arabic.png", "wb") as out:
        out.write(response.content)
    print("regions:", response.headers["X-Text-Regions"],
          "needs review:", response.headers["X-Review-Count"],
          "seconds:", response.headers["X-Processing-Seconds"])
else:
    print(response.status_code, response.json()["detail"])
```

### Python with retries

```python
import time
from pathlib import Path

import requests

URL = "https://www.coda.eracoda.ai/ocr-endpoint"
RETRYABLE = {429, 502, 504}


def translate_image(source: str, direction: str = "en-ar", target: str | None = None, attempts: int = 4) -> Path:
    source_path = Path(source)
    suffix = "-arabic.png" if direction == "en-ar" else "-english.png"
    target_path = Path(target or source_path.with_name(source_path.stem + suffix))
    delays = [10, 30, 60]
    for attempt in range(attempts):
        with open(source_path, "rb") as f:
            response = requests.post(URL, files={"image": (source_path.name, f)},
                                     data={"direction": direction}, timeout=180)
        if response.ok:
            target_path.write_bytes(response.content)
            return target_path
        if response.status_code not in RETRYABLE or attempt == attempts - 1:
            raise RuntimeError(f"{response.status_code}: {response.text}")
        time.sleep(delays[min(attempt, len(delays) - 1)])


print(translate_image("diagram.png"))                  # English -> Arabic
print(translate_image("dashboard.png", "ar-en"))       # Arabic -> English
```

### JavaScript (Node.js 18+)

```javascript
import { readFile, writeFile } from "node:fs/promises";

const form = new FormData();
form.append("image", new Blob([await readFile("diagram.png")], { type: "image/png" }), "diagram.png");
form.append("direction", "en-ar"); // or "ar-en" for an Arabic image

const response = await fetch("https://www.coda.eracoda.ai/ocr-endpoint", {
  method: "POST",
  body: form,
  signal: AbortSignal.timeout(180_000),
});

if (!response.ok) {
  const { detail } = await response.json();
  throw new Error(`${response.status}: ${JSON.stringify(detail)}`);
}
await writeFile("diagram-arabic.png", Buffer.from(await response.arrayBuffer()));
console.log("regions:", response.headers.get("x-text-regions"),
            "needs review:", response.headers.get("x-review-count"));
```

Don't set the `Content-Type` header yourself. `fetch` sets it automatically, with the multipart boundary the server needs.

### PHP

```php
<?php
$ch = curl_init('https://www.coda.eracoda.ai/ocr-endpoint');
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => ['image' => new CURLFile('diagram.png', 'image/png'), 'direction' => 'en-ar'],
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT => 180,
]);
$body = curl_exec($ch);
$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($status === 200) {
    file_put_contents('diagram-arabic.png', $body);
} else {
    echo "Error $status: " . $body;
}
```

### Postman / Insomnia

1. Set the method to **POST** and the URL to `https://www.coda.eracoda.ai/ocr-endpoint`.
2. Under **Body**, choose **form-data**.
3. Add a key named `image`, change its type from *Text* to *File*, and select your image.
4. For an Arabic image, add a text key named `direction` with the value `ar-en`.
5. In the settings, raise the request timeout to at least 180 seconds.
6. Send the request. The image appears in the response pane; use **Save response → Save to a file** to keep it.

---

## Tips for good results

- **Flat images work best:** diagrams, screenshots, slides, banners and UI mockups with solid backgrounds. Photos, gradients and textures are reconstructed by inpainting and may show traces.
- **Send the original image.** Re-saving it as a lower-quality JPEG blurs small text and leaves artifacts around the erased letters.
- **Give the translation room.** Translations are often longer than the original, especially Arabic → English. Tight boxes with long labels are the most common cause of small text (`X-Review-Count` above `0`) or a `422`.
- **Check numbers in Arabic → English results**, especially numbers written in Arabic-Indic digits. See [Arabic OCR accuracy](#arabic-ocr-accuracy).
- **Crop busy images.** Very large images with tiny text read better when split, and there is a limit of 300 text regions.
- **Check `X-Review-Count`.** If it's above `0`, look at the image. For full control, open the [web app](https://www.coda.eracoda.ai/ocr/), which shows each region's translation and lets you edit it.
- Curved, rotated, perspective or handwritten text may be missed or placed imperfectly.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| The saved `.png` file won't open | It contains a JSON error, not an image. Open it as text, or use `--fail-with-body` and check the status code. |
| Opening the URL in a browser shows `405` | Expected: the endpoint only accepts `POST`. Use one of the examples above. |
| The response is a large HTML page with status `404` | The URL is wrong, for example `/ocwr-endpoint` or `/ocr-endpoint/`. The path must be exactly `/ocr-endpoint`. |
| `422` with `Field required` | The file field isn't named `image`, or the body isn't `multipart/form-data` (for example, it was sent as JSON or raw binary). |
| `422` "No readable English text" on an image that has text | The text is too small or blurry, or it's Arabic: send `direction=ar-en`. |
| `422` "No readable Arabic text" on an image that has text | The text is too small or blurry, or it's English: leave out `direction` or send `en-ar`. |
| A number in an `ar-en` result is wrong | Arabic-Indic digits are the OCR's weakest point. See [Arabic OCR accuracy](#arabic-ocr-accuracy). |
| `422` with an Arabic message (`en-ar`) | Some translations couldn't fit. Use the web app to shorten them by hand, or give the text more room. |
| `429` after about 12 images | You've reached the hourly per-IP limit. Wait, or ask the operator to raise `MAX_JOBS_PER_IP_HOUR`. |
| Your client times out first | Raise its timeout to 180 seconds. Many clients default to 30 or 60 seconds. |
| `403 Requests must come from this website.` | The request came from a web page on another domain. Call the endpoint from your server instead. |

---

## Operations

This section is for whoever runs the server.

| Item | Location |
|---|---|
| Route handler | `ocr_endpoint` in `app.py`; the worker function is `translate_image`. |
| Shared pipeline | `find_text` and `compose` in `app.py`, used by both the endpoint and web-app jobs; `detect`, `translate`, `render` and `shorten` in `pipeline.py`. Each takes the source or target language; the defaults are English → Arabic. |
| OCR models | English: `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`. Arabic: the same detector + `models/arabic_PP-OCRv6_small_rec/` (not covered by the `models/` ignore rule because PaddleX cannot download it; pinned revision, re-download steps and checksums in `SOURCE.txt` and `SHA256SUMS`), with `arabic_PP-OCRv5_mobile_rec` re-reading lines that contain digits. The line-orientation classifier is off for Arabic: it turned about one Arabic line in ten upside down. |
| Fonts | `static/fonts/NotoSansArabic.ttf` (Arabic), `static/fonts/NotoSans.ttf` (English), both OFL. |
| Server timeout | `API_TIMEOUT` in `app.py` (170 s) |
| nginx route | `location = /ocr-endpoint` in `deploy/coda-ocr.conf` (`proxy_read_timeout 180s`), installed at `/etc/nginx/snippets/coda-ocr.conf` |
| Service | `coda-ocr.service`, listening on `127.0.0.1:8115` |
| Limits | `MAX_JOBS_PER_IP_HOUR`, `MAX_JOBS_PER_DAY` in `.env`, shared with the web app |

The nginx snippet is included in the `www.coda.eracoda.ai` and `coda.eracoda.ai` server blocks. Other domains (`.com`, `.sa`) don't route this path.

```bash
# Health check of the shared OCR engine
curl -s https://www.coda.eracoda.ai/ocr/api/health

# Logs and restart
sudo journalctl -u coda-ocr -n 80 --no-pager
sudo systemctl restart coda-ocr

# After editing deploy/coda-ocr.conf
sudo install -m 644 deploy/coda-ocr.conf /etc/nginx/snippets/coda-ocr.conf
sudo nginx -t && sudo systemctl reload nginx
```

Restarting the service cancels any image that is being processed and resets all rate-limit counters.
