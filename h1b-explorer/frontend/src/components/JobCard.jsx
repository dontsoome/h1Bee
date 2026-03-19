import React, { useState, useEffect } from 'react'
import { WageLevelBadge } from './Badges.jsx'
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
  } catch {
    return null
  }
}

const ATS_BADGE_STYLES = {
  greenhouse:     'bg-green-50 text-green-700 border-green-100',
  lever:          'bg-blue-50 text-blue-700 border-blue-100',
  ashby:          'bg-purple-50 text-purple-700 border-purple-100',
  workday:        'bg-orange-50 text-orange-700 border-orange-100',
  icims:          'bg-teal-50 text-teal-700 border-teal-100',
  jazzhr:         'bg-pink-50 text-pink-700 border-pink-100',
  smartrecruiters:'bg-indigo-50 text-indigo-700 border-indigo-100',
}

function getAtsBadgeStyle(platform) {
  const key = (platform || '').toLowerCase()
  return ATS_BADGE_STYLES[key] || 'bg-gray-50 text-gray-600 border-gray-200'
}

const FAVORITES_KEY = 'h1bee_favorites'

function getFavorites() {
  try {
    return JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]')
  } catch {
    return []
  }
}

function setFavorites(ids) {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify(ids))
  } catch {}
}

export default function JobCard({ job }) {
  const timeAgo = getTimeAgo(job.scraped_at)
  const hasLca = job.lca_count > 0

  const [isFavorited, setIsFavorited] = useState(false)

  useEffect(() => {
    const favs = getFavorites()
    setIsFavorited(favs.includes(job.id))
  }, [job.id])

  const toggleFavorite = () => {
    const favs = getFavorites()
    let updated
    if (favs.includes(job.id)) {
      updated = favs.filter((id) => id !== job.id)
    } else {
      updated = [...favs, job.id]
    }
    setFavorites(updated)
    setIsFavorited(updated.includes(job.id))
  }

  const handleCardClick = () => {
    if (job.job_url) {
      window.open(job.job_url, '_blank', 'noopener,noreferrer')
    }
  }

  const handleViewJobClick = (e) => {
    e.stopPropagation()
    if (job.job_url) {
      window.open(job.job_url, '_blank', 'noopener,noreferrer')
    }
  }

  return (
    <article
      onClick={handleCardClick}
      className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 hover:shadow-md hover:border-gray-200 transition-all duration-200 cursor-pointer flex flex-col gap-3 h-full"
    >
      {/* ROW 1: Logo + title + time + heart */}
      <div className="flex justify-between items-start">
        <div className="flex gap-3 items-start flex-1 min-w-0">
          <CompanyLogo employerName={job.employer_name} size="md" />
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-gray-900 leading-tight line-clamp-2">
              {job.job_title || 'Untitled Position'}
            </h3>
            <p className="text-sm text-gray-500 mt-0.5 truncate">
              {job.employer_name || '—'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1 ml-2 flex-shrink-0 mt-0.5">
          {timeAgo && (
            <span className="text-xs text-gray-400 whitespace-nowrap">
              {timeAgo}
            </span>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); toggleFavorite() }}
            className="p-1 rounded-full hover:bg-red-50 transition-colors"
            aria-label={isFavorited ? 'Remove from favorites' : 'Add to favorites'}
          >
            <svg width="18" height="18" viewBox="0 0 24 24"
                 fill={isFavorited ? "red" : "none"}
                 stroke={isFavorited ? "red" : "#9ca3af"}
                 strokeWidth="2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
          </button>
        </div>
      </div>

      {/* ROW 2: Location + department */}
      {(job.location || job.department) && (
        <div className="flex items-center gap-2 text-sm text-gray-500 flex-wrap">
          {job.location && (
            <span className="flex items-center gap-1">
              <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              {job.location}
            </span>
          )}
          {job.location && job.department && (
            <span className="text-gray-300">•</span>
          )}
          {job.department && (
            <span>{job.department}</span>
          )}
        </div>
      )}

      {/* ROW 3: Tags (soc_title or department) */}
      {(job.soc_title || job.department) && (
        <div className="flex flex-wrap gap-1.5">
          {job.soc_title && (
            <span className="bg-gray-100 text-gray-600 text-xs px-2.5 py-1 rounded-full">
              {job.soc_title}
            </span>
          )}
          {job.department && !job.location && (
            <span className="bg-gray-100 text-gray-600 text-xs px-2.5 py-1 rounded-full">
              {job.department}
            </span>
          )}
        </div>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* ROW 4: Badges + View Job */}
      <div className="flex items-center justify-between mt-1">
        <div className="flex flex-wrap gap-1.5">
          {hasLca && (
            <>
              <span className="bg-blue-50 text-blue-600 border border-blue-100 text-xs font-medium px-2.5 py-0.5 rounded-full">
                {job.lca_count.toLocaleString()} LCAs
              </span>
              {job.avg_wage_from > 0 && (
                <span className="bg-purple-50 text-purple-600 border border-purple-100 text-xs font-medium px-2.5 py-0.5 rounded-full">
                  ~${Math.round(job.avg_wage_from / 1000)}k
                  {job.avg_wage_to && Math.round(job.avg_wage_to / 1000) !== Math.round(job.avg_wage_from / 1000)
                    ? `–$${Math.round(job.avg_wage_to / 1000)}k`
                    : ''}
                </span>
              )}
              {job.top_wage_level && (
                <WageLevelBadge level={job.top_wage_level} />
              )}
            </>
          )}
          {job.ats_platform && (
            <span
              className={`text-xs font-medium px-2.5 py-0.5 rounded-full border capitalize ${getAtsBadgeStyle(job.ats_platform)}`}
            >
              {job.ats_platform}
            </span>
          )}
        </div>
        <button
          onClick={handleViewJobClick}
          disabled={!job.job_url}
          className={`ml-2 flex-shrink-0 border border-gray-200 text-gray-600 text-xs px-3 py-1.5 rounded-lg
            hover:border-purple-400 hover:text-purple-600 transition-all duration-150
            ${!job.job_url ? 'opacity-40 pointer-events-none' : ''}`}
        >
          View Job →
        </button>
      </div>
    </article>
  )
}
