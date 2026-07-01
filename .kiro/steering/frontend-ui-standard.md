---
inclusion: auto
---

# Frontend UI Standard — Sakai + PrimeReact + Emcure Theme

All frontend UI MUST follow the Sakai template layout pattern with PrimeReact components and the Emcure brand color scheme.

## Design Reference

#[[file:frontend/src/assets/design/EMCURE_THEME_REFERENCE.md]]

---

## Component Library

- **PrimeReact** is the ONLY component library. Do NOT use Material UI, Ant Design, Chakra, or custom components.
- Use PrimeReact components: DataTable, Dialog, Button, InputText, Dropdown, MultiSelect, Tree, Tag, Toast, Toolbar, Avatar, Badge, Menu, InputSwitch, Password, InputNumber, InputTextarea, Calendar.
- Use **PrimeFlex** for layout utilities (flex, grid, spacing, responsive).
- Use **PrimeIcons** for all icons (`pi pi-*`).

---

## Layout Structure (Sakai-style)

```
┌────────────────────────────────────────────────────────────────┐
│ Sidebar (220px / 60px collapsed)  │  Content Area              │
│                                   │                            │
│ ┌─── Logo ──────────────────────┐ │ ┌─── Topbar (48px) ─────┐ │
│ │ EMCURE          [◀]           │ │ │ 🏠 / Page    🔔 👤    │ │
│ └───────────────────────────────┘ │ └────────────────────────┘ │
│                                   │                            │
│ ┌─── Nav ───────────────────────┐ │ ┌─── Page Content ──────┐ │
│ │ MAIN                          │ │ │                        │ │
│ │   Dashboard                   │ │ │  surface-card p-3      │ │
│ │   Orders                      │ │ │  border-round shadow-1 │ │
│ │ MANAGEMENT                    │ │ │                        │ │
│ │   Users                       │ │ │  DataTable / Forms     │ │
│ │   Roles                       │ │ │                        │ │
│ └───────────────────────────────┘ │ └────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

---

## Color Scheme (Emcure Brand — NEVER change these)

| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary` | #ED1C24 | Primary buttons, active states, links |
| `--color-primary-hover` | #C8141B | Button hover |
| `--color-primary-50` | #FFF0F0 | Active sidebar item background |
| `--color-success` | #17C765 | Save, approved, active tags |
| `--color-warning` | #FFA21E | Pending, caution |
| `--color-error` | #EF4444 | Delete, rejected, blocked |
| `--color-info` | #3B82F6 | Info, draft, system roles |

---

## Compact Density Rules

- Base font: 13px
- DataTable header: 0.6rem padding, uppercase, 0.75rem font
- DataTable body: 0.5rem padding, 0.813rem font
- Buttons: 0.5rem 0.85rem padding
- Tags: 0.2rem 0.5rem padding, 0.7rem font
- Dialogs: compact header/footer padding
- Rounded icon buttons: 1.75rem × 1.75rem

---

## Page Template

Every page MUST follow this structure:

```tsx
export const MyPage = () => {
  return (
    <div className="p-3">
      {/* Header */}
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Page Title</h2>
        <p className="text-600 mt-1 mb-0">Page description</p>
      </div>

      {/* Content Card */}
      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Item" icon="pi pi-plus" />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined />
          </div>
        )} />

        <DataTable value={data} stripedRows paginator rows={10}>
          {/* columns */}
        </DataTable>
      </div>

      {/* Dialogs */}
      <Dialog ... />
    </div>
  );
};
```

---

## DataTable Standards

- Always use: `stripedRows`, `paginator`, `rows={10}`
- Row actions: rounded outlined icon buttons (1.75rem size)
- Status columns: use `<Tag>` with severity mapping
- Date columns: format as `dd-MM-yyyy hh:mm:ss AM/PM`
- Enable `filter` and `filterDisplay="row"` for searchable tables
- Use `emptyMessage` prop

---

## Dialog Standards

- Width: 450px (forms), 550px (trees), 650px (details), 700px (complex forms)
- Modal: always `modal`
- Footer: Cancel (secondary text) + Action (primary)
- Form layout: `flex flex-column gap-4 pt-3`

---

## Button Variants

| Use Case | Component |
|----------|-----------|
| Primary CTA | `<Button label="Create" icon="pi pi-plus" />` |
| Secondary | `<Button label="Cancel" severity="secondary" outlined />` |
| Danger | `<Button severity="danger" />` |
| Row action (view) | `<Button icon="pi pi-eye" rounded outlined severity="secondary" size="small" />` |
| Row action (edit) | `<Button icon="pi pi-pencil" rounded outlined severity="info" size="small" />` |
| Row action (delete) | `<Button icon="pi pi-trash" rounded outlined severity="danger" size="small" />` |

---

## Tag/Badge Severity Mapping

| Status | Severity |
|--------|----------|
| Active, Approved, Success | `success` |
| Inactive, Rejected, Blocked | `danger` |
| Pending, In Progress | `warning` |
| Draft, Info, System | `info` |

---

## Responsive Rules

- Sidebar hidden below 768px (use `hidden md:flex`)
- Font scales down at 1440px (12.5px) and 1280px (12px)
- DataTable uses `tableStyle={{ minWidth: '0' }}` to prevent horizontal scroll

---

## NEVER DO

- ❌ Use inline styles for colors — use CSS variables
- ❌ Use custom CSS classes when PrimeFlex utilities exist
- ❌ Use Material Design icons — use PrimeIcons only
- ❌ Change the Emcure brand colors
- ❌ Use fixed pixel widths on content area
- ❌ Use any component library other than PrimeReact
- ❌ Use localStorage for tokens (memory only)
- ❌ Create custom button/input components — use PrimeReact's
