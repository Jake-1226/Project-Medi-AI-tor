# Medi-AI-tor UI/UX Audit Report — Round 2

**Date:** 2026-03-24  
**Method:** Pixel-level code review of all 6 pages across 360px, 768px, 1440px breakpoints  
**Scope:** Only user-facing bugs that would break layouts, confuse users, or hide content

---

## Confirmed Bugs (25 issues)

### CRITICAL — App-breaking

| # | Page | Bug | Root Cause |
|---|------|-----|------------|
| 1 | Dashboard | **Light mode completely broken** — toggling to light leaves most UI dark because JS injects `--bg-primary`, `--card-bg` etc. but CSS reads `--bg-body`, `--bg-card` | Variable name mismatch in `app.js:4026-4042` vs `style.css:17-25` |
| 2 | Dashboard | Sidebar text invisible in light mode — sidebar bg is `#343a40` but links inherit light-mode `--text-secondary` (`#6c757d`) | Light theme overrides don't cover sidebar text |

### HIGH — Layout breaks on real devices

| # | Page | Bug | Root Cause |
|---|------|-----|------------|
| 3 | Mobile | 360px grid fix doesn't work — selectors `.quick-stats-grid` / `.action-buttons-grid` don't match HTML classes `.quick-stats` / `.action-buttons` | Typo in mobile.css:1120-1121 |
| 4 | Realtime | Mobile form fix doesn't work — selector `.connection-form` doesn't match HTML class `.connection-form-inline` | Typo in realtime.css:438 |
| 5 | Customer | Toast notifications overflow on 360px phones — `min-width: 260px` + `right: 16px` = wider than viewport | No mobile toast rules in customer.css |
| 6 | Customer | Char count overlaps hint text on mobile — `float: right` breaks layout in narrow viewports | Inline float style on charCount span in customer.html:160 |
| 7 | Fleet | Server table unreadable on 768px tablets — 9 columns crammed into 768px with no horizontal scroll | No table responsive wrapper in fleet.css |
| 8 | Fleet | Overview grid (`2fr 1fr 1fr`) doesn't stack on tablets — cards cramped at 200px each | No responsive breakpoint for fleet overview grid |
| 9 | Dashboard | Investigation feed bottom hidden behind floating chat button | No bottom padding in agent-feed for FAB clearance |
| 10 | Realtime | Input fields shrink to ~50px on 360px phones — no min-width constraint | No mobile breakpoint for `.input-sm` |

### MEDIUM — Visible contrast/state issues

| # | Page | Bug | Root Cause |
|---|------|-----|------------|
| 11 | Dashboard | Sub-tab active state barely visible in dark mode — `#0076CE` on dark bg | Needs brighter active color |
| 12 | Dashboard | Ops button grid cramped on 1024px — `minmax(180px)` too small | Needs responsive breakpoint |
| 13 | Dashboard | Quick action buttons show no visual change when disabled (disconnected) | `.qa-btn:disabled` not styled |
| 14 | Dashboard | Scrollbar thumb same color as track in dark mode — invisible | Thumb color too dark |
| 15 | Customer | Overview card badges overflow on mobile — no `flex-wrap` | `.ov-badges` needs `flex-wrap: wrap` |
| 16 | Fleet | Modal too wide on 768px tablets (78% viewport) | No tablet breakpoint for modal |
| 17 | Login | Error shake animation overflows on 360px | Translate values too large |
| 18 | Mobile | Navigation doesn't close on tap outside | Missing click-outside handler |

### LOW — Minor polish

| # | Page | Bug | Root Cause |
|---|------|-----|------------|
| 19 | Realtime | Charts too tall on 360px — 150px x 3 charts = lots of scrolling | No ultra-small breakpoint |
| 20 | Fleet | Dark mode zebra striping invisible (`rgba(255,255,255,0.02)`) | Opacity too low |
| 21 | Mobile | Reduced-motion uses `0.01ms` duration instead of `none` | Should be `animation: none` |
| 22 | Dashboard | Connect-field-row still 2-col on 600px mobile | Media query exists but inner grid not overridden |
| 23 | Dashboard | Placeholder text in SR# input too dark in dark mode | Needs lighter placeholder color |
| 24 | Fleet | Health circle inner bg `white` doesn't work on light bg | Needs light-mode override |
| 25 | Fleet | Escape key inconsistent with close button on modals | Different DOM operations |
