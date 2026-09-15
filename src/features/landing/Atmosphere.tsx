/**
 * Background system for the public pages: soft lavender and pink gradient
 * fields, stippled pigment near the edges, and a fine grain layer over the top.
 * Pure CSS and an inline SVG filter, so there is no image dependency.
 */
export function Atmosphere() {
  return (
    <div className="atmos" aria-hidden="true">
      <span className="atmos__blob atmos__blob--lavender" />
      <span className="atmos__blob atmos__blob--pink" />
      <span className="atmos__blob atmos__blob--violet" />
      <span className="atmos__stipple atmos__stipple--tl" />
      <span className="atmos__stipple atmos__stipple--tr" />
      <span className="atmos__stipple atmos__stipple--br" />
      <span className="atmos__grain" />
    </div>
  );
}
