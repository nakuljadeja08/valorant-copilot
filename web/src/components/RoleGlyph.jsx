/* Angular per-role emblems, in the VALORANT tactical-HUD idiom: sharp cuts, no
 * curves. These stand in for agent portraits -- which are Riot's art and cannot
 * be redistributed in a public repo or hotlinked without breaking the build's
 * no-third-party-request guarantee. A glyph is decorative: it is always shown
 * beside the written role label, so nothing is ever conveyed by shape or hue
 * alone. The colours are role identity, not data, and never touch a chart. */

const ROLE_GLYPH = {
  // Duelist -- a forward attack chevron: the entry fragger taking first contact.
  duelist: {
    color: "#ff6a4d",
    paths: ["M6 4 L16 12 L6 20 L10 12 Z", "M13 4 L23 12 L13 20 L17 12 Z"],
  },
  // Controller -- stacked angled planes: map control cut into zones by smokes.
  controller: {
    color: "#a06fe0",
    paths: ["M4 8 L14 3 L24 8 L14 13 Z", "M4 15 L14 10 L24 15 L14 20 Z"],
  },
  // Initiator -- a radiating burst: recon and flashes clearing the way in.
  initiator: {
    color: "#e6c34a",
    paths: [
      "M14 3 L17 11 L14 14 L11 11 Z",
      "M25 14 L17 17 L14 14 L17 11 Z",
      "M14 25 L11 17 L14 14 L17 17 Z",
      "M3 14 L11 11 L14 14 L11 17 Z",
    ],
  },
  // Sentinel -- an angular shield: the anchor holding a site.
  sentinel: {
    color: "#3fbfa3",
    paths: ["M14 3 L24 7 V13 Q24 21 14 25 Q4 21 4 13 V7 Z"],
  },
};

export default function RoleGlyph({ role, size = 34 }) {
  const g = ROLE_GLYPH[role];
  if (!g) return null;
  return (
    <span className="role-glyph" style={{ "--glyph": g.color }} aria-hidden="true">
      <svg width={size} height={size} viewBox="0 0 28 28" fill="none">
        <path
          d="M2 2 L26 2 L26 20 L20 26 L2 26 Z"
          fill="color-mix(in srgb, var(--glyph) 12%, transparent)"
          stroke="color-mix(in srgb, var(--glyph) 55%, transparent)"
          strokeWidth="1"
        />
        {g.paths.map((d, i) => (
          <path key={i} d={d} fill="var(--glyph)" />
        ))}
      </svg>
    </span>
  );
}
