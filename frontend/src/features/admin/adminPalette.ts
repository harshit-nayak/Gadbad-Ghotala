import type { AttackType } from '../../domain/types';

/** Lavender scale for Administrator charts; red is reserved for risk states. */
export const lavender = ['#5b3fd9', '#8a6ff0', '#b3a0f8', '#d6cbfc', '#ece6fe'];

export const attackColor: Record<AttackType, string> = {
  executive_voice_clone: lavender[0],
  vendor_impersonation: lavender[1],
  it_helpdesk_impersonation: lavender[2],
  payroll_change: lavender[3],
};
