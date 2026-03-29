import React from 'react'

function XIcon() {
  return (
    <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

/**
 * FilterChips — shows active filters as removable chips.
 *
 * filters: Array<{ id: string, name: string, value: string }>
 * onRemove(id): called when a chip's X is clicked
 * onClearAll(): called when "Clear all" is clicked
 */
export default function FilterChips({ filters = [], onRemove, onClearAll }) {
  if (!filters.length) return null

  return (
    <div className="px-3 py-2 rounded-xl bg-gray-100 dark:bg-gray-800">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap">
          Filters:
        </span>
        {filters.map((f) => (
          <span
            key={f.id}
            className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-600"
          >
            <span className="truncate max-w-[140px]">
              {f.name}: <span className="text-amber-600 dark:text-amber-400">{f.value}</span>
            </span>
            <button
              type="button"
              onClick={() => onRemove?.(f.id)}
              className="ml-0.5 flex-shrink-0 rounded-full p-0.5 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            >
              <XIcon />
              <span className="sr-only">Remove {f.name}</span>
            </button>
          </span>
        ))}
        <button
          type="button"
          onClick={onClearAll}
          className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 underline whitespace-nowrap transition-colors"
        >
          Clear all
        </button>
      </div>
    </div>
  )
}
