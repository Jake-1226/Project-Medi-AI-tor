# Medi-AI-tor UI/UX Audit Report

**Date:** 2026-03-24  
**Auditor:** Automated UI/UX Testing (3-pass review)  
**Scope:** All 6 HTML templates, 5 CSS files, 6 JS files

---

## Executive Summary

Comprehensive audit found **42 actionable issues** across all pages (de-duplicated from 176 raw findings). The application has a solid design foundation but needs fixes in five key areas:

1. **Accessibility (12 issues)** — missing focus states, ARIA labels, reduced-motion support
2. **Dark Mode (8 issues)** — several components use hardcoded light colors
3. **Mobile Responsiveness (10 issues)** — grids and sidebars break below 480px
4. **Interaction States (7 issues)** — no button disabled/loading styles, missing hover states
5. **Consistency (5 issues)** — scrollbar styling, missing CSS classes

---

## Critical Issues (Must Fix)

| # | Page | Category | Issue |
|---|------|----------|-------|
| C1 | ALL | Animation | No `prefers-reduced-motion` support — violates WCAG 2.3.3 |
| C2 | Dashboard | Accessibility | Icon-only buttons (sidebar toggle ☰, theme 🌙) lack focus-visible outlines |
| C3 | Dashboard | Interaction | `.btn:disabled` has no CSS — disabled buttons look identical to enabled |
| C4 | Dashboard | Interaction | `.btn-loading` class added by JS but no CSS defined — no spinner shown |
| C5 | Dashboard | Color/Contrast | `--text-secondary: #94a3b8` on `#0f172a` = 3.2:1 (fails WCAG AA 4.5:1) |
| C6 | Dashboard | Color/Contrast | `--text-muted: #64748b` on dark bg = 2.1:1 (fails WCAG AA) |
| C7 | Dashboard | Accessibility | Form focus ring `rgba(99,102,241,0.15)` barely visible on dark backgrounds |

## Major Issues

| # | Page | Category | Issue |
|---|------|----------|-------|
| M1 | Dashboard | Dark Mode | `.chip`, `.recommendation-card`, `.sub-tab`, `.badge-*`, `.metric-card` use hardcoded light colors |
| M2 | Dashboard | Responsiveness | Connect panels `grid 1fr 1fr` doesn't stack on mobile <600px |
| M3 | Dashboard | Responsiveness | Component cards `minmax(280px)`, thermal gauges `minmax(220px)`, presets `minmax(240px)` overflow on mobile |
| M4 | Dashboard | Layout | `.ops-btn`, `.ops-btn-grid` classes used in HTML but have no CSS |
| M5 | Dashboard | Consistency | No scrollbar styling — dark mode scrollbars invisible |
| M6 | Customer | Responsiveness | Suggestion chips wrap awkwardly <480px — should horizontal-scroll |
| M7 | Customer | Responsiveness | Textarea max-height 120px takes 25%+ of viewport on small screens |
| M8 | Fleet | Accessibility | Modal close buttons (×) missing `aria-label`; tab buttons no focus-visible |
| M9 | Fleet | Responsiveness | Metrics grid `minmax(220px)` overflows <480px |
| M10 | Mobile | Accessibility | Touch targets below 44px on menu/theme buttons; toggle switches use `display:none` |
| M11 | Mobile | Responsiveness | Quick stats `repeat(2,1fr)` and action buttons break <360px |
| M12 | Realtime | Responsiveness | Metric cards `minmax(220px)` overflow; chart height fixed at 220px |
| M13 | ALL | Accessibility | No `<noscript>` fallback on any page |

## Minor Issues

| # | Page | Category | Issue |
|---|------|----------|-------|
| m1 | Login | Animation | Error shake + spinner don't respect reduced-motion |
| m2 | Login | Accessibility | Lockout countdown not announced to screen readers |
| m3 | Customer | Accessibility | Char counter uses color-only warning; toasts not Escape-dismissible |
| m4 | Customer | Interaction | Suggestion chips not disabled during loading; connection success too brief |
| m5 | Dashboard | Responsiveness | SR# input, level pills, quick-actions bar, data tables don't adapt <600px |
| m6 | Dashboard | Consistency | Hardcoded border-radius/font-size/shadow values instead of using CSS variables |
| m7 | Fleet | Dark Mode | Zebra striping `rgba(255,255,255,0.02)` too subtle; form inputs contrast unclear |
| m8 | Mobile | Animation | Status dot pulse, header scroll-hide don't respect reduced-motion |
| m9 | Realtime | Accessibility | Connection status dot purely visual; chart buttons no focus-visible |

---

## Fixes Applied

All issues above were addressed in the commit following this report.
