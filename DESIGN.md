# Design System: AI Image Generator
**Based on:** Void-Black Design Language (NetGlyph lineage)
**Target Framework:** CustomTkinter (Python)

## 1. Visual Theme & Atmosphere

The AI Image Generator adopts a **void-black creative studio aesthetic** — a dark, immersive canvas where the generated images are the star, not the UI chrome. The interface recedes into true black, letting vibrant AI-generated imagery pop against the void. Controls feel surgical and precise — sliders, toggles, and model selectors are tools in a darkroom, not widgets in a settings panel.

The atmosphere is **cinematic and focused**. The left panel is a control strip — dense but organized. The right panel is a gallery stage — spacious, image-forward, with generous breathing room. The UI communicates: "this is where art happens."

Accent color shifts from NetGlyph's coral-red to **electric violet** — a creative, generative energy that signals "AI at work" without the aggressive heat of red.

## 2. Color Palette & Roles

| Token | Color | Hex | Role |
|-------|-------|-----|------|
| `background` | Void Black | `#000000` | App background — true black |
| `surface` | Near Black | `#0a0a0a` | Panel fills, card backgrounds |
| `surface-elevated` | Charcoal | `#111111` | Elevated sections, hover states, parameter groups |
| `surface-input` | Deep Charcoal | `#151515` | Input fields, dropdown backgrounds |
| `border-subtle` | Ghost White | `rgba(255,255,255,0.08)` | Panel borders, dividers |
| `border-hover` | Soft White | `rgba(255,255,255,0.15)` | Hover state borders |
| `accent` | Electric Violet | `#8B5CF6` | Active controls, selected model, generate button glow, progress bar |
| `accent-hover` | Bright Violet | `#A78BFA` | Hover state on accent elements |
| `accent-glow` | Violet Glow | `rgba(139,92,246,0.25)` | Box shadow / highlight glow on active elements |
| `success` | Muted Emerald | `#4ADE80` | Generation complete, status: ready |
| `warning` | Amber | `#FBBF24` | NSFW filter warnings, cost indicators |
| `error` | Soft Red | `#F87171` | API errors, failed generations |
| `text-primary` | Pure White | `#FFFFFF` | Headings, labels, prompt text |
| `text-secondary` | Muted Gray | `#888888` | Descriptions, placeholders, parameter labels |
| `text-tertiary` | Dim Gray | `#555555` | Disabled text, inactive elements |
| `button-primary` | Electric Violet | `#8B5CF6` | "Generate" button — the main CTA |
| `button-secondary` | Dark Card | `#1a1a1a` | Secondary buttons (Browse, Clear, Save) |
| `button-border` | Ghost White | `rgba(255,255,255,0.10)` | Secondary button borders |
| `slider-track` | Near Black | `#1a1a1a` | Slider track background |
| `slider-fill` | Electric Violet | `#8B5CF6` | Slider filled portion |
| `slider-thumb` | Pure White | `#FFFFFF` | Slider handle |

**Critical rule:** Electric Violet (`#8B5CF6`) is reserved for: the Generate button, active/selected states, progress indicators, and slider fills. Everything else is grayscale on black. Gold (`#FFD700`) is eliminated — it belongs to the old theme.

## 3. Typography Rules

CustomTkinter uses system fonts. The design targets:

- **Headings:** CTkFont weight="bold", size=16, Pure White
- **Section labels:** CTkFont weight="bold", size=12, Muted Gray — uppercase optional for group headers
- **Body/parameters:** CTkFont size=13, Pure White
- **Secondary text:** CTkFont size=12, Muted Gray
- **Prompt input:** CTkFont family="Consolas" or monospace, size=13, Pure White on Deep Charcoal
- **Status bar:** CTkFont size=11, Muted Gray

## 4. Component Stylings

### CTk Color Mapping
```python
# Replace current constants
APP_BG_COLOR = "#000000"       # Was #181818 — now true void black
FRAME_BG_COLOR = "#0a0a0a"     # Was #232323 — now near black
SURFACE_ELEVATED = "#111111"   # For parameter groups, elevated panels
INPUT_BG_COLOR = "#151515"     # For entry fields, textboxes
TEXT_COLOR = "#FFFFFF"          # Unchanged
TEXT_SECONDARY = "#888888"     # For labels, hints
ACCENT_COLOR = "#8B5CF6"       # Was #FFD700 (gold) — now electric violet
ACCENT_HOVER = "#A78BFA"       # Lighter violet for hover
BUTTON_PRIMARY_FG = "#8B5CF6"  # Generate button fill
BUTTON_SECONDARY_FG = "#1a1a1a" # Other buttons
BUTTON_TEXT_COLOR = "#FFFFFF"  # Was #000000 — now white on violet
BORDER_COLOR = "#1a1a1a"       # Subtle borders
SUCCESS_COLOR = "#4ADE80"      # Status: ready/complete
WARNING_COLOR = "#FBBF24"      # Warnings
ERROR_COLOR = "#F87171"        # Errors
```

### Buttons
- **Generate (Primary CTA):** `fg_color="#8B5CF6"`, `hover_color="#A78BFA"`, `text_color="#FFFFFF"`, `corner_radius=8`, `height=40`. Full-width in its container. The only violet-filled element.
- **Secondary (Browse, Clear, Save):** `fg_color="#1a1a1a"`, `border_color="#333333"`, `border_width=1`, `hover_color="#252525"`, `text_color="#FFFFFF"`, `corner_radius=6`
- **Danger (Clear All, Stop):** `fg_color="#1a1a1a"`, `hover_color="#7F1D1D"`, `text_color="#F87171"`, `corner_radius=6`

### Frames / Panels
- **Left control panel:** `fg_color="#0a0a0a"`, `corner_radius=0` (flush edge), fixed width ~380px
- **Right gallery panel:** `fg_color="#000000"`, no border — the void is the background
- **Parameter groups:** `fg_color="#111111"`, `corner_radius=8`, `border_width=1`, `border_color="#1a1a1a"` — each group (Model, Size, Steps, etc.) is a distinct rounded card
- **Separator between panels:** 1px line, `#1a1a1a`

### Inputs / Forms
- **CTkEntry (text inputs):** `fg_color="#151515"`, `border_color="#1a1a1a"`, `border_width=1`, `text_color="#FFFFFF"`, `placeholder_text_color="#555555"`, `corner_radius=6`
- **CTkTextbox (prompt):** Same as entry but taller (100-150px), monospace font. The prompt box is the creative heart — give it visual weight with a subtle border glow on focus.
- **CTkComboBox (dropdowns):** `fg_color="#151515"`, `border_color="#1a1a1a"`, `button_color="#1a1a1a"`, `dropdown_fg_color="#111111"`, `corner_radius=6`
- **CTkSlider:** `fg_color="#1a1a1a"` (track), `progress_color="#8B5CF6"` (fill), `button_color="#FFFFFF"` (thumb), `button_hover_color="#A78BFA"`
- **CTkSwitch:** `fg_color="#1a1a1a"` (off), `progress_color="#8B5CF6"` (on), `button_color="#FFFFFF"`

### Image Display (Right Panel)
- Generated image displayed centered on void black background
- Thin 1px `#1a1a1a` border around image frame
- Image info (dimensions, seed, model) in `text_secondary` below
- Thumbnail strip at bottom: 64x64 squares, `corner_radius=4`, selected thumbnail gets violet border

### Progress Indicator
- **CTkProgressBar:** `fg_color="#1a1a1a"`, `progress_color="#8B5CF6"`, height=4px — thin, elegant
- Status text below in Muted Gray: "Generating... (step 14/30)"

### Status Bar (Bottom)
- Full-width bar, `fg_color="#0a0a0a"`, height=28px
- Left: service indicator dot (emerald=connected, red=error) + service name
- Center: model name + parameters summary
- Right: generation count, cost estimate

## 5. Layout Principles

### Two-Panel Layout
```
┌─────────────────────────┬──────────────────────────────────┐
│   CONTROL PANEL (380px) │       GALLERY / PREVIEW          │
│                         │                                  │
│  [Service Toggle]       │                                  │
│  [Model Selector]       │      ┌──────────────────┐       │
│  ┌─────────────────┐    │      │                  │       │
│  │ Prompt           │    │      │   Generated      │       │
│  │ (multiline)      │    │      │   Image          │       │
│  └─────────────────┘    │      │   (centered)     │       │
│  [Negative Prompt]      │      │                  │       │
│                         │      └──────────────────┘       │
│  ┌─ Parameters ───────┐ │                                  │
│  │ Steps    [slider]  │ │      [seed] [dims] [model]      │
│  │ Guidance [slider]  │ │                                  │
│  │ Size     [combo]   │ │  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐     │
│  │ Seed     [entry]   │ │  │  │ │  │ │  │ │  │ │  │     │
│  └────────────────────┘ │  └──┘ └──┘ └──┘ └──┘ └──┘     │
│                         │      [thumbnail strip]          │
│  [▓▓▓▓ GENERATE ▓▓▓▓]  │                                  │
│  [━━━━ progress ━━━━]  │                                  │
├─────────────────────────┴──────────────────────────────────┤
│  ● Connected │ flux-1.1-pro │ 30 steps │ 1024x1024 │ #3  │
└────────────────────────────────────────────────────────────┘
```

- **Left panel:** Scrollable if content exceeds window height. CTkScrollableFrame.
- **Right panel:** Image scales to fit, maintaining aspect ratio. Void black padding around image.
- **Minimum window:** 900x700. Resizable. Right panel grows with window width.
- **Spacing:** 12px padding inside panels. 16px between parameter groups. 8px between related controls.
- **Visual hierarchy:** Section headers in uppercase muted gray. Controls are white. Only the Generate button and active states use violet.
