# Dark Mode Implementation Guidelines

**Last Updated**: 2025-10-05
**Status**: Active - All new components MUST follow these guidelines

---

## 🎨 Overview

This project uses **dark mode by default**. All UI components must support both light and dark themes using Tailwind's `dark:` prefix.

---

## ✅ Required Dark Mode Classes

### Form Inputs (Text, Number, Email, etc.)

```tsx
// ✅ CORRECT - Always use these classes for inputs
<input
  className="w-full px-3 py-2 border dark:border-gray-700 rounded-md
             text-gray-900 dark:text-gray-100
             bg-white dark:bg-gray-800"
/>
```

**Required Classes:**
- `dark:border-gray-700` - Border color in dark mode
- `text-gray-900 dark:text-gray-100` - Text color (dark in light mode, light in dark mode)
- `bg-white dark:bg-gray-800` - Background color

### Select Dropdowns

```tsx
// ✅ CORRECT
<select
  className="w-full px-3 py-2 border dark:border-gray-700 rounded-md
             text-gray-900 dark:text-gray-100
             bg-white dark:bg-gray-800"
>
  <option value="option1">Option 1</option>
  <option value="option2">Option 2</option>
</select>
```

**Same classes as inputs**

### Textarea

```tsx
// ✅ CORRECT
<textarea
  rows={4}
  className="w-full px-3 py-2 border dark:border-gray-700 rounded-md
             text-gray-900 dark:text-gray-100
             bg-white dark:bg-gray-800"
/>
```

**Same classes as inputs**

### Labels

```tsx
// ✅ CORRECT
<label className="block text-sm font-medium mb-2 text-gray-900 dark:text-gray-100">
  Field Name
</label>
```

### Helper Text

```tsx
// ✅ CORRECT
<p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
  This is helper text
</p>
```

### Error Messages

```tsx
// ✅ CORRECT
<p className="text-xs text-red-600 dark:text-red-400 mt-1">
  This field is required
</p>
```

---

## 🚀 Reusable Components

Use the pre-built dark mode-compatible components from `components/ui/form-input.tsx`:

### Input Component

```tsx
import { Input } from '@/components/ui/form-input'

// ✅ BEST PRACTICE - Use reusable component
<Input
  type="text"
  label="API Key"
  placeholder="Enter your API key"
  helperText="Your OpenAI API key"
  error={errors.apiKey}
/>
```

### TextArea Component

```tsx
import { TextArea } from '@/components/ui/form-input'

// ✅ BEST PRACTICE
<TextArea
  label="System Prompt"
  rows={4}
  helperText="Instructions for the agent"
/>
```

### Select Component

```tsx
import { Select } from '@/components/ui/form-input'

// ✅ BEST PRACTICE
<Select label="Provider">
  <option value="openai">OpenAI</option>
  <option value="anthropic">Anthropic</option>
  <option value="gemini">Google Gemini</option>
</Select>
```

**Benefits:**
- ✅ Automatic dark mode support
- ✅ Consistent styling across the app
- ✅ Built-in label, helper text, and error handling
- ✅ Less code to maintain

---

## ❌ Common Mistakes

### Missing Text Color

```tsx
// ❌ WRONG - Text invisible in dark mode
<input className="w-full px-3 py-2 border dark:border-gray-700 rounded-md" />
```

**Problem**: Text defaults to black, invisible on dark background

**Fix**: Add `text-gray-900 dark:text-gray-100`

### Missing Background Color

```tsx
// ❌ WRONG - Input has wrong background in dark mode
<input className="w-full px-3 py-2 border dark:border-gray-700 rounded-md
                 text-gray-900 dark:text-gray-100" />
```

**Problem**: Background defaults to white, looks wrong in dark mode

**Fix**: Add `bg-white dark:bg-gray-800`

### Incomplete Dark Mode Classes

```tsx
// ❌ WRONG - Missing dark mode border
<input className="w-full px-3 py-2 border rounded-md
                 text-gray-900 dark:text-gray-100
                 bg-white dark:bg-gray-800" />
```

**Problem**: Border stays light gray in dark mode, poor contrast

**Fix**: Add `dark:border-gray-700`

---

## 🎨 Other Common Elements

### Containers/Cards

```tsx
// ✅ CORRECT
<div className="border dark:border-gray-700 rounded-lg p-6
                bg-white dark:bg-gray-800">
  {/* Content */}
</div>
```

### Buttons

```tsx
// ✅ CORRECT - Primary button
<button className="px-4 py-2 bg-blue-600 text-white rounded-md
                   hover:bg-blue-700 dark:hover:bg-blue-500">
  Submit
</button>

// ✅ CORRECT - Secondary button
<button className="px-4 py-2 bg-gray-600 text-white rounded-md
                   hover:bg-gray-700 dark:hover:bg-gray-500">
  Cancel
</button>

// ✅ CORRECT - Outline button
<button className="px-4 py-2 border border-gray-300 dark:border-gray-600
                   text-gray-700 dark:text-gray-300 rounded-md
                   hover:bg-gray-100 dark:hover:bg-gray-700">
  Cancel
</button>
```

### Modals/Dialogs

```tsx
// ✅ CORRECT
<div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
  <div className="bg-white dark:bg-gray-800 rounded-lg max-w-2xl w-full">
    {/* Modal header */}
    <div className="bg-gray-100 dark:bg-gray-800 px-6 py-4 border-b dark:border-gray-700">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
        Modal Title
      </h3>
    </div>

    {/* Modal body */}
    <div className="p-6 text-gray-900 dark:text-gray-100">
      {/* Content */}
    </div>

    {/* Modal footer */}
    <div className="bg-gray-100 dark:bg-gray-800 px-6 py-4 border-t dark:border-gray-700">
      {/* Buttons */}
    </div>
  </div>
</div>
```

### Info/Warning Boxes

```tsx
// ✅ CORRECT - Info box
<div className="bg-blue-50 dark:bg-blue-900/20
                border border-blue-200 dark:border-blue-700
                rounded-lg p-4">
  <p className="text-blue-800 dark:text-blue-200">Info message</p>
</div>

// ✅ CORRECT - Warning box
<div className="bg-yellow-50 dark:bg-yellow-900/20
                border border-yellow-200 dark:border-yellow-700
                rounded-lg p-4">
  <p className="text-yellow-800 dark:text-yellow-200">Warning message</p>
</div>

// ✅ CORRECT - Error box
<div className="bg-red-50 dark:bg-red-900/20
                border border-red-200 dark:border-red-700
                rounded-lg p-4">
  <p className="text-red-800 dark:text-red-200">Error message</p>
</div>
```

---

## 🧪 Testing Dark Mode

### Manual Testing

1. Toggle dark mode in your browser/OS
2. Check all form inputs are readable
3. Verify borders are visible
4. Ensure buttons have proper contrast
5. Test modals and overlays

### Before Submitting PR

- [ ] All inputs have text color (`dark:text-gray-100`)
- [ ] All inputs have background color (`dark:bg-gray-800`)
- [ ] All borders have dark variant (`dark:border-gray-700`)
- [ ] All text is readable in both modes
- [ ] All containers have proper backgrounds
- [ ] All buttons have proper hover states

---

## 📚 Reference

### Standard Color Palette

| Element | Light Mode | Dark Mode |
|---------|-----------|-----------|
| Text (primary) | `text-gray-900` | `dark:text-gray-100` |
| Text (secondary) | `text-gray-600` | `dark:text-gray-400` |
| Background (primary) | `bg-white` | `dark:bg-gray-800` |
| Background (secondary) | `bg-gray-50` | `dark:bg-gray-900` |
| Border | `border-gray-300` | `dark:border-gray-700` |
| Input background | `bg-white` | `dark:bg-gray-800` |
| Input text | `text-gray-900` | `dark:text-gray-100` |

### Common Patterns

```tsx
// Text input pattern
const inputClasses = "w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"

// Container pattern
const containerClasses = "border dark:border-gray-700 rounded-lg p-6 bg-white dark:bg-gray-800"

// Modal pattern
const modalClasses = "bg-white dark:bg-gray-800 rounded-lg shadow-lg"

// Label pattern
const labelClasses = "block text-sm font-medium mb-2 text-gray-900 dark:text-gray-100"

// Helper text pattern
const helperClasses = "text-xs text-gray-500 dark:text-gray-400 mt-1"
```

---

## 🔧 Migration Guide

If you find a component missing dark mode:

1. **Identify the element type** (input, select, textarea, etc.)
2. **Add the required classes**:
   - Text color: `text-gray-900 dark:text-gray-100`
   - Background: `bg-white dark:bg-gray-800`
   - Border: `dark:border-gray-700`
3. **Test in both modes**
4. **Consider using reusable components** from `components/ui/form-input.tsx`

---

## 🎯 Quick Checklist for New Forms

When creating a new form or modal:

- [ ] Use `<Input />`, `<TextArea />`, or `<Select />` from `@/components/ui/form-input`
- [ ] If using raw HTML elements, apply all 3 required classes (text, bg, border)
- [ ] Add `dark:border-gray-700` to all `border` classes
- [ ] Add `dark:bg-gray-800` to all containers
- [ ] Add `dark:text-gray-100` to all text elements
- [ ] Test dark mode before committing
- [ ] Check modal headers/footers have proper backgrounds

---

## 📝 Examples from Codebase

### Good Example: Settings Page

```tsx
// From: frontend/app/settings/page.tsx
<input
  type="text"
  value={config.messages_db_path}
  onChange={(e) => setConfig({ ...config, messages_db_path: e.target.value })}
  className="w-full px-3 py-2 border dark:border-gray-700 rounded-md
             font-mono text-sm text-gray-900 dark:text-gray-100
             bg-white dark:bg-gray-800"
/>
```

### Fixed Example: Agent Skills Manager

```tsx
// From: frontend/components/AgentSkillsManager.tsx (FIXED)
const inputClasses = "w-full px-3 py-2 border dark:border-gray-700 rounded-md
                      text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"

<input
  type="text"
  value={value || schema.default || ''}
  onChange={(e) => setConfigData({ ...configData, [key]: e.target.value })}
  className={inputClasses}
/>
```

---

## 🚨 Important Notes

1. **Always test in dark mode** - Dark mode is the default, so it's critical
2. **Use reusable components** - Prefer `<Input />` over raw `<input />`
3. **Copy-paste the classes** - Use the patterns above to avoid mistakes
4. **Check modals carefully** - They have multiple layers that all need dark mode
5. **Watch for nested elements** - Labels, helper text, errors all need dark classes

---

**Remember**: Every form input needs **3 things** for dark mode:
1. ✅ Text color: `text-gray-900 dark:text-gray-100`
2. ✅ Background: `bg-white dark:bg-gray-800`
3. ✅ Border: `border dark:border-gray-700`

**When in doubt**, use the reusable components from `components/ui/form-input.tsx`!
