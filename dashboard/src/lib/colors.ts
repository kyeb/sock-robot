export const CYAN = '#00fff5'
export const AMBER = '#ffb000'
export const CORAL = '#ff4444'
export const GREEN = '#00ff88'
export const DIM = '#333'

export const CHART_COLORS = {
  accel: [CORAL, CYAN, AMBER],
  gyro: [AMBER, GREEN, CYAN],
  orientation: [CORAL, GREEN, AMBER],
} as const

export const CHART_LABELS = {
  accel: ['X', 'Y', 'Z'],
  gyro: ['X', 'Y', 'Z'],
  orientation: ['Roll', 'Pitch', 'Yaw'],
} as const

export const CHART_UNITS = {
  accel: 'm/s²',
  gyro: 'rad/s',
  orientation: '°',
} as const
