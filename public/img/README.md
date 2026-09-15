# Landing page photographs

This folder is populated by:

```bash
npm run fetch:images
```

That downloads the eight photographs listed in `scripts/fetch-images.mjs` (about 1.5 MB total).
The `.jpg` files are gitignored so the repository stays small; each developer runs the command
once after cloning. If you would rather commit the images, remove `public/img/*.jpg` from
`.gitignore`.

Using your own photography instead: drop files here with the same filenames
(`hero-call.jpg`, `problem-executive.jpg`, `problem-vendor.jpg`, `problem-authority.jpg`,
`case-executive.jpg`, `case-vendor.jpg`, `case-authority.jpg`, `cta.jpg`). Nothing else needs
to change. See `IMAGES.md` in the project root for the subject and crop each slot expects.
