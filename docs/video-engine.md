# Video engine

## The contract

Every render produces exactly one file: **1080×1920, 9:16, MP4, H.264 High@4.1, yuv420p,
AAC 44.1 kHz stereo when the source has audio, `+faststart`**. Suitable for Instagram Reels,
YouTube Shorts and TikTok. The output is flat — no editable layers survive into the download.

## Pipeline

`backend/app/worker/tasks.py` runs eight stages, each owning a slice of the 0–100 progress range:

| Stage | Range | What actually happens |
| --- | --- | --- |
| `upload` | 0–5 | Marked done at job creation; the upload already succeeded |
| `validation` | 5–14 | Download from storage, `ffprobe` re-validation |
| `video_processing` | 14–26 | Resolve the template document and background mode |
| `brand` | 26–36 | Fetch the logo, build `BrandContext`, write `brand_snapshot` |
| `text` | 36–46 | Compose and rasterise every non-video layer into one PNG |
| `logo` | 46–52 | (the logo is part of the same composite) |
| `rendering` | 52–92 | FFmpeg, driven by real `-progress` output |
| `quality_check` | 92–100 | `ffprobe` the result against the contract, extract a thumbnail |

Scratch files live in a per-job temp directory removed in a `finally` block. A failure at any
stage marks the job `FAILED` with a message written for a non-technical user
(`_friendly_ffmpeg_error`), never a raw stack trace.

## Why the overlay is a PNG

FFmpeg's `drawtext` hands strings straight to FreeType with no HarfBuzz shaping and no bidi
reordering. Arabic comes out as disconnected, reversed letters. So ASEELO rasterises every text
layer with Pillow and composites the result with a single `overlay` filter.

Two shaping paths, both supported:

1. **libraqm present** (the container installs `libraqm0`) — Pillow uses HarfBuzz + FriBidi
   natively, and `prepare_display_text()` is the identity function. This is the correct path.
2. **libraqm absent** — fall back to `arabic-reshaper` (presentation-form substitution) plus
   `python-bidi` (manual reordering).

`text_engine_info()` reports which path is live. Paragraph direction follows UAX#9 P2/P3: the
first strong character decides, so `"عرض خاص - 50% OFF"` is RTL while `"50% OFF عرض"` is LTR.
Logical alignment (`start`/`end`) resolves against that direction, so `start` means *right* in an
Arabic paragraph.

## Font coverage

Fonts are resolved by slug (`app/video/fonts.py`) through a preference list — Noto Sans Arabic,
Noto Kufi Arabic, Amiri, DejaVu Sans — falling back to `fc-match`.

**Pillow does no font fallback.** A glyph the chosen file lacks renders as a tofu box, and the
Arabic-only Noto families have *no Latin letters and no `%` glyph*. Naively defaulting to Noto
Sans Arabic therefore renders `"عرض خاص - 50% OFF"` with `OFF` and `%` as empty boxes.

So `resolve_font()` is coverage-aware: given the text, it reads each candidate's cmap (via
fontTools, cached per file) and returns the first font that covers **every** non-space character
in the string. Measured coverage of the container's installed families:

| Family | Arabic | Latin | `%` |
| --- | --- | --- | --- |
| Noto Sans Arabic | yes | **no** | **no** |
| Noto Kufi Arabic | yes | **no** | **no** |
| Amiri | yes | yes | yes |
| DejaVu Sans | yes | yes | yes |

Pure-Arabic text keeps the requested family; mixed text falls through to a dual-script family.
If nothing covers the string, the preferred font is used and a `no_font_covers_text` warning is
logged rather than failing the render.

`tests/test_text.py::test_resolved_font_covers_every_character` locks this in.

## Auto-fit

`fit_text()` shrinks the font in 2 px steps from `size` down to `min_size` until the wrapped
paragraph fits both `max_lines` and the box height. Word wrap is greedy on the *logical* string
and honours explicit newlines; a single word wider than the box is broken by character. This is
why a long Arabic headline and a short English one both stay inside the safe area.

## The FFmpeg graph

Three background modes, selected per template:

```
cover     [0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[base]
pad       [0:v]scale=…:decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black[base]
blur_pad  [0:v]split=2[bgsrc][fgsrc];
          [bgsrc]scale=…:increase,crop=1080:1920,gblur=sigma=28[bg];
          [fgsrc]scale=…:decrease[fg];
          [bg][fg]overlay=(W-w)/2:(H-h)/2[base]
```

then, identically for all three:

```
[1:v]scale=1080:1920[ovl];
[base][ovl]overlay=0:0:format=auto:eof_action=repeat[composed];
[composed]fps=30,setsar=1,format=yuv420p[outv]
```

`cover` centre-crops (the Reels default). `blur_pad` fills the frame with a blurred copy so
nothing is cut off — better for landscape sources where the edges matter.

Progress comes from parsing `out_time_us` / `out_time_ms` / `out_time` on FFmpeg's `-progress
pipe:1` stream and dividing by the probed duration. Reports are throttled to 1% movement.

## Templates are data

A template is a JSONB document in `templates.configuration`, interpreted by
`app/video/compose.py`. Adding one is an INSERT — the renderer never changes.

```jsonc
{
  "version": 1,
  "canvas": { "width": 1080, "height": 1920 },
  "safe_area": { "top": 180, "bottom": 320, "left": 72, "right": 72 },
  "background": { "mode": "cover", "overlay_color": "$black", "overlay_alpha": 0.28 },
  "layers": [
    { "type": "gradient", "box": {"x":0,"y":1180,"w":1080,"h":740},
      "color": "$black", "from_alpha": 0.0, "to_alpha": 0.80 },
    { "type": "logo", "name": "brand-logo", "box": {"x":430,"y":150,"w":220,"h":220}, "fit": "contain" },
    { "type": "text", "name": "headline", "source": "text_content",
      "box": {"x":90,"y":700,"w":900,"h":600},
      "style": { "bold": true, "size": 86, "min_size": 40, "color": "$white",
                 "align": "center", "line_spacing": 1.28, "shadow": true, "max_lines": 5 } }
  ]
}
```

**Layer types:** `fill` (full-canvas wash), `gradient` (vertical alpha ramp — legibility scrim),
`bar` (solid/rounded rectangle), `text` (Arabic-aware, auto-fitted), `logo` (aspect-preserving
contain/cover).

**Colour tokens** resolve against the user's brand at render time: `$primary`, `$secondary`,
`$accent`, `$white`, `$black`. A literal `#RRGGBB` passes through. One template therefore serves
every brand.

**Text sources:** `text_content`, `title`, `brand_name`, `tagline`, `phone`, `whatsapp`,
`website`, `address`, `contact_inline`, `contact_multiline`, `social_inline`, `literal:…`.
Contact labels switch to Arabic (`هاتف`, `واتساب`) when the content is Arabic, and a WhatsApp
number identical to the phone number is not repeated.

Layers whose source resolves to an empty string are skipped, not rendered blank — a brand with no
tagline simply has no tagline band.

The three seeded templates (`app/video/templates.py`): **clean-minimal** (centred headline, top
logo, bottom contact), **bold-headline** (upper headline over a blurred fill, solid bottom brand
bar), **modern-promo** (highlighted headline plate in brand colours, multi-line contact block).

## Quality gates

`validate_output()` re-probes the render and fails the job unless *all* hold: file exists,
≥20 KB, readable as MP4/MOV, `h264`, exactly 1080×1920, `yuv420p`, duration >0.05 s and within
`max(1 s, 8%)` of the source, AAC audio present iff the source had audio, and effective bitrate
above 150 kbps (below that it is almost certainly a black or broken render). Issues are collected
and stored on the job so the user sees *why*.

Thumbnail extraction is deliberately non-fatal: it seeks to 1 s, retries at frame 0 for very
short clips, and on failure just logs and leaves `thumbnail_url` null.

## Testing it

`backend/tests/test_render.py` encodes real clips with `testsrc`/`sine` and asserts the output
against the contract for all three templates, plus a silent portrait source, a corrupt source,
and a deliberately wrong-resolution file. Nothing in the render path is mocked.

```bash
docker compose run --rm backend pytest tests/test_render.py -v
```
