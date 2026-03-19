import React from 'react'

// Derive a domain from employer name for Clearbit logo lookup
function deriveCompanyDomain(name) {
  if (!name) return null
  let s = name.toLowerCase()

  // Special cases first
  const specialCases = {
    'amazon': 'amazon.com',
    'amazon.com': 'amazon.com',
    'google': 'google.com',
    'meta': 'meta.com',
    'apple': 'apple.com',
    'microsoft': 'microsoft.com',
    'tesla': 'tesla.com',
    'netflix': 'netflix.com',
    'uber': 'uber.com',
    'lyft': 'lyft.com',
    'airbnb': 'airbnb.com',
    'stripe': 'stripe.com',
    'twitter': 'twitter.com',
    'x corp': 'x.com',
    'linkedin': 'linkedin.com',
    'salesforce': 'salesforce.com',
    'oracle': 'oracle.com',
    'ibm': 'ibm.com',
    'intel': 'intel.com',
    'qualcomm': 'qualcomm.com',
    'nvidia': 'nvidia.com',
    'adobe': 'adobe.com',
    'spotify': 'spotify.com',
    'snapchat': 'snap.com',
    'snap': 'snap.com',
    'palantir': 'palantir.com',
    'databricks': 'databricks.com',
    'snowflake': 'snowflake.com',
    'coinbase': 'coinbase.com',
    'robinhood': 'robinhood.com',
    'doordash': 'doordash.com',
    'instacart': 'instacart.com',
    'pinterest': 'pinterest.com',
    'reddit': 'reddit.com',
    'twitch': 'twitch.tv',
    'discord': 'discord.com',
    'zoom': 'zoom.us',
    'slack': 'slack.com',
    'shopify': 'shopify.com',
    'atlassian': 'atlassian.com',
    'github': 'github.com',
    'gitlab': 'gitlab.com',
    'cloudflare': 'cloudflare.com',
    'figma': 'figma.com',
    'notion': 'notion.so',
    'airtable': 'airtable.com',
    'hubspot': 'hubspot.com',
    'twilio': 'twilio.com',
    'datadog': 'datadoghq.com',
    'elastic': 'elastic.co',
    'mongodb': 'mongodb.com',
    'confluent': 'confluent.io',
    'hashicorp': 'hashicorp.com',
    'okta': 'okta.com',
    'pagerduty': 'pagerduty.com',
    'zendesk': 'zendesk.com',
    'workday': 'workday.com',
    'servicenow': 'servicenow.com',
    'splunk': 'splunk.com',
    'veeva': 'veeva.com',
    'jpmorgan': 'jpmorgan.com',
    'jp morgan': 'jpmorgan.com',
    'goldman sachs': 'goldmansachs.com',
    'morgan stanley': 'morganstanley.com',
    'bank of america': 'bankofamerica.com',
    'wells fargo': 'wellsfargo.com',
    'citibank': 'citigroup.com',
    'citigroup': 'citigroup.com',
    'deloitte': 'deloitte.com',
    'pwc': 'pwc.com',
    'kpmg': 'kpmg.com',
    'ernst young': 'ey.com',
    'mckinsey': 'mckinsey.com',
    'bcg': 'bcg.com',
    'bain': 'bain.com',
    'accenture': 'accenture.com',
    'infosys': 'infosys.com',
    'tata': 'tcs.com',
    'wipro': 'wipro.com',
    'cognizant': 'cognizant.com',
    'capgemini': 'capgemini.com',
  }

  // Check special cases (strip legal suffixes first for matching)
  const stripped = s
    .replace(/\b(llc|inc|corp|corporation|ltd|limited|lp|llp|na|pc|pllc|plc|incorporated|co\.|u\.s\.|usa|us|l\.p\.|s\.a\.|n\.a\.)\b\.?/g, '')
    .replace(/[^a-z0-9\s]/g, '')
    .trim()

  for (const [key, domain] of Object.entries(specialCases)) {
    if (stripped.includes(key) || key.includes(stripped)) {
      if (Math.abs(stripped.length - key.length) <= 3) return domain
    }
  }
  for (const [key, domain] of Object.entries(specialCases)) {
    if (stripped === key || stripped.startsWith(key + ' ') || key.startsWith(stripped)) {
      return domain
    }
  }

  // Generic: take first meaningful word(s) and append .com
  const words = stripped.split(/\s+/).filter(w => w.length >= 3)
  if (!words.length) return null
  // If first word is long enough, use it alone
  if (words[0].length >= 5) return words[0] + '.com'
  // Otherwise combine first two words
  if (words.length >= 2) return (words[0] + words[1]) + '.com'
  return words[0] + '.com'
}

const AVATAR_COLORS = [
  'bg-purple-500', 'bg-blue-500', 'bg-green-500', 'bg-orange-500',
  'bg-red-500', 'bg-teal-500', 'bg-pink-500', 'bg-indigo-500',
]

function getAvatarColor(name) {
  if (!name) return AVATAR_COLORS[0]
  const sum = name.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0)
  return AVATAR_COLORS[sum % AVATAR_COLORS.length]
}

function getInitials(name) {
  if (!name) return '?'
  const words = name.replace(/[^a-zA-Z\s]/g, '').split(/\s+/).filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  return (words[0]?.[0] || '?').toUpperCase()
}

export default function CompanyLogo({ employerName, size = 'md' }) {
  const [imgState, setImgState] = React.useState('loading') // 'loading' | 'loaded' | 'error'
  const domain = React.useMemo(() => deriveCompanyDomain(employerName), [employerName])

  const sizeClass = size === 'sm' ? 'w-8 h-8 text-xs' : size === 'lg' ? 'w-14 h-14 text-base' : 'w-12 h-12 text-sm'
  const avatarColor = getAvatarColor(employerName)
  const initials = getInitials(employerName)

  React.useEffect(() => {
    setImgState('loading')
  }, [employerName])

  if (!domain) {
    return (
      <div className={`${sizeClass} rounded-lg ${avatarColor} flex items-center justify-center text-white font-bold flex-shrink-0`}>
        {initials}
      </div>
    )
  }

  return (
    <div className={`${sizeClass} rounded-lg flex-shrink-0 overflow-hidden relative`}>
      {imgState === 'loading' && (
        <div className={`absolute inset-0 rounded-lg bg-gray-200 animate-pulse`} />
      )}
      {imgState === 'error' && (
        <div className={`absolute inset-0 rounded-lg ${avatarColor} flex items-center justify-center text-white font-bold`}>
          {initials}
        </div>
      )}
      <img
        src={`https://logo.clearbit.com/${domain}`}
        alt={employerName}
        className={`w-full h-full object-contain rounded-lg ${imgState === 'loaded' ? 'opacity-100' : 'opacity-0'}`}
        onLoad={() => setImgState('loaded')}
        onError={() => setImgState('error')}
      />
    </div>
  )
}
