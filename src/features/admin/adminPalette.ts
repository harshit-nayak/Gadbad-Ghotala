import type { AttackType } from '../../domain/types';

/**
 * Administrator chart scale: forest to olive, with amber for the lightest step.
 * Red stays reserved for risk states and is never used as a category colour.
 */
export const dataScale = ['#30483a', '#567a63', '#68745a', '#9aa38c', '#c8ccbc'];

/** Kept as `lavender` was the old name; charts import `dataScale`. */
export const attackColor: Record<AttackType, string> = {
  executive_voice_clone: dataScale[0],
  vendor_impersonation: dataScale[1],
  it_helpdesk_impersonation: dataScale[2],
  payroll_change: dataScale[3],
};
