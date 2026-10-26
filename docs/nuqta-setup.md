# Nuqta Arabic OCR setup

Arabic-to-English processing uses PP-OCRv6 Medium to detect text, then Nuqta Arabic OCR 0.8B Q8_0 to read original-resolution crops. English-to-Arabic processing retains PP-OCRv6 Medium detection and recognition. The Nuqta runtime is a separate local CPU process.

## Provision and run

Run these commands from the repository root with Python 3.12+ and the dependencies in `requirements.txt` installed:

```bash
.venv/bin/python scripts/nuqta.py setup
.venv/bin/python scripts/nuqta.py verify
.venv/bin/python scripts/nuqta.py serve
```

`setup` downloads and verifies assets; it does not install or start services. `verify` checks the model files and executable. `serve` runs the model in the foreground on `127.0.0.1:8116`. Start the web application separately as described in the README. Its startup check waits for the `nuqta-arabic` model alias before reporting ready.

Model and vision weights total about 1.08 GB. The exact Hugging Face revision, file hashes, and llama.cpp b11907 Linux x86-64 archive hash are recorded in `nuqta-assets.json`. Downloads use temporary files and replace their destination only after SHA256 verification. Model cards and license are downloaded alongside the weights. The existing vendored small Arabic Paddle model is no longer loaded by this pipeline.

The bundled runtime targets Ubuntu Linux x86-64. On another platform, supply a compatible llama.cpp executable with `NUQTA_LLAMA_SERVER`; this skips the bundled runtime download. Custom executables are checked for existence and execution permission, not against the bundled archive hash. The model weights remain pinned and verified.

## Configuration

Settings can be placed in the repository's private `.env`. Do not commit credentials.

| Variable | Default | Purpose |
|---|---|---|
| `NUQTA_BASE_URL` | `http://127.0.0.1:8116` | Application's model server root URL, without `/v1`. Arabic image crops go to this host. |
| `NUQTA_PORT` | `8116` | Launcher's listening port; update the base URL if changed. |
| `NUQTA_MODEL_DIR` | `models/nuqta` under the repository | Downloaded weights and runtime directory. |
| `NUQTA_LLAMA_SERVER` | Pinned executable under the model directory | Optional existing executable override. |
| `OCR_CPU_THREADS` | `4` | Paddle and llama.cpp CPU thread count. |
| `ARABIC_DETECTION_SCALE` | `2` | Detection enlargement, allowed values `1` or `2`. Images whose longest side exceeds 1600 px are not enlarged. |
| `NUQTA_MAX_REGIONS` | `64` | Maximum detected Arabic crops after duplicate removal; exceeding it returns HTTP 422 before recognition. |
| `NUQTA_IMAGE_TIMEOUT` | `120` | Arabic OCR image budget in seconds, including detection. Checked between operations and used to bound each inference request. |
| `NUQTA_REQUEST_TIMEOUT` | `30` | Per-crop HTTP timeout in seconds, capped by the remaining image budget. |
| `NUQTA_STARTUP_TIMEOUT` | `120` | Time to wait for the configured model during app warmup. |

The launcher disables GPU layers and vision offload, uses one inference slot, an 8192-token context, and the `nuqta-arabic` alias. Recognition uses deterministic decoding with at most 256 output tokens per crop. A truncated or failed crop fails the entire image instead of silently returning partial OCR. Arabic OCR timeouts return HTTP 504. The endpoint also has its existing 170-second overall timeout.

The Nuqta process used approximately 1.3 GiB RSS in the synthetic trial, separately from Paddle and the web worker. Allow additional memory for image buffers and concurrent processes. The provided units cap Nuqta at 4 GiB and the application at 8 GiB; each has a four-core CPU quota.

## Future service installation

`deploy/coda-nuqta.service` and `deploy/coda-ocr.service` are installation templates. They assume user/group `bassem` and repository path `/home/bassem/screenshot-ocr`; adjust these for the target host. Provision assets before installing the units. The web unit requires the Nuqta unit, and application warmup checks model readiness. No installation or restart is performed by the provisioning script or by committing these files.

Keep the model server on loopback. To use a separate model host, arrange network access and update `NUQTA_BASE_URL`; image crops will then leave the application host. Coda continues to receive extracted text for translation.

## Validation and limitations

```bash
.venv/bin/python -m pytest -q
```

Tests cover routing, original crop coordinates, nested-box suppression, unknown confidence, malformed/truncated responses, readiness, workload limits and timeout handling, along with the existing image composition checks.

An isolated native-model check on five synthetic fixtures passed warmup and routing. Arabic OCR took about 10–18 seconds per image; English took about 1.3 seconds. The two numeric Arabic fixtures preserved `١٢٥٬٠٠٠` and `٢٠٢٦-١٠٤٢`. The smallest circle diagram still read `رسم بياني` as `رسم بيانتي`. These are small recreated fixtures, not a representative accuracy benchmark or the user's original files.

Nuqta returns text in logical Arabic order and has no calibrated recognition confidence. Arabic regions therefore carry `confidence: null` and a review warning. There is no old character-reversal step or digit rereading fallback. Detection can still miss text, and recognition can introduce errors. Translation fitting and drawing retain known limitations with tilted boxes, faint text and tight labels; this OCR change does not resolve those layout issues.
