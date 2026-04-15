export const CYAN = '#00fff5'
export const AMBER = '#ffb000'
export const CORAL = '#ff4444'
export const GREEN = '#00ff88'
export const DIM = '#333'

export const PURPLE = '#bb66ff'

export const CHART_COLORS = {
  accel: [CORAL, CYAN, AMBER],
  gyro: [AMBER, GREEN, CYAN],
  orientation: [CORAL, GREEN, AMBER],
  encoders: [CYAN, PURPLE],
} as const

export const CHART_LABELS = {
  accel: ['X', 'Y', 'Z'],
  gyro: ['X', 'Y', 'Z'],
  orientation: ['Roll', 'Pitch', 'Yaw'],
  encoders: ['M1', 'M2'],
} as const

export const CHART_UNITS = {
  accel: 'm/s²',
  gyro: 'rad/s',
  orientation: '°',
  encoders: 'rad/s',
} as const
