/**
 * Landing page photography: one distinct photograph per slot.
 *
 * RULE: never point two slots at the same image. `assertUniqueImagery()` warns
 * in development if that happens. All photographs are free under the Unsplash
 * licence; see IMAGES.md for the credits and the shot list.
 */
/**
 * Photographs are served from `public/img`. Run `npm run fetch:images` once
 * after cloning to populate that folder. Until then (or if a file is missing)
 * the component falls back to the same photograph on Unsplash's CDN, so the
 * page never shows a broken image. Each fallback is also unique.
 */
const remote = (id: string, w = 1600) =>
  `https://images.unsplash.com/photo-${id}?fm=jpg&q=72&w=${w}&auto=format&fit=crop`;

export interface ImageSlot {
  /** Local path under public/img */
  src: string;
  /** Used only if the local file is missing */
  fallback: string;
  alt: string;
  focus?: string;
  credit: string;
  /** Suggested filename if the image is downloaded into public/img/ */
  filename: string;
}

export const imagery = {
  hero: {
    src: '/img/hero-call.jpg',
    fallback: remote('1758873272000-d3763373f863', 2000),
    alt: 'An employee taking a mobile phone call in an open-plan office',
    focus: '74% 38%',
    credit: 'Vitaly Gariev / Unsplash',
    filename: 'hero-call.jpg',
  },
  problemExecutive: {
    src: '/img/executive-call.jpg',
    fallback: remote('1630659508738-74252299fa4d'),
    alt: 'A senior executive seated in an office',
    focus: '50% 35%',
    credit: 'Becomes Co / Unsplash',
    filename: 'executive-call.jpg',
  },
  problemVendor: {
    src: '/img/vendor-payment.jpg',
    fallback: remote('1761914410572-02614b575847'),
    alt: 'A desk with a calculator, charts and payment paperwork',
    focus: '50% 50%',
    credit: 'Cht Gsml / Unsplash',
    filename: 'vendor-payment.jpg',
  },
  problemAuthority: {
    src: '/img/employee-call.jpg',
    fallback: remote('1713947506536-2edbac14d3bb'),
    alt: 'An employee taking a call at her desk while working',
    focus: '55% 40%',
    credit: 'Vitaly Gariev / Unsplash',
    filename: 'employee-call.jpg',
  },
  caseExecutive: {
    src: '/img/case-executive.jpg',
    fallback: remote('1758518731457-5ef826b75b3b'),
    alt: 'Business professionals in a meeting room',
    focus: '50% 40%',
    credit: 'Vitaly Gariev / Unsplash',
    filename: 'case-executive.jpg',
  },
  caseVendor: {
    src: '/img/case-vendor.jpg',
    fallback: remote('1544377193-33dcf4d68fb5'),
    alt: 'A payment authorisation sheet and pen on a desk',
    focus: '50% 50%',
    credit: 'NORTHFOLK / Unsplash',
    filename: 'case-vendor.jpg',
  },
  caseAuthority: {
    src: '/img/case-authority.jpg',
    fallback: remote('1674471361339-2e1e1dbd3e73'),
    alt: 'An employee working at a desk in an office',
    focus: '50% 40%',
    credit: 'Anton Savinov / Unsplash',
    filename: 'case-authority.jpg',
  },
  finalCta: {
    src: '/img/cta-office.jpg',
    fallback: remote('1590649681928-4b179f773bd5', 2000),
    alt: 'Colleagues talking at a standing desk in a glass-walled office',
    focus: '50% 42%',
    credit: 'LinkedIn Sales Solutions / Unsplash',
    filename: 'cta-office.jpg',
  },
} satisfies Record<string, ImageSlot>;

export type ImageKey = keyof typeof imagery;

/** Development guard: every slot must use a different photograph. */
export function assertUniqueImagery() {
  const seen = new Map<string, string>();
  for (const [key, slot] of Object.entries(imagery)) {
    const id = slot.src;
    const first = seen.get(id);
    if (first) {
      console.warn(`[imagery] "${key}" reuses the photograph already used by "${first}". Every slot needs its own image.`);
    } else {
      seen.set(id, key);
    }
  }
}
