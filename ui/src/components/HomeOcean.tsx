import "./home-ocean.css";
import "./ocean.css";

export default function HomeOcean() {
  return (
    <>
      {/* Deep haze (blue-shifted, unique to home) */}
      <div className="home-caustics" />

      {/* Light rays (shared CSS from ocean.css) */}
      <div className="light-rays">
        <div className="light-ray" style={{ left: "15%", animationDelay: "0s" }} />
        <div className="light-ray" style={{ left: "40%", width: 80, opacity: 0.5, animationDelay: "3s" }} />
        <div className="light-ray" style={{ left: "65%", width: 70, animationDelay: "5s" }} />
        <div className="light-ray" style={{ left: "85%", width: 55, opacity: 0.4, animationDelay: "1.5s" }} />
      </div>

      {/* Marine snow (replaces plankton) */}
      <div className="marine-snow">
        <div className="snow-p" style={{ left: "8%", top: -10, width: 2, height: 2, background: "rgba(200,220,240,0.2)", animationDuration: "18s" }} />
        <div className="snow-p" style={{ left: "22%", top: -10, width: 1.5, height: 1.5, background: "rgba(200,220,240,0.15)", animationDuration: "22s", animationDelay: "3s" }} />
        <div className="snow-p" style={{ left: "45%", top: -10, width: 2, height: 2, background: "rgba(200,220,240,0.18)", animationDuration: "20s", animationDelay: "7s" }} />
        <div className="snow-p" style={{ left: "65%", top: -10, width: 1.5, height: 1.5, background: "rgba(200,220,240,0.12)", animationDuration: "25s", animationDelay: "2s" }} />
        <div className="snow-p" style={{ left: "82%", top: -10, width: 2, height: 2, background: "rgba(200,220,240,0.2)", animationDuration: "19s", animationDelay: "10s" }} />
        <div className="snow-p" style={{ left: "35%", top: -10, width: 1, height: 1, background: "rgba(200,220,240,0.15)", animationDuration: "24s", animationDelay: "5s" }} />
        <div className="snow-p" style={{ left: "55%", top: -10, width: 2, height: 2, background: "rgba(200,220,240,0.1)", animationDuration: "21s", animationDelay: "12s" }} />
        <div className="snow-p" style={{ left: "90%", top: -10, width: 1.5, height: 1.5, background: "rgba(200,220,240,0.18)", animationDuration: "17s", animationDelay: "8s" }} />
      </div>

      {/* Bubbles (shared CSS from ocean.css) */}
      <div className="bubbles">
        <div className="bubble" style={{ left: "20%", bottom: 0, width: 5, height: 5, animationDuration: "15s" }} />
        <div className="bubble" style={{ left: "55%", bottom: 0, width: 6, height: 6, animationDuration: "19s", animationDelay: "4s" }} />
        <div className="bubble" style={{ left: "75%", bottom: 0, width: 4, height: 4, animationDuration: "16s", animationDelay: "7s" }} />
        <div className="bubble" style={{ left: "40%", bottom: 0, width: 3, height: 3, animationDuration: "21s", animationDelay: "11s" }} />
      </div>

      {/* ═══ WHALE — upper left ═══ */}
      <div className="whale" style={{ top: "14%", left: "4%" }}>
        <div className="whale-head">
          <div className="whale-eye" />
        </div>
        <div className="whale-body" />
        <div className="whale-dorsal" />
        <div className="whale-pec" />
        <div className="whale-fluke">
          <div className="fluke-lobe-top" />
          <div className="fluke-lobe-bottom" />
        </div>
      </div>

      {/* ═══ HAMMERHEAD SHARK — mid right ═══ */}
      <div className="hammerhead" style={{ top: "42%", right: "5%" }}>
        <div className="hammerhead-hammer">
          <div className="hammerhead-eye-l" />
          <div className="hammerhead-eye-r" />
        </div>
        <div className="hammerhead-body" />
        <div className="hammerhead-dorsal" />
        <div className="hammerhead-pec-l" />
        <div className="hammerhead-pec-r" />
        <div className="hammerhead-tail">
          <div className="hammerhead-tail-top" />
          <div className="hammerhead-tail-bottom" />
        </div>
      </div>

      {/* ═══ OCEAN FLOOR — unique coral/flora ═══ */}
      <div className="ocean-floor">
        {/* Sea fan — left */}
        <div className="sea-fan" style={{ left: 35 }}>
          <div className="fan-trunk" style={{ height: 75, background: "linear-gradient(0deg, rgba(255,77,142,0.3), rgba(255,77,142,0.06))" }}>
            <div className="fan-branch" style={{ height: 32, left: -9, bottom: 42, background: "linear-gradient(0deg, rgba(255,77,142,0.25), rgba(255,77,142,0.04))", transform: "rotate(-25deg)" }} />
            <div className="fan-branch" style={{ height: 24, left: -15, bottom: 58, background: "linear-gradient(0deg, rgba(255,77,142,0.2), rgba(255,77,142,0.03))", transform: "rotate(-35deg)" }} />
            <div className="fan-branch" style={{ height: 30, right: -9, bottom: 46, background: "linear-gradient(0deg, rgba(255,77,142,0.25), rgba(255,77,142,0.04))", transform: "rotate(22deg)" }} />
            <div className="fan-branch" style={{ height: 20, right: -13, bottom: 62, background: "linear-gradient(0deg, rgba(255,77,142,0.2), rgba(255,77,142,0.03))", transform: "rotate(32deg)" }} />
          </div>
        </div>
        <div className="sea-fan" style={{ left: 65, animationDelay: "2s" }}>
          <div className="fan-trunk" style={{ height: 52, background: "linear-gradient(0deg, rgba(255,77,142,0.22), rgba(255,77,142,0.04))" }}>
            <div className="fan-branch" style={{ height: 22, left: -7, bottom: 30, background: "linear-gradient(0deg, rgba(255,77,142,0.18), rgba(255,77,142,0.03))", transform: "rotate(-22deg)" }} />
            <div className="fan-branch" style={{ height: 20, right: -7, bottom: 34, background: "linear-gradient(0deg, rgba(255,77,142,0.18), rgba(255,77,142,0.03))", transform: "rotate(24deg)" }} />
          </div>
        </div>

        {/* Tube worms — center left */}
        <div className="tube-worm-cluster" style={{ left: 150 }}>
          <div className="tube-worm" style={{ height: 30, background: "linear-gradient(0deg, rgba(255,107,53,0.35), rgba(255,107,53,0.08))" }}>
            <div className="worm-bloom" style={{ background: "rgba(255,107,53,0.4)", boxShadow: "0 0 6px rgba(255,107,53,0.3)" }} />
          </div>
          <div className="tube-worm" style={{ height: 38, background: "linear-gradient(0deg, rgba(255,107,53,0.3), rgba(255,107,53,0.06))", animationDelay: "0.5s" }}>
            <div className="worm-bloom" style={{ background: "rgba(255,107,53,0.35)", boxShadow: "0 0 6px rgba(255,107,53,0.25)", animationDelay: "0.5s" }} />
          </div>
          <div className="tube-worm" style={{ height: 24, background: "linear-gradient(0deg, rgba(255,107,53,0.3), rgba(255,107,53,0.06))", animationDelay: "1s" }}>
            <div className="worm-bloom" style={{ background: "rgba(255,107,53,0.3)", boxShadow: "0 0 6px rgba(255,107,53,0.2)", animationDelay: "1s" }} />
          </div>
          <div className="tube-worm" style={{ height: 32, background: "linear-gradient(0deg, rgba(255,107,53,0.28), rgba(255,107,53,0.05))", animationDelay: "1.5s" }}>
            <div className="worm-bloom" style={{ background: "rgba(255,107,53,0.35)", boxShadow: "0 0 6px rgba(255,107,53,0.25)", animationDelay: "1.5s" }} />
          </div>
        </div>

        {/* Staghorn coral — right */}
        <div className="staghorn" style={{ right: 45 }}>
          <div className="stag-branch" style={{ height: 48, left: 0, background: "linear-gradient(0deg, rgba(168,85,247,0.3), rgba(168,85,247,0.06))", transform: "rotate(-8deg)" }}>
            <div className="stag-tip" style={{ background: "rgba(168,85,247,0.25)" }} />
          </div>
          <div className="stag-branch" style={{ height: 60, left: 12, background: "linear-gradient(0deg, rgba(168,85,247,0.35), rgba(168,85,247,0.08))", transform: "rotate(-2deg)" }}>
            <div className="stag-tip" style={{ background: "rgba(168,85,247,0.3)" }} />
          </div>
          <div className="stag-branch" style={{ height: 42, left: 24, background: "linear-gradient(0deg, rgba(168,85,247,0.28), rgba(168,85,247,0.05))", transform: "rotate(5deg)" }}>
            <div className="stag-tip" style={{ background: "rgba(168,85,247,0.22)" }} />
          </div>
          <div className="stag-branch" style={{ height: 52, left: 36, background: "linear-gradient(0deg, rgba(168,85,247,0.3), rgba(168,85,247,0.06))", transform: "rotate(10deg)" }}>
            <div className="stag-tip" style={{ background: "rgba(168,85,247,0.25)" }} />
          </div>
        </div>

        {/* Sea fan — right */}
        <div className="sea-fan" style={{ right: 25, animationDelay: "4s" }}>
          <div className="fan-trunk" style={{ height: 62, background: "linear-gradient(0deg, rgba(76,224,210,0.25), rgba(76,224,210,0.04))" }}>
            <div className="fan-branch" style={{ height: 26, left: -8, bottom: 36, background: "linear-gradient(0deg, rgba(76,224,210,0.2), rgba(76,224,210,0.03))", transform: "rotate(-22deg)" }} />
            <div className="fan-branch" style={{ height: 22, right: -8, bottom: 40, background: "linear-gradient(0deg, rgba(76,224,210,0.2), rgba(76,224,210,0.03))", transform: "rotate(25deg)" }} />
          </div>
        </div>

        {/* Tube worms — right */}
        <div className="tube-worm-cluster" style={{ right: 130 }}>
          <div className="tube-worm" style={{ height: 22, background: "linear-gradient(0deg, rgba(42,255,160,0.3), rgba(42,255,160,0.06))", animationDelay: "0.3s" }}>
            <div className="worm-bloom" style={{ background: "rgba(42,255,160,0.35)", boxShadow: "0 0 6px rgba(42,255,160,0.25)", animationDelay: "0.3s" }} />
          </div>
          <div className="tube-worm" style={{ height: 28, background: "linear-gradient(0deg, rgba(42,255,160,0.25), rgba(42,255,160,0.05))", animationDelay: "0.8s" }}>
            <div className="worm-bloom" style={{ background: "rgba(42,255,160,0.3)", boxShadow: "0 0 6px rgba(42,255,160,0.2)", animationDelay: "0.8s" }} />
          </div>
          <div className="tube-worm" style={{ height: 18, background: "linear-gradient(0deg, rgba(42,255,160,0.28), rgba(42,255,160,0.05))", animationDelay: "1.3s" }}>
            <div className="worm-bloom" style={{ background: "rgba(42,255,160,0.3)", boxShadow: "0 0 6px rgba(42,255,160,0.2)", animationDelay: "1.3s" }} />
          </div>
        </div>
      </div>
    </>
  );
}
