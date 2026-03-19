import React from 'react'

function getPageNumbers(page, totalPages) {
  const pages = new Set()
  pages.add(1)
  pages.add(totalPages)
  for (let i = Math.max(1, page - 2); i <= Math.min(totalPages, page + 2); i++) {
    pages.add(i)
  }
  const sorted = Array.from(pages).sort((a, b) => a - b)

  const result = []
  let prev = null
  for (const p of sorted) {
    if (prev !== null && p - prev > 1) {
      result.push('...')
    }
    result.push(p)
    prev = p
  }
  return result
}

export default function Pagination({ page, totalPages, onPageChange, dark = false }) {
  if (totalPages <= 1) return null

  const pages = getPageNumbers(page, totalPages)

  const btnBase = 'px-3 py-1.5 text-sm rounded-lg border transition-all duration-150'

  const btnActive = dark
    ? 'bg-red-500 border-red-500 text-white font-semibold'
    : 'bg-purple-600 border-purple-600 text-white font-semibold'

  const btnInactive = dark
    ? 'bg-[#1a1a1a] border-[#333] text-gray-300 hover:bg-[#2a2a2a] hover:text-white'
    : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'

  const btnDisabled = dark
    ? 'bg-[#1a1a1a] border-[#333] text-gray-600 cursor-not-allowed'
    : 'bg-white border-gray-200 text-gray-300 cursor-not-allowed'

  const btnNav = dark
    ? 'bg-[#1a1a1a] border-[#333] text-gray-300 hover:bg-[#2a2a2a] hover:text-white'
    : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'

  return (
    <div className="flex items-center justify-center gap-1.5 flex-wrap">
      <button
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className={`${btnBase} ${page <= 1 ? btnDisabled : btnNav}`}
        aria-label="Previous page"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      {pages.map((p, idx) =>
        p === '...' ? (
          <span key={`ellipsis-${idx}`} className={`px-2 text-sm ${dark ? 'text-gray-600' : 'text-gray-400'}`}>
            …
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onPageChange(p)}
            className={`${btnBase} ${p === page ? btnActive : btnInactive}`}
            aria-label={`Page ${p}`}
            aria-current={p === page ? 'page' : undefined}
          >
            {p}
          </button>
        )
      )}

      <button
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className={`${btnBase} ${page >= totalPages ? btnDisabled : btnNav}`}
        aria-label="Next page"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <span className={`text-xs ml-2 ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
        Page {page} of {totalPages.toLocaleString()}
      </span>
    </div>
  )
}
