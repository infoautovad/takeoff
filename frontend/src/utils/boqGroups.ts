/** Municipal Estimate-of-Quantities section grouping for BOQ UI. */

export const BOQ_GROUP_ORDER = [
  'General / Traffic Control',
  'Removals',
  'Clearing & Grubbing',
  'Grading',
  'Erosion Control / Restoration',
  'Surfacing',
  'Curb, Gutter & Sidewalk',
  'Storm Sewer',
  'Watermain',
  'Sanitary Sewer',
  'Water & Sewer Services',
  'Traffic Signals & Signing',
  'Lighting & Electrical',
  'Gas & Dry Utilities',
  'Structures',
  'Landscaping & Irrigation',
  'Miscellaneous',
  'Unmapped Takeoff',
] as const

const CATEGORY_ALIASES: Record<string, string> = {
  utilities: 'Watermain',
  utility: 'Watermain',
  drainage: 'Storm Sewer',
  earthwork: 'Grading',
  pavement: 'Surfacing',
  roadside: 'Curb, Gutter & Sidewalk',
  landscaping: 'Landscaping & Irrigation',
  traffic: 'Traffic Signals & Signing',
  markings: 'Traffic Signals & Signing',
  structures: 'Structures',
  demolition: 'Removals',
  'site clearing': 'Clearing & Grubbing',
  geometry: 'Miscellaneous',
  general: 'General / Traffic Control',
  'bid schedule': 'Miscellaneous',
  'unmapped takeoff': 'Unmapped Takeoff',
}

const GROUP_RULES: Array<{ keys: string[]; group: string }> = [
  {
    keys: ['remove ', 'removal', 'demolition', 'sawcut', 'saw cut', 'abandon', 'mill and remove'],
    group: 'Removals',
  },
  {
    keys: [
      'mobilization',
      'demobilization',
      'traffic control',
      'temporary traffic',
      'flagging',
      'construction entrance',
      'field office',
      'survey',
      'staking',
      'audiovisual',
      'permit',
      'allowance',
    ],
    group: 'General / Traffic Control',
  },
  { keys: ['clearing', 'grubbing', 'tree removal', 'stump', 'brush'], group: 'Clearing & Grubbing' },
  {
    keys: [
      'unclassified excavation',
      'excavation',
      'earthwork',
      'embankment',
      'borrow',
      'grading',
      'subgrade',
      'topsoil',
      'proof roll',
      'trench stabilization',
      'select backfill',
      'imported fill',
      'rock excavation',
    ],
    group: 'Grading',
  },
  {
    keys: [
      'erosion',
      'silt fence',
      'inlet protection',
      'sediment',
      'seeding',
      'sodding',
      'mulch',
      'fertiliz',
      'hydroseed',
      'weed control',
      'water for vegetation',
      'turf establishment',
      'swppp',
    ],
    group: 'Erosion Control / Restoration',
  },
  {
    keys: [
      'aggregate base',
      'crushed aggregate',
      'asphalt',
      'hma',
      'hot mix',
      'bituminous',
      'pavement',
      'paving',
      'gsb',
      'wmm',
      'dbm',
      'prime coat',
      'tack coat',
      'milling',
      'overlay',
      'surface course',
      'pcc pavement',
      'concrete pavement',
    ],
    group: 'Surfacing',
  },
  {
    keys: ['curb and gutter', 'curb', 'gutter', 'sidewalk', 'driveway', 'ada', 'detectable warning', 'kerb'],
    group: 'Curb, Gutter & Sidewalk',
  },
  {
    keys: [
      'watermain',
      'water main',
      'waterline',
      'water line',
      'c900',
      'fire hydrant',
      'hydrant',
      'gate valve',
      'butterfly valve',
      'water valve',
      'blowoff',
      'air release',
      'water meter',
      'thrust block',
      'trenchless',
      'directional drill',
      'casing pipe',
      'potable',
    ],
    group: 'Watermain',
  },
  {
    keys: [
      'sanitary sewer',
      'sanitary pipe',
      'sanitary manhole',
      'ssmh',
      'force main',
      'forcemain',
      'sanitary service',
      'cleanout',
      'lift station',
    ],
    group: 'Sanitary Sewer',
  },
  {
    keys: [
      'storm sewer',
      'storm drain',
      'storm pipe',
      'catch basin',
      'inlet',
      'culvert',
      'headwall',
      'junction box',
      'retention',
      'detention',
      'storm manhole',
      'drainage structure',
      'underdrain',
    ],
    group: 'Storm Sewer',
  },
  {
    keys: ['water service', 'service connection', 'corporation stop', 'curb stop', 'meter pit', 'lateral'],
    group: 'Water & Sewer Services',
  },
  {
    keys: [
      'traffic signal',
      'pavement marking',
      'striping',
      'thermoplastic',
      'road sign',
      'traffic sign',
      'signage',
    ],
    group: 'Traffic Signals & Signing',
  },
  {
    keys: ['street light', 'lighting', 'luminaire', 'electrical conduit', 'pull box', 'electric'],
    group: 'Lighting & Electrical',
  },
  { keys: ['gas main', 'gas service', 'telecom', 'fiber', 'joint trench'], group: 'Gas & Dry Utilities' },
  {
    keys: ['bridge', 'retaining wall', 'reinforced concrete', 'structural concrete', 'rebar', 'formwork', 'pile'],
    group: 'Structures',
  },
  { keys: ['landscape', 'irrigation', 'planting', 'shrub', 'groundcover'], group: 'Landscaping & Irrigation' },
  { keys: ['sewer'], group: 'Sanitary Sewer' },
  { keys: ['drain', 'drainage'], group: 'Storm Sewer' },
  { keys: ['water', 'valve', 'pipe', 'fitting', 'bend', 'tee', 'reducer'], group: 'Watermain' },
  { keys: ['fence', 'guardrail', 'barrier'], group: 'Miscellaneous' },
]

function matchDescription(text: string): string | null {
  const low = text.toLowerCase()
  if (!low.trim()) return null
  for (const rule of GROUP_RULES) {
    if (rule.keys.some((k) => low.includes(k))) return rule.group
  }
  return null
}

export function resolveBoqGroup(description?: string | null, category?: string | null): string {
  const cat = (category || '').trim()
  if (cat) {
    const alias = CATEGORY_ALIASES[cat.toLowerCase()]
    if (alias) {
      if (['Watermain', 'Storm Sewer', 'Sanitary Sewer', 'Miscellaneous'].includes(alias)) {
        const refined = matchDescription(description || '')
        if (refined) return refined
      }
      return alias
    }
    if ((BOQ_GROUP_ORDER as readonly string[]).includes(cat)) return cat
  }
  const matched = matchDescription(`${description || ''} ${category || ''}`)
  if (matched) return matched
  if (cat.toLowerCase() === 'unmapped takeoff') return 'Unmapped Takeoff'
  return 'Miscellaneous'
}

export interface BoqGroupSection<T> {
  group: string
  items: T[]
}

export function groupBoqItems<T extends { description?: string | null; category?: string | null }>(
  items: T[],
): BoqGroupSection<T & { display_number: number }>[] {
  const buckets = new Map<string, T[]>()
  for (const item of items) {
    const group = resolveBoqGroup(item.description, item.category)
    const list = buckets.get(group) || []
    list.push(item)
    buckets.set(group, list)
  }
  const ordered: BoqGroupSection<T & { display_number: number }>[] = []
  let serial = 1
  const pushSection = (name: string, list: T[]) => {
    if (!list.length) return
    ordered.push({
      group: name,
      items: list.map((item) => ({ ...item, display_number: serial++ })),
    })
  }
  for (const name of BOQ_GROUP_ORDER) {
    const list = buckets.get(name)
    if (list?.length) {
      pushSection(name, list)
      buckets.delete(name)
    }
  }
  for (const [name, list] of [...buckets.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    pushSection(name, list)
  }
  return ordered
}
