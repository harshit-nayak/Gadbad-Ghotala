/** Audit history derived from incident timelines plus organisation events. */
import { PRODUCT_NAME } from '../app/brand';
import type { AuditCategory, AuditEvent, Incident, TimelineEvent } from '../domain/types';
import { currentAdmin } from './people';

const categoryFor = (e: TimelineEvent): AuditCategory => {
  if (e.actor === 'claimed_person') return 'verification';
  if (e.actor === 'employee') return 'employee_action';
  if (e.actor === 'security') return 'security_response';
  return 'system';
};

export function auditFromIncidents(incidents: Incident[]): AuditEvent[] {
  return incidents.flatMap((incident) =>
    incident.timeline.map((e, index) => {
      const actor =
        e.actor === 'employee'
          ? incident.receiver.name
          : e.actor === 'claimed_person'
            ? incident.claimedIdentity.name
            : e.actor === 'security'
              ? (incident.assignee ?? 'Security team')
              : PRODUCT_NAME;
      return {
        id: `${incident.id}-${index}`,
        at: e.at,
        category: categoryFor(e),
        actor,
        action: e.label,
        target: `Incident #${incident.id}`,
        incidentId: incident.id,
      };
    }),
  );
}

export const organisationAudit: AuditEvent[] = [
  { id: 'org-1', at: '2026-09-08T16:20:00+05:30', category: 'profile', actor: PRODUCT_NAME, action: 'Voice profile updated from a verified genuine call', target: 'Rahul Sharma' },
  { id: 'org-2', at: '2026-09-05T11:00:00+05:30', category: 'system', actor: currentAdmin, action: 'Browser extension enabled for Finance and Treasury', target: 'Document security' },
  { id: 'org-3', at: '2026-09-01T10:15:00+05:30', category: 'report', actor: currentAdmin, action: 'Exported August 2026 organisation report', target: 'Reports' },
  { id: 'org-4', at: '2026-08-28T16:10:00+05:30', category: 'profile', actor: currentAdmin, action: 'Started voice enrolment', target: 'Sana Qureshi' },
  { id: 'org-5', at: '2026-08-20T12:40:00+05:30', category: 'system', actor: currentAdmin, action: 'Dual-approval limit set to ₹5,00,000 for call requests', target: 'Detection policy' },
  { id: 'org-6', at: '2026-08-14T09:30:00+05:30', category: 'profile', actor: PRODUCT_NAME, action: 'Profile flagged for review: reference audio older than 180 days', target: 'Vikram Rao' },
];
