// Phase 10 demo device: since a live demo can't cleanly close and reopen
// a real browser tab mid-presentation, this full-screen overlay simulates
// "leaving the shopping app" — a generic phone-style home screen with a
// few decorative app icons. It has no real functionality beyond existing
// and being closeable. Closing it calls the SAME idle-check function the
// real useCartAbandonment timer already runs (passed in as onClose) —
// this is not a separate trigger path, just a manual way to force that
// same check at a moment the presenter chooses.
const DECORATIVE_APPS = [
  { emoji: "🌤️", label: "Weather" },
  { emoji: "📝", label: "Notes" },
  { emoji: "📷", label: "Camera" },
  { emoji: "💬", label: "Messages" },
  { emoji: "🎵", label: "Music" },
  { emoji: "📅", label: "Calendar" },
];

export default function LeaveAppOverlay({ onClose }) {
  return (
    <div className="fixed inset-0 z-[100] flex flex-col bg-gradient-to-b from-sky-400 to-indigo-600">
      <div className="flex items-center justify-between px-6 pt-6">
        <p className="text-sm font-medium text-white/80">Demo: simulating "left the app"</p>
        <button
          onClick={onClose}
          className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20 text-white backdrop-blur transition-colors hover:bg-white/30"
          aria-label="Return to shopping app"
        >
          ✕
        </button>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-8">
        <p className="text-lg font-medium text-white/90">Home Screen</p>
        <div className="grid grid-cols-3 gap-6">
          {DECORATIVE_APPS.map((app) => (
            <div key={app.label} className="flex flex-col items-center gap-1.5">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/25 text-3xl backdrop-blur">
                {app.emoji}
              </div>
              <span className="text-xs text-white/80">{app.label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="pb-8 text-center">
        <button
          onClick={onClose}
          className="rounded-full bg-white px-6 py-2.5 text-sm font-semibold text-indigo-700 shadow-lg transition-transform hover:scale-105"
        >
          ← Return to shopping app
        </button>
      </div>
    </div>
  );
}
