import React, { useState } from 'react'
import CompanyLogo from './CompanyLogo.jsx'
import { WageLevelBadge } from './Badges.jsx'

function formatCurrency(val) {
  if (val == null || val === '') return '—'
  const n = Number(val)
  if (isNaN(n)) return '—'
  if (n >= 1_000_000) return '$' + (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return '$' + Math.round(n / 1_000) + 'K'
  return '$' + Math.round(n).toLocaleString()
}

const COLUMNS = [
  { key: 'employer_name',  label: 'Company',     sortable: false, className: 'text-left' },
  { key: 'total_lcas',    label: 'Total LCAs',   sortable: true,  className: 'text-right' },
  { key: 'top_wage_level',label: 'Wage Level',   sortable: false, className: 'text-center' },
  { key: 'avg_wage_from', label: 'Avg Wage',     sortable: true,  className: 'text-right' },
]

export default function CompanyTable({ companies, loading, onRowClick, selectedEmployer, sortKey = 'total_lcas', sortDir = 'desc', onSort }) {
  const handleSort = (key) => {
    if (!onSort) return
    if (sortKey === key) {
      onSort(key, sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      onSort(key, 'desc')
    }
  }

  const sorted = companies

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
          <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                onClick={col.sortable ? () => handleSort(col.key) : undefined}
                className={`px-4 py-3 font-medium text-gray-500 dark:text-gray-400 uppercase text-xs whitespace-nowrap
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
                <tr key={i} className="border-b border-gray-100 dark:border-gray-800">
                  {COLUMNS.map((col) => (
                    <td key={col.key} className="px-4 py-3">
                      <div
                        className="h-4 bg-gray-100 dark:bg-gray-700 animate-pulse rounded"
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
  return (
    <tr
      onClick={onClick}
      className={`border-b border-gray-100 dark:border-gray-800 cursor-pointer transition-colors
        ${isSelected ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-100' : 'hover:bg-gray-50 dark:hover:bg-gray-800/60'}
      `}
    >
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <CompanyLogo employerName={company.employer_name} size="sm" />
          <span className={`font-medium truncate max-w-xs ${isSelected ? 'text-amber-700 dark:text-amber-400' : 'text-gray-900 dark:text-gray-100'}`}>
            {company.employer_name}
          </span>
          {isSelected && (
            <svg className="w-4 h-4 text-amber-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        <span className="font-semibold text-gray-900 dark:text-gray-100">{company.total_lcas?.toLocaleString() ?? '—'}</span>
      </td>
      <td className="px-4 py-3 text-center">
        <WageLevelBadge level={company.top_wage_level} />
      </td>
      <td className="px-4 py-3 text-right">
        <span className="text-green-600 font-medium">
          {formatCurrency(company.avg_wage_from)}
          {company.avg_wage_to && company.avg_wage_to !== company.avg_wage_from
            ? ` – ${formatCurrency(company.avg_wage_to)}`
            : ''}
        </span>
      </td>
    </tr>
  )
}
