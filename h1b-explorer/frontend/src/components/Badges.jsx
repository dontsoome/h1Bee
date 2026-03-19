import React from 'react'

export const WAGE_LEVEL_LIGHT = {
  I: 'bg-blue-100 text-blue-700',
  II: 'bg-green-100 text-green-700',
  III: 'bg-yellow-100 text-yellow-700',
  IV: 'bg-red-100 text-red-700',
}

export const WAGE_LEVEL_DARK = {
  I: 'bg-blue-900/40 text-blue-300 border border-blue-700',
  II: 'bg-green-900/40 text-green-300 border border-green-700',
  III: 'bg-yellow-900/40 text-yellow-300 border border-yellow-700',
  IV: 'bg-red-900/40 text-red-300 border border-red-700',
}

export const ATS_COLORS = {
  greenhouse: 'bg-green-100 text-green-700 border-green-200',
  lever: 'bg-blue-100 text-blue-700 border-blue-200',
  ashby: 'bg-purple-100 text-purple-700 border-purple-200',
  workday: 'bg-orange-100 text-orange-700 border-orange-200',
  icims: 'bg-teal-100 text-teal-700 border-teal-200',
  jazzhr: 'bg-pink-100 text-pink-700 border-pink-200',
  smartrecruiters: 'bg-indigo-100 text-indigo-700 border-indigo-200',
}

export function getAtsColor(platform) {
  const key = (platform || '').toLowerCase()
  return ATS_COLORS[key] || 'bg-gray-100 text-gray-600 border-gray-200'
}

export function WageLevelBadge({ level, dark = false }) {
  if (!level) return null
  const cls = dark
    ? WAGE_LEVEL_DARK[level] || 'bg-gray-800 text-gray-300 border border-gray-600'
    : WAGE_LEVEL_LIGHT[level] || 'bg-gray-100 text-gray-700'
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${cls}`}>
      Level {level}
    </span>
  )
}

export function LcaCountBadge({ count }) {
  if (!count || count === 0) return null
  return (
    <span className="bg-blue-100 text-blue-800 text-xs font-medium px-2 py-0.5 rounded-full">
      {count.toLocaleString()} LCA{count !== 1 ? 's' : ''}
    </span>
  )
}

export function WageRangeBadge({ from, to }) {
  if (from == null && to == null) return null
  const fmt = (v) => {
    if (v == null) return null
    const k = Math.round(v / 1000)
    return `$${k}k`
  }
  const fromFmt = fmt(from)
  const toFmt = fmt(to)
  let label = ''
  if (fromFmt && toFmt && Math.round(from / 1000) !== Math.round(to / 1000)) {
    label = `${fromFmt}–${toFmt}`
  } else if (fromFmt) {
    label = `Avg ${fromFmt}`
  } else {
    label = `Avg ${toFmt}`
  }
  return (
    <span className="bg-purple-100 text-purple-700 text-xs font-medium px-2 py-0.5 rounded-full">
      {label}
    </span>
  )
}
