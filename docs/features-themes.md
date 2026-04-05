# Color Themes

Memoire supports 11 colour themes selectable from Settings. The theme is stored in `localStorage` and applied immediately without a page reload.

## Available Themes

| Theme | Description |
|---|---|
| Void | Near-black dark theme (default dark) |
| Abyss | Deep dark blue-black |
| Terminal | Dark with green accents |
| Noir | Dark with warm grey tones |
| Bloodmoon | Dark with red accents |
| Inferno | Dark with orange/amber accents |
| Ocean | Dark with blue tones |
| Parchment | Light, warm cream |

## Implementation

Themes are applied by setting a `data-theme` attribute on `<html>`. Each theme is defined as a set of CSS custom properties (variables) scoped to `[data-theme="..."]` selectors. All colours throughout the app reference these variables, so switching themes is a single attribute change.

Key variables:
- `--bg` — main background
- `--surface` — card/panel background
- `--border` — border colour
- `--text` — primary text
- `--muted` — secondary/muted text
- `--accent` — interactive accent colour
- `--hover` — hover state background
