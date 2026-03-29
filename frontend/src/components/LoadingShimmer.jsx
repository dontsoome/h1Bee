import React, { useEffect, useRef, useState } from 'react'

// Cached across renders — computed once
let _cachedPathLength = 0
let _stylesInjected = false

const DRAW_KEYFRAMES = `
  @keyframes drawStroke {
    0%   { stroke-dashoffset: var(--path-length); animation-timing-function: ease-in-out; }
    50%  { stroke-dashoffset: 0;                  animation-timing-function: ease-in-out; }
    100% { stroke-dashoffset: calc(var(--path-length) * -1); }
  }
  @keyframes textShimmer {
    0%   { background-position: -100% center; }
    100% { background-position:  200% center; }
  }
`

function AnimatedLoader({ size = 20, strokeWidth = 2.5, className = '' }) {
  const pathRef = useRef(null)
  const [pathLength, setPathLength] = useState(_cachedPathLength)

  useEffect(() => {
    if (!_stylesInjected) {
      _stylesInjected = true
      const style = document.createElement('style')
      style.innerHTML = DRAW_KEYFRAMES
      document.head.appendChild(style)
    }
    if (!_cachedPathLength && pathRef.current) {
      _cachedPathLength = pathRef.current.getTotalLength()
      setPathLength(_cachedPathLength)
    }
  }, [])

  const ready = pathLength > 0

  return (
    <svg
      role="status"
      aria-label="Loading"
      viewBox="0 0 19 19"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      className={`text-current ${className}`}
    >
      <path
        ref={pathRef}
        d="M4.43431 2.42415C-0.789139 6.90104 1.21472 15.2022 8.434 15.9242C15.5762 16.6384 18.8649 9.23035 15.9332 4.5183C14.1316 1.62255 8.43695 0.0528911 7.51841 3.33733C6.48107 7.04659 15.2699 15.0195 17.4343 16.9241"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        style={ready ? {
          strokeDasharray: pathLength,
          '--path-length': pathLength,
        } : undefined}
        className={ready ? 'animate-[drawStroke_2.5s_infinite]' : 'opacity-0'}
      />
    </svg>
  )
}

// Inline chevron — no lucide dep needed
function ChevronRight({ size = 16, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}

// ── LoadingShimmer ─────────────────────────────────────────────────────────────
// Drop-in replacement for the skeleton loading state.
// Shows: animated SVG loader + shimmer text + chevron

export function LoadingShimmer({ text = 'Finding jobs' }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4">
      {/* Logo mark — pulses gently while loading */}
      <svg width="44" height="44" viewBox="0 0 32 32" fill="none" className="mb-1" style={{ animation: 'logoPulse 2s ease-in-out infinite' }}>
        <style>{`@keyframes logoPulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:0.7; transform:scale(0.93); } }`}</style>
        <path d="M16 2L28 9V23L16 30L4 23V9L16 2Z" fill="#F59E0B"/>
        <text x="16" y="21" textAnchor="middle" fill="white" fontSize="12" fontWeight="bold">S</text>
      </svg>

      {/* Shimmer text row */}
      <div className="flex items-center gap-2 text-[15px] font-medium tracking-wide">
        <span
          className="bg-clip-text text-transparent"
          style={{
            backgroundImage: 'linear-gradient(90deg, rgb(161 161 170) 0%, rgb(161 161 170) 40%, rgb(245 158 11) 50%, rgb(161 161 170) 60%, rgb(161 161 170) 100%)',
            backgroundSize: '200% auto',
            animation: 'textShimmer 2s ease-in-out infinite',
          }}
        >
          {text}
        </span>

        <ChevronRight size={16} className="text-zinc-400 dark:text-zinc-500" />
      </div>

      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Searching verified H-1B sponsors
      </p>
    </div>
  )
}

// ── HeaderLoadingShimmer ───────────────────────────────────────────────────────
// Smaller inline version for the "Showing X of Y jobs" header slot

export function HeaderLoadingShimmer() {
  return (
    <div className="flex items-center gap-2">
      <AnimatedLoader size={14} strokeWidth={2} className="text-amber-500" />
      <span
        className="text-sm bg-clip-text text-transparent"
        style={{
          backgroundImage: 'linear-gradient(90deg, rgb(161 161 170) 0%, rgb(161 161 170) 40%, rgb(245 158 11) 50%, rgb(161 161 170) 60%, rgb(161 161 170) 100%)',
          backgroundSize: '200% auto',
          animation: 'textShimmer 2s ease-in-out infinite',
        }}
      >
        Loading results
      </span>
    </div>
  )
}
