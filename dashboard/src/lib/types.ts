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
  ap: number       // accel-only pitch
  yr: number       // yaw rate (deg/s)
  effort: number   // total controller effort (%)
  up: number       // k_pitch * (pitch - θ_eq)
  ur: number       // k_pitch_rate * pitch_rate
  ux: number       // k_pos * (pos - home)
  uv: number       // k_vel * (vel - tvel)
  uy: number       // k_yaw * yaw_error
  ctrl_on: number
  e1: number
  e2: number
  v1: number
  v2: number
  wp: number       // wheel position (rad)
  lhz: number      // inner control-loop rate (Hz)
}

export type ChartTab = 'all' | 'accel' | 'gyro' | 'orientation' | 'encoders' | 'control'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

// Column indices in the data buffer
export const COL = {
  T: 0,
  AX: 1, AY: 2, AZ: 3,
  GX: 4, GY: 5, GZ: 6,
  ROLL: 7, PITCH: 8, AP: 9, YR: 10,
  V1: 11, V2: 12,
  EFFORT: 13, UP: 14, UR: 15, UX: 16, UV: 17, UY: 18,
} as const

export const NUM_COLUMNS = 19

export const MAX_WINDOW_SECONDS = 60
export const TELEMETRY_HZ = 50

export const TAB_COLUMNS: Record<Exclude<ChartTab, 'all'>, number[]> = {
  accel: [COL.T, COL.AX, COL.AY, COL.AZ],
  gyro: [COL.T, COL.GX, COL.GY, COL.GZ],
  orientation: [COL.T, COL.ROLL, COL.PITCH, COL.AP],
  encoders: [COL.T, COL.V1, COL.V2],
  control: [COL.T, COL.EFFORT, COL.UP, COL.UR, COL.UX, COL.UV, COL.UY],
}
