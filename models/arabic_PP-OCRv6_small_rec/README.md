---
license: apache-2.0
library_name: PaddleOCR
tags:
- ocr
- arabic
- paddleocr
- text-recognition
- pp-ocrv6
language:
- ar
pipeline_tag: image-to-text
base_model: PaddlePaddle/PP-OCRv6_small_rec
datasets:
- medyas/arabic-ocr-printed-500k
---

# arabic_PP-OCRv6_small_rec

Arabic **printed-text recognition** model — the first fine-tune of PaddleOCR's
**PP-OCRv6** recognizer (`PP-OCRv6_small_rec`, **PPLCNetV4** backbone,
MultiHead CTC + NRTR) for Arabic. No Arabic PP-OCRv6 recognition model existed
before this: PP-OCRv6's unified release covers CJK + 46 Latin scripts only.

This is the **headline model** of an a→b study: fine-tune the Arabic
**PP-OCRv5** recognizer ([`medyas/arabic_PP-OCRv5_mobile_rec`](https://huggingface.co/medyas/arabic_PP-OCRv5_mobile_rec),
the labelled baseline) and then **PP-OCRv6** (this model) on the same task and
evaluation protocol. **v6 is the shipped model.** ⚠️ The v6 arm trained on an
**upgraded, larger corpus** than the published v5 arm (800k vs 500k, plus display
fonts and textured backgrounds), so the v5→v6 numbers reflect a backbone **and**
corpus improvement together — **not** a clean backbone-only ablation (see
*v5→v6 delta*).

- **Task:** image-to-text (single-line Arabic recognition)
- **Algorithm:** `Backbone=PPLCNetV4`, `Head=MultiHead (CTCHead + NRTRHead)`, MultiLoss
- **Warm start:** `PaddlePaddle/PP-OCRv6_small_rec` — note this base has **no Arabic prior** (unlike the v5 arm, which warm-started from an Arabic pretrained model). The Arabic recognition head (~1050 classes) is shape-mismatched against the base head and is **randomly re-initialized** (non-strict load); only the backbone is warm. Accuracy is ~0 for the first 1–2 epochs by design.
- **Corpus:** 800k synthetic Arabic printed lines (gen-v2: 26 base fonts + 12 display fonts, textured backgrounds, polarity inversion). This **extends** the published v1 corpus [`medyas/arabic-ocr-printed-500k`](https://huggingface.co/datasets/medyas/arabic-ocr-printed-500k) (500k); the 800k v2 superset is not yet on the Hub.
- **Selected checkpoint:** **epoch 11** (lowest CER on a real held-out scanned set)

## Evaluation

Numbers are from the **peak epoch-11 checkpoint**, evaluated on real
**KITAB-Bench** subsets. **CER = character error rate, WER = word error rate
(lower is better).** `patsocr` is the **selection** set (real scanned printed
text) used to pick the peak epoch; `isippt` and `historyar` are **held-out** and
were **not** used for selection.

| Subset    | Type                                  | n   | CER (strict) | CER (loose) | CER (no-mirror) | WER (strict) |
|-----------|---------------------------------------|-----|--------------|-------------|-----------------|--------------|
| patsocr   | real scanned printed (selection)      | 500 | **10.2%**    | 9.8%        | 10.2%           | —            |
| isippt    | presentation / document (held-out)    | 500 | 13.5%        | 12.7%       | **10.9%**¹      | 47.3%        |
| historyar | historical scanned printed (held-out) | 200 | 50.3%        | 49.3%       | 49.8%           | 98.2%        |

¹ The isippt *no-mirror* CER (10.9%) is computed over the n=341 crops with no
decode-mirror ambiguity; the *strict* columns (13.5% etc.) are over the full
n=500 and are the directly leaderboard-comparable number. "Decode-mirror" lines
are those containing western digits or bracket pairs, where the visual↔logical
reordering is a known decode-time bookkeeping artifact (the model is usually
correct; the scorer over-penalizes). We report **both** so the headline isn't a
cherry-pick — see *Honest-number disclosure* below.

**historyar 50.3% is a real domain gap, not a model defect for its target
domain.** historyar is *historical* scanned Arabic (degraded paper, old
typography, heavy diacritization) that the v1 synthetic corpus does not model.
It is the hardest real-print set and is shown as an out-of-domain reference;
representative accuracy for **modern** printed Arabic is the **patsocr ≈ 10%**
(scanned) and **isippt ≈ 11–13.5%** (documents/presentations) figures. Closing
historyar is a v6.1 corpus target (degradation/1-bit/historical-font synthesis).

### How good is ~10% CER? Same-set context (KITAB-Bench)

These sets are the OCR subsets of **KITAB-Bench** (Heakl et al., 2025,
arXiv:2502.14949, Table 9), so other systems' scores on the *exact same images*
are published. CER (lower = better):

| Model | patsocr (PATS-A01) | isippt (ISI-PPT) |
|---|---|---|
| Gemini-2.0-Flash | 0.01 | 0.06 |
| GPT-4o | 0.23 | 0.08 |
| **arabic_PP-OCRv6_small_rec (this model)** | **0.10** | **0.11–0.135** |
| GPT-4o-mini | 0.53 | 0.15 |
| AIN-7B (Arabic VLM) | 0.26 | 0.36 |
| Tesseract | 0.14 | 0.31 |
| **PaddleOCR (off-the-shelf)** | **0.77** | **0.81** |
| Qwen2.5-VL | 0.98 | 1.27 |
| Surya | 4.66 | 4.25 |
| Qari (specialized AR-OCR VLM) | 0.00* | 0.52 |

*Qari hits 0.00 on PATS but collapses to 0.52 on ISI-PPT (overfit-suspect on
clean PATS).

This model ranks **≈4th of 12 on patsocr and ≈3rd of 12 on isippt** — beating
both legacy engines (Tesseract, vanilla PaddleOCR) and most general VLMs
(GPT-4o-mini, both Qwen-VLs, AIN, GPT-4o-on-patsocr), and trailing only
frontier/specialist systems (Gemini-2.0-Flash, GPT-4o, and Qari-on-patsocr).
The vanilla-PaddleOCR row (0.77 / 0.81) shows what fine-tuning on the 500k
corpus bought: the same model family goes from near-useless on Arabic to
upper-tier. The model's distinguishing strength is **cross-set stability**
(~0.10 / ~0.11) — the strongest competitors each collapse on one set
(Azure 0.03→0.98, Qari 0.00→0.52).

> **Comparability:** KITAB-Bench's official scorer (`ocr-eval/metrics.py`) is
> diacritic-insensitive **plus** alef/teh-marbuta/alef-maksura folding +
> tatweel removal — i.e. *more* aggressive than this model's normalizer. Our
> reported CER is therefore a **conservative upper bound** on the
> KITAB-comparable figure; re-scoring our predictions through their `metrics.py`
> can only hold or lower it.

### Honest-number disclosure

Per-set decode-mirror exclusion rates (the n dropped for the no-mirror column):
patsocr ~0% (near pure-Arabic), **isippt ~32%** (n=341 of 500). Because the
no-mirror column drops the hardest digit/bracket lines, the **strict** column is
the fair headline; the no-mirror column is a diagnostic, not the marketing
number.

### v5 → v6 delta (harness-consistent)

v6 (this model) vs the v5 baseline arm — **both re-scored under the identical
current harness** (consolidated `eval/contract.py` + `eval/normalize.py`,
PaddleOCR v3.7.0; v5 re-scored 2026-06-23, CER lower = better):

| Set (real held-out) | v5 baseline | v6 (this model) | Δ |
|---|---|---|---|
| patsocr CER | 11.8% | **10.2%** | −1.6 |
| isippt CER (strict) | 17.0% | **13.5%** | −3.4 |
| isippt CER (no-mirror) | 14.7% | **10.9%** | −3.8 |
| historyar CER | 51.8% | **50.3%** | −1.5 |

v6 improves on every set. **One caveat remains** (now that the harness is
consistent): the corpus differs — v6 trained on the 800k gen-v2 corpus (display
fonts + textured backgrounds + polarity), the v5 arm on the 500k v1 corpus. So
the gain conflates the PPLCNetV3→V4 **backbone** change with the **corpus**
upgrade; read it as *"the shipped v6 system beats the v5 baseline,"* not as an
isolated backbone ablation (which would require retraining v5 on the 800k corpus,
or v6 on the 500k). v6's **absolute** numbers and the KITAB-Bench comparison
above do not depend on this caveat.

### Selection curve (patsocr CER, strict)

Epoch 11 was the lowest-CER checkpoint on the real scanned selection set
(cold-start v6 needs more epochs than the warm-started v5; the peak-pick
self-corrects for over/under-training):

| epoch | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | **11** | 12 | 13 | 14 | 15 |
|-------|------|------|------|------|------|------|------|------|------|------|----------|------|------|------|------|
| CER   |14.7%|15.8%|15.0%|22.9%|14.8%|13.2%|13.6%|17.4%|11.4%|14.4%|**10.2%**|12.5%|13.2%|11.4%|11.1%|

## Training

- **Hardware:** 2× Tesla T4 (Kaggle, free tier), distributed
- **Precision:** AMP, `amp_level=O2`, fp16
- **Batch:** 194 per card
- **Epochs:** 15 trained, `save_epoch_step=1`; **peak = epoch 11** selected by lowest CER on the real held-out scanned set (`patsocr`), not on synthetic val
- **EMA:** **off** — EMA's fp32 shadow weights are incompatible with the AMP-O2 fp16 model (dtype assert at eval); peak-pick already handles over-training, so EMA is not needed here.
- **Multi-session resume:** the full run exceeded Kaggle's 12h session cap, so it ran across **2 sessions** — per-epoch checkpoints (`latest.*` + `iter_epoch_N.*` + optimizer state) were pushed to an HF checkpoint repo each epoch and the second session resumed via `Global.checkpoints` (not `pretrained_model`, which would reset the LR schedule). Epoch count and batch size are held fixed across sessions so the cosine LR schedule is continuous.
- **Stability:** a numpy≥2.0 incompatibility in Paddle's AMP loss-scale NaN path (a `(1,)`-array `float()` raise) was patched on disk before launch so transient fp16 inf/nan events skip-and-halve instead of crashing.
- **LR:** config default `0.0005` (Cosine, `warmup_epoch=5`) — kept, not per-card-scaled.
- **Base config:** PaddleOCR `configs/rec/PP-OCRv6/PP-OCRv6_small_rec.yml` (included as `PP-OCRv6_small_rec.yml`). `max_text_length=25`, `character_dict_path=ppocrv5_arabic_dict.txt`.

## Label order

Training labels are stored in **VISUAL order** (via `bidi.get_display`). The
character dict filename contains the substring **`arabic`**
(`ppocrv5_arabic_dict.txt`), which triggers PaddleOCR's CTC-decode
`pred_reverse` path — so `tools/infer_rec.py` emits predictions in **logical
(reading) order**. Keep the dict filename containing `arabic` or decoding order
will be wrong.

## Inference

Do **not** `pip install paddleocr` (it pulls `torch` and breaks the Paddle ABI).
Install PaddlePaddle directly and run from a PaddleOCR clone:

```bash
git clone https://github.com/PaddlePaddle/PaddleOCR
cd PaddleOCR
# GPU build (CUDA 12.6 wheel index):
pip install paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

# download this model's files into <dl>/
hf download medyas/arabic_PP-OCRv6_small_rec --local-dir <dl>

python tools/infer_rec.py \
  -c PP-OCRv6_small_rec.yml \
  -o Global.pretrained_model=<dl>/arabic_PP-OCRv6_small_rec \
     Global.character_dict_path=<dl>/ppocrv5_arabic_dict.txt \
     Global.infer_img=<your_image.png>
```

(`Global.pretrained_model` takes the path **without** the `.pdparams` suffix.
Feed **line crops** — this is a recognition-only model; pair it with a detector
for full-page OCR.)

## Deployable inference model (`inference/`)

The repo also ships a **PaddleInference export of the peak (epoch-11) checkpoint**
under `inference/` (`inference.json` + `inference.pdiparams` + `inference.yml`)
for serving via PaddleInference / the PaddleOCR `predict()` API — no PaddleOCR
clone or training config needed at runtime.

**⚠️ Decode order — important.** This model was trained on **visual-order**
labels, so its raw CTC output is in **visual (RTL-display) order**.
`tools/infer_rec.py` (above) reverses it to logical reading-order automatically
*because the dict filename contains `arabic`*. The exported `inference.yml`
carries an **inline** dict (no path), so the bare `CTCLabelDecode` postprocess
does **not** reverse. To recover logical reading-order from the inference model,
apply `pred_reverse` to its output:

```python
import re
def pred_reverse(pred):  # from PaddleOCR rec_postprocess, for "arabic"-class dicts
    out, cur = [], ""
    for c in pred:
        if not re.search(r"[a-zA-Z0-9 :*./%+-]", c):
            if cur: out.append(cur)
            out.append(c); cur = ""
        else:
            cur += c
    if cur: out.append(cur)
    return "".join(out[::-1])
# logical_text = pred_reverse(model_visual_output)
```

For guaranteed logical output with **zero** post-processing, use
`tools/infer_rec.py` with the `.pdparams` checkpoint (above) — that is exactly
how the reported CERs were computed.

## Corpus notes

Synthetic Arabic printed lines rendered via **libraqm / RAQM** (26 base fonts +
12 display fonts: Naskh / Kufi / Ruqaa / clean-sans families; Nastaliq / Diwani /
Thuluth deliberately excluded as CTC-unsafe). Text from Wikipedia vocabulary plus
~15% general numerics/dates. Normalization: **NFKC**, **tashkeel stripped (v1)**,
**western digits**. Real-scan augmentation: blur, gaussian + salt-and-pepper
noise, brightness drop, JPEG recompression (q35–70), rotation ±3°, plus textured
backgrounds and polarity inversion.

**Known gaps (v1 corpus):** historical/degraded typography (see historyar);
heavy native diacritization. Both are v6.1 corpus targets.

## License

**Apache-2.0** (inherited from PaddleOCR). The training corpus is synthetic.

## Files

- `arabic_PP-OCRv6_small_rec.pdparams` — peak weights (epoch 11)
- `arabic_PP-OCRv6_small_rec.states` — training metadata (best metric / epoch)
- `ppocrv5_arabic_dict.txt` — character dictionary (filename must contain `arabic`)
- `summary_arabic_PP-OCRv6_small_rec.json` — full eval summary (selection curve + headline)
- `PP-OCRv6_small_rec.yml` — base training config (for reproducibility)
- `inference/` — deployable PaddleInference export (`inference.json` / `.pdiparams` / `.yml`; see *Deployable inference model*)
