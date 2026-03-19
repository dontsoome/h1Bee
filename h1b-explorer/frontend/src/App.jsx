import React, { useState } from 'react'
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import Explorer from './pages/Explorer.jsx'
import Jobs from './pages/Jobs.jsx'

export default function App() {
  const navigate = useNavigate()
  const [searchValue, setSearchValue] = useState('')
  const [committedSearch, setCommittedSearch] = useState('')

  const handleSearchSubmit = () => {
    setCommittedSearch(searchValue)
  }

  const handleSearchKeyDown = (e) => {
    if (e.key === 'Enter') handleSearchSubmit()
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Navbar */}
      <nav className="bg-white border-b border-gray-100 shadow-sm sticky top-0 z-50">
        <div className="max-w-full px-4 sm:px-6 lg:px-8">
          <div className="flex items-center h-16 gap-6">
            {/* Brand */}
            <button
              onClick={() => navigate('/jobs')}
              className="flex items-center gap-2 flex-shrink-0"
            >
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                <path d="M16 2L28 9V23L16 30L4 23V9L16 2Z" fill="#7C3AED"/>
                <text x="16" y="21" textAnchor="middle" fill="white" fontSize="12" fontWeight="bold">b</text>
              </svg>
              <span className="text-xl font-bold text-gray-900 tracking-tight">
                H1BEE
              </span>
              <span className="bg-purple-100 text-purple-700 text-xs font-medium px-2 py-0.5 rounded-full ml-1">
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

            {/* Center: Search bar (Jobs page only, shown on md+) */}
            <div className="relative w-96 hidden md:flex items-center flex-shrink-0 mx-auto">
              <div className="absolute left-3 text-gray-400 pointer-events-none">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <input
                type="text"
                placeholder="Search jobs or employers..."
                value={searchValue}
                onChange={(e) => setSearchValue(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                className="w-full rounded-l-full border border-gray-200 bg-white shadow-sm pl-10 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 focus:border-transparent"
              />
              <button
                onClick={handleSearchSubmit}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 text-sm rounded-r-full border border-purple-600 transition-all duration-150 whitespace-nowrap flex-shrink-0"
              >
                Search
              </button>
            </div>

            {/* Right nav */}
            <div className="ml-auto flex items-center gap-5">
              <a href="#" className="hidden md:block text-sm text-gray-500 hover:text-gray-900 transition-colors">
                Post a job
              </a>
              <a href="#" className="hidden md:block text-sm text-gray-500 hover:text-gray-900 transition-colors">
                Pricing
              </a>
              <a href="#" className="hidden md:block text-sm text-gray-500 hover:text-gray-900 transition-colors">
                Login
              </a>
              <button className="bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium px-5 py-2 rounded-full transition-all duration-150">
                Get Access
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
          <Route path="/" element={<Explorer />} />
        </Routes>
      </main>
    </div>
  )
}
