/**
 * Document analysis service.
 * The prototype runs a small rule-based analyser in the browser so pasted
 * content gives real, explainable results. In production the same
 * `DocumentAnalysis` shape should come from the API (POST /v1/documents/analyse).
 */
import { ORG_DOMAIN } from '../app/brand';
import { directory } from '../data/people';
import { formatInr } from '../domain/format';
import { riskLevelFor } from '../domain/risk';
import type {
  ConsistencyCheck,
  DocumentAnalysis,
  DocumentSource,
  ExtractedEntity,
  RiskLevel,
  SuspiciousInstruction,
} from '../domain/types';

/** Payees on file. Anything else is flagged as unregistered. */
const APPROVED_VENDORS = ['Tristar Industrial Supplies', 'Coastal Freight Services', 'Kaveri Holdings Ltd'];
const DUAL_APPROVAL_LIMIT = 500_000;
const orgStem = ORG_DOMAIN.split('.')[0]; // "kaveriholdings"

interface Rule {
  pattern: RegExp;
  reason: string;
  level: RiskLevel;
}

const instructionRules: Rule[] = [
  { pattern: /\b(do not|don't|dont)\s+(inform|tell|discuss|involve|loop|copy|cc)\b/i, reason: 'Asks to avoid approval and oversight', level: 'high' },
  { pattern: /\b(do not|don't|dont)\s+use\s+the\s+(old|existing|previous|registered|usual)\s+(account|details|bank)/i, reason: 'Asks to bypass verified payee records', level: 'high' },
  { pattern: /\b(bypass|skip|without)\b.{0,20}\b(approval|process|verification|committee|call-?back)\b/i, reason: 'Asks to bypass a control', level: 'high' },
  { pattern: /\b(change|update|new|revised|updated)\b.{0,25}\b(bank|account|remittance|beneficiary)\b|\b(bank|account|remittance)\b.{0,20}\b(changed|updated|has changed)\b/i, reason: 'Changes where money is sent', level: 'high' },
  { pattern: /\b(share|send|read|give)\b.{0,25}\b(otp|password|passcode|code|credentials|pin)\b/i, reason: 'Requests credentials or one-time codes', level: 'high' },
  { pattern: /\bgift\s?cards?\b/i, reason: 'Gift card payment request', level: 'high' },
  { pattern: /\b(urgent|urgently|immediately|asap|time-sensitive|right away|within \d+ (minutes|hours))\b/i, reason: 'Urgency pressure', level: 'medium' },
  { pattern: /\b(confidential|secret|between us|keep this private)\b/i, reason: 'Secrecy pressure', level: 'medium' },
  { pattern: /\b(whatsapp|personal (email|number|phone)|telegram)\b/i, reason: 'Moves the conversation off official channels', level: 'medium' },
];

const sentences = (text: string) =>
  text
    .split(/(?<=[.!?])\s+|\n+/)
    .map((s) => s.trim())
    .filter(Boolean);

function parseAmount(raw: string): number | null {
  const lower = raw.toLowerCase().replace(/,/g, '');
  const num = parseFloat(lower.replace(/[^\d.]/g, ''));
  if (Number.isNaN(num)) return null;
  if (/crore|\bcr\b/.test(lower)) return num * 1e7;
  if (/lakh|lac|\bl\b/.test(lower)) return num * 1e5;
  return num;
}

function extractEntities(text: string): ExtractedEntity[] {
  const entities: ExtractedEntity[] = [];
  const seen = new Set<string>();
  const add = (e: ExtractedEntity) => {
    const key = `${e.kind}:${e.value}`;
    if (!seen.has(key)) {
      seen.add(key);
      entities.push(e);
    }
  };

  for (const m of text.matchAll(/(₹|rs\.?|inr)\s?[\d,]+(\.\d+)?(\s?(lakh|lac|crore|cr))?|\b\d+(\.\d+)?\s?(lakh|lac|crore)\b/gi)) {
    const value = parseAmount(m[0]);
    if (value && value >= 1000) {
      add({ kind: 'amount', value: formatInr(value), note: value >= DUAL_APPROVAL_LIMIT ? 'Above dual-approval limit of ₹5,00,000' : undefined, flagged: value >= DUAL_APPROVAL_LIMIT });
    }
  }
  for (const m of text.matchAll(/[\w.+-]+@([\w-]+\.)+[a-z]{2,}/gi)) {
    const domain = m[0].split('@')[1].toLowerCase();
    const internal = domain === ORG_DOMAIN;
    const lookalike = !internal && domain.replace(/[^a-z]/g, '').includes(orgStem);
    add({ kind: 'email', value: m[0], note: lookalike ? `Look-alike of ${ORG_DOMAIN}` : internal ? 'Organisation domain' : 'External domain', flagged: lookalike });
  }
  for (const m of text.matchAll(/\b(?:https?:\/\/)?(?:[a-z0-9-]+\.)+(?:com|co|in|net|org|io|xyz|info)(?:\/[\w\-./?=&]*)?/gi)) {
    if (m[0].includes('@') || text[m.index! - 1] === '@') continue;
    const host = m[0].replace(/^https?:\/\//, '').split('/')[0].toLowerCase();
    if (host.endsWith(ORG_DOMAIN) || /@/.test(text.slice(Math.max(0, m.index! - 40), m.index!).split(/\s/).pop() ?? '')) continue;
    add({ kind: 'url', value: m[0], note: 'External site', flagged: /\.(xyz|info|co)$/.test(host) || host.replace(/[^a-z]/g, '').includes(orgStem) });
  }
  for (const m of text.matchAll(/\b[A-Z]{4}0[A-Z0-9]{6}\b/g)) add({ kind: 'ifsc', value: m[0], flagged: false });
  for (const m of text.matchAll(/\b\d{9,18}\b/g)) {
    add({ kind: 'bank_account', value: m[0], note: 'Not on file for any vendor', flagged: true });
  }
  for (const m of text.matchAll(/\+91[\s-]?\d{5}[\s-]?\d{5}/g)) add({ kind: 'phone', value: m[0], flagged: false });
  for (const m of text.matchAll(/\b([A-Z][\w&]*(?:\s+[A-Z][\w&]*){0,4}\s+(?:Pvt\.?\s+Ltd|Private Limited|LLP|Ltd))\b/g)) {
    const name = m[1].replace(/^(To|Pay|Dear|From)\s+/, '');
    const approved = APPROVED_VENDORS.some((v) => v.toLowerCase() === name.toLowerCase());
    add({ kind: 'organisation', value: name, note: approved ? 'Approved vendor' : 'Not in approved vendor list', flagged: !approved });
  }
  for (const person of directory) {
    if (text.includes(person.name)) add({ kind: 'person', value: `${person.name}, ${person.roleShort}`, note: 'Named in content', flagged: false });
  }
  for (const m of text.matchAll(/\b(today|immediately|by eod|end of day|within \d+ (?:minutes|hours)|before \d{1,2}\s?(?:am|pm))\b/gi)) {
    add({ kind: 'deadline', value: m[0][0].toUpperCase() + m[0].slice(1), flagged: true });
  }
  return entities;
}

function findInstructions(text: string): SuspiciousInstruction[] {
  const found: SuspiciousInstruction[] = [];
  for (const sentence of sentences(text)) {
    for (const rule of instructionRules) {
      const match = sentence.match(rule.pattern);
      if (match && !found.some((f) => f.reason === rule.reason)) {
        found.push({ quote: sentence.length > 110 ? `${sentence.slice(0, 107)}…` : sentence, reason: rule.reason, level: rule.level });
      }
    }
  }
  return found.sort((a, b) => (a.level === b.level ? 0 : a.level === 'high' ? -1 : 1));
}

function checkConsistency(entities: ExtractedEntity[], instructions: SuspiciousInstruction[]): ConsistencyCheck[] {
  const checks: ConsistencyCheck[] = [];
  const emails = entities.filter((e) => e.kind === 'email');
  const orgs = entities.filter((e) => e.kind === 'organisation' && e.value !== 'Kaveri Holdings Ltd');
  const people = entities.filter((e) => e.kind === 'person');
  const bigAmount = entities.some((e) => e.kind === 'amount' && e.flagged);
  const lookalike = emails.find((e) => e.flagged);

  if (emails.length) {
    checks.push(
      lookalike
        ? { label: 'Sender domain matches organisation', result: 'fail', detail: `${lookalike.value.split('@')[1]} is not ${ORG_DOMAIN}` }
        : { label: 'Sender domain matches organisation', result: emails.some((e) => e.value.endsWith(ORG_DOMAIN)) ? 'pass' : 'warn', detail: emails.map((e) => e.value.split('@')[1]).join(', ') },
    );
  }
  if (people.length) {
    checks.push({
      label: 'Claimed identity consistent with sender',
      result: lookalike ? 'fail' : 'pass',
      detail: lookalike ? `${people[0].value} named, but sent from an outside domain` : `${people[0].value} named in content`,
    });
  }
  if (orgs.length) {
    const unregistered = orgs.filter((o) => o.flagged);
    checks.push({
      label: 'Beneficiary in vendor master',
      result: unregistered.length ? 'fail' : 'pass',
      detail: unregistered.length ? `${unregistered[0].value} has no vendor record` : 'All named vendors approved',
    });
  }
  if (bigAmount) {
    const bypass = instructions.some((i) => i.level === 'high');
    checks.push({
      label: 'Request follows payment policy',
      result: bypass ? 'fail' : 'warn',
      detail: bypass ? 'High-value request combined with a control bypass' : 'High-value request needs dual approval',
    });
  }
  if (!checks.length) checks.push({ label: 'No payment, credential or data requests', result: 'pass', detail: 'Nothing to verify' });
  return checks;
}

export function analyseText(input: { id: string; name: string; source: DocumentSource; sourceDetail: string; submittedBy: string; meta: string; text: string; at: string }): DocumentAnalysis {
  const entities = extractEntities(input.text);
  const instructions = findInstructions(input.text);
  const consistency = checkConsistency(entities, instructions);

  const high = instructions.filter((i) => i.level === 'high').length;
  const medium = instructions.length - high;
  const failed = consistency.filter((c) => c.result === 'fail').length;
  const flaggedAmount = entities.some((e) => e.kind === 'amount' && e.flagged);
  const score = Math.min(97, Math.round(5 + high * 20 + medium * 8 + failed * 11 + (flaggedAmount ? 10 : 0)));
  const level = riskLevelFor(score);

  const reasons = [
    ...consistency.filter((c) => c.result === 'fail').map((c) => c.detail),
    ...instructions.map((i) => i.reason),
  ].filter((r, i, all) => all.indexOf(r) === i).slice(0, 5);

  const actionSentence = sentences(input.text).find((s) => /\b(transfer|pay|process|release|update|change|share|send|wire)\b/i.test(s));
  const counterparty = entities.find((e) => e.kind === 'organisation' && e.flagged)?.value;

  return {
    id: input.id,
    name: input.name,
    source: input.source,
    sourceDetail: input.sourceDetail,
    submittedBy: input.submittedBy,
    analysedAt: input.at,
    state: 'complete',
    meta: input.meta,
    excerpt: input.text.split('\n').map((l) => l.trim()).filter(Boolean).slice(0, 14),
    entities,
    instructions,
    consistency,
    contextSummary:
      level === 'high'
        ? 'Content asks the reader to take a sensitive action while avoiding normal checks.'
        : level === 'medium'
          ? 'Content includes a sensitive request that should be verified before acting.'
          : 'No requests for payment changes, credentials or data sharing that need verification.',
    requestedAction: actionSentence ?? 'None found',
    reasons,
    recommendation:
      level === 'high'
        ? 'Do not act on this content. Verify through an official channel and send it to the Security team.'
        : level === 'medium'
          ? 'Verify the request with the named person or vendor through an official channel before acting.'
          : 'No action needed.',
    riskScore: score,
    riskLevel: level,
    counterparty,
  };
}

/** Sample bodies used when the browser can't read a file's text locally. */
const paymentSample = `From: Accounts <accounts@nexatrade-solutions.co>
Please note our bank details have changed. Update the remittance account before today's payment run.
Account: 60419920038812  IFSC: ICIC0006120
Amount due: ₹8,40,000 to Nexa Trade Solutions Pvt Ltd.
This is urgent. Do not use the old account.`;
const neutralSample = `Internal document for Kaveri Holdings Ltd.
Summary of the quarterly review and next steps for the team.
Please share feedback with your manager by Friday.`;

export const sampleTextForFile = (name: string) =>
  /(pay|invoice|bank|vendor|remit|salary|account|transfer)/i.test(name) ? paymentSample : neutralSample;

export const sampleTextForUrl = (url: string) =>
  url.includes(ORG_DOMAIN)
    ? `Kaveri Holdings Ltd intranet page. Holiday calendar and office announcements.`
    : `Invoice portal for ${url.replace(/^https?:\/\//, '').split('/')[0]}.
Amount due: ₹4,75,000. Pay to the new account shown on this page within 24 hours to avoid late fees.
Account: 30118845120077  IFSC: YESB0000417
For faster processing contact us on WhatsApp.`;

export const readableAsText = (file: File) =>
  file.type.startsWith('text/') || /\.(txt|md|csv|eml|html?)$/i.test(file.name);
