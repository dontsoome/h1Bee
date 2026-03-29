import React, { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import client from '../api/client.js'
import FilterPanel from '../components/FilterPanel.jsx'
import JobCard from '../components/JobCard.jsx'
import Pagination from '../components/Pagination.jsx'
import { LoadingShimmer, HeaderLoadingShimmer } from '../components/LoadingShimmer.jsx'

const DEFAULT_FILTERS = {
  h1bOnly: false,
  remoteOnly: false,
  employmentTypes: [],
  states: [],
  city: '',
  minWage: '',
  maxWage: '',
  wageLevels: [],
  atsPlatforms: [],
}

function buildApiParams(search, filters, page) {
  const params = { page, limit: 50 }
  if (search) params.search = search
  if (filters.h1bOnly) params.h1b_only = true
  if (filters.remoteOnly) params.is_remote = true
  if (filters.employmentTypes.length) params.employment_type = filters.employmentTypes.join(',')
  if (filters.states.length) params.states = filters.states.join(',')
  if (filters.city) params.city = filters.city
  if (filters.atsPlatforms.length) params.ats_platform = filters.atsPlatforms.join(',')
  if (filters.minWage) params.min_wage = filters.minWage
  if (filters.maxWage) params.max_wage = filters.maxWage
  if (filters.wageLevels.length) params.wage_level = filters.wageLevels.join(',')
  return params
}

function JobCardSkeleton() {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 shadow-sm p-5 animate-pulse">
      <div className="flex gap-3">
        <div className="w-12 h-12 rounded-lg bg-gray-200 dark:bg-gray-700" />
        <div className="flex-1">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-2" />
          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/2" />
        </div>
      </div>
      <div className="mt-3 h-3 bg-gray-200 dark:bg-gray-700 rounded w-full" />
      <div className="mt-2 flex gap-2">
        <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded-full w-16" />
        <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded-full w-20" />
        <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded-full w-12" />
      </div>
    </div>
  )
}

function EmptyState({ onClear, hasFilters }) {
  return (
    <div className="text-center py-16">
      <div className="text-6xl text-gray-200 mb-4">🔍</div>
      <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mt-4">No jobs found</h3>
      <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">Try adjusting your filters or search terms</p>
      {hasFilters && (
        <button
          onClick={onClear}
          className="mt-3 text-amber-500 text-sm underline cursor-pointer hover:text-amber-600 transition-colors"
        >
          Clear all filters
        </button>
      )}
    </div>
  )
}

export default function Jobs({ externalSearch, onExternalSearchChange, onExternalSearchSubmit }) {
  const [searchParams, setSearchParams] = useSearchParams()

  // If external search props are provided, use them; otherwise fall back to internal state
  const usingExternalSearch = externalSearch !== undefined

  const [searchInput, setSearchInput] = useState(searchParams.get('q') || '')
  const [committedSearch, setCommittedSearch] = useState(searchParams.get('q') || '')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [committedFilters, setCommittedFilters] = useState(DEFAULT_FILTERS)
  const [page, setPage] = useState(parseInt(searchParams.get('page') || '1', 10))

  const [jobs, setJobs] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [filterOptions, setFilterOptions] = useState(null)

  // Mobile filter sheet state
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false)

  // Load filter options on mount
  useEffect(() => {
    client.get('/api/filters/options').then((res) => setFilterOptions(res.data)).catch(() => {})
  }, [])

  const fetchJobs = useCallback(async (search, f, p) => {
    setLoading(true)
    setError(null)
    try {
      const params = buildApiParams(search, f, p)
      const res = await client.get('/api/jobs', { params })
      setJobs(res.data.data)
      setTotalCount(res.data.total_count)
      setTotalPages(res.data.total_pages)
      if (p > res.data.total_pages && res.data.total_pages > 0) {
        setPage(1)
      }
    } catch {
      setError('Failed to load job listings. Please try again.')
      setJobs([])
    } finally {
      setLoading(false)
    }
  }, [])

  // When external search changes (from navbar), commit it
  useEffect(() => {
    if (usingExternalSearch) {
      setCommittedSearch(externalSearch)
      setPage(1)
    }
  }, [externalSearch, usingExternalSearch])

  useEffect(() => {
    const activeSearch = usingExternalSearch ? externalSearch : committedSearch
    fetchJobs(activeSearch || committedSearch, committedFilters, page)
    const urlParams = {}
    const s = usingExternalSearch ? externalSearch : committedSearch
    if (s) urlParams.q = s
    if (page > 1) urlParams.page = page
    setSearchParams(urlParams)
  }, [committedSearch, externalSearch, committedFilters, page, fetchJobs])

  const handleSearch = () => {
    if (usingExternalSearch) {
      onExternalSearchSubmit?.()
    } else {
      setCommittedSearch(searchInput)
    }
    setCommittedFilters(filters)
    setPage(1)
    setMobileFilterOpen(false)
  }

  const handleSearchKeyDown = (e) => {
    if (e.key === 'Enter') handleSearch()
  }

  const handlePageChange = (newPage) => {
    setPage(newPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleClearAll = () => {
    if (usingExternalSearch) {
      onExternalSearchChange?.('')
    }
    setSearchInput('')
    setCommittedSearch('')
    setFilters(DEFAULT_FILTERS)
    setCommittedFilters(DEFAULT_FILTERS)
    setPage(1)
    setSearchParams({})
    setMobileFilterOpen(false)
  }

  const activeSearch = usingExternalSearch ? externalSearch : committedSearch

  const hasActiveFilters =
    activeSearch ||
    committedFilters.remoteOnly ||
    committedFilters.employmentTypes.length ||
    committedFilters.states.length ||
    committedFilters.city ||
    committedFilters.atsPlatforms.length ||
    committedFilters.minWage ||
    committedFilters.maxWage ||
    committedFilters.wageLevels.length

  const activeFilterCount =
    (committedFilters.remoteOnly ? 1 : 0) +
    (committedFilters.employmentTypes.length > 0 ? 1 : 0) +
    (committedFilters.states.length > 0 ? 1 : 0) +
    (committedFilters.city ? 1 : 0) +
    (committedFilters.atsPlatforms.length > 0 ? 1 : 0) +
    (committedFilters.minWage ? 1 : 0) +
    (committedFilters.maxWage ? 1 : 0) +
    (committedFilters.wageLevels.length > 0 ? 1 : 0)

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col pb-16">
      {/* HERO SEARCH — commented out, revert if needed
      <div className="bg-white border-b border-gray-100 pt-8 pb-6 px-4">
        <div className="max-w-2xl mx-auto">
          <div className="flex border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            <div className="flex items-center pl-4">
              <svg
                className="w-5 h-5 text-gray-400"
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <input
              type="text"
              placeholder="Search by job title or employer..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              className="flex-1 py-3.5 px-3 text-base outline-none bg-transparent placeholder-gray-400"
            />
            <button
              onClick={handleSearch}
              className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-3.5 font-medium text-sm transition-all duration-150 whitespace-nowrap"
            >
              Search
            </button>
          </div>
          <p className="text-sm text-gray-400 text-center mt-2">
            Data verified by the U.S. Department of Labor.
          </p>
        </div>
      </div>
      */}

      {/* Main content: two-column */}
      <div className="flex-1 max-w-screen-2xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex gap-6 items-start">
          {/* LEFT: Job list */}
          <div className="flex-1 min-w-0">
            {/* Results header */}
            <div className="mb-4 flex items-center justify-between">
              {loading ? (
                <HeaderLoadingShimmer />
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Showing{' '}
                  <span className="font-medium text-gray-700 dark:text-gray-300">{jobs.length.toLocaleString()}</span>
                  {' '}of{' '}
                  <span className="font-medium text-gray-700 dark:text-gray-300">{totalCount.toLocaleString()}</span>
                  {' '}jobs
                </p>
              )}
              <button
                onClick={() => setMobileFilterOpen(true)}
                className="lg:hidden flex items-center gap-1.5 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition-all"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                </svg>
                Filters
                {activeFilterCount > 0 && (
                  <span className="bg-amber-500 text-white text-xs rounded-full px-1.5 ml-1 leading-5 min-w-[1.25rem] text-center">
                    {activeFilterCount}
                  </span>
                )}
              </button>
            </div>

            {/* Error state */}
            {error && (
              <div className="bg-red-50 border border-red-100 rounded-xl p-4 flex items-start gap-3 mb-4">
                <span className="text-red-400 text-xl mt-0.5">⚠️</span>
                <div>
                  <p className="font-medium text-red-700">Failed to load jobs</p>
                  <p className="text-sm text-red-500 mt-0.5">Please try again later</p>
                </div>
              </div>
            )}

            {/* Job cards — 3-column grid */}
            {loading ? (
              <LoadingShimmer text="Finding jobs" />
            ) : jobs.length === 0 ? (
              <EmptyState onClear={handleClearAll} hasFilters={!!hasActiveFilters} />
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                  {jobs.map((job) => (
                    <JobCard key={job.id} job={job} />
                  ))}
                </div>
                {totalPages > 1 && (
                  <div className="mt-8">
                    <Pagination page={page} totalPages={totalPages} onPageChange={handlePageChange} />
                  </div>
                )}
              </>
            )}
          </div>

          {/* RIGHT: Filter panel, desktop only */}
          <div className="hidden lg:flex w-[340px] xl:w-[380px] flex-shrink-0 sticky top-6 h-[80vh] rounded-xl overflow-hidden border border-gray-200 shadow-sm">
            <FilterPanel
              filters={filters}
              onFiltersChange={setFilters}
              onSearch={handleSearch}
              filterOptions={filterOptions}
            />
          </div>
        </div>
      </div>

      {/* Sticky bottom bar */}
      <div className="fixed bottom-0 left-0 right-0 bg-gray-900 text-white py-3 px-6 flex items-center justify-between z-10">
        <span className="text-sm text-gray-400">590,000+ verified H-1B LCA records</span>
        <a
          href="/"
          className="bg-white text-gray-900 text-sm font-medium px-4 py-1.5 rounded-full hover:bg-gray-100 transition-all duration-150"
        >
          Explore LCA Data →
        </a>
      </div>

      {/* Mobile filter bottom sheet */}
      {mobileFilterOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setMobileFilterOpen(false)}
          />
          <div className="absolute bottom-0 left-0 right-0 bg-white dark:bg-gray-900 rounded-t-2xl shadow-2xl max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
              <h2 className="font-semibold text-gray-800 dark:text-gray-100">Filters</h2>
              <button
                onClick={() => setMobileFilterOpen(false)}
                className="text-gray-500 hover:text-gray-700 p-1"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <FilterPanel
                filters={filters}
                onFiltersChange={setFilters}
                onSearch={handleSearch}
                filterOptions={filterOptions}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
