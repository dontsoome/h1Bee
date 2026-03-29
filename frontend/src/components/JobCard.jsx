import React, { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { WageLevelBadge, getAtsColor } from './Badges.jsx'
import CompanyLogo from './CompanyLogo.jsx'

function getTimeAgo(scraped_at) {
  if (!scraped_at) return null
  try {
    const date = new Date(scraped_at)
    const now = new Date()
    const diffMs = now - date
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    if (diffHours < 24) return diffHours <= 1 ? '1h ago' : `${diffHours}h ago`
    if (diffDays === 1) return '1d ago'
    if (diffDays < 30) return `${diffDays}d ago`
    if (diffDays < 60) return '1mo ago'
    return `${Math.floor(diffDays / 30)}mo ago`
  } catch { return null }
}

function formatWage(from, to, approximate = true) {
  if (!from || from === 0) return null
  const f = Math.round(from / 1000)
  const t = to ? Math.round(to / 1000) : null
  const prefix = approximate ? '~' : ''
  if (t && t !== f) return `${prefix}$${f}k–$${t}k`
  return `${prefix}$${f}k`
}

const FAVORITES_KEY = 'h1bee_favorites'
function getFavorites() {
  try { return JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]') } catch { return [] }
}
function setFavorites(ids) {
  try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(ids)) } catch {}
}

// ── Expanded overlay ─────────────────────────────────────────────────────────

function ExpandedCard({ job, isFavorited, onToggleFavorite, onClose }) {
  const wage = job.salary_min
    ? formatWage(job.salary_min, job.salary_max, false)
    : formatWage(job.avg_wage_from, job.avg_wage_to, true)
  const hasLca = job.lca_count > 0

  const handleViewJob = (e) => {
    e.stopPropagation()
    if (job.job_url) window.open(job.job_url, '_blank', 'noopener,noreferrer')
  }

  const handleCopyLink = (e) => {
    e.stopPropagation()
    if (job.job_url) navigator.clipboard.writeText(job.job_url).catch(() => {})
  }

  return createPortal(
    <AnimatePresence>
      <motion.div
        key="backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/25 backdrop-blur-sm"
      />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <motion.div
          key="modal"
          initial={{ opacity: 0, scale: 0.94, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.94, y: 16 }}
          transition={{ type: 'spring', damping: 28, stiffness: 320 }}
          onClick={(e) => e.stopPropagation()}
          className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-2xl w-full max-w-lg pointer-events-auto max-h-[82vh] overflow-y-auto"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 pt-5 pb-4">
            <div className="flex items-center gap-3">
              <CompanyLogo employerName={job.employer_name} size="lg" />
              <div>
                <p className="font-semibold text-gray-900 dark:text-white text-base leading-tight">
                  {job.employer_name || '—'}
                </p>
                {wage ? (
                  <p className="text-sm text-amber-500 font-medium mt-0.5">{wage} / yr</p>
                ) : (
                  <p className="text-sm text-gray-400 dark:text-gray-500 mt-0.5">Salary not listed</p>
                )}
              </div>
            </div>
            <button onClick={onClose}
              className="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>

          {/* Job title */}
          <div className="px-5 pb-4">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white leading-snug">
              {job.job_title || 'Untitled Position'}
            </h2>
          </div>

          {/* Details */}
          <div className="px-5 pb-4 space-y-2 text-sm text-gray-600 dark:text-gray-400">
            {job.location && (() => {
              const parts = job.location.split(';').map(p => p.trim()).filter(Boolean)
              return (
                <div className="flex items-start gap-2">
                  <svg className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  <div>
                    <span className="font-medium text-gray-700 dark:text-gray-300">Location: </span>
                    {parts.length === 1
                      ? parts[0]
                      : parts.map((p, i) => (
                          <span key={i}>
                            {i > 0 && <span className="text-gray-300 dark:text-gray-600 mx-1">·</span>}
                            {p}
                          </span>
                        ))
                    }
                  </div>
                </div>
              )
            })()}
            {job.department && (
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                <span><span className="font-medium text-gray-700 dark:text-gray-300">Team:</span> {job.department}</span>
              </div>
            )}
            {job.soc_title && (
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <span><span className="font-medium text-gray-700 dark:text-gray-300">Role type:</span> {job.soc_title}</span>
              </div>
            )}
          </div>

          {/* H-1B Sponsorship section */}
          {hasLca && (
            <div className="mx-5 mb-4 bg-amber-50 dark:bg-amber-900/20 rounded-xl px-4 py-3 border border-amber-100 dark:border-amber-800">
              <p className="text-xs font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-wide mb-2">
                H-1B Sponsorship History
              </p>
              <div className="flex flex-wrap gap-1.5">
                <span className="bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-xs font-medium px-2.5 py-1 rounded-full">
                  {job.lca_count.toLocaleString()} LCA{job.lca_count !== 1 ? 's' : ''}
                </span>
                {wage && (
                  <span className="bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 text-xs font-medium px-2.5 py-1 rounded-full">
                    {wage}
                  </span>
                )}
                {job.top_wage_level && <WageLevelBadge level={job.top_wage_level} />}
                {job.ats_platform && (
                  <span className={`text-xs font-medium px-2.5 py-1 rounded-full border capitalize ${getAtsColor(job.ats_platform)}`}>
                    {job.ats_platform}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Footer buttons */}
          <div className="flex items-center justify-between px-5 py-4 border-t border-gray-100 dark:border-gray-800">
            <div className="flex gap-2">
              <button
                onClick={(e) => { e.stopPropagation(); onToggleFavorite() }}
                className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-xl border transition-all
                  ${isFavorited
                    ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-600 dark:text-red-400'
                    : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800'
                  }`}
              >
                <svg width="14" height="14" viewBox="0 0 24 24"
                  fill={isFavorited ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2">
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                </svg>
                {isFavorited ? 'Saved' : 'Save'}
              </button>
              <button
                onClick={handleCopyLink}
                className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 transition-all"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>
                Copy Link
              </button>
            </div>
            <button
              onClick={handleViewJob}
              disabled={!job.job_url}
              className={`flex items-center gap-1.5 text-sm px-5 py-1.5 rounded-xl font-medium transition-all
                ${job.job_url
                  ? 'bg-amber-500 text-white hover:bg-amber-600 shadow-sm'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-400 pointer-events-none'
                }`}
            >
              Apply
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M7 17L17 7M17 7H7M17 7v10"/>
              </svg>
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>,
    document.body
  )
}

// ── Collapsed card ────────────────────────────────────────────────────────────

export default function JobCard({ job }) {
  const [expanded, setExpanded] = useState(false)
  const [isFavorited, setIsFavorited] = useState(false)

  useEffect(() => {
    setIsFavorited(getFavorites().includes(job.id))
  }, [job.id])

  useEffect(() => {
    if (!expanded) return
    const onKey = (e) => { if (e.key === 'Escape') setExpanded(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expanded])

  const toggleFavorite = () => {
    const favs = getFavorites()
    const updated = favs.includes(job.id) ? favs.filter(id => id !== job.id) : [...favs, job.id]
    setFavorites(updated)
    setIsFavorited(updated.includes(job.id))
  }

  const timeAgo = getTimeAgo(job.posted_at || job.scraped_at)
  // Prefer scraped salary (job-specific) over LCA average (company-wide estimate)
  const wage = job.salary_min
    ? formatWage(job.salary_min, job.salary_max, false)
    : formatWage(job.avg_wage_from, job.avg_wage_to, true)
  const hasLca = job.lca_count > 0

  return (
    <>
      <motion.article
        whileHover={{ y: -2, boxShadow: '0 8px 24px rgba(0,0,0,0.08)' }}
        transition={{ type: 'spring', stiffness: 400, damping: 30 }}
        onClick={() => setExpanded(true)}
        className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 shadow-sm cursor-pointer flex flex-col h-full overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-4 pb-3">
          <div className="flex items-center gap-3">
            <CompanyLogo employerName={job.employer_name} size="md" />
            <div className="min-w-0">
              <p className="font-semibold text-gray-900 dark:text-white text-sm leading-tight truncate max-w-[160px]">
                {job.employer_name || '—'}
              </p>
              {wage ? (
                <p className="text-xs text-amber-500 font-medium mt-0.5">{wage} / yr</p>
              ) : (
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Salary not listed</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            {timeAgo && <span className="text-xs text-gray-400 dark:text-gray-500">{timeAgo}</span>}
            <button
              onClick={(e) => { e.stopPropagation(); toggleFavorite() }}
              className="p-1 rounded-full hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors ml-0.5"
              aria-label={isFavorited ? 'Remove from favorites' : 'Save'}
            >
              <svg width="16" height="16" viewBox="0 0 24 24"
                fill={isFavorited ? 'red' : 'none'}
                stroke={isFavorited ? 'red' : '#9ca3af'} strokeWidth="2">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Job title */}
        <div className="px-4 pb-3">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white leading-snug line-clamp-2">
            {job.job_title || 'Untitled Position'}
          </h3>
        </div>

        {/* Details */}
        <div className="px-4 pb-3 space-y-1.5 text-sm flex-1">
          {job.location && (() => {
            const parts = job.location.split(';').map(p => p.trim()).filter(Boolean)
            return (
              <p className="text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                <span className="truncate">{parts[0]}</span>
                {parts.length > 1 && (
                  <span className="flex-shrink-0 text-xs bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 px-1.5 py-0.5 rounded-full">
                    +{parts.length - 1}
                  </span>
                )}
              </p>
            )
          })()}
          {job.department && (
            <p className="text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
              <span className="truncate">{job.department}</span>
            </p>
          )}
          {job.soc_title && (
            <p className="text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <span className="truncate">{job.soc_title}</span>
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1 min-w-0">
            {hasLca && (
              <>
                <span className="bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-300 border border-blue-100 dark:border-blue-800 text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap">
                  {job.lca_count.toLocaleString()} LCAs
                </span>
                {job.top_wage_level && <WageLevelBadge level={job.top_wage_level} />}
              </>
            )}
            {job.ats_platform && (
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full border capitalize ${getAtsColor(job.ats_platform)}`}>
                {job.ats_platform}
              </span>
            )}
          </div>
          <div className="flex gap-1.5 flex-shrink-0">
            <button
              onClick={(e) => { e.stopPropagation(); setExpanded(true) }}
              className="text-xs px-3 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-amber-300 dark:hover:border-amber-700 hover:text-amber-600 dark:hover:text-amber-400 transition-all whitespace-nowrap"
            >
              Details
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation()
                if (job.job_url) window.open(job.job_url, '_blank', 'noopener,noreferrer')
              }}
              disabled={!job.job_url}
              className={`text-xs px-3 py-1.5 rounded-xl font-medium transition-all whitespace-nowrap
                ${job.job_url
                  ? 'bg-amber-500 text-white hover:bg-amber-600'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-400 pointer-events-none'
                }`}
            >
              Apply →
            </button>
          </div>
        </div>
      </motion.article>

      {expanded && (
        <ExpandedCard
          job={job}
          isFavorited={isFavorited}
          onToggleFavorite={toggleFavorite}
          onClose={() => setExpanded(false)}
        />
      )}
    </>
  )
}
