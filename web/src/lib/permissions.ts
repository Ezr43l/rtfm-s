import type { AccessRole } from '../types'

const levels: Record<AccessRole, number> = { reader: 0, operator: 1, full_control: 2 }

export function canOperate(role?: AccessRole | null) {
  return role ? levels[role] >= levels.operator : false
}

export function hasFullControl(role?: AccessRole | null) {
  return role === 'full_control'
}

export const roleLabels: Record<AccessRole, string> = {
  reader: 'Solo lectura',
  operator: 'Operador',
  full_control: 'Control total',
}
