import { useState } from "react";

const FALLBACK_NOTE =
  "Simulated data conforming to the val-match-v1 schema — production key application pending";

/** The provenance banner. Sticky, on every view, and never dismissible —
 *  only expandable. The honesty is the pitch. */
export default function ProvenanceBanner({ provenance }) {
  const [open, setOpen] = useState(false);
  const note = provenance?.note ?? FALLBACK_NOTE;

  return (
    <div className="banner">
      <div className="banner-inner">
        <span className="banner-dot" aria-hidden="true" />
        <span className="banner-note">
          <strong>Data status:</strong> {note}
        </span>
        {provenance?.detail && (
          <button
            className="banner-toggle"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            {open ? "Less" : "Why?"}
          </button>
        )}
      </div>
      {open && provenance?.detail && <p className="banner-detail">{provenance.detail}</p>}
    </div>
  );
}
