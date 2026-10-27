import clsx from 'clsx'
import { Plus } from 'lucide-react'
import { useState } from 'react'

/** Toggle chips from a vocabulary, plus free-text additions. */
export function TagPicker({ options, value, onChange, tone = 'neutral' }: { options: string[]; value: string[]; onChange: (v: string[]) => void; tone?: 'neutral' | 'neg' }) {
  const [draft, setDraft] = useState('')
  const all = [...options, ...value.filter((v) => !options.includes(v))]
  const toggle = (t: string) => onChange(value.includes(t) ? value.filter((x) => x !== t) : [...value, t])
  const add = () => {
    const t = draft.trim()
    if (t && !value.includes(t)) onChange([...value, t])
    setDraft('')
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {all.map((t) => {
        const on = value.includes(t)
        return (
          <button
            type="button"
            key={t}
            aria-pressed={on}
            onClick={() => toggle(t)}
            className={clsx(
              'rounded-md border px-2 py-1 text-xs transition-colors',
              on
                ? tone === 'neg'
                  ? 'border-neg/50 bg-neg/15 text-neg'
                  : 'border-accent/50 bg-accent/15 text-accent'
                : 'border-border text-ink-2 hover:border-ink-2/40 hover:text-ink',
            )}
          >
            {t}
          </button>
        )
      })}
      <span className="inline-flex items-center rounded-md border border-dashed border-border">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          placeholder="Add…"
          aria-label="Add a tag"
          className="w-20 bg-transparent px-2 py-1 text-xs text-ink placeholder:text-muted focus:outline-none"
        />
        <button type="button" aria-label="Add tag" onClick={add} className="px-1.5 text-muted hover:text-ink">
          <Plus size={12} />
        </button>
      </span>
    </div>
  )
}
