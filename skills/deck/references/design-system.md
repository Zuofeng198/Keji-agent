# Deck Design System

Default visual system for generated decks. Users may override any of these in their prompt or PLANNING.md.

## Color Palette (Default: Claude.com Style)

| Role | Color | Usage |
|------|-------|-------|
| Background | `#F7F4EF` | Warm beige, slide background |
| Primary text | `#2B2A27` | Deep charcoal, titles and body |
| Secondary text | `#5D4E42` | Medium brown, subtitles and captions |
| Accent (primary) | `#E07A59` | Coral orange — borders, icons, key data |
| Accent (secondary) | `#9FD3B8` | Mint green — secondary highlights |
| Strong text | `#4A3F35` | Dark brown-black, bold emphasis |

**Rules**: No high-saturation neon colors. Keep palette warm and restrained.

## Typography

- **Headings**: `Inter`, weight 600-700, sizes 48-72px, letter-spacing -0.5 to -1px
- **Body**: `Inter`, weight 400-500, sizes 18-30px, line-height 1.5-1.7
- **Chinese fallback**: `PingFang SC`, `Microsoft YaHei`, `Hiragino Sans GB`
- **Code**: `Source Code Pro`, monospace
- **Import**: `@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');`

## Slide Dimensions

- **Canvas**: 1280px x 720px (16:9)
- **Padding**: 60-120px depending on slide type
- **Content area**: Keep text within safe margins (min 60px from edges)

## Animations

```css
/* Primary content fade-in */
@keyframes fadeInContent {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}

/* List items staggered reveal */
@keyframes slideInUp {
    from { opacity: 0; transform: translateY(30px); }
    to { opacity: 1; transform: translateY(0); }
}
```

- Use `animation-delay` increments of 0.1s for staggered items
- Duration: 0.5-1.2s, easing: `ease-out` or `ease-in-out`
- Decorative shapes: `scale(0.8)` to `scale(1)` over 2s

## Layout Patterns

- **Per slide**: 1 key information point + 2-4 supporting bullets maximum
- **Avoid**: Large blocks of text, walls of bullets, dense paragraphs
- **Visual elements**: At least 1 per slide (icon, chart, diagram, card, color block)
- **Footer**: Page number + section name, positioned bottom-left or bottom-right

## Content Density & Overflow Prevention

All content must fit within the 1280×720 canvas without overflow or clipping.

- **Code blocks / file trees**: Maximum ~15 lines at 15px font size, or ~18 lines at 13px. If content exceeds this, reduce font size (minimum 12px) or split across slides.
- **Dense technical slides**: Use smaller font sizes (13-14px for code, 16-18px for body) and tighter padding (50-60px) to fit more content. Always verify the content fits within 720px height minus footer space (~50px).
- **Bullet lists**: Maximum 6 items per slide. If more are needed, split into multiple slides or use a 2-column grid.
- **Tables**: Maximum 8-10 rows. Beyond that, split across slides or use a smaller font size (13-14px).
- **When in doubt, split**: It is always better to use two clear slides than one cramped slide.

## Links

- All links in slides should include `target="_blank" rel="noopener"` since slides are rendered inside iframes.
- Style links to match the accent color (`#E07A59`) with `text-decoration: none`.

## Decorative Elements

- Background accent shapes: radial gradients with low opacity (0.08-0.15)
- Card style: rounded corners (8-12px), subtle shadow `0 4px 12px rgba(0,0,0,0.05)`
- Borders: 1px solid with muted colors
- Bullet markers: Colored bars (12x28px with accent color) or large accent-colored dots
