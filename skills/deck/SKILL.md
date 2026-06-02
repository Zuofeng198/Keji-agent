---
name: deck
description: 通过严格的两阶段工作流生成高质量 HTML 演示文稿。支持技术分享、架构评审、战略汇报、研究成果展示和团队更新等场景。
---

# Deck — Presentation Deck Generator

## Command Modes

Parse the invocation to determine mode:

- **`/deck --plan [prompt]`** — Planning mode. Create deck outline, save to `PLANNING.md`, present for review. **Do NOT generate HTML.**
- **`/deck --generate [optional instructions]`** — Generation mode. Produce final HTML slides from approved `PLANNING.md`. **Refuse if `PLANNING.md` is missing.**
- **`/deck --export pptx [--scale N]`** — Export mode. Convert generated HTML slides into a PPTX file. Optional `--scale N` controls image resolution multiplier (default 3). **Refuse if `presentation/slides/` is missing or contains no slide HTML files.**

If neither flag is provided, ask the user which mode they want.

---

## Planning Mode (`--plan`)

1. **Check `resources/` folder**
   - If missing or empty, remind the user: _"Place relevant source materials (articles, reports, notes, images) into `resources/` before planning for best results."_
   - If present, read and analyze all files. Summarize what was found.

2. **Analyze the user prompt**
   - Extract: topic, audience, tone, language, slide count, goals, style preferences.
   - If the user prompt is under-specified, ask clarifying questions (audience, slide count, language, goals).

3. **Draft the plan**
   - Follow the structure in [references/planning-template.md](references/planning-template.md).
   - For each slide: specify the key point, supporting bullets, and visual element type.
   - Map content from `resources/` to specific slides — cite which resource informs which slide.
   - Include visual/layout guidelines (colors, fonts) — use defaults from [references/design-system.md](references/design-system.md) unless the user specifies otherwise.

4. **Save to `PLANNING.md`** in the working directory.

5. **Present the plan** to the user for review. Summarize slide count, structure, and key decisions. Ask for approval or revision feedback.

6. **Stop.** Do NOT proceed to generation.

---

## Generation Mode (`--generate`)

1. **Check for `PLANNING.md`**
   - If missing: stop and tell the user to run `/deck --plan` first.
   - If present: read it as the source of truth.

2. **Confirm approval**
   - If the user has not clearly approved the plan in this conversation, ask: _"The plan in PLANNING.md is ready. Proceed with generation?"_

3. **Read design references**
   - Load [references/design-system.md](references/design-system.md) for color palette, typography, animations.
   - Load [references/slide-patterns.md](references/slide-patterns.md) for HTML patterns matching each slide type.

4. **Generate slides**
   - Create `presentation/slides/` directory.
   - Generate each slide as `slide{N}.html` — standalone HTML, 1280x720 canvas.
   - Follow the slide-by-slide outline from `PLANNING.md` exactly.
   - Apply appropriate pattern from slide-patterns.md for each slide type (cover, agenda, content grid, comparison table, code, closing, etc.).
   - Incorporate content synthesized from `resources/` as specified in the plan.
   - Include animations (fade-in, staggered reveals) per the design system.

5. **Generate the viewer**
   - Copy `assets/viewer-template.html` to `presentation/index.html`.
   - Replace `{{DECK_TITLE}}` with the deck title from PLANNING.md.
   - Replace `{{SLIDES_ARRAY}}` with the actual slide paths: `"slides/slide1.html", "slides/slide2.html", ...`

6. **Optional deliverables** (generate if the plan requests them or the deck has 8+ slides)
   - `presentation/slides/PRESENTATION_SUMMARY.md` — deck overview, structure, design specs.
   - `presentation/slides/PRESENTATION_SCRIPT.md` — speaker notes per slide (2-4 sentences each).

7. **Open & summarize**
   - Open the presentation in the default browser:
     - macOS: `open presentation/index.html`
     - Linux: `xdg-open presentation/index.html`
     - Windows: `start presentation/index.html`
   - Then report what was generated: file count, total slides, and output location.

---

## Export Mode (`--export pptx`)

1. **Check for `presentation/slides/`**
   - If missing or empty: stop and tell the user to run `/deck --generate` first.
   - Verify that slide HTML files (`slide1.html`, `slide2.html`, ...) exist in the directory.

2. **Install dependencies** (first time only)
   - Check if `node_modules/` exists in the skill's `scripts/` directory.
   - If not, run: `cd <skill-path>/scripts && npm install`
   - The skill's `scripts/` directory is located relative to this SKILL.md file, under `scripts/`.

3. **Run the export script**
   - Execute: `node <skill-path>/scripts/export-pptx.mjs <presentation-dir> [deck-title] [--scale N]`
   - `<presentation-dir>` is the `presentation/` directory in the working directory.
   - `[deck-title]` is optional — extract it from `PLANNING.md` if available, otherwise default to `deck`.
   - `[--scale N]` is optional — pass through from the user's invocation if provided (default 3).
   - The script will:
     - Launch a headless browser to render each slide at 1280x720 (Nx resolution for crisp output, default 3x)
     - Capture each slide as a high-quality PNG screenshot
     - Assemble all screenshots into a PPTX file
     - Save the PPTX to `presentation/<deck-title>.pptx`
     - Clean up temporary image files automatically

4. **Report results**
   - Tell the user the PPTX file path and slide count.
   - If the export fails, show the error message and suggest troubleshooting steps:
     - Ensure Node.js >= 18 is installed
     - Ensure `presentation/slides/` contains valid slide HTML files
     - Try running `cd <skill-path>/scripts && npm install` manually if dependency installation failed

---

## Slide Quality Rules

- **One key point per slide** + up to 4 supporting bullets.
- **No text walls.** If a slide has more than ~60 words of body text, split it.
- **No overflow.** All content must fit within 1280×720 without clipping. For dense content (code blocks, file trees, tables), reduce font size or split across multiple slides. See content density guidelines in [references/design-system.md](references/design-system.md).
- **Every slide has a visual element** — icon set, grid layout, chart placeholder, diagram, color-blocked card, or image.
- **Consistent styling** — all slides share the same color palette, font stack, and animation approach.
- **Scannable** — use bold labels, short phrases, and structured layouts (grids, lists, cards).
- **Footer** — include page number on content slides.

---

## Output Structure

```
working-directory/
├── PLANNING.md                  # Created in --plan mode
├── resources/                   # User-provided reference materials
└── presentation/                # Created in --generate mode
    ├── index.html               # Viewer (from viewer-template.html)
    ├── <deck-title>.pptx        # Created in --export pptx mode
    └── slides/
        ├── slide1.html          # Individual slides
        ├── slide2.html
        ├── ...
        ├── slideN.html
        ├── images/              # If slides reference images
        ├── PRESENTATION_SUMMARY.md   # Optional
        └── PRESENTATION_SCRIPT.md    # Optional
```
