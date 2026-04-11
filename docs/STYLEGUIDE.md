# UI Style Guide

## Purpose

This style guide translates the visual language of [`oliver-koeth/foodcoach`](https://github.com/oliver-koeth/foodcoach) into a reusable foundation for the meal planning UI in this project.

The source UI is:

- compact
- data-first
- card-based
- neutral in tone
- driven by semantic nutrition colors instead of decorative accents

This document keeps that character while adapting it from a nutrition dashboard into a broader meal planning product.

## Core Design Principles

### 1. Calm, utility-first interface

The UI should feel clear and trustworthy, not playful or sales-driven. Favor restrained surfaces, obvious hierarchy, and practical controls.

### 2. Data is the hero

Calories, macros, meal timing, and plan structure should be readable at a glance. Visual styling should support comprehension rather than compete with it.

### 3. Small number of strong patterns

Reuse the same shells repeatedly:

- sticky top bar
- section cards
- metric rows
- compact charts
- expandable detail blocks
- simple forms

Avoid introducing a new visual pattern for every screen.

### 4. Semantic color over brand color

Use neutrals for structure and semantic colors for meaning:

- green for on-target / low-carb / positive states
- amber for caution / medium-carb / approaching limit
- red for overrun / high-carb / error
- cyan for single-value quantitative bars

### 5. Dense, never cramped

The reference UI packs a lot of information into a small area, but spacing remains consistent. Preserve density without sacrificing scanability.

## Visual Character

### Overall mood

- clinical but friendly
- modern but not trendy
- efficient rather than expressive
- lightweight rather than heavy or premium-luxury

### Layout language

- white or near-white surfaces in light mode
- very dark slate surfaces in dark mode
- rounded cards
- thin borders
- small shadows
- compact sticky navigation
- generous use of grid layouts for panels and meal cards

### Typography

The reference app uses a system sans stack. Keep that direction for the meal planning app.

Recommended stack:

```css
font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
```

Typography rules:

- page titles: compact, semibold, not oversized
- section labels: uppercase, tracked, small
- body text: 14px to 16px equivalent
- metric labels and helper text: 12px to 13px equivalent
- tables and dense nutritional rows: 11px to 12px equivalent

Avoid oversized hero typography.

## Color System

These tokens are derived from the reference UI and should be standardized for implementation.

### Neutrals

```text
Background canvas:       slate-50
Card surface:            white
Muted surface:           slate-100
Border:                  slate-200
Primary text:            slate-800
Secondary text:          slate-600
Muted text:              slate-500

Dark canvas:             slate-950
Dark card:               slate-900
Dark muted surface:      slate-800
Dark border:             slate-800
Dark primary text:       slate-100
Dark secondary text:     slate-300
Dark muted text:         slate-400
```

### Semantic colors

```text
Success / target met:    emerald-500 to emerald-700
Caution / medium state:  amber-500 to amber-700
Critical / overrun:      red-500 to red-700
Quant bars / carbs:      cyan-500
```

### Usage rules

- Use neutrals for structure, not blue or purple brand washes.
- Keep semantic fills saturated enough to read inside small bars and pills.
- Use tinted backgrounds for badges and alerts, not full-screen color blocks.
- Do not use multiple accent colors on the same component unless they carry distinct meaning.

## Spacing, Radius, and Elevation

### Spacing scale

Use a tight, consistent scale:

- 4px for micro spacing
- 8px for control padding and chip spacing
- 12px for dense card gaps
- 16px for standard card padding
- 24px for section separation

### Border radius

- cards: 12px
- controls: 8px
- pills: full or highly rounded
- tables/details: 8px to 10px containers inside cards

### Elevation

- default cards: subtle shadow only
- sticky header: mostly border + translucent background + blur
- avoid deep shadows

The UI should feel layered through borders and surfaces, not dramatic elevation.

## App Shell

### Header

Keep the top bar sticky and compact, following the source app.

Include:

- product title
- current context or selected day
- primary quick actions
- theme toggle
- navigation links

Header behavior:

- sticky at top
- translucent surface with backdrop blur
- thin bottom border
- wraps cleanly on smaller screens

### Main content width

Use a centered content column with a generous max width.

Recommended:

- app shell max width: 1280px
- settings/forms width: 768px to 896px

### Navigation

Navigation should remain plain-text or lightly pill-based. The reference UI uses simple links with underline/weight for active state; that restraint should remain.

## Component System

### 1. Section Card

The section card is the primary surface.

Use for:

- daily summaries
- meal plan summaries
- training fuel guidance
- settings blocks
- shopping and prep summaries

Specs:

- rounded card
- light border
- white/dark-slate background
- 16px padding
- subtle shadow
- optional small uppercase section title

Multi-form pages (for example Set User) must use one parent stack wrapper around sibling form cards.
Do not place multiple sibling forms/cards without a shared spacing container.

Required defaults for multi-form stacks:

- outer stack gap: 16px minimum
- preserve breathing room around the stack inside its parent card
- normalize form/card margins to `0` and rely on stack gap for rhythm

### 2. Metric Comparison Bar

This is the key data component from FoodCoach and should remain central.

Use for:

- consumed vs target calories
- protein vs goal
- carbs vs meal target
- fiber or hydration progress

Structure:

- top row with label and optional status
- compact horizontal bar
- bottom row with consumed and goal values

Color behavior:

- overrun logic for calories
- target-band logic for protein/fiber
- single cyan fill for absolute bars such as carbs scale

### 3. Meal Card

Meal cards should be directly inspired by the reference UI.

Required anatomy:

- meal name
- carb strategy badge
- calories progress
- carbs progress
- optional protein/fat summary
- expandable meal details

Badge rules:

- `LCARB` -> green
- `MCARB` -> amber
- `HCARB` -> red
- fallback / unplanned -> neutral gray

Meal card behavior:

- collapsed by default
- expandable details for foods, notes, or prep instructions
- fixed meal ordering across the app

Canonical meal order:

1. Breakfast
2. Morning Snack
3. Lunch
4. Afternoon Snack
5. Dinner
6. Evening Snack
7. Training

### 4. Forms

Forms should stay plain and highly legible.

Rules:

- labels above fields
- helper labels in smaller muted text
- rounded bordered inputs
- avoid floating labels
- group related controls into 2-column grids on desktop
- primary action filled, secondary action outlined

Recommended buttons:

- primary: dark filled button in light mode, light filled button in dark mode
- secondary: bordered neutral button
- destructive: red text/border only when truly destructive

### 5. Alerts and Empty States

The reference UI uses inline messaging instead of dramatic empty-state illustrations. Keep that approach.

Patterns:

- errors: soft red panel with concise copy and recovery action
- loading: neutral bordered block
- empty state: one short sentence in a card or bordered box

Avoid mascot illustrations or marketing-style empty screens.

### 6. Tables and Detail Blocks

Use compact tables for food-level detail.

Rules:

- fixed headers
- small text
- numeric values right-aligned
- rows separated by subtle borders
- wrap the table in an overflow container on mobile

If there is no detailed log, replace table content with a text block for suggestions or prep notes.

## Content Hierarchy

Adopt the same hierarchy visible in the reference app:

1. app context
2. high-level daily summary
3. per-meal breakdown
4. expandable detailed records

For this project, map that hierarchy to:

1. selected plan day
2. daily calorie and macro targets
3. meal-by-meal plan cards
4. ingredient, recipe, or note-level details

## Screen Blueprints For Meal Planning

### Dashboard / Today View

Should feel like FoodCoach with meal-planning intent.

Recommended sections:

- top summary card for total kcal, protein, carbs, fat
- meal card grid in canonical order
- training meal card only when relevant
- secondary insights block for tomorrow’s training impact

### Plan Builder

Use the same card system, but with more editing affordances.

Recommended layout:

- left: editable meal list or meal card stack
- right: sticky summary panel with totals and validation warnings

Even in editing mode, avoid heavy drag-and-drop visuals unless necessary.

### Meal Detail

A meal detail screen should be an enlarged version of the meal card pattern:

- meal title and carb strategy badge
- macro targets and actual values
- food/ingredient table
- notes or suggestions area
- optional prep guidance

### Settings

Keep settings visually close to the source app:

- centered narrow form
- grouped fields
- low visual noise
- clear testing/validation actions

## Responsiveness

Preserve the reference app’s pragmatic responsiveness.

Recommended behavior:

- mobile: single-column stack
- tablet: 2-column meal grid
- desktop: 3-column meal grid where space allows
- sticky header remains usable when wrapping
- controls must remain tap-friendly without becoming oversized

Priority on small screens:

- preserve meal ordering
- keep summary metrics visible near the top
- allow horizontal overflow for tables, never for main layout

## Dark Mode

Dark mode should be supported exactly as a first-class theme, not as an afterthought.

Dark mode principles:

- retain the same hierarchy and spacing
- use dark surfaces, not inverted bright accents
- preserve semantic colors for badges and bars
- ensure borders remain visible on dark cards

Do not redesign components between themes. Only swap tokens.

## Motion and Interaction

Motion should be minimal.

Use animation for:

- expanding meal details
- progress bar width changes
- theme transitions if already supported by framework

Avoid:

- large entrance animations
- parallax
- animated backgrounds
- bouncing counters

## Voice and Copy

Copy should be plain, short, and operational.

Examples:

- good: `No data available`
- good: `Open Settings`
- good: `Training meal inserted before lunch`
- avoid: `Let’s optimize your nutrition journey`

The product voice should sound like a practical coach or tool, not a wellness brand.

## Implementation Tokens

These tokens are a strong default for a first UI implementation.

```css
:root {
  --bg: #f8fafc;
  --surface: #ffffff;
  --surface-muted: #f1f5f9;
  --border: #e2e8f0;
  --text: #1e293b;
  --text-secondary: #475569;
  --text-muted: #64748b;

  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --info: #06b6d4;

  --radius-card: 12px;
  --radius-control: 8px;
  --shadow-card: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.dark {
  --bg: #020617;
  --surface: #0f172a;
  --surface-muted: #1e293b;
  --border: #1e293b;
  --text: #f8fafc;
  --text-secondary: #cbd5e1;
  --text-muted: #94a3b8;
}
```

## Tailwind Mapping

If the UI is implemented with Tailwind, these utility choices stay close to the source app:

- page background: `bg-slate-50 dark:bg-slate-950`
- card: `rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900`
- section title: `text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-200`
- body text: `text-sm text-slate-700 dark:text-slate-200`
- helper text: `text-xs text-slate-600 dark:text-slate-300`
- table header: `bg-slate-100 dark:bg-slate-800`
- primary button: `bg-slate-900 text-white dark:bg-slate-200 dark:text-slate-900`

## What To Keep From FoodCoach

- sticky operational header
- compact data cards
- nutrition-specific semantic colors
- simple progress bars
- expandable detail sections
- low-noise settings experience
- fixed meal ordering
- light and dark parity

## What To Evolve For This Project

- add a stronger planning workflow, not just tracking
- support meal plan editing and confirmation states
- show generated recommendations and rationale in card-based summaries
- allow richer meal detail content such as ingredients, swaps, and prep notes
- add validation and warning patterns for impossible or inconsistent plans

## Implemented Visual Baseline (Current UI Shell)

This section captures the concrete visual tokens and component-level rules currently implemented in `src/mealplan/web/ui_server.py`. Treat these as required defaults unless intentionally redesigned.

### Theme and font tokens

```css
/* Base type stack */
font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;

/* Light */
--canvas: #f8fafc;
--surface: #ffffff;
--surface-muted: #f1f5f9;
--border: #e2e8f0;
--text: #1e293b;
--text-muted: #475569;
--text-subtle: #64748b;
--accent: #f59e0b;
--accent-hover: #fbbf24;
--accent-soft: rgba(245, 158, 11, 0.16);
--accent-strong: rgba(245, 158, 11, 0.35);

/* Dark */
--canvas: #020617;
--surface: #0f172a;
--surface-muted: #1e293b;
--border: #1f2937;
--text: #e2e8f0;
--text-muted: #cbd5e1;
--text-subtle: #94a3b8;
```

### Calendar cards and bars

- Day summary totals cards use a unified orange style:
  - border: `rgba(217, 119, 6, 0.45)`
  - background gradient: `rgba(217, 119, 6, 0.24)` -> `rgba(120, 53, 15, 0.2)`
  - equal card width target on desktop (`~176px`), wrapping between cards.
- Totals rows are single-line and non-bold for numeric values and units:
  - format: `Planned: 3863 kcal`, `Actual: 2828 kcal`
  - values and units are regular weight.
- Actual-value threshold colors (used in meal rows and totals actual values):
  - in-band (`80%..120%`): `#16a34a` (dark theme: `#86efac`)
  - out-of-band (`<80%` or `>120%`): `#dc2626` (dark theme: `#fca5a5`)
- Day progress bars:
  - planned bar fill is white (`#ffffff`, dark: `#f8fafc`)
  - actual bar fill uses the same threshold colors as actual-value text
  - progress section order: Day Plan totals -> Day Progress heading/bars -> Meal Plans.

### Calendar headings and layout hierarchy

- Root route defaults to Calendar view.
- Calendar result hierarchy:
  1. `Day Plan`
  2. orange totals cards
  3. `Day Progress` + 2 bars (planned/actual)
  4. `Meal Plans` + meal cards
- Meal ordering in Calendar cards: `training` first, then canonical meals.

### Log search date interaction

- Log search date filter starts cleared/inactive by default.
- First activation (focus/click) initializes the field to today.
- Clear button (`X`) restores inactive/empty state.

## What To Avoid

- glossy wellness branding
- oversized hero banners
- decorative gradients as primary identity
- too many accent colors
- deep shadows and glassmorphism-heavy panels
- dense forms without grouping
- charts that are more complex than the decision being made

## Definition of Done For Future UI Work

A new meal planning screen fits this style guide when it:

- uses the neutral card-based shell
- preserves compact information density
- relies on semantic nutrition colors
- keeps meal information scannable in canonical order
- works in light and dark mode
- favors simple bars, tables, and text over elaborate data viz
- feels clearly descended from FoodCoach, but adapted for planning rather than only tracking
