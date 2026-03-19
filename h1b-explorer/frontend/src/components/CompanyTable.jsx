import React, { useState } from 'react'
import CompanyLogo from './CompanyLogo.jsx'

function formatCurrency(val) {
  if (val == null || val === '') return '—'
  const n = Number(val)
  if (isNaN(n)) return '—'
  if (n >= 1_000_000) return '$' + (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return '$' + Math.round(n / 1_000) + 'K'
  return '$' + Math.round(n).toLocaleString()
}

const COLUMNS = [
  { key: 'employer_name', label: 'Company', sortable: false, className: 'text-left' },
  { key: 'total_lcas', label: 'Total LCAs', sortable: true, className: 'text-right' },
  { key: 'states', label: 'States', sortable: false, className: 'text-left' },
  { key: 'min_wage', label: 'Min Salary', sortable: true, className: 'text-right' },
  { key: 'max_wage', label: 'Max Salary', sortable: true, className: 'text-right' },
  { key: 'avg_wage', label: 'Avg Salary', sortable: true, className: 'text-right' },
]

export default function CompanyTable({ companies, loading, onRowClick, selectedEmployer }) {
  const [sortKey, setSortKey] = useState('total_lcas')
  const [sortDir, setSortDir] = useState('desc')

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = [...companies].sort((a, b) => {
    const av = a[sortKey]
    const bv = b[sortKey]
    if (av == null) return 1
    if (bv == null) return -1
    const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv
    return sortDir === 'asc' ? cmp : -cmp
  })

  if (!loading && companies.length === 0) {
    return (
      <div className="text-center py-20">
        <svg className="w-12 h-12 text-gray-300 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p className="text-gray-500 text-lg">No companies found</p>
        <p className="text-gray-400 text-sm mt-1">Try adjusting your filters</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-100">
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                onClick={col.sortable ? () => handleSort(col.key) : undefined}
                className={`px-4 py-3 font-medium text-gray-500 uppercase text-xs whitespace-nowrap
                  ${col.className}
                  ${col.sortable ? 'cursor-pointer hover:text-gray-700 select-none' : ''}
                `}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {col.sortable && (
                    <span className="text-gray-400">
                      {sortKey === col.key ? (sortDir === 'asc' ? '↑' : '↓') : '↕'}
                    </span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: 15 }).map((_, i) => (
                <tr key={i} className="border-b border-gray-100">
                  {COLUMNS.map((col) => (
                    <td key={col.key} className="px-4 py-3">
                      <div
                        className="h-4 bg-gray-100 animate-pulse rounded"
                        style={{ width: col.key === 'employer_name' ? '200px' : '80px' }}
                      />
                    </td>
                  ))}
                </tr>
              ))
            : sorted.map((company, idx) => (
                <CompanyRow
                  key={company.employer_name + idx}
                  company={company}
                  isSelected={selectedEmployer === company.employer_name}
                  onClick={() => onRowClick(company)}
                />
              ))}
        </tbody>
      </table>
    </div>
  )
}

function CompanyRow({ company, isSelected, onClick }) {
  const statesArr = company.states
    ? company.states.split(',').map((s) => s.trim()).filter(Boolean)
    : []

  return (
    <tr
      onClick={onClick}
      className={`border-b border-gray-100 cursor-pointer transition-colors
        ${isSelected ? 'bg-purple-50 border-purple-100' : 'hover:bg-gray-50'}
      `}
    >
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <CompanyLogo employerName={company.employer_name} size="sm" />
          <span className={`font-medium truncate max-w-xs ${isSelected ? 'text-purple-700' : 'text-gray-900'}`}>
            {company.employer_name}
          </span>
          {isSelected && (
            <svg className="w-4 h-4 text-purple-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        <span className="font-semibold text-gray-900">{company.total_lcas?.toLocaleString() ?? '—'}</span>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap gap-1 max-w-xs">
          {statesArr.slice(0, 5).map((state) => (
            <span key={state} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
              {state}
            </span>
          ))}
          {statesArr.length > 5 && (
            <span className="text-xs text-gray-400">+{statesArr.length - 5}</span>
          )}
          {statesArr.length === 0 && <span className="text-gray-400">—</span>}
        </div>
      </td>
      <td className="px-4 py-3 text-right text-gray-600">{formatCurrency(company.min_wage)}</td>
      <td className="px-4 py-3 text-right text-gray-600">{formatCurrency(company.max_wage)}</td>
      <td className="px-4 py-3 text-right">
        <span className="text-green-600 font-medium">{formatCurrency(company.avg_wage)}</span>
      </td>
    </tr>
  )
}
