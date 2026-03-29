import React from 'react'
import { WageLevelBadge } from './Badges.jsx'

function formatCurrency(val) {
  if (val == null || val === '') return '—'
  const n = Number(val)
  if (isNaN(n)) return '—'
  if (n >= 1_000_000) return '$' + (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return '$' + Math.round(n / 1_000) + 'K'
  return '$' + Math.round(n).toLocaleString()
}

const RECORD_COLUMNS = [
  { key: 'job_title', label: 'Job Title', className: 'text-left' },
  { key: 'worksite_city', label: 'Location', className: 'text-left' },
  { key: 'visa_class', label: 'Visa', className: 'text-left' },
  { key: 'annual_wage_from', label: 'Wage From', className: 'text-right' },
  { key: 'annual_wage_to', label: 'Wage To', className: 'text-right' },
  { key: 'pw_wage_level', label: 'Level', className: 'text-center' },
  { key: 'case_status', label: 'Status', className: 'text-left' },
  { key: 'fiscal_year', label: 'FY', className: 'text-center' },
]

export default function LCATable({ records, loading }) {
  if (!loading && records.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-400 dark:text-gray-500">No LCA records found.</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
            {RECORD_COLUMNS.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-3 font-medium text-gray-500 dark:text-gray-400 uppercase text-xs whitespace-nowrap ${col.className}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: 10 }).map((_, i) => (
                <tr key={i} className="border-b border-gray-100 dark:border-gray-800">
                  {RECORD_COLUMNS.map((col) => (
                    <td key={col.key} className="px-4 py-3">
                      <div className="h-4 bg-gray-100 dark:bg-gray-700 animate-pulse rounded" style={{ width: col.key === 'job_title' ? '160px' : '80px' }} />
                    </td>
                  ))}
                </tr>
              ))
            : records.map((rec, idx) => (
                <LCARecordRow key={idx} record={rec} />
              ))}
        </tbody>
      </table>
    </div>
  )
}

function LCARecordRow({ record }) {
  const location = [record.worksite_city, record.worksite_state].filter(Boolean).join(', ')

  return (
    <tr className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/60 transition-colors">
      <td className="px-4 py-3 text-gray-900 dark:text-gray-100 max-w-[200px]">
        <span className="truncate block">{record.job_title || '—'}</span>
      </td>
      <td className="px-4 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{location || '—'}</td>
      <td className="px-4 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{record.visa_class || '—'}</td>
      <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{formatCurrency(record.annual_wage_from)}</td>
      <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{formatCurrency(record.annual_wage_to)}</td>
      <td className="px-4 py-3 text-center">
        {record.pw_wage_level ? (
          <WageLevelBadge level={record.pw_wage_level} />
        ) : (
          <span className="text-gray-400">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        {record.case_status ? (
          <span
            className={`text-xs px-2 py-0.5 rounded font-medium ${
              record.case_status === 'Certified'
                ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
            }`}
          >
            {record.case_status}
          </span>
        ) : (
          <span className="text-gray-400">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-center text-gray-500 dark:text-gray-400">
        {record.fiscal_year ? `FY${record.fiscal_year}` : '—'}
      </td>
    </tr>
  )
}
