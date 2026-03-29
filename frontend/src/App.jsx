import React, { useState, useEffect } from 'react'
import { Routes, Route, NavLink, useNavigate, useLocation } from 'react-router-dom'
import Explorer from './pages/Explorer.jsx'
import Jobs from './pages/Jobs.jsx'

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const isJobsTab = location.pathname === '/jobs'
  const [searchValue, setSearchValue] = useState('')
  const [committedSearch, setCommittedSearch] = useState('')
  const [lcaSearch, setLcaSearch] = useState('')
  const [committedLcaSearch, setCommittedLcaSearch] = useState('')
  const [darkMode, setDarkMode] = useState(() => {
    return localStorage.getItem('stampd_dark') === 'true'
  })

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
    localStorage.setItem('stampd_dark', darkMode)
  }, [darkMode])

  const handleSearchSubmit = () => {
    if (isJobsTab) {
      setCommittedSearch(searchValue)
    } else {
      setCommittedLcaSearch(lcaSearch)
    }
  }

  const handleSearchKeyDown = (e) => {
    if (e.key === 'Enter') handleSearchSubmit()
  }

  const currentSearchValue = isJobsTab ? searchValue : lcaSearch
  const handleCurrentSearchChange = (e) => {
    if (isJobsTab) setSearchValue(e.target.value)
    else setLcaSearch(e.target.value)
  }

  return (
    <div className="min-h-screen flex flex-col bg-white dark:bg-gray-950 transition-colors duration-200">
      {/* Navbar */}
      <nav className="bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 shadow-sm sticky top-0 z-50">
        <div className="max-w-full px-4 sm:px-6 lg:px-8">
          <div className="flex items-center h-16 gap-6">
            {/* Brand */}
            <button
              onClick={() => navigate('/jobs')}
              className="flex items-center gap-2 flex-shrink-0"
            >
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                <path d="M16 2L28 9V23L16 30L4 23V9L16 2Z" fill="#F59E0B"/>
                <text x="16" y="21" textAnchor="middle" fill="white" fontSize="12" fontWeight="bold">S</text>
              </svg>
              <span className="text-xl font-bold text-gray-900 dark:text-white tracking-tight">
                Stampd
              </span>
              <span className="bg-amber-100 text-amber-700 text-xs font-medium px-2 py-0.5 rounded-full ml-1">
                BETA
              </span>
            </button>

            {/* Tab switcher */}
            <div className="flex items-center gap-1 ml-2">
              <NavLink
                to="/jobs"
                className={({ isActive }) =>
                  `px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-150 ${
                    isActive
                      ? 'bg-gray-900 text-white'
                      : 'text-gray-500 hover:text-gray-900'
                  }`
                }
              >
                Job Board
              </NavLink>
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `px-4 py-1.5 rounded-full text-sm font-medium transition-all duration-150 ${
                    isActive
                      ? 'bg-gray-900 text-white'
                      : 'text-gray-500 hover:text-gray-900'
                  }`
                }
              >
                LCA Explorer
              </NavLink>
            </div>

            {/* Center: Search bar — always visible, context-aware */}
            <div className="relative w-96 hidden md:flex items-center flex-shrink-0 mx-auto">
              <div className="absolute left-3 text-gray-400 pointer-events-none">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <input
                type="text"
                placeholder={isJobsTab ? 'Search jobs or employers...' : 'Search job titles or employers...'}
                value={currentSearchValue}
                onChange={handleCurrentSearchChange}
                onKeyDown={handleSearchKeyDown}
                className="w-full rounded-l-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 shadow-sm pl-10 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent"
              />
              <button
                onClick={handleSearchSubmit}
                className="bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 text-sm rounded-r-full border border-amber-500 transition-all duration-150 whitespace-nowrap flex-shrink-0"
              >
                Search
              </button>
            </div>

            {/* Right nav — dark mode toggle */}
            <div className="ml-auto flex items-center">
              <button
                onClick={() => setDarkMode((d) => !d)}
                className="w-9 h-9 flex items-center justify-center rounded-full border border-gray-200 text-gray-500 hover:border-gray-300 hover:text-gray-700 transition-all"
                aria-label="Toggle dark mode"
              >
                {darkMode ? (
                  // Sun icon
                  <svg className="w-4.5 h-4.5" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="5"/>
                    <line x1="12" y1="1" x2="12" y2="3"/>
                    <line x1="12" y1="21" x2="12" y2="23"/>
                    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                    <line x1="1" y1="12" x2="3" y2="12"/>
                    <line x1="21" y1="12" x2="23" y2="12"/>
                    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                  </svg>
                ) : (
                  // Moon icon
                  <svg className="w-4.5 h-4.5" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Page content */}
      <main className="flex-1">
        <Routes>
          <Route
            path="/jobs"
            element={
              <Jobs
                externalSearch={committedSearch}
                onExternalSearchChange={setSearchValue}
                onExternalSearchSubmit={handleSearchSubmit}
              />
            }
          />
          <Route path="/" element={<Explorer externalSearch={committedLcaSearch} />} />
        </Routes>
      </main>
    </div>
  )
}
