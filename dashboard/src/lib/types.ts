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
  ap: number  // accel-only pitch
  yr: number  // yaw rate (deg/s)
  pid: number  // controller effort
  p: number    // inner P term
  i: number    // outer I term
  d: number    // inner D term
  pid_on: number
  e1: number
  e2: number
  v1: number
  v2: number
  tp: number   // target pitch (from outer loop)
  op: number   // outer P term
  wp: number   // wheel position
  pc: number   // position correction
  yc: number   // yaw correction
  lhz: number  // inner control-loop rate (Hz)
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
  PID: 13, TP: 14, PC: 15, YC: 16,
} as const

export const NUM_COLUMNS = 17

export const TAB_COLUMNS: Record<Exclude<ChartTab, 'all'>, number[]> = {
  accel: [COL.T, COL.AX, COL.AY, COL.AZ],
  gyro: [COL.T, COL.GX, COL.GY, COL.GZ],
  orientation: [COL.T, COL.ROLL, COL.PITCH, COL.AP],
  encoders: [COL.T, COL.V1, COL.V2],
  control: [COL.T, COL.PID, COL.TP, COL.PC, COL.YC],
}
