import React, { useState } from 'react'

const VISA_TYPES = [
  'H-1B',
  'H-1B1 Chile',
  'H-1B1 Singapore',
  'TN',
  'F-1 OPT',
  'F-1 CPT',
  'J-1',
  'H-2A',
  'H-2B',
]

const ATS_PLATFORMS = [
  'greenhouse',
  'lever',
  'ashby',
  'workday',
  'icims',
  'jazzhr',
  'smartrecruiters',
]

const WAGE_LEVELS = ['I', 'II', 'III', 'IV']

const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA',
  'HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
  'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
  'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
  'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY',
  'DC',
]

const CATEGORIES = [
  { id: 'location', label: 'Location', icon: '📍' },
  { id: 'salary',   label: 'Salary',   icon: '💰' },
  { id: 'ats',      label: 'Platform', icon: '🖥' },
]

// Per-platform pastel colors when unselected; solid color when selected
const ATS_PILL_STYLES = {
  greenhouse:     { unselected: 'bg-green-50 text-green-700 border-green-100',    selected: 'bg-green-600 text-white border-green-600' },
  lever:          { unselected: 'bg-blue-50 text-blue-700 border-blue-100',       selected: 'bg-blue-600 text-white border-blue-600' },
  ashby:          { unselected: 'bg-purple-50 text-purple-700 border-purple-100', selected: 'bg-purple-600 text-white border-purple-600' },
  workday:        { unselected: 'bg-orange-50 text-orange-700 border-orange-100', selected: 'bg-orange-600 text-white border-orange-600' },
  icims:          { unselected: 'bg-teal-50 text-teal-700 border-teal-100',       selected: 'bg-teal-600 text-white border-teal-600' },
  jazzhr:         { unselected: 'bg-pink-50 text-pink-700 border-pink-100',       selected: 'bg-pink-600 text-white border-pink-600' },
  smartrecruiters:{ unselected: 'bg-indigo-50 text-indigo-700 border-indigo-100', selected: 'bg-indigo-600 text-white border-indigo-600' },
}

const WAGE_LEVEL_SELECTED = {
  I:   'bg-blue-600 text-white border-blue-600',
  II:  'bg-green-600 text-white border-green-600',
  III: 'bg-amber-500 text-white border-amber-500',
  IV:  'bg-red-600 text-white border-red-600',
}

const WAGE_LEVEL_UNSELECTED = {
  I:   'bg-blue-50 text-blue-600 border-blue-100',
  II:  'bg-green-50 text-green-600 border-green-100',
  III: 'bg-amber-50 text-amber-600 border-amber-100',
  IV:  'bg-red-50 text-red-600 border-red-100',
}

function countActiveFilters(filters, categoryId) {
  switch (categoryId) {
    case 'location': return (filters.states.length > 0 ? 1 : 0) + (filters.city ? 1 : 0)
    case 'salary':   return (filters.minWage ? 1 : 0) + (filters.maxWage ? 1 : 0) + filters.wageLevels.length
    case 'ats':      return filters.atsPlatforms.length
    default:         return 0
  }
}

export default function FilterPanel({ filters, onFiltersChange, onSearch, filterOptions }) {
  const [activeCategory, setActiveCategory] = useState('location')
  const [stateSearch, setStateSearch] = useState('')

  const availableStates = filterOptions?.worksite_state || US_STATES

  const filteredStates = stateSearch
    ? availableStates.filter((s) => s.toLowerCase().includes(stateSearch.toLowerCase()))
    : availableStates

  const toggleArray = (field, value) => {
    onFiltersChange((prev) => {
      const arr = prev[field]
      return {
        ...prev,
        [field]: arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value],
      }
    })
  }

  const setField = (field, value) => {
    onFiltersChange((prev) => ({ ...prev, [field]: value }))
  }

  return (
    <aside className="w-full h-full bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
      {/* Two-column layout: category nav + content pane */}
      <div className="flex flex-1 overflow-hidden">
        {/* LEFT: Category nav */}
        <nav className="w-28 flex-shrink-0 border-r border-gray-100 py-2 overflow-y-auto">
          {CATEGORIES.map((cat) => {
            const count = countActiveFilters(filters, cat.id)
            const isActive = activeCategory === cat.id
            return (
              <button
                key={cat.id}
                type="button"
                onClick={() => setActiveCategory(cat.id)}
                className={`w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-all duration-150 border-l-2
                  ${isActive
                    ? 'border-purple-600 text-purple-700 font-medium bg-purple-50'
                    : 'border-transparent text-gray-500 hover:bg-gray-50'
                  }`}
              >
                <span className="text-base leading-none flex-shrink-0">{cat.icon}</span>
                <span className="text-xs leading-tight truncate">{cat.label}</span>
                {count > 0 && (
                  <span className="ml-auto bg-purple-600 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center flex-shrink-0 font-semibold leading-none">
                    {count}
                  </span>
                )}
              </button>
            )
          })}
        </nav>

        {/* RIGHT: Content pane */}
        <div className="flex-1 overflow-y-auto p-4">

          {/* LOCATION PANE */}
          {activeCategory === 'location' && (
            <div className="space-y-4">
              <div>
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">State</p>
                <input
                  type="text"
                  placeholder="Search states..."
                  value={stateSearch}
                  onChange={(e) => setStateSearch(e.target.value)}
                  className="w-full mb-2 px-3 py-1.5 border border-gray-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
                <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
                  {filteredStates.map((st) => {
                    const selected = filters.states.includes(st)
                    return (
                      <button
                        key={st}
                        type="button"
                        onClick={() => toggleArray('states', st)}
                        className={`text-xs px-3 py-1.5 rounded-full border transition-all duration-150
                          ${selected
                            ? 'bg-purple-600 border-purple-600 text-white'
                            : 'border-gray-200 bg-white text-gray-600 hover:border-purple-300 hover:text-purple-600'
                          }`}
                      >
                        {st}
                      </button>
                    )
                  })}
                </div>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">City</p>
                <input
                  type="text"
                  placeholder="e.g. San Francisco"
                  value={filters.city}
                  onChange={(e) => setField('city', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
            </div>
          )}

          {/* SALARY PANE */}
          {activeCategory === 'salary' && (
            <div className="space-y-4">
              <div>
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Annual Wage</p>
                <div className="flex gap-2">
                  <div className="flex-1">
                    <label className="text-xs text-gray-400 block mb-1">Min $</label>
                    <input
                      type="number"
                      placeholder="80000"
                      value={filters.minWage}
                      onChange={(e) => setField('minWage', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-xs text-gray-400 block mb-1">Max $</label>
                    <input
                      type="number"
                      placeholder="200000"
                      value={filters.maxWage}
                      onChange={(e) => setField('maxWage', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                    />
                  </div>
                </div>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Wage Level</p>
                <div className="flex flex-wrap gap-2">
                  {WAGE_LEVELS.map((level) => {
                    const selected = filters.wageLevels.includes(level)
                    return (
                      <button
                        key={level}
                        type="button"
                        onClick={() => toggleArray('wageLevels', level)}
                        className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all duration-150
                          ${selected
                            ? WAGE_LEVEL_SELECTED[level]
                            : WAGE_LEVEL_UNSELECTED[level]
                          }`}
                      >
                        {level}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ATS PLATFORM PANE */}
          {activeCategory === 'ats' && (
            <div>
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">ATS Platform</p>
              <div className="flex flex-wrap gap-2">
                {ATS_PLATFORMS.map((p) => {
                  const selected = filters.atsPlatforms.includes(p)
                  const style = ATS_PILL_STYLES[p] || {
                    unselected: 'bg-gray-50 text-gray-600 border-gray-200',
                    selected: 'bg-gray-600 text-white border-gray-600',
                  }
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => toggleArray('atsPlatforms', p)}
                      className={`text-xs px-3 py-1.5 rounded-full border capitalize transition-all duration-150
                        ${selected ? style.selected : style.unselected + ' hover:opacity-80'}`}
                    >
                      {p}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

        </div>
      </div>

      {/* Panel footer */}
      <div className="border-t border-gray-100 p-4 flex items-center justify-between">
        <button
          type="button"
          onClick={() =>
            onFiltersChange({
              states: [],
              city: '',
              minWage: '',
              maxWage: '',
              wageLevels: [],
              atsPlatforms: [],
            })
          }
          className="text-sm text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
        >
          Clear all
        </button>
        <button
          type="button"
          onClick={onSearch}
          className="bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-all duration-150"
        >
          Search
        </button>
      </div>
    </aside>
  )
}
