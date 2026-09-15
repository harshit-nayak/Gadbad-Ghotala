/**
 * Incident report generation.
 *
 * Produces an enterprise-style PDF from the CURRENT incident state, so a
 * report always reflects the live status, outcome and verification result.
 * Rendering is client-side (jsPDF) and deliberately isolated here: swap
 * `buildIncidentReport` for a server-rendered PDF later and keep the caller.
 */
import { jsPDF } from 'jspdf';
import { PRODUCT_NAME, ORG_NAME } from '../app/brand';
import { callEnvelope } from '../data/callAudio';
import {
  attackTypeLabel,
  incidentStatusLabel,
  outcomeLabel,
  requestKindLabel,
  riskLevelLabel,
  signalShortLabel,
} from '../components/incident/labels';
import { formatClock, formatDateTimeIst, formatInr, formatTimeIst } from '../domain/format';
import { RISK_THRESHOLDS } from '../domain/risk';
import type { Incident } from '../domain/types';

/* Report palette, matching the product's master colours. */
const INK: [number, number, number] = [23, 26, 23];
const MUTED: [number, number, number] = [92, 97, 87];
const FOREST: [number, number, number] = [48, 72, 58];
const OLIVE: [number, number, number] = [104, 116, 90];
const AMBER: [number, number, number] = [154, 106, 43];
const DANGER: [number, number, number] = [184, 74, 58];
const HAIRLINE: [number, number, number] = [207, 200, 185];
const IVORY: [number, number, number] = [245, 241, 232];

const PAGE = { w: 595.28, h: 841.89 }; // A4 points
const M = { left: 56, right: 56, top: 64, bottom: 62 };
const CONTENT_W = PAGE.w - M.left - M.right;

/**
 * jsPDF's built-in fonts are WinAnsi, which has no rupee sign or smart quotes.
 * Map those to safe equivalents so nothing silently drops out of the PDF.
 */
function pdfText(value: string): string {
  return value
    .replace(/\u20b9\s?/g, 'INR ')
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/[\u2013\u2014]/g, '-')
    .replace(/\u2026/g, '...')
    .replace(/\u00d7/g, 'x')
    .replace(/\u00f7/g, '/')
    .replace(/[^\x00-\xFF]/g, '');
}

const riskColour = (level: Incident['riskLevel']) => (level === 'high' ? DANGER : level === 'medium' ? AMBER : FOREST);

interface Ctx {
  doc: jsPDF;
  y: number;
  page: number;
  incident: Incident;
  generatedAt: string;
}

function header(ctx: Ctx) {
  const { doc } = ctx;
  doc.setFillColor(...IVORY);
  doc.rect(0, 0, PAGE.w, 38, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(9);
  doc.setTextColor(...FOREST);
  doc.text(`${PRODUCT_NAME} SECURITY INCIDENT REPORT`, M.left, 24);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(...MUTED);
  doc.text(`Incident #${ctx.incident.id}`, PAGE.w - M.right, 24, { align: 'right' });
  doc.setDrawColor(...HAIRLINE);
  doc.setLineWidth(0.6);
  doc.line(0, 38, PAGE.w, 38);
}

function footer(ctx: Ctx) {
  const { doc } = ctx;
  doc.setDrawColor(...HAIRLINE);
  doc.setLineWidth(0.6);
  doc.line(M.left, PAGE.h - 44, PAGE.w - M.right, PAGE.h - 44);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(7.5);
  doc.setTextColor(...MUTED);
  doc.text(`${ORG_NAME} · Confidential · Generated ${ctx.generatedAt}`, M.left, PAGE.h - 30);
  doc.text(`Page ${ctx.page}`, PAGE.w - M.right, PAGE.h - 30, { align: 'right' });
}

function newPage(ctx: Ctx) {
  footer(ctx);
  ctx.doc.addPage();
  ctx.page += 1;
  header(ctx);
  ctx.y = M.top + 14;
}

function need(ctx: Ctx, space: number) {
  if (ctx.y + space > PAGE.h - M.bottom) newPage(ctx);
}

function sectionTitle(ctx: Ctx, index: number, title: string) {
  need(ctx, 54);
  ctx.y += 10;
  const { doc } = ctx;
  doc.setDrawColor(...HAIRLINE);
  doc.setLineWidth(0.6);
  doc.line(M.left, ctx.y, PAGE.w - M.right, ctx.y);
  ctx.y += 16;
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(7.5);
  doc.setTextColor(...OLIVE);
  doc.text(`SECTION ${String(index).padStart(2, '0')}`, M.left, ctx.y);
  ctx.y += 14;
  doc.setFontSize(13);
  doc.setTextColor(...INK);
  doc.text(title, M.left, ctx.y);
  ctx.y += 16;
}

function paragraph(ctx: Ctx, text: string, opts: { size?: number; colour?: [number, number, number]; gap?: number } = {}) {
  const { doc } = ctx;
  const size = opts.size ?? 9.5;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(size);
  doc.setTextColor(...(opts.colour ?? MUTED));
  const lines = doc.splitTextToSize(pdfText(text), CONTENT_W) as string[];
  lines.forEach((line) => {
    need(ctx, 16);
    doc.text(line, M.left, ctx.y);
    ctx.y += size + 3.6;
  });
  ctx.y += opts.gap ?? 6;
}

/** Two-column label/value grid. */
function facts(ctx: Ctx, rows: [string, string][]) {
  const { doc } = ctx;
  const colW = CONTENT_W / 2;
  rows.forEach(([label, value], i) => {
    const col = i % 2;
    if (col === 0) need(ctx, 34);
    const x = M.left + col * colW;
    const rowY = ctx.y;
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(7.5);
    doc.setTextColor(...OLIVE);
    doc.text(pdfText(label.toUpperCase()), x, rowY);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9.5);
    doc.setTextColor(...INK);
    const lines = doc.splitTextToSize(pdfText(value), colW - 16) as string[];
    lines.slice(0, 2).forEach((line, li) => doc.text(line, x, rowY + 12 + li * 11));
    if (col === 1 || i === rows.length - 1) ctx.y += 12 + Math.min(2, lines.length) * 11 + 8;
  });
  ctx.y += 4;
}

/** Horizontal signal bar with score. */
function signalBar(ctx: Ctx, label: string, value: number, weight: string, colour: [number, number, number]) {
  need(ctx, 26);
  const { doc } = ctx;
  const barX = M.left + 216;
  const barW = CONTENT_W - 216 - 56;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(...INK);
  doc.text(pdfText(label), M.left, ctx.y + 8);
  doc.setFontSize(7.5);
  doc.setTextColor(...OLIVE);
  doc.text(pdfText(weight), M.left + 118, ctx.y + 8);
  doc.setFillColor(232, 228, 216);
  doc.roundedRect(barX, ctx.y + 1, barW, 8, 3, 3, 'F');
  doc.setFillColor(...colour);
  doc.roundedRect(barX, ctx.y + 1, Math.max(3, (barW * value) / 100), 8, 3, 3, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(9);
  doc.setTextColor(...INK);
  doc.text(String(value), PAGE.w - M.right, ctx.y + 8, { align: 'right' });
  ctx.y += 20;
}

/** Simple table with a header row. */
function table(ctx: Ctx, columns: { label: string; width: number; align?: 'left' | 'right' }[], rows: string[][]) {
  const { doc } = ctx;
  const drawHead = () => {
    need(ctx, 34);
    doc.setFillColor(...IVORY);
    doc.rect(M.left, ctx.y, CONTENT_W, 18, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(7.5);
    doc.setTextColor(...OLIVE);
    let x = M.left + 8;
    columns.forEach((c) => {
      doc.text(pdfText(c.label.toUpperCase()), c.align === 'right' ? x + c.width - 16 : x, ctx.y + 12, { align: c.align ?? 'left' });
      x += c.width;
    });
    ctx.y += 18;
  };
  drawHead();
  rows.forEach((row) => {
    const heights = row.map((cell, i) => (doc.splitTextToSize(cell, columns[i].width - 16) as string[]).length);
    const rowH = Math.max(...heights) * 11 + 8;
    if (ctx.y + rowH > PAGE.h - M.bottom) {
      newPage(ctx);
      drawHead();
    }
    let x = M.left + 8;
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8.5);
    doc.setTextColor(...INK);
    row.forEach((cell, i) => {
      const lines = doc.splitTextToSize(pdfText(cell), columns[i].width - 16) as string[];
      lines.forEach((line, li) =>
        doc.text(line, columns[i].align === 'right' ? x + columns[i].width - 16 : x, ctx.y + 12 + li * 11, {
          align: columns[i].align ?? 'left',
        }),
      );
      x += columns[i].width;
    });
    ctx.y += rowH;
    doc.setDrawColor(...HAIRLINE);
    doc.setLineWidth(0.4);
    doc.line(M.left, ctx.y, PAGE.w - M.right, ctx.y);
  });
  ctx.y += 10;
}

/** Waveform drawn from the same envelope the app shows, with flagged regions. */
function waveform(ctx: Ctx, incident: Incident) {
  need(ctx, 96);
  const { doc } = ctx;
  const h = 56;
  const top = ctx.y;
  const env = callEnvelope(incident);
  const bars = 150;
  const barW = CONTENT_W / bars;

  doc.setFillColor(250, 248, 243);
  doc.rect(M.left, top, CONTENT_W, h, 'F');

  const duration = incident.metadata.durationSec;
  incident.audioRegions.forEach((r) => {
    const x = M.left + (r.start / duration) * CONTENT_W;
    const w = Math.max(2, ((r.end - r.start) / duration) * CONTENT_W);
    const c = riskColour(r.level);
    doc.setFillColor(c[0], c[1], c[2]);
    doc.setGState(new (doc as unknown as { GState: new (o: { opacity: number }) => unknown }).GState({ opacity: 0.12 }));
    doc.rect(x, top, w, h, 'F');
    doc.setGState(new (doc as unknown as { GState: new (o: { opacity: number }) => unknown }).GState({ opacity: 1 }));
  });

  doc.setFillColor(...FOREST);
  for (let i = 0; i < bars; i++) {
    const from = Math.floor((i / bars) * env.length);
    const to = Math.max(from + 1, Math.floor(((i + 1) / bars) * env.length));
    const amp = Math.max(...env.slice(from, to));
    const barH = Math.max(1, amp * (h - 10));
    doc.rect(M.left + i * barW, top + h / 2 - barH / 2, Math.max(0.7, barW - 0.8), barH, 'F');
  }

  doc.setDrawColor(...HAIRLINE);
  doc.setLineWidth(0.6);
  doc.rect(M.left, top, CONTENT_W, h);
  ctx.y = top + h + 8;

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(7.5);
  doc.setTextColor(...MUTED);
  doc.text('00:00', M.left, ctx.y + 6);
  doc.text(formatClock(duration), PAGE.w - M.right, ctx.y + 6, { align: 'right' });
  doc.text('Shaded regions mark where detection signals fired.', M.left + CONTENT_W / 2, ctx.y + 6, { align: 'center' });
  ctx.y += 18;
}

function coverBlock(ctx: Ctx) {
  const { doc, incident } = ctx;
  const colour = riskColour(incident.riskLevel);
  const prevented = incident.outcome === 'impersonation_confirmed';

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(22);
  doc.setTextColor(...INK);
  doc.text('Security incident report', M.left, ctx.y);
  ctx.y += 12;
  doc.setDrawColor(...FOREST);
  doc.setLineWidth(2);
  doc.line(M.left, ctx.y, M.left + 46, ctx.y);
  ctx.y += 26;

  // Status strip
  const boxH = 58;
  doc.setFillColor(...IVORY);
  doc.rect(M.left, ctx.y, CONTENT_W, boxH, 'F');
  doc.setDrawColor(...HAIRLINE);
  doc.setLineWidth(0.6);
  doc.rect(M.left, ctx.y, CONTENT_W, boxH);
  doc.setFillColor(...colour);
  doc.rect(M.left, ctx.y, 3, boxH, 'F');

  const cells: [string, string, [number, number, number]][] = [
    ['Incident', `#${incident.id}`, INK],
    ['Classification', attackTypeLabel[incident.attackType], INK],
    ['Risk', `${riskLevelLabel[incident.riskLevel].toUpperCase()} · ${incident.riskScore}/100`, colour],
    ['Status', prevented ? 'PREVENTED' : incidentStatusLabel[incident.status].toUpperCase(), prevented ? FOREST : colour],
  ];
  const cw = (CONTENT_W - 14) / cells.length;
  cells.forEach(([label, value, tone], i) => {
    const x = M.left + 14 + i * cw;
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(7.5);
    doc.setTextColor(...OLIVE);
    doc.text(label.toUpperCase(), x, ctx.y + 22);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10.5);
    doc.setTextColor(...tone);
    const valueLines = (doc.splitTextToSize(pdfText(value), cw - 10) as string[]).slice(0, 2);
    valueLines.forEach((line, li) => doc.text(line, x, ctx.y + 40 + li * 11));
  });
  ctx.y += boxH + 14;

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text(`Report generated ${ctx.generatedAt} · ${ORG_NAME} · Confidential`, M.left, ctx.y);
  ctx.y += 14;
}

export function buildIncidentReport(incident: Incident, options: { generatedBy: string; generatedAtIso: string }): jsPDF {
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const generatedAt = `${formatDateTimeIst(options.generatedAtIso)} IST`;
  const ctx: Ctx = { doc, y: M.top, page: 1, incident, generatedAt };
  const { claimedIdentity: claimed, receiver, request, metadata, verification } = incident;
  const prevented = incident.outcome === 'impersonation_confirmed';
  const amount = request.amountInr ? formatInr(request.amountInr) : 'No amount specified';

  header(ctx);
  ctx.y = M.top + 8;
  coverBlock(ctx);

  // 1. Executive summary
  sectionTitle(ctx, 1, 'Executive summary');
  paragraph(
    ctx,
    `On ${formatDateTimeIst(metadata.startedAt)} IST, ${receiver.name} (${receiver.role}, ${receiver.department}, ${incident.office}) received an external ${metadata.network} call. The caller presented as ${claimed.name}, ${claimed.role}, and requested ${requestKindLabel[request.kind].toLowerCase()}: ${request.description.toLowerCase()} of ${amount} to ${request.counterparty}. ${request.counterpartyNote}.`,
  );
  paragraph(
    ctx,
    `${PRODUCT_NAME} analysed ${formatClock(metadata.analysedSec)} of call audio and combined voice, acoustic and conversational signals into a weighted risk score of ${incident.riskScore} of 100, classified ${riskLevelLabel[incident.riskLevel].toUpperCase()} RISK. The employee was alerted and asked to verify the specific request before acting.`,
  );
  paragraph(
    ctx,
    `Verification outcome: ${verification.summary}. ${outcomeLabel[incident.outcome]}. ${prevented ? `The requested action was not carried out and ${amount} was not transferred.` : 'The incident remains under review by the security team.'} Current status: ${incidentStatusLabel[incident.status]}.`,
  );

  // 2. Incident details
  sectionTitle(ctx, 2, 'Incident details');
  facts(ctx, [
    ['Incident ID', `#${incident.id}`],
    ['Created', `${formatDateTimeIst(incident.createdAt)} IST`],
    ['Call started', `${formatTimeIst(metadata.startedAt)} IST`],
    ['Call duration', `${formatClock(metadata.durationSec)} (${formatClock(metadata.analysedSec)} analysed)`],
    ['Target employee', `${receiver.name}, ${receiver.role}`],
    ['Department / office', `${receiver.department}, ${incident.office}`],
    ['Claimed identity', `${claimed.name}, ${claimed.role}`],
    ['Caller number', incident.callerNumber],
    ['Attack type', attackTypeLabel[incident.attackType]],
    ['Requested action', `${requestKindLabel[request.kind]}: ${amount}`],
    ['Counterparty', `${request.counterparty} — ${request.counterpartyNote}`],
    ['Current status', `${incidentStatusLabel[incident.status]} · ${incident.assignee ?? 'Unassigned'}`],
  ]);

  // 3. Risk assessment
  sectionTitle(ctx, 3, 'Risk assessment');
  paragraph(
    ctx,
    `Overall risk score ${incident.riskScore} of 100 (${riskLevelLabel[incident.riskLevel].toUpperCase()}). Classification thresholds in force: medium at ${RISK_THRESHOLDS.medium}, high at ${RISK_THRESHOLDS.high}. Each signal contributes its risk reading multiplied by its configured weight.`,
  );
  const scored = incident.signals.filter((s) => s.weight > 0);
  const totalWeight = scored.reduce((sum, s) => sum + s.weight, 0);
  [...scored]
    .sort((a, b) => (b.weight * b.risk) / totalWeight - (a.weight * a.risk) / totalWeight)
    .forEach((s) =>
      signalBar(
        ctx,
        signalShortLabel[s.id],
        s.risk,
        `weight ${s.weight.toFixed(2)} · +${((s.weight * s.risk) / totalWeight).toFixed(1)}`,
        s.conclusive ? riskColour(s.risk >= RISK_THRESHOLDS.high ? 'high' : s.risk >= RISK_THRESHOLDS.medium ? 'medium' : 'low') : OLIVE,
      ),
    );
  const contextual = incident.signals.filter((s) => s.weight === 0);
  if (contextual.length) {
    paragraph(
      ctx,
      `Context inputs not scored: ${contextual.map((s) => `${signalShortLabel[s.id]} (${s.reading})`).join('; ')}`,
      { size: 8 },
    );
  }

  // 4. Voice analysis
  sectionTitle(ctx, 4, 'Voice analysis');
  paragraph(
    ctx,
    `Audio conditions: ${metadata.network} call, ${metadata.codec}, audio quality ${metadata.audioQuality.toLowerCase()}, background noise ${metadata.backgroundNoise.toLowerCase()}, language ${metadata.language}. ${metadata.callerIdNote}.`,
  );
  waveform(ctx, incident);
  table(
    ctx,
    [
      { label: 'Time', width: 80 },
      { label: 'Signal', width: 130 },
      { label: 'Observation', width: CONTENT_W - 210 },
    ],
    incident.audioRegions.map((r) => [`${formatClock(r.start)}–${formatClock(r.end)}`, signalShortLabel[r.signal], r.label]),
  );

  // 5. Conversation analysis
  sectionTitle(ctx, 5, 'Conversation analysis');
  const flagged = incident.transcript.filter((l) => l.flags?.length);
  table(
    ctx,
    [
      { label: 'Time', width: 60 },
      { label: 'Speaker', width: 110 },
      { label: 'Transcript excerpt', width: CONTENT_W - 170 },
    ],
    (flagged.length ? flagged : incident.transcript).map((l) => [
      formatClock(l.at),
      l.speaker === 'caller' ? `Caller (claims ${claimed.name.split(' ')[0]})` : receiver.name,
      l.text,
    ]),
  );
  const tactics = request.pressureTactics.join(', ');
  paragraph(ctx, `Context signals: urgency (${request.deadline}); authority (caller claimed ${claimed.roleShort}); requested action (${requestKindLabel[request.kind].toLowerCase()}, ${amount}); pressure tactics (${tactics || 'none recorded'}).`);

  // 6. Verification
  sectionTitle(ctx, 6, 'Verification');
  facts(ctx, [
    ['Verification requested', 'Yes, at the point of high-risk alert'],
    ['Method', verification.method.replace(/_/g, ' ')],
    ['Result', verification.result.replace(/_/g, ' ').toUpperCase()],
    ['Recorded at', verification.at ? `${formatDateTimeIst(verification.at)} IST` : 'Not completed'],
  ]);
  paragraph(ctx, verification.summary, { colour: INK });

  // 7. Timeline
  sectionTitle(ctx, 7, 'Timeline');
  table(
    ctx,
    [
      { label: 'Time (IST)', width: 90 },
      { label: 'Actor', width: 110 },
      { label: 'Event', width: CONTENT_W - 200 },
    ],
    incident.timeline.map((e) => [
      formatTimeIst(e.at),
      e.actor === 'system' ? PRODUCT_NAME : e.actor === 'claimed_person' ? 'Claimed person' : e.actor === 'employee' ? 'Employee' : 'Security',
      e.label,
    ]),
  );

  // 8. Decision
  sectionTitle(ctx, 8, 'Decision');
  facts(ctx, [
    ['Detection', `${riskLevelLabel[incident.riskLevel].toUpperCase()} RISK (${incident.riskScore}/100)`],
    ['Decision', prevented ? 'ACTION PREVENTED' : outcomeLabel[incident.outcome].toUpperCase()],
  ]);
  paragraph(
    ctx,
    prevented
      ? `Reason: voice and contextual signals exceeded the configured high-risk threshold of ${RISK_THRESHOLDS.high}, and the requested action failed independent verification with ${claimed.name}.`
      : `Reason: voice and contextual signals scored ${incident.riskScore} against a high-risk threshold of ${RISK_THRESHOLDS.high}. ${verification.summary}.`,
  );

  // 9. Recommended actions
  sectionTitle(ctx, 9, 'Recommended actions');
  const recommendations = [
    `Do not process ${amount} to ${request.counterparty} without written confirmation through an approved channel.`,
    `Contact ${claimed.name} on the number held in the company directory, not the number that placed this call.`,
    'Preserve the call recording, transcript and signal output attached to this incident.',
    'Review related incidents for the same claimed identity, counterparty or caller number.',
    `Escalate to the fraud team and, if the counterparty is external, notify the bank per organisational policy.`,
    'Confirm the targeted employee has been briefed, and brief the wider department if the pattern repeats.',
  ];
  recommendations.forEach((line, i) => {
    need(ctx, 22);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor(...FOREST);
    doc.text(`${i + 1}.`, M.left, ctx.y + 8);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...INK);
    const lines = doc.splitTextToSize(pdfText(line), CONTENT_W - 20) as string[];
    lines.forEach((l, li) => doc.text(l, M.left + 18, ctx.y + 8 + li * 11));
    ctx.y += lines.length * 11 + 8;
  });

  // 10. Technical appendix
  sectionTitle(ctx, 10, 'Technical appendix');
  paragraph(ctx, 'For the security team. Not shown to the employee receiving the call.', { size: 8 });
  table(
    ctx,
    [
      { label: 'Signal', width: 140 },
      { label: 'Risk', width: 50, align: 'right' },
      { label: 'Weight', width: 55, align: 'right' },
      { label: 'Reading', width: CONTENT_W - 245 },
    ],
    incident.signals.map((s) => [
      signalShortLabel[s.id],
      String(s.risk),
      s.weight > 0 ? s.weight.toFixed(2) : 'context',
      `${s.reading}${s.conclusive ? '' : ' (inconclusive)'}`,
    ]),
  );
  facts(ctx, [
    ['Weighted score', `${incident.riskScore} / 100 (sum of weight × risk ÷ total weight)`],
    ['Thresholds', `medium ${RISK_THRESHOLDS.medium}, high ${RISK_THRESHOLDS.high}`],
    ['Audio processed', `${formatClock(metadata.analysedSec)} of ${formatClock(metadata.durationSec)} · ${metadata.codec}`],
    ['Voice profile impact', incident.voiceProfileUpdate === 'excluded' ? 'Excluded from trusted profile updates' : 'Eligible after verification'],
    ['Report generated by', options.generatedBy],
    ['Data source', `${PRODUCT_NAME} prototype demonstration data`],
  ]);
  paragraph(
    ctx,
    'Signal weights and thresholds are prototype configuration values pending calibration by the model team. This report makes no claim about overall detection accuracy.',
    { size: 8 },
  );

  footer(ctx);
  return doc;
}

export const reportFilename = (incident: Incident) => `Pehchaan-AI-incident-${incident.id}-report.pdf`;

/** Builds the PDF and returns an object URL the UI can download or open. */
export function generateIncidentReport(incident: Incident, options: { generatedBy: string; generatedAtIso: string }) {
  const doc = buildIncidentReport(incident, options);
  const blob = doc.output('blob');
  return {
    url: URL.createObjectURL(blob),
    filename: reportFilename(incident),
    pages: doc.getNumberOfPages(),
    generatedAtIso: options.generatedAtIso,
  };
}
