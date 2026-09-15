/**
 * What to do after a suspected AI voice-clone call, tailored to what happened.
 * India-specific, checked against official sources (September 2026):
 *
 *  - 1930 / cybercrime.gov.in: national cyber crime helpline and portal, run
 *    24/7 by I4C (Ministry of Home Affairs). Reporting money loss fast lets
 *    banks hold funds before they leave mule accounts ("golden hour").
 *  - Chakshu on Sanchar Saathi (DoT): reporting suspected fraud calls, SMS and
 *    WhatsApp, including impersonation, where no money was lost.
 *  - RBI, 6 July 2017: zero liability for unauthorised electronic transactions
 *    caused by a third-party breach if the bank is told within three working
 *    days of its alert.
 *  - CERT-In directions, 28 April 2022: organisations report incidents such
 *    as identity theft and phishing within 6 hours.
 *  - FTC voice-cloning advice: hang up, verify on a number you already have,
 *    agree a code word.
 *  - WhatsApp Help Center: in-app Report sends recent messages and basic
 *    call info; the other person isn't told.
 */
import type { CallDetails } from '../../services/reportService';

export interface GuidanceLink {
  label: string;
  href: string;
}

export interface GuidanceStep {
  id: string;
  title: string;
  when: 'now' | 'today' | 'this_week';
  summary: string;
  actions: string[];
  links?: GuidanceLink[];
}

export const whenLabel: Record<GuidanceStep['when'], string> = {
  now: 'Do this now',
  today: 'Today',
  this_week: 'This week',
};

export const GUIDANCE_SOURCES: GuidanceLink[] = [
  { label: 'National Cyber Crime Reporting Portal (I4C, MHA)', href: 'https://cybercrime.gov.in/' },
  { label: 'PIB: Chakshu facility of Sanchar Saathi', href: 'https://www.pib.gov.in/PressReleasePage.aspx?PRID=2223779' },
  { label: 'Sanchar Saathi: report suspected fraud communication', href: 'https://sancharsaathi.gov.in/sfc/' },
  { label: 'RBI zero or limited liability for unauthorised transactions (Business Standard)', href: 'https://www.business-standard.com/article/pf/customers-have-zero-to-limited-liability-in-unauthorised-transactions-rbi-118082901378_1.html' },
  { label: 'CERT-In cyber security directions, 2022 (Internet Society brief)', href: 'https://www.internetsociety.org/resources/doc/2022/internet-impact-brief-india-cert-in-cybersecurity-directions-2022/' },
  { label: 'FTC: Fighting back against harmful voice cloning', href: 'https://consumer.ftc.gov/consumer-alerts/2024/04/fighting-back-against-harmful-voice-cloning' },
  { label: 'WhatsApp Help Center: how to block and report someone', href: 'https://faq.whatsapp.com/1142481766359885/' },
];

export function buildGuidance(details: CallDetails): GuidanceStep[] {
  const person = details.claimedName.trim() || 'the person the caller pretended to be';
  const lostMoney = details.outcome === 'sent_money';
  const acted = details.outcome !== 'nothing';
  const official = ['bank', 'government', 'company_support'].includes(details.relationship);
  const onWhatsApp = details.platform === 'whatsapp_voice' || details.platform === 'whatsapp_video';
  const atWork = details.relationship === 'boss_colleague' || details.organisation.trim() !== '';
  const amount = Number(details.amountInr) > 0 ? `₹${Number(details.amountInr).toLocaleString('en-IN')}` : 'the amount';

  const steps: GuidanceStep[] = [];

  if (lostMoney) {
    steps.push(
      {
        id: 'call-1930',
        title: 'Call 1930 right now',
        when: 'now',
        summary:
          "1930 is India's national cyber crime helpline, open 24 hours and run by the Indian Cyber Crime Coordination Centre. Money sent to a fraudster usually waits briefly in a mule account, so reporting within the first hour gives banks the best chance to hold it.",
        actions: [
          'Dial 1930 and say you sent money after an impersonation call.',
          `Give ${amount}, the payment method (${details.paymentMethod.replace('_', ' ')}), the transaction ID or UTR${details.transactionRef.trim() ? ` (${details.transactionRef.trim()})` : ''} and the time you paid.`,
          'Write down the acknowledgement number they give you. You will need it for the complaint.',
        ],
        links: [{ label: 'Call 1930', href: 'tel:1930' }],
      },
      {
        id: 'bank',
        title: 'Tell your bank',
        when: 'now',
        summary: 'Your bank can flag the transaction, block further payments and start a fraud dispute.',
        actions: [
          "Call the customer care number printed on your card or on the bank's official website, never a number from the caller or a search ad.",
          'Ask them to block the card or UPI you used and to raise a fraud complaint for the transaction.',
          'If any payment went out without your approval, for example after you shared an OTP, RBI rules give zero liability only if you tell the bank within three working days of its alert. Do it today.',
        ],
      },
    );
  }

  steps.push(
    {
      id: 'stop',
      title: 'Stop talking to the caller',
      when: 'now',
      summary: 'Voice-clone scams run on pressure and panic. Ending the call removes both.',
      actions: [
        'Hang up. If they call again, don\'t answer.',
        "Don't send money, OTPs, PINs or passwords, however urgent or upset the voice sounds.",
        "Don't call back the number that called you or any number they gave you.",
        "Don't open links or install apps they sent.",
      ],
    },
    {
      id: 'verify',
      title: 'Check with the real person',
      when: 'now',
      summary: 'A cloned voice can sound exactly like someone you know. Confirm through a channel the caller does not control.',
      actions: [
        official
          ? "Call the organisation on the number from its official website, your card or a statement. Real banks, police and officials never ask for OTPs, or for money to 'settle' a case over a call."
          : `Call ${person} on the number already saved in your phone, not the one that called you.`,
        details.relationship === 'family' || details.relationship === 'friend'
          ? "If you can't reach them, contact someone who is with them, such as another family member or friend."
          : 'If they are unreachable, confirm through someone else who knows them, such as a manager or the office line.',
        'Ask something only the real person would know.',
      ],
    },
  );

  const sharedSensitive = acted && details.requests.some((r) => r === 'otp' || r === 'bank_details' || r === 'personal_info' || r === 'remote_app');
  if (sharedSensitive) {
    steps.push({
      id: 'secure',
      title: 'Lock down your accounts',
      when: 'now',
      summary: 'Anything you shared can be used for a second attack, often within minutes.',
      actions: [
        ...(details.requests.includes('otp') || details.requests.includes('bank_details')
          ? ['Ask your bank to block the card or UPI linked to anything you shared, and change your UPI PIN and net banking password.']
          : []),
        ...(details.requests.includes('remote_app')
          ? ['Uninstall any screen-sharing or remote-access app they asked you to install, then check your bank and email for logins you don\'t recognise.']
          : []),
        'Change passwords you might have revealed and turn on two-step verification for WhatsApp, email and banking apps.',
        ...(details.requests.includes('personal_info')
          ? ['Expect follow-up calls that use the details you shared to sound convincing. Treat them the same way.']
          : []),
      ],
    });
  }

  steps.push({
    id: 'evidence',
    title: 'Save the evidence',
    when: 'today',
    summary: 'Police, banks and platforms act faster with clear evidence, and some of it disappears if you clean up your phone.',
    actions: [
      "Don't delete the call log, the chat or the caller's number.",
      "Take screenshots of the caller's number, name and profile photo, and of any messages.",
      ...(lostMoney ? ['Keep the payment receipt, the UTR or transaction ID, and the bank SMS alerts.'] : []),
      'Download or print this report and keep the original recording, if you have one.',
    ],
  });

  steps.push(
    lostMoney
      ? {
          id: 'complaint',
          title: 'File a complaint on cybercrime.gov.in',
          when: 'today',
          summary: 'The online complaint is the formal record police and banks work from. It follows up your 1930 call.',
          actions: [
            'Open cybercrime.gov.in and choose to report a financial fraud.',
            'Add your 1930 acknowledgement number, the transaction details and the caller\'s number.',
            'Attach this report and your screenshots and receipts, and note the complaint number.',
          ],
          links: [{ label: 'Open cybercrime.gov.in', href: 'https://cybercrime.gov.in/' }],
        }
      : {
          id: 'chakshu',
          title: 'Report the number on Sanchar Saathi (Chakshu)',
          when: 'today',
          summary:
            "Chakshu, from the Department of Telecommunications, takes reports of suspected fraud calls, SMS and WhatsApp, including impersonation, when no money was lost. Reported numbers can be disconnected.",
          actions: [
            'Open Sanchar Saathi on the web or in its app and choose Chakshu, report suspected fraud communication.',
            'Pick the impersonation category, then add the number, the date and time and a short description.',
            'If you later find you lost money, call 1930 instead. Chakshu is for cases without financial loss.',
          ],
          links: [{ label: 'Open Chakshu', href: 'https://sancharsaathi.gov.in/sfc/' }],
        },
  );

  if (onWhatsApp) {
    steps.push({
      id: 'whatsapp',
      title: 'Block and report the number on WhatsApp',
      when: 'today',
      summary: 'Reporting in the app lets WhatsApp act on the account. The other person is not told.',
      actions: [
        "Open the chat with the caller's number, tap the name or the menu, and choose Report.",
        'Then block the number so it can\'t call or message you again.',
        'WhatsApp receives the last few messages and basic information about recent calls with that number, so you don\'t need to send anything else.',
      ],
      links: [{ label: 'WhatsApp: block and report', href: 'https://faq.whatsapp.com/1142481766359885/' }],
    });
  }

  if (atWork) {
    steps.push({
      id: 'workplace',
      title: "Tell your organisation's security team",
      when: 'today',
      summary: 'Attackers who clone an executive or colleague usually try several people in the same company.',
      actions: [
        'Send this report to your IT or security team, or your manager, through an official channel.',
        "Keep any request from the call on hold until it's confirmed.",
        'Organisations in India must report cyber incidents such as identity theft and phishing to CERT-In within 6 hours of noticing them. Your security team handles that.',
      ],
    });
  }

  steps.push({
    id: 'warn',
    title: 'Warn the person and the people around you',
    when: 'this_week',
    summary: 'A voice can be cloned from a few seconds of video or voice notes posted online, so the same caller will try again.',
    actions: [
      `Tell ${person} that someone is imitating their voice.`,
      'Agree a family or team code word to ask for in any urgent call about money.',
      'Consider making public videos and voice notes private.',
      'Tell friends, family or colleagues about this caller so they are ready for it.',
    ],
  });

  return steps;
}
