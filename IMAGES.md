# Pehchaan AI landing page photography

8 slots, 8 different photographs. **Never point two slots at the same image.**
`assertUniqueImagery()` runs on mount in development and warns if a duplicate appears.

The hero uses ONE photograph. The other photographs belong to the problem, case-study and CTA
sections, so each section carries its own visual story.

| Slot | Suggested filename | Subject | Credit |
| --- | --- | --- | --- |
| `hero` | hero-call.jpg | An employee taking a mobile phone call in an open-plan office | Vitaly Gariev / Unsplash |
| `problemExecutive` | executive-call.jpg | A senior executive seated in an office | Becomes Co / Unsplash |
| `problemVendor` | vendor-payment.jpg | A desk with a calculator, charts and payment paperwork | Cht Gsml / Unsplash |
| `problemAuthority` | employee-call.jpg | An employee taking a call at her desk while working | Vitaly Gariev / Unsplash |
| `caseExecutive` | case-executive.jpg | Business professionals in a meeting room | Vitaly Gariev / Unsplash |
| `caseVendor` | case-vendor.jpg | A payment authorisation sheet and pen on a desk | NORTHFOLK / Unsplash |
| `caseAuthority` | case-authority.jpg | An employee working at a desk in an office | Anton Savinov / Unsplash |
| `finalCta` | cta-office.jpg | Colleagues talking at a standing desk in a glass-walled office | LinkedIn Sales Solutions / Unsplash |

All free under the [Unsplash licence](https://unsplash.com/license); the footer credits the photographers.

## Before the demo: download them locally

Images load from Unsplash's CDN, so the page needs internet at presentation time. Save each file
into `public/img/` with the filename above and point the slot at it:

```ts
hero: { src: '/img/hero-call.jpg', alt: '...', focus: '58% 38%', credit: '...', filename: 'hero-call.jpg' },
```

## Replacing a photograph

Change `src` on that slot in `src/features/landing/imagery.ts`. `focus` is the CSS object-position;
adjust it so the subject stays in frame. For the hero, pick a shot with the subject left or centre:
the call panel sits over the photograph's lower-left corner and must not cover a face.
