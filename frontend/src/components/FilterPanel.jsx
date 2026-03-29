import React, { useState } from 'react'

const ATS_PLATFORMS = [
  'greenhouse', 'lever', 'ashby', 'workday', 'icims', 'jazzhr', 'smartrecruiters',
]
const EMPLOYMENT_TYPES = ['Full-time', 'Part-time', 'Contract', 'Internship']
const WAGE_LEVELS = ['I', 'II', 'III', 'IV']
const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA',
  'HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
  'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
  'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
  'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC',
]

const MAX_SALARY = 300000

const ATS_PILL_STYLES = {
  greenhouse:     { u: 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border-green-100 dark:border-green-800',    s: 'bg-green-600 text-white border-green-600' },
  lever:          { u: 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 border-blue-100 dark:border-blue-800',          s: 'bg-blue-600 text-white border-blue-600' },
  ashby:          { u: 'bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-400 border-purple-100 dark:border-purple-800', s: 'bg-purple-600 text-white border-purple-600' },
  workday:        { u: 'bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-400 border-orange-100 dark:border-orange-800', s: 'bg-orange-600 text-white border-orange-600' },
  icims:          { u: 'bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-400 border-teal-100 dark:border-teal-800',           s: 'bg-teal-600 text-white border-teal-600' },
  jazzhr:         { u: 'bg-pink-50 dark:bg-pink-900/20 text-pink-700 dark:text-pink-400 border-pink-100 dark:border-pink-800',           s: 'bg-pink-600 text-white border-pink-600' },
  smartrecruiters:{ u: 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-400 border-indigo-100 dark:border-indigo-800', s: 'bg-indigo-600 text-white border-indigo-600' },
}
const WAGE_LEVEL_SELECTED = {
  I: 'bg-blue-600 text-white border-blue-600',
  II: 'bg-green-600 text-white border-green-600',
  III: 'bg-amber-500 text-white border-amber-500',
  IV: 'bg-red-600 text-white border-red-600',
}
const WAGE_LEVEL_UNSELECTED = {
  I:   'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border-blue-100 dark:border-blue-800',
  II:  'bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 border-green-100 dark:border-green-800',
  III: 'bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400 border-amber-100 dark:border-amber-800',
  IV:  'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border-red-100 dark:border-red-800',
}

function fmtSalary(val) {
  if (!val || val === 0) return 'Any'
  if (val >= MAX_SALARY) return `$${MAX_SALARY / 1000}k+`
  return `$${Math.round(val / 1000)}k`
}

function SectionHeader({ label }) {
  return (
    <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-3">
      {label}
    </p>
  )
}

export default function FilterPanel({ filters, onFiltersChange, onSearch, filterOptions }) {
  const [stateSearch, setStateSearch] = useState('')

  const availableStates = filterOptions?.worksite_state || US_STATES
  const filteredStates = stateSearch
    ? availableStates.filter((s) => s.toLowerCase().includes(stateSearch.toLowerCase()))
    : availableStates

  const toggleArray = (field, value) => {
    onFiltersChange((prev) => {
      const arr = prev[field]
      return { ...prev, [field]: arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value] }
    })
  }
  const setField = (field, value) => onFiltersChange((prev) => ({ ...prev, [field]: value }))

  const minVal = filters.minWage ? Number(filters.minWage) : 0
  const maxVal = filters.maxWage ? Number(filters.maxWage) : MAX_SALARY

  const activeFilterCount =
    (filters.h1bOnly ? 1 : 0) +
    (filters.remoteOnly ? 1 : 0) +
    (filters.employmentTypes?.length > 0 ? 1 : 0) +
    (filters.states.length > 0 ? 1 : 0) +
    (filters.city ? 1 : 0) +
    (filters.atsPlatforms.length > 0 ? 1 : 0) +
    (filters.minWage ? 1 : 0) +
    (filters.maxWage ? 1 : 0) +
    (filters.wageLevels.length > 0 ? 1 : 0)

  return (
    <aside className="w-full h-full bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden flex flex-col">
      {/* Header */}
      <div className="px-4 pt-4 pb-3 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">Filters</span>
        {activeFilterCount > 0 && (
          <button
            type="button"
            onClick={() => onFiltersChange({ h1bOnly: false, remoteOnly: false, employmentTypes: [], states: [], city: '', minWage: '', maxWage: '', wageLevels: [], atsPlatforms: [] })}
            className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          >
            Clear all ({activeFilterCount})
          </button>
        )}
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">

        {/* ── H-1B ── */}
        <div>
          <SectionHeader label="H-1B Sponsorship" />
          <button
            type="button"
            onClick={() => setField('h1bOnly', !filters.h1bOnly)}
            className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl border-2 transition-all duration-150 text-left
              ${filters.h1bOnly
                ? 'border-amber-500 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400'
                : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:border-amber-300 dark:hover:border-amber-700'
              }`}
          >
            <div>
              <p className="font-semibold text-sm">H-1B Sponsors Only</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Verified DOL LCA records</p>
            </div>
            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0
              ${filters.h1bOnly ? 'border-amber-500 bg-amber-500' : 'border-gray-300 dark:border-gray-600'}`}>
              {filters.h1bOnly && (
                <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
          </button>
        </div>

        {/* ── Remote ── */}
        <div>
          <SectionHeader label="Work Type" />
          <button
            type="button"
            onClick={() => setField('remoteOnly', !filters.remoteOnly)}
            className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl border-2 transition-all duration-150 text-left
              ${filters.remoteOnly
                ? 'border-amber-500 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400'
                : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:border-amber-300 dark:hover:border-amber-700'
              }`}
          >
            <div>
              <p className="font-semibold text-sm">Remote Only</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Jobs with remote option</p>
            </div>
            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0
              ${filters.remoteOnly ? 'border-amber-500 bg-amber-500' : 'border-gray-300 dark:border-gray-600'}`}>
              {filters.remoteOnly && (
                <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
          </button>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {EMPLOYMENT_TYPES.map((type) => {
              const selected = filters.employmentTypes?.includes(type)
              return (
                <button key={type} type="button" onClick={() => toggleArray('employmentTypes', type)}
                  className={`text-xs px-3 py-1.5 rounded-full border transition-all duration-150
                    ${selected
                      ? 'bg-amber-500 border-amber-500 text-white'
                      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:border-amber-300 dark:hover:border-amber-700'
                    }`}>
                  {type}
                </button>
              )
            })}
          </div>
        </div>

        {/* ── Location ── */}
        <div>
          <SectionHeader label="Location" />
          <input
            type="text"
            placeholder="Search states..."
            value={stateSearch}
            onChange={(e) => setStateSearch(e.target.value)}
            className="w-full mb-2.5 px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-400"
          />
          <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto mb-3">
            {['REMOTE', ...filteredStates].map((st) => {
              const selected = filters.states.includes(st)
              return (
                <button key={st} type="button" onClick={() => toggleArray('states', st)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-all duration-150
                    ${selected
                      ? 'bg-amber-500 border-amber-500 text-white'
                      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:border-amber-300 dark:hover:border-amber-700'
                    }`}>
                  {st}
                </button>
              )
            })}
          </div>
          <input
            type="text"
            placeholder="City (e.g. San Francisco)"
            value={filters.city}
            onChange={(e) => setField('city', e.target.value)}
            className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-400"
          />
        </div>

        {/* ── Salary ── */}
        <div>
          <SectionHeader label="Salary (Annual)" />

          {/* Min slider */}
          <div className="mb-3">
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span>Minimum</span>
              <span className="font-medium text-gray-700 dark:text-gray-300">{fmtSalary(minVal)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={MAX_SALARY}
              step={5000}
              value={minVal}
              onChange={(e) => {
                const v = Number(e.target.value)
                setField('minWage', v > 0 ? v : '')
              }}
              className="w-full accent-amber-500 cursor-pointer"
            />
          </div>

          {/* Max slider */}
          <div className="mb-3">
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span>Maximum</span>
              <span className="font-medium text-gray-700 dark:text-gray-300">{fmtSalary(maxVal)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={MAX_SALARY}
              step={5000}
              value={maxVal}
              onChange={(e) => {
                const v = Number(e.target.value)
                setField('maxWage', v < MAX_SALARY ? v : '')
              }}
              className="w-full accent-amber-500 cursor-pointer"
            />
          </div>

          {/* Wage level pills */}
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">Wage Level</p>
          <div className="flex flex-wrap gap-2">
            {WAGE_LEVELS.map((level) => {
              const selected = filters.wageLevels.includes(level)
              return (
                <button key={level} type="button" onClick={() => toggleArray('wageLevels', level)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all duration-150
                    ${selected ? WAGE_LEVEL_SELECTED[level] : WAGE_LEVEL_UNSELECTED[level]}`}>
                  Level {level}
                </button>
              )
            })}
          </div>
        </div>

        {/* ── ATS Platform ── */}
        <div>
          <SectionHeader label="ATS Platform" />
          <div className="flex flex-wrap gap-1.5">
            {ATS_PLATFORMS.map((p) => {
              const selected = filters.atsPlatforms.includes(p)
              const style = ATS_PILL_STYLES[p] || { u: 'bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700', s: 'bg-gray-600 text-white border-gray-600' }
              return (
                <button key={p} type="button" onClick={() => toggleArray('atsPlatforms', p)}
                  className={`text-xs px-3 py-1.5 rounded-full border capitalize transition-all duration-150
                    ${selected ? style.s : style.u + ' hover:opacity-80'}`}>
                  {p}
                </button>
              )
            })}
          </div>
        </div>

      </div>

      {/* Footer */}
      <div className="border-t border-gray-100 dark:border-gray-800 p-4">
        <button type="button" onClick={onSearch}
          className="w-full bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium px-4 py-2.5 rounded-xl transition-all duration-150">
          Apply Filters
        </button>
      </div>
    </aside>
  )
}
