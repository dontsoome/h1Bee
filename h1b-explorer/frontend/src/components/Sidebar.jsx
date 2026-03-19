import React, { useState } from 'react'

const WAGE_LEVEL_STYLES = {
  I:   { unselected: 'border border-blue-200 text-blue-600 bg-white',   selected: 'bg-blue-600 text-white border border-blue-600' },
  II:  { unselected: 'border border-green-200 text-green-600 bg-white',  selected: 'bg-green-600 text-white border border-green-600' },
  III: { unselected: 'border border-amber-200 text-amber-600 bg-white',  selected: 'bg-amber-600 text-white border border-amber-600' },
  IV:  { unselected: 'border border-red-200 text-red-600 bg-white',      selected: 'bg-red-600 text-white border border-red-600' },
}

const CASE_STATUS_OPTIONS = [
  'Certified',
  'Certified - Withdrawn',
  'Denied',
  'Withdrawn',
]

const FISCAL_YEAR_OPTIONS = ['2025', '2026']

export default function Sidebar({ filters, setFilters, filterOptions, onApply, onClear }) {
  const [stateSearch, setStateSearch] = useState('')
  const [stateDropdownOpen, setStateDropdownOpen] = useState(false)

  const availableStates = filterOptions?.worksite_state || []
  const filteredStates = stateSearch
    ? availableStates.filter((s) => s.toLowerCase().includes(stateSearch.toLowerCase()))
    : availableStates

  const handleCheckboxChange = (field, value) => {
    setFilters((prev) => {
      const current = prev[field]
      if (current.includes(value)) {
        return { ...prev, [field]: current.filter((v) => v !== value) }
      } else {
        return { ...prev, [field]: [...current, value] }
      }
    })
  }

  const handleStateSelect = (state) => {
    setFilters((prev) => ({ ...prev, worksite_state: state }))
    setStateDropdownOpen(false)
    setStateSearch('')
  }

  return (
    <aside className="w-[220px] flex-shrink-0 bg-white border-r border-gray-200 min-h-screen sticky top-14 h-[calc(100vh-3.5rem)] overflow-y-auto">
      <div className="p-4 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Filters</h2>
        </div>

        {/* Case Status */}
        <div>
          <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Case Status</h3>
          <div className="space-y-1.5">
            {CASE_STATUS_OPTIONS.map((status) => (
              <label key={status} className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={filters.case_status.includes(status)}
                  onChange={() => handleCheckboxChange('case_status', status)}
                  className="w-3.5 h-3.5 rounded border-gray-300 text-purple-600 focus:ring-purple-400 focus:ring-offset-0 cursor-pointer"
                />
                <span className="text-sm text-gray-700 group-hover:text-gray-900 transition-colors">{status}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Fiscal Year — pill toggles */}
        <div>
          <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Fiscal Year</h3>
          <div className="flex gap-2">
            {FISCAL_YEAR_OPTIONS.map((year) => {
              const isSelected = filters.fiscal_year.includes(year)
              return (
                <button
                  key={year}
                  onClick={() => handleCheckboxChange('fiscal_year', year)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-all duration-150 ${
                    isSelected
                      ? 'bg-purple-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  FY{year}
                </button>
              )
            })}
          </div>
        </div>

        {/* Worksite State */}
        <div>
          <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Worksite State</h3>
          <div className="relative">
            <button
              type="button"
              onClick={() => setStateDropdownOpen((v) => !v)}
              className="w-full flex items-center justify-between bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-left hover:border-gray-300 transition-colors focus:outline-none focus:ring-2 focus:ring-purple-400"
            >
              <span className={filters.worksite_state ? 'text-gray-900' : 'text-gray-400'}>
                {filters.worksite_state || 'All states'}
              </span>
              <svg
                className={`w-4 h-4 text-gray-400 transition-transform ${stateDropdownOpen ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {stateDropdownOpen && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-xl z-20 max-h-56 overflow-hidden flex flex-col">
                <div className="p-2 border-b border-gray-100">
                  <input
                    autoFocus
                    type="text"
                    placeholder="Search states..."
                    value={stateSearch}
                    onChange={(e) => setStateSearch(e.target.value)}
                    className="w-full bg-gray-50 border border-gray-200 rounded px-2 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-400"
                  />
                </div>
                <div className="overflow-y-auto flex-1">
                  {filters.worksite_state && (
                    <button
                      onClick={() => {
                        setFilters((prev) => ({ ...prev, worksite_state: '' }))
                        setStateDropdownOpen(false)
                      }}
                      className="w-full text-left px-3 py-2 text-sm text-gray-400 hover:bg-gray-50 hover:text-gray-700"
                    >
                      — All states
                    </button>
                  )}
                  {filteredStates.map((state) => (
                    <button
                      key={state}
                      onClick={() => handleStateSelect(state)}
                      className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors ${
                        filters.worksite_state === state
                          ? 'text-purple-600 bg-purple-50'
                          : 'text-gray-700 hover:text-gray-900'
                      }`}
                    >
                      {state}
                    </button>
                  ))}
                  {filteredStates.length === 0 && (
                    <p className="px-3 py-2 text-sm text-gray-400">No states found</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Wage Level — outlined pill buttons */}
        <div>
          <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Wage Level</h3>
          <div className="flex flex-wrap gap-2">
            {['I', 'II', 'III', 'IV'].map((level) => {
              const isSelected = filters.wage_level.includes(level)
              const styles = WAGE_LEVEL_STYLES[level]
              return (
                <button
                  key={level}
                  onClick={() => handleCheckboxChange('wage_level', level)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
                    isSelected ? styles.selected : styles.unselected + ' hover:opacity-80'
                  }`}
                >
                  Level {level}
                </button>
              )
            })}
          </div>
        </div>

        {/* Annual Wage Range */}
        <div>
          <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Annual Wage Range</h3>
          <div className="space-y-2">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Min ($)</label>
              <input
                type="number"
                placeholder="e.g. 80000"
                value={filters.min_wage}
                onChange={(e) => setFilters((prev) => ({ ...prev, min_wage: e.target.value }))}
                className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-400 hover:border-gray-300"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Max ($)</label>
              <input
                type="number"
                placeholder="e.g. 200000"
                value={filters.max_wage}
                onChange={(e) => setFilters((prev) => ({ ...prev, max_wage: e.target.value }))}
                className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-400 hover:border-gray-300"
              />
            </div>
          </div>
        </div>

        {/* Employer Name */}
        <div>
          <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Employer Name</h3>
          <input
            type="text"
            placeholder="Search employer..."
            value={filters.employer_name}
            onChange={(e) => setFilters((prev) => ({ ...prev, employer_name: e.target.value }))}
            className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-400 hover:border-gray-300"
          />
        </div>

        {/* Action buttons */}
        <div className="space-y-2 pt-2">
          <button
            onClick={onApply}
            className="w-full py-2.5 bg-purple-600 hover:bg-purple-700 text-white font-semibold rounded-lg text-sm transition-all duration-150"
          >
            Apply Filters
          </button>
          <button
            onClick={onClear}
            className="w-full py-2 text-gray-400 hover:text-gray-600 text-sm transition-all duration-150"
          >
            Clear
          </button>
        </div>
      </div>
    </aside>
  )
}
