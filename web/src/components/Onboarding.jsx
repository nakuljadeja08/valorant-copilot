import { useEffect, useRef } from "react";

const BASE = import.meta.env.BASE_URL;

const STEPS = [
  { n: "01", verb: "Read", accent: "brand", text: "The verdict, up front on every match." },
  { n: "02", verb: "Trace", accent: "blue", text: "One click to the rows behind it." },
  { n: "03", verb: "Trust", accent: "good", text: "Verified, or it never prints." },
];

/* First-run overlay. Dismiss is persisted by the shell (localStorage), and the
   rail's "?" button replays it. A real modal: Escape and the backdrop close it,
   focus lands on the primary action, and the surrounding app is inert to
   assistive tech via aria-hidden on the shell (set by the caller is overkill --
   here we simply trap the initial focus and return the verdict). */

export default function Onboarding({ onClose }) {
  const primaryRef = useRef(null);

  useEffect(() => {
    primaryRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="onboard" role="dialog" aria-modal="true" aria-labelledby="onboard-title">
        <div className="onboard-edge" aria-hidden="true" />
        <img
          className="onboard-art"
          src={`${BASE}assets/keyart-launch.png`}
          alt=""
          aria-hidden="true"
        />
        <div className="onboard-body">
          <div className="onboard-lockup">
            <span className="rail-mark" aria-hidden="true" />
            <span className="onboard-word">
              Coaching <span className="wordmark-accent">Copilot</span>
            </span>
          </div>

          <div className="onboard-kicker">// First deploy</div>
          <h2 id="onboard-title" className="onboard-title">
            Coaching that shows
            <br />
            its work.
          </h2>
          <p className="onboard-lede">
            Every claim expands into the rounds it was computed from. No number reaches you
            unless a Watchdog re-checked it against the store. Read the verdict — then pull the
            trace.
          </p>

          <div className="onboard-steps">
            {STEPS.map((s) => (
              <div key={s.n} className={`onboard-step accent-${s.accent}`}>
                <div className="onboard-step-head">
                  {s.n} · {s.verb}
                </div>
                <div className="onboard-step-text">{s.text}</div>
              </div>
            ))}
          </div>

          <div className="onboard-actions">
            <button ref={primaryRef} type="button" className="onboard-enter" onClick={onClose}>
              Enter the client
            </button>
            <span className="onboard-note">
              <span className="onboard-note-dot" aria-hidden="true" />
              SIM DATA · production key pending
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
