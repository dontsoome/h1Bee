import React, { useState } from 'react'
import { motion } from 'framer-motion'

export default function Pagination({ page, totalPages, onPageChange }) {
  const [inputVal, setInputVal] = useState('')

  if (totalPages <= 1) return null

  const prevPage = () => { if (page > 1) onPageChange(page - 1) }
  const nextPage = () => { if (page < totalPages) onPageChange(page + 1) }

  const getVisiblePages = () => {
    const half = 2
    let start = page - half
    let end = page + half
    if (start < 1) { end += 1 - start; start = 1 }
    if (end > totalPages) { start -= end - totalPages; end = totalPages; if (start < 1) start = 1 }
    const pages = []
    for (let i = start; i <= end; i++) pages.push(i)
    return pages
  }

  const handleGoTo = (e) => {
    e.preventDefault()
    const num = parseInt(inputVal, 10)
    if (!isNaN(num)) {
      onPageChange(Math.max(1, Math.min(num, totalPages)))
    }
    setInputVal('')
  }

  const visiblePages = getVisiblePages()

  return (
    <div className="flex items-center justify-center gap-1.5 select-none">
      {/* Prev arrow */}
      <button
        onClick={prevPage}
        disabled={page <= 1}
        className="w-9 h-9 flex items-center justify-center rounded-full border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
        aria-label="Previous page"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      {/* Wheel: page circles, with input replacing the active page */}
      {visiblePages.map((p) =>
        p === page ? (
          <form key="active-input" onSubmit={handleGoTo}>
            <input
              type="number"
              value={inputVal}
              placeholder={String(page)}
              onChange={(e) => setInputVal(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { handleGoTo(e); e.currentTarget.blur() } }}
              onBlur={() => setInputVal('')}
              className="w-9 h-9 text-center text-sm font-bold rounded-full bg-amber-500 text-white placeholder-white/80
                focus:outline-none focus:ring-2 focus:ring-amber-300
                [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              aria-label="Current page, type to jump"
            />
          </form>
        ) : (
          <motion.button
            key={p}
            animate={{ scale: 1 }}
            whileHover={{ scale: 1.1 }}
            transition={{ type: 'spring', stiffness: 320, damping: 26 }}
            onClick={() => onPageChange(p)}
            className="w-9 h-9 flex items-center justify-center rounded-full text-sm font-medium
              bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300
              hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
            aria-label={`Page ${p}`}
          >
            {p}
          </motion.button>
        )
      )}

      {/* Next arrow */}
      <button
        onClick={nextPage}
        disabled={page >= totalPages}
        className="w-9 h-9 flex items-center justify-center rounded-full border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
        aria-label="Next page"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">of {totalPages.toLocaleString()}</span>
    </div>
  )
}
