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
}

export type ChartTab = 'all' | 'accel' | 'gyro' | 'orientation'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

// Column indices in the data buffer
export const COL = {
  T: 0,
  AX: 1, AY: 2, AZ: 3,
  GX: 4, GY: 5, GZ: 6,
  ROLL: 7, PITCH: 8, YAW: 9,
} as const

export const TAB_COLUMNS: Record<ChartTab, number[]> = {
  accel: [COL.T, COL.AX, COL.AY, COL.AZ],
  gyro: [COL.T, COL.GX, COL.GY, COL.GZ],
  orientation: [COL.T, COL.ROLL, COL.PITCH, COL.YAW],
}
