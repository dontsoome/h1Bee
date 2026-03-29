import React, { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import client from '../api/client.js'
import Sidebar from '../components/Sidebar.jsx'
import CompanyTable from '../components/CompanyTable.jsx'
import LCATable from '../components/LCATable.jsx'
import Pagination from '../components/Pagination.jsx'
import { WageLevelBadge } from '../components/Badges.jsx'
import FilterChips from '../components/FilterChips.jsx'

const DEFAULT_FILTERS = {
  case_status: ['Certified'],
  fiscal_year: ['2025', '2026'],
  worksite_state: '',
  wage_level: [],
  min_wage: '',
  max_wage: '',
  employer_name: '',
  min_lcas: '',
  max_lcas: '',
}

function filtersToParams(filters, page, sortKey, sortDir) {
  const p = {}
  if (filters.case_status.length) p.case_status = filters.case_status.join(',')
  if (filters.fiscal_year.length) p.fiscal_year = filters.fiscal_year.join(',')
  if (filters.worksite_state) p.state = filters.worksite_state
  if (filters.wage_level.length) p.wage_level = filters.wage_level.join(',')
  if (filters.min_wage !== '') p.min_wage = filters.min_wage
  if (filters.max_wage !== '') p.max_wage = filters.max_wage
  if (filters.employer_name) p.employer_name = filters.employer_name
  if (filters.min_lcas !== '') p.min_lcas = filters.min_lcas
  if (filters.max_lcas !== '') p.max_lcas = filters.max_lcas
  if (sortKey) { p.order_by = sortKey; p.order_dir = sortDir }
  p.page = page
  p.limit = 50
  return p
}

function paramsToFilters(searchParams) {
  return {
    case_status: searchParams.get('case_status')
      ? searchParams.get('case_status').split(',')
      : DEFAULT_FILTERS.case_status,
    fiscal_year: searchParams.get('fiscal_year')
      ? searchParams.get('fiscal_year').split(',')
      : DEFAULT_FILTERS.fiscal_year,
    worksite_state: searchParams.get('state') || '',
    wage_level: searchParams.get('wage_level') ? searchParams.get('wage_level').split(',') : [],
    min_wage: searchParams.get('min_wage') || '',
    max_wage: searchParams.get('max_wage') || '',
    employer_name: searchParams.get('employer_name') || '',
  }
}

// Sub-tab: Companies vs Records
const SUB_TABS = ['Companies', 'Records']

export default function Explorer({ externalSearch = '' }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [filters, setFilters] = useState(() => paramsToFilters(searchParams))
  const [pendingFilters, setPendingFilters] = useState(() => paramsToFilters(searchParams))
  const [page, setPage] = useState(parseInt(searchParams.get('page') || '1', 10))
  const [filterOptions, setFilterOptions] = useState(null)
  const [subTab, setSubTab] = useState('Companies')
  const [sortKey, setSortKey] = useState('lca_count')
  const [sortDir, setSortDir] = useState('desc')

  // Companies data
  const [companies, setCompanies] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // LCA Records tab
  const [lcaRecords, setLcaRecords] = useState([])
  const [lcaTotal, setLcaTotal] = useState(0)
  const [lcaTotalPages, setLcaTotalPages] = useState(1)
  const [lcaPage, setLcaPage] = useState(1)
  const [lcaLoading, setLcaLoading] = useState(false)
  const [lcaError, setLcaError] = useState(null)
  const [selectedEmployerFilter, setSelectedEmployerFilter] = useState('')

  // Drill-down slide-out
  const [drillDown, setDrillDown] = useState(null)
  const [drillRecords, setDrillRecords] = useState([])
  const [drillTotal, setDrillTotal] = useState(0)
  const [drillTotalPages, setDrillTotalPages] = useState(1)
  const [drillPage, setDrillPage] = useState(1)
  const [drillLoading, setDrillLoading] = useState(false)

  useEffect(() => {
    client.get('/api/filters/options').then((res) => setFilterOptions(res.data)).catch(() => {})
  }, [])

  const fetchCompanies = useCallback(async (f, p, sk, sd, extSearch) => {
    setLoading(true)
    setError(null)
    try {
      const params = filtersToParams(f, p, sk, sd)
      if (extSearch) params.employer_name = extSearch
      const res = await client.get('/api/lca/companies', { params })
      setCompanies(res.data.data)
      setTotalCount(res.data.total_count)
      setTotalPages(res.data.total_pages)
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to load data. Please try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial mount + filter/page changes — always run with defaults on mount
  useEffect(() => {
    fetchCompanies(filters, page, sortKey, sortDir, externalSearch)
  }, [filters, page, sortKey, sortDir, externalSearch, fetchCompanies])

  // Reset to page 1 when external search changes
  useEffect(() => {
    setPage(1)
    setLcaPage(1)
  }, [externalSearch])

  const handleSort = (key, dir) => {
    setSortKey(key)
    setSortDir(dir)
    setPage(1)
  }

  const fetchLcaRecords = useCallback(async (f, empFilter, p, extSearch) => {
    setLcaLoading(true)
    setLcaError(null)
    try {
      const params = {
        case_status: f.case_status.join(','),
        fiscal_year: f.fiscal_year.join(','),
        page: p,
        limit: 50,
      }
      if (f.worksite_state) params.worksite_state = f.worksite_state
      if (f.wage_level.length) params.wage_level = f.wage_level.join(',')
      if (f.min_wage) params.min_wage = f.min_wage
      if (f.max_wage) params.max_wage = f.max_wage
      if (empFilter) params.employer_name = empFilter
      else if (f.employer_name) params.employer_name = f.employer_name
      if (extSearch) params.search = extSearch

      const res = await client.get('/api/lca/records', { params })
      setLcaRecords(res.data.data)
      setLcaTotal(res.data.total_count)
      setLcaTotalPages(res.data.total_pages)
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to load records.'
      setLcaError(msg)
      setLcaRecords([])
    } finally {
      setLcaLoading(false)
    }
  }, [])

  useEffect(() => {
    if (subTab === 'Records') {
      fetchLcaRecords(filters, selectedEmployerFilter, lcaPage, externalSearch)
    }
  }, [subTab, filters, selectedEmployerFilter, lcaPage, externalSearch, fetchLcaRecords])

  const fetchDrillRecords = useCallback(async (employerName, p) => {
    setDrillLoading(true)
    try {
      const params = {
        employer_name: employerName,
        case_status: filters.case_status.join(','),
        fiscal_year: filters.fiscal_year.join(','),
        page: p,
        limit: 50,
      }
      const res = await client.get('/api/lca/records', { params })
      setDrillRecords(res.data.data)
      setDrillTotal(res.data.total_count)
      setDrillTotalPages(res.data.total_pages)
    } catch {
      setDrillRecords([])
    } finally {
      setDrillLoading(false)
    }
  }, [filters.case_status, filters.fiscal_year])

  useEffect(() => {
    if (drillDown) {
      fetchDrillRecords(drillDown.employer_name, drillPage)
    }
  }, [drillDown, drillPage, fetchDrillRecords])

  const handleApplyFilters = () => {
    setFilters({ ...pendingFilters })
    setPage(1)
    setLcaPage(1)
    setDrillDown(null)
    setSelectedEmployerFilter('')
    const params = filtersToParams(pendingFilters, 1)
    setSearchParams(params)
  }

  const handleClearFilters = () => {
    setPendingFilters({ ...DEFAULT_FILTERS })
    setFilters({ ...DEFAULT_FILTERS })
    setPage(1)
    setLcaPage(1)
    setDrillDown(null)
    setSelectedEmployerFilter('')
    setSearchParams({})
  }

  const handlePageChange = (newPage) => {
    setPage(newPage)
    const params = filtersToParams(filters, newPage)
    setSearchParams(params)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleCompanyRowClick = (company) => {
    setDrillDown({ employer_name: company.employer_name })
    setDrillPage(1)
    setDrillRecords([])
  }

  const handleSwitchToRecords = (company) => {
    setSelectedEmployerFilter(company.employer_name)
    setSubTab('Records')
    setLcaPage(1)
    setDrillDown(null)
  }

  return (
    <div className="flex bg-gray-50 dark:bg-gray-950 min-h-screen">
      {/* Sidebar */}
      <Sidebar
        filters={pendingFilters}
        setFilters={setPendingFilters}
        filterOptions={filterOptions}
        onApply={handleApplyFilters}
        onClear={handleClearFilters}
      />

      {/* Main content */}
      <div className="flex-1 min-w-0 p-6 overflow-x-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">LCA Explorer</h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">Browse H-1B Labor Condition Application filings</p>
        </div>

        {/* Active filter chips */}
        {(() => {
          const chips = []
          if (externalSearch) chips.push({ id: 'ext_search', name: 'Search', value: externalSearch })
          if (filters.worksite_state) chips.push({ id: 'worksite_state', name: 'State', value: filters.worksite_state })
          filters.wage_level.forEach((l) => chips.push({ id: `wl_${l}`, name: 'Level', value: l }))
          if (filters.employer_name) chips.push({ id: 'employer_name', name: 'Employer', value: filters.employer_name })
          if (filters.min_wage) chips.push({ id: 'min_wage', name: 'Min Wage', value: `$${Number(filters.min_wage).toLocaleString()}` })
          if (filters.max_wage) chips.push({ id: 'max_wage', name: 'Max Wage', value: `$${Number(filters.max_wage).toLocaleString()}` })
          if (filters.min_lcas) chips.push({ id: 'min_lcas', name: 'Min LCAs', value: filters.min_lcas })
          if (filters.max_lcas) chips.push({ id: 'max_lcas', name: 'Max LCAs', value: filters.max_lcas })
          if (selectedEmployerFilter && subTab === 'Records') chips.push({ id: 'emp_filter', name: 'Records for', value: selectedEmployerFilter })
          return chips.length ? (
            <div className="mb-4">
              <FilterChips
                filters={chips}
                onRemove={(id) => {
                  if (id === 'emp_filter') { setSelectedEmployerFilter(''); setLcaPage(1); return }
                  if (id.startsWith('wl_')) { setFilters((p) => ({ ...p, wage_level: p.wage_level.filter((l) => `wl_${l}` !== id) })); return }
                  setFilters((p) => ({ ...p, [id]: id === 'wage_level' ? [] : '' }))
                }}
                onClearAll={handleClearFilters}
              />
            </div>
          ) : null
        })()}

        {/* Sub-tab switcher */}
        <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit mb-5">
          {SUB_TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => { setSubTab(tab); if (tab === 'Companies') setSelectedEmployerFilter('') }}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-150 ${
                subTab === tab
                  ? 'bg-amber-500 text-white'
                  : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Error — styled with retry */}
        {error && (
          <div className="bg-red-50 border border-red-100 rounded-xl p-4 mb-4 flex items-start gap-3">
            <span className="text-red-400 text-xl mt-0.5">⚠️</span>
            <div className="flex-1">
              <p className="font-medium text-red-700">Failed to load data</p>
              <p className="text-sm text-red-500 mt-0.5">{error}</p>
            </div>
            <button
              onClick={() => fetchCompanies(filters, page)}
              className="flex-shrink-0 text-xs px-3 py-1.5 bg-red-100 hover:bg-red-200 text-red-700 rounded-lg transition-colors font-medium"
            >
              Retry
            </button>
          </div>
        )}

        {/* Companies tab */}
        {subTab === 'Companies' && (
          <>
            {!loading && !error && (
              <p className="text-gray-500 dark:text-gray-400 text-sm mb-4">
                {totalCount.toLocaleString()} companies found
              </p>
            )}
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-100 dark:border-gray-800">
              <CompanyTable
                companies={companies}
                loading={loading}
                onRowClick={handleCompanyRowClick}
                selectedEmployer={drillDown?.employer_name}
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={handleSort}
              />
            </div>
            {!loading && totalPages > 1 && (
              <div className="mt-6">
                <Pagination page={page} totalPages={totalPages} onPageChange={handlePageChange} />
              </div>
            )}
          </>
        )}

        {/* Records tab */}
        {subTab === 'Records' && (
          <>
            {!lcaLoading && !lcaError && (
              <p className="text-gray-500 text-sm mb-4">
                {lcaTotal.toLocaleString()} records found
                {selectedEmployerFilter ? ` for "${selectedEmployerFilter}"` : ''}
              </p>
            )}
            {lcaError && (
              <div className="bg-red-50 border border-red-100 rounded-xl p-4 mb-4 flex items-start gap-3">
                <span className="text-red-400 text-xl mt-0.5">⚠️</span>
                <div>
                  <p className="font-medium text-red-700">Failed to load records</p>
                  <p className="text-sm text-red-500 mt-0.5">{lcaError}</p>
                </div>
              </div>
            )}
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-100 dark:border-gray-800">
              <LCATable records={lcaRecords} loading={lcaLoading} />
            </div>
            {!lcaLoading && lcaTotalPages > 1 && (
              <div className="mt-6">
                <Pagination page={lcaPage} totalPages={lcaTotalPages} onPageChange={(p) => setLcaPage(p)} />
              </div>
            )}
          </>
        )}
      </div>

      {/* Drill-down slide-out panel */}
      {drillDown && (
        <div className="fixed inset-0 z-40 flex items-start justify-end" onClick={() => setDrillDown(null)}>
          <div
            className="h-full w-full max-w-3xl bg-white border-l border-gray-200 overflow-y-auto shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="sticky top-0 bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between z-10">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 truncate max-w-xs">
                  {drillDown.employer_name}
                </h2>
                {!drillLoading && (
                  <p className="text-xs text-gray-500 mt-0.5">
                    {drillTotal.toLocaleString()} LCA records
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleSwitchToRecords(drillDown)}
                  className="text-xs px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors font-medium"
                >
                  View all records →
                </button>
                <button
                  onClick={() => setDrillDown(null)}
                  className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded"
                  aria-label="Close"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Records */}
            <div className="p-6">
              {drillLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="h-16 bg-gray-100 animate-pulse rounded-lg" />
                  ))}
                </div>
              ) : drillRecords.length === 0 ? (
                <div className="text-center py-16">
                  <p className="text-gray-400">No records found for this employer.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {drillRecords.map((rec, idx) => (
                    <DrillRecordCard key={idx} record={rec} />
                  ))}
                </div>
              )}

              {!drillLoading && drillTotalPages > 1 && (
                <div className="mt-6">
                  <Pagination
                    page={drillPage}
                    totalPages={drillTotalPages}
                    onPageChange={(p) => setDrillPage(p)}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function DrillRecordCard({ record }) {
  const formatWage = (val) => {
    if (val == null) return '—'
    return '$' + Math.round(val).toLocaleString()
  }

  return (
    <div className="bg-white border border-gray-100 rounded-lg p-4 hover:border-gray-200 hover:shadow-sm transition-all">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-gray-900 truncate">{record.job_title || '—'}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1">
            <span className="text-xs text-gray-500">
              {record.worksite_city}
              {record.worksite_city && record.worksite_state ? ', ' : ''}
              {record.worksite_state}
            </span>
            {record.visa_class && <span className="text-xs text-gray-400">{record.visa_class}</span>}
            {record.fiscal_year && <span className="text-xs text-gray-400">FY{record.fiscal_year}</span>}
            {record.full_time_position === 'Y' && <span className="text-xs text-gray-400">Full-time</span>}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <span className="text-sm font-semibold text-gray-900">
            {formatWage(record.annual_wage_from)}
            {record.annual_wage_to && record.annual_wage_to !== record.annual_wage_from
              ? ` – ${formatWage(record.annual_wage_to)}`
              : ''}
          </span>
          {record.pw_wage_level && <WageLevelBadge level={record.pw_wage_level} />}
        </div>
      </div>
      <div className="flex items-center gap-3 mt-2">
        {record.case_status && (
          <span
            className={`text-xs px-2 py-0.5 rounded ${
              record.case_status === 'Certified'
                ? 'bg-green-50 text-green-700'
                : 'bg-gray-100 text-gray-500'
            }`}
          >
            {record.case_status}
          </span>
        )}
        {record.soc_title && <span className="text-xs text-gray-400 truncate">{record.soc_title}</span>}
      </div>
    </div>
  )
}
