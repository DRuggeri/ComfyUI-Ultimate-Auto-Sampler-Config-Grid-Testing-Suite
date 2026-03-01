# Builder UI Navigation, Layout & Styles Design

**Date:** 2026-03-01
**Status:** Approved

## Summary

Overhaul the Builder UI with a sticky top bar (session name + settings dropdown),
left sidebar with navigation icons and quick actions, uniform section headers with
accent color stripes, and improved dark mode colors for better readability.

## Requirements

1. **Sticky Top Bar:** Session name text input (far left), Settings button with
   dropdown (far right). Settings contains: Load Session, Load Config, Save Config
   (inline-expandable), Auto-Save toggle, Enable Distribution toggle, Refresh
   Models action, Label Mode toggle, Include None toggle, Include Default toggle.

2. **Left Sidebar:** ~40px wide icon column, sticky alongside top bar. Navigation
   icons scroll to sections (Global Prompts, Config Arrays, Distribution Settings,
   JSON Preview). Quick action icons (Add Config, Refresh Models) below divider.
   Active section highlighted via scroll spy.

3. **Remove Top Row:** The 3-section top row (Session Management, Config Management,
   Distribution) is eliminated. Controls move to top bar, settings dropdown, and
   distribution section.

4. **Distribution Section:** When enabled via Settings dropdown, appears as its own
   full-width section below Config Arrays (above Preview). Sidebar gets nav icon.

5. **Uniform Section Headers:** White/light text (16px bold) on subtle dark gradient
   bar with left accent color stripe. Consistent across all sections.

6. **Color/Contrast Fixes:** Brighter text colors, better button contrast, improved
   header visibility for dark mode.

## Layout

```
+------------------------------------------------------+
| TOP BAR (sticky, z-index: 100)                       |
| [Session Name input________]        [Settings gear]  |
+----+-------------------------------------------------+
| S  |  MAIN CONTENT (scrollable)                      |
| I  |                                                 |
| D  |  [Global Prompts section]                       |
| E  |  [Config Arrays section]                        |
| B  |  [Distribution Settings] (when enabled)         |
| A  |  [JSON Preview section]                         |
| R  |                                                 |
+----+-------------------------------------------------+
```

## Top Bar

- Height: ~40px, background: `#1a1a1a`, border-bottom: `1px solid #3a3a3a`
- Session name: text input, `flex: 1`, transparent bg, border on focus
- Settings button: `gear` icon, opens dropdown below on click

### Settings Dropdown

Dropdown opens below settings button, closes on click-outside. Items:

| Item | Type | Behavior |
|------|------|----------|
| Load Session | Expandable | Click expands inline searchable select |
| Load Config | Expandable | Click expands inline searchable select |
| Save Config | Expandable | Click expands config name input + save button |
| --- | Divider | |
| Auto-Save (2s) | Toggle | Checkbox, immediate effect |
| --- | Divider | |
| Enable Distribution | Toggle | Checkbox, shows/hides distribution section |
| --- | Divider | |
| Refresh Models | Action | Click triggers refresh, shows feedback |
| Label Mode | Toggle | Checkbox |
| Include None | Toggle | Checkbox |
| Include Default | Toggle | Checkbox |

## Sidebar

- Width: ~40px, background: `#1e1e1e`, border-right: `1px solid #333`
- Position: sticky left column, full height below top bar
- Icons: emoji in ~36px square buttons, tooltip on hover

### Icons (top to bottom)

| Icon | Label | Type | Action |
|------|-------|------|--------|
| 📝 | Global Prompts | Nav | Scroll to section |
| ⚙️ | Config Arrays | Nav | Scroll to section |
| 🌐 | Distribution | Nav | Scroll to section (only when enabled) |
| 📄 | JSON Preview | Nav | Scroll to section |
| --- | Divider | | |
| + | Add Config | Action | Adds new config array |
| 🔄 | Refresh | Action | Refresh models/LoRAs |

Active section highlighted via scroll spy (brighter background).

## Section Headers

Uniform style replacing varied `.cb-section-title`:

- Font: 16px bold, color: `#e0e0e0` (bright white-gray)
- Background: subtle gradient from accent color at 15% opacity to transparent
- Left border: 3px solid accent color
- Padding: 10px 12px
- Each section has a unique accent color

| Section | Accent Color | Emoji |
|---------|-------------|-------|
| Global Prompts | `#00cc55` (green) | 📝 |
| Config Arrays | `#0088ff` (blue) | ⚙️ |
| Distribution | `#ff8800` (orange) | 🌐 |
| JSON Preview | `#00cccc` (teal) | 📄 |

## Color/Contrast Improvements

| Element | Old | New |
|---------|-----|-----|
| `.cb-label` | `#aaa` | `#ccc` |
| `.cb-section-title` | `#0066cc` (14px) | `#e0e0e0` (16px) with accent stripe |
| `.cb-button` | `#4a4a4a` bg | `#4a4a4a` bg, `#e0e0e0` text |
| `.cb-button.primary` | `#0066cc` | `#0077dd` (slightly brighter) |
| `.cb-controls-bar` | `#252525` | `#2a2a2a` |
| `.cb-input, .cb-select` | `#1a1a1a` bg, `#4a4a4a` border | `#1a1a1a` bg, `#555` border |
| Info text | `#888` | `#999` |

## Files Changed

| File | Change |
|------|--------|
| `conf-builder-ui-components.js` | New CSS classes, `createTopBar()`, `createSidebar()`, `createSettingsDropdown()`, `createSectionHeader()`, color updates |
| `conf-builder-config-management.js` | `renderUI()` restructure, section ID attributes, remove top row rendering |
| `conf-builder-distribution.js` | New `renderDistributionSettingsSection()` for standalone full-width section |
