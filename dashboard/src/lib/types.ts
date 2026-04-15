export interface IMUSample {
  t: number
  ax: number
  ay: number
  az: number
  gx: number
  gy: number
  gz: number
  temp: number
  roll: number
  pitch: number
  yaw: number
  e1: number
  e2: number
  v1: number
  v2: number
}

export type ChartTab = 'all' | 'accel' | 'gyro' | 'orientation' | 'encoders'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

// Column indices in the data buffer
export const COL = {
  T: 0,
  AX: 1, AY: 2, AZ: 3,
  GX: 4, GY: 5, GZ: 6,
  ROLL: 7, PITCH: 8, YAW: 9,
  V1: 10, V2: 11,
} as const

export const TAB_COLUMNS: Record<ChartTab, number[]> = {
  accel: [COL.T, COL.AX, COL.AY, COL.AZ],
  gyro: [COL.T, COL.GX, COL.GY, COL.GZ],
  orientation: [COL.T, COL.ROLL, COL.PITCH, COL.YAW],
  encoders: [COL.T, COL.V1, COL.V2],
}
