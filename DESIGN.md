```markdown
# Design System Specification: High-End Fintech Analysis

## 1. Overview & Creative North Star
### Creative North Star: "The Obsidian Lens"
This design system rejects the cluttered, "dashboard-heavy" aesthetics of traditional trading platforms in favor of a sophisticated, editorial experience. It is designed to feel like a high-end physical tool—think of a precision-engineered watch or a dark-room glass desk. 

By utilizing **intentional asymmetry** and **tonal depth**, we move away from "boxed-in" layouts. The goal is to provide a sense of calm authority. We break the template look by prioritizing breathing room (generous white space) and using high-contrast typography scales that guide the eye through complex market data without visual fatigue.

---

## 2. Colors & Surface Philosophy
The palette is rooted in deep, atmospheric navies, avoiding the "flatness" of pure black.

### The "No-Line" Rule
**Explicit Instruction:** 1px solid borders for sectioning are strictly prohibited. 
Structural boundaries must be defined solely through background color shifts or tonal transitions. Use `surface-container-low` against a `surface` background to denote a change in context. Lines create visual noise; tonal shifts create focus.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers. Use the surface-container tiers to create depth:
*   **Base Layer:** `surface` (#0b1326) – The canvas.
*   **Subtle Recess:** `surface-container-low` (#131b2e) – For large sidebar areas or background groupings.
*   **Primary Interactive Surface:** `surface-container` (#171f33) – The default state for cards and main UI blocks.
*   **Elevated Focus:** `surface-container-high` (#222a3d) – For active states or nested elements within a card.

### The "Glass & Gradient" Rule
To achieve a premium "Signature" feel:
*   **Glassmorphism:** Use `surface-variant` with a `backdrop-filter: blur(12px)` and 40-60% opacity for floating modals, tooltips, or top-level navigation headers.
*   **Mesh Gradients:** For the main analysis dashboard, implement subtle mesh gradients transitioning from `primary` (#d2f2ff) to `on_secondary_container` (#b3b1ff) at very low opacities (5-8%) to provide visual "soul" to the dark background.

---

## 3. Typography
The system uses a dual-font approach to balance editorial authority with technical precision.

*   **Display & Headlines (Manrope):** Used for high-level data summaries and page titles. The wide aperture of Manrope provides a modern, "Global Bank" feel.
*   **Body & UI (Inter):** The workhorse for readability. Used for all form labels, secondary data, and general UI.
*   **Monospace (JetBrains Mono / Roboto Mono):** Mandatory for API keys, logs, and numerical stock data to ensure character alignment.

### Key Scales:
*   **Display-LG (3.5rem):** High-impact market movements.
*   **Title-MD (1.125rem):** Standard card headings.
*   **Label-SM (0.6875rem):** Metadata and micro-copy, always in `on_surface_variant`.

---

## 4. Elevation & Depth
### The Layering Principle
Depth is achieved by "stacking" tones. Place a `surface-container-lowest` card on a `surface-container-low` section to create a soft, natural "recessed" look. 

### Ambient Shadows
Avoid black shadows. Use a tinted version of `on-surface` (#dae2fd) at 4% opacity with a blur radius of 30px-40px. This mimics the way light interacts with dark glass rather than paper.

### The "Ghost Border" Fallback
If accessibility requirements demand a border (e.g., high-contrast mode), use `outline-variant` (#3b494c) at **20% opacity**. Never use 100% opaque lines.

---

## 5. Components

### Buttons
*   **Primary:** Background `primary` (#d2f2ff), Text `on_primary` (#003543). Use a subtle `0.5rem` (lg) corner radius. No shadow.
*   **Secondary:** Glassmorphic background (Surface-variant + blur) with `primary` text.
*   **Tertiary:** No background. `primary` text with an underline appearing only on hover.

### Form Fields (API & SMTP)
Fields should feel integrated into the background.
*   **Input Area:** `surface-container-highest` background. No border.
*   **Focus State:** A 2px bottom-only glow in `tertiary` (#acfaff).
*   **Monospace Content:** API keys and SMTP strings must use the Monospace font at `body-md` scale.

### Status Indicators
*   **Idle:** `outline` (grey) dot.
*   **Running:** Pulsing `primary` (cyan) dot with a 4px blur glow.
*   **Success:** `tertiary` (mint/cyan) text and icon.
*   **Error:** `error` (#ffb4ab) text; background of container shifts to `error_container` (#93000a) at 10% opacity.

### Markdown Rendering Area
For long-form analysis, use a "Paper on Glass" approach.
*   **Background:** `surface-container-lowest`.
*   **Typography:** Increase line-height to 1.6. Use `on_surface` for headers and `on_surface_variant` for body text to create a soft, readable contrast.
*   **Code Blocks:** Background `surface-container-highest`, border-radius `md`.

### Cards & Lists
**Constraint:** Do not use divider lines. 
Separate list items using `spacing-4` (1rem) vertical gaps. For table-style data, use alternating row backgrounds (`surface-container-low` vs `surface-container-lowest`) instead of borders.

---

## 6. Do’s and Don’ts

### Do:
*   **Do** use `primary_fixed_dim` for data highlights to ensure readability against dark backgrounds.
*   **Do** lean into the Spacing Scale (2.5rem - 4rem) for page margins to convey "High-End Editorial" luxury.
*   **Do** use `backdrop-blur` on any element that sits "above" the main content.

### Don’t:
*   **Don't** use pure white (#ffffff) for text; it causes "halo" eye strain on dark backgrounds. Use `on_surface` (#dae2fd).
*   **Don't** use standard 1px borders to separate the sidebar from the main content. Use a background shift from `surface` to `surface-container-low`.
*   **Don't** use high-saturation "Danger Red" for errors; use the provided `error` (#ffb4ab) which is optimized for dark-mode harmony.

### Signature Interaction
When a user hovers over a stock data card, the background should transition from `surface-container` to a very subtle `primary_container` (#7bddff) gradient at 5% opacity, creating a "shimmer" effect that feels like polished glass catching the light.