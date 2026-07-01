# Emcure Theme v2.0 — Design Reference

## Color Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary` | #ED1C24 | Primary CTA, active states |
| `--color-primary-hover` | #C8141B | Primary hover |
| `--color-primary-50` | #FFF0F0 | Primary light background |
| `--color-primary-100` | #FFD6D8 | Primary subtle |
| `--color-success` | #17C765 | Save, approved, positive |
| `--color-success-hover` | #0DA050 | Success hover |
| `--color-warning` | #FFA21E | Pending, caution |
| `--color-error` | #EF4444 | Delete, rejected, error |
| `--color-info` | #3B82F6 | Info, draft |
| `--color-text-primary` | #212529 | Main text |
| `--color-text-secondary` | #6C757D | Secondary text |
| `--color-text-muted` | #ADB5BD | Muted/label text |
| `--color-surface` | #FFFFFF | Card/panel background |
| `--color-surface-ground` | #F8F9FA | Page background |
| `--color-surface-border` | #E9ECEF | Borders |
| `--color-surface-hover` | #F1F3F5 | Hover states |

## Gradient Buttons

| Variant | Gradient | Usage |
|---------|----------|-------|
| Primary | #ff4d54 → #b00e14 | Main CTA |
| Save | #34d874 → #0da050 | Form submission |
| Delete | #ff6b6b → #b91c1c | Destructive |
| Secondary | #f8f9fa → #e9ecef | Alternative action |
| Cancel | Ghost/transparent | Dismiss |

## Spacing Tokens

| Token | Value |
|-------|-------|
| --space-1 | 4px |
| --space-2 | 8px |
| --space-3 | 12px |
| --space-4 | 16px |
| --space-5 | 20px |
| --space-6 | 24px |
| --space-8 | 32px |

## Radius Tokens

| Token | Value |
|-------|-------|
| --radius-sm | 4px |
| --radius-md | 8px |
| --radius-lg | 12px |
| --radius-full | 9999px |

## Badge Styles

- **Flat**: Approved (green bg), In Progress (blue bg), Closed (gray), Requested (orange), Draft (light)
- **Gradient**: Completed, Overdue, Waiting, Assigned, Referred

## Data Grid

- Header: uppercase, smaller font, surface-ground background
- Rows: compact padding, striped, hover highlight
- Actions: inline gradient buttons (Save, Delete)
- Pagination: bottom-right with page numbers
- Search: inline toolbar with icons

## Layout (Sakai-like)

- **Sidebar**: 220px, collapsible, section headers (Main, Management, Services)
- **Topbar**: 48px, logo left, notifications + avatar right
- **Content**: Full remaining width, p-3 padding
- **Cards**: border-round, shadow-1, surface-card
