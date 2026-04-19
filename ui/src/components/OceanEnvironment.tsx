import "./ocean.css";

export default function OceanEnvironment() {
  return (
    <>
      {/* Caustic light */}
      <div className="caustics" />

      {/* Light rays */}
      <div className="light-rays">
        <div className="light-ray" style={{ left: "12%", animationDelay: "0s" }} />
        <div className="light-ray" style={{ left: "35%", width: 70, opacity: 0.6, animationDelay: "2.5s" }} />
        <div className="light-ray" style={{ left: "58%", width: 90, animationDelay: "4s" }} />
        <div className="light-ray" style={{ left: "82%", width: 60, opacity: 0.5, animationDelay: "1s" }} />
      </div>

      {/* Bioluminescent plankton */}
      <div className="plankton">
        <div className="p-dot" style={{ left: "6%", top: "22%", width: 3, height: 3, background: "rgba(76,224,210,0.5)", boxShadow: "0 0 8px rgba(76,224,210,0.4)", animationDuration: "4s" }} />
        <div className="p-dot" style={{ left: "18%", top: "58%", width: 2, height: 2, background: "rgba(42,255,160,0.5)", boxShadow: "0 0 6px rgba(42,255,160,0.3)", animationDuration: "5s", animationDelay: "1s" }} />
        <div className="p-dot" style={{ left: "85%", top: "32%", width: 3, height: 3, background: "rgba(168,85,247,0.4)", boxShadow: "0 0 10px rgba(168,85,247,0.3)", animationDuration: "6s", animationDelay: "2s" }} />
        <div className="p-dot" style={{ left: "70%", top: "72%", width: 2, height: 2, background: "rgba(76,224,210,0.4)", boxShadow: "0 0 6px rgba(76,224,210,0.3)", animationDuration: "3.5s", animationDelay: "0.5s" }} />
        <div className="p-dot" style={{ left: "42%", top: "12%", width: 2, height: 2, background: "rgba(42,255,160,0.3)", boxShadow: "0 0 6px rgba(42,255,160,0.2)", animationDuration: "7s", animationDelay: "3s" }} />
        <div className="p-dot" style={{ left: "30%", top: "82%", width: 3, height: 3, background: "rgba(168,85,247,0.3)", boxShadow: "0 0 8px rgba(168,85,247,0.2)", animationDuration: "5.5s", animationDelay: "2.5s" }} />
        <div className="p-dot" style={{ left: "55%", top: "45%", width: 2, height: 2, background: "rgba(76,224,210,0.35)", boxShadow: "0 0 5px rgba(76,224,210,0.3)", animationDuration: "4.5s", animationDelay: "1.5s" }} />
        <div className="p-dot" style={{ left: "92%", top: "65%", width: 2, height: 2, background: "rgba(42,255,160,0.4)", boxShadow: "0 0 6px rgba(42,255,160,0.3)", animationDuration: "6.5s", animationDelay: "4s" }} />
      </div>

      {/* Bubbles */}
      <div className="bubbles">
        <div className="bubble" style={{ left: "15%", bottom: 0, width: 6, height: 6, animationDuration: "13s" }} />
        <div className="bubble" style={{ left: "38%", bottom: 0, width: 4, height: 4, animationDuration: "16s", animationDelay: "3s" }} />
        <div className="bubble" style={{ left: "62%", bottom: 0, width: 7, height: 7, animationDuration: "18s", animationDelay: "1s" }} />
        <div className="bubble" style={{ left: "80%", bottom: 0, width: 5, height: 5, animationDuration: "14s", animationDelay: "5s" }} />
        <div className="bubble" style={{ left: "50%", bottom: 0, width: 3, height: 3, animationDuration: "20s", animationDelay: "7s" }} />
        <div className="bubble" style={{ left: "25%", bottom: 0, width: 4, height: 4, animationDuration: "17s", animationDelay: "9s" }} />
        <div className="bubble" style={{ left: "72%", bottom: 0, width: 5, height: 5, animationDuration: "15s", animationDelay: "2s" }} />
      </div>

      {/* Jellyfish — purple, near card left */}
      <div className="jellyfish jf1" style={{ top: "22%", left: "8%" }}>
        <div className="jelly-body" style={{ width: 45, height: 34, background: "radial-gradient(ellipse at 40% 30%, rgba(168,85,247,0.3), rgba(168,85,247,0.08) 50%, rgba(168,85,247,0.02))", boxShadow: "0 0 25px rgba(168,85,247,0.2), 0 0 50px rgba(168,85,247,0.06)" }} />
        <div className="jelly-tentacles">
          <div className="jelly-t" style={{ height: 40, background: "linear-gradient(180deg, rgba(168,85,247,0.25), transparent)" }} />
          <div className="jelly-t" style={{ height: 50, background: "linear-gradient(180deg, rgba(200,140,255,0.2), transparent)", animationDelay: "0.3s" }} />
          <div className="jelly-t" style={{ height: 35, background: "linear-gradient(180deg, rgba(168,85,247,0.25), transparent)", animationDelay: "0.6s" }} />
          <div className="jelly-t" style={{ height: 45, background: "linear-gradient(180deg, rgba(200,140,255,0.15), transparent)", animationDelay: "0.9s" }} />
          <div className="jelly-t" style={{ height: 30, background: "linear-gradient(180deg, rgba(168,85,247,0.2), transparent)", animationDelay: "1.2s" }} />
        </div>
      </div>

      {/* Jellyfish — cyan, right side */}
      <div className="jellyfish jf2" style={{ top: "35%", right: "6%" }}>
        <div className="jelly-body" style={{ width: 32, height: 24, background: "radial-gradient(ellipse at 40% 30%, rgba(76,224,210,0.25), rgba(76,224,210,0.06) 50%, transparent)", boxShadow: "0 0 20px rgba(76,224,210,0.12)" }} />
        <div className="jelly-tentacles">
          <div className="jelly-t" style={{ height: 28, background: "linear-gradient(180deg, rgba(76,224,210,0.2), transparent)", animationDelay: "0.2s" }} />
          <div className="jelly-t" style={{ height: 35, background: "linear-gradient(180deg, rgba(76,224,210,0.15), transparent)", animationDelay: "0.5s" }} />
          <div className="jelly-t" style={{ height: 25, background: "linear-gradient(180deg, rgba(76,224,210,0.2), transparent)", animationDelay: "0.8s" }} />
        </div>
      </div>

      {/* Jellyfish — orange, small background */}
      <div className="jellyfish jf3" style={{ top: "60%", left: "82%", opacity: 0.5 }}>
        <div className="jelly-body" style={{ width: 18, height: 14, background: "radial-gradient(ellipse at 40% 30%, rgba(255,107,53,0.25), rgba(255,107,53,0.04))", boxShadow: "0 0 12px rgba(255,107,53,0.12)" }} />
        <div className="jelly-tentacles">
          <div className="jelly-t" style={{ height: 16, background: "linear-gradient(180deg, rgba(255,107,53,0.18), transparent)", animationDelay: "0.4s" }} />
          <div className="jelly-t" style={{ height: 20, background: "linear-gradient(180deg, rgba(255,107,53,0.12), transparent)", animationDelay: "0.7s" }} />
          <div className="jelly-t" style={{ height: 14, background: "linear-gradient(180deg, rgba(255,107,53,0.18), transparent)", animationDelay: "1s" }} />
        </div>
      </div>

      {/* Jellyfish — green, left mid */}
      <div className="jellyfish jf4" style={{ top: "50%", left: "15%", opacity: 0.6 }}>
        <div className="jelly-body" style={{ width: 28, height: 22, background: "radial-gradient(ellipse at 40% 30%, rgba(42,255,160,0.25), rgba(42,255,160,0.06) 50%, transparent)", boxShadow: "0 0 18px rgba(42,255,160,0.12)" }} />
        <div className="jelly-tentacles">
          <div className="jelly-t" style={{ height: 22, background: "linear-gradient(180deg, rgba(42,255,160,0.2), transparent)", animationDelay: "0.1s" }} />
          <div className="jelly-t" style={{ height: 28, background: "linear-gradient(180deg, rgba(42,255,160,0.15), transparent)", animationDelay: "0.4s" }} />
          <div className="jelly-t" style={{ height: 18, background: "linear-gradient(180deg, rgba(42,255,160,0.2), transparent)", animationDelay: "0.7s" }} />
          <div className="jelly-t" style={{ height: 24, background: "linear-gradient(180deg, rgba(42,255,160,0.12), transparent)", animationDelay: "1s" }} />
        </div>
      </div>

      {/* Jellyfish — purple, right low */}
      <div className="jellyfish jf5" style={{ top: "68%", right: "18%", opacity: 0.45 }}>
        <div className="jelly-body" style={{ width: 22, height: 16, background: "radial-gradient(ellipse at 40% 30%, rgba(168,85,247,0.22), rgba(168,85,247,0.05) 50%, transparent)", boxShadow: "0 0 14px rgba(168,85,247,0.1)" }} />
        <div className="jelly-tentacles">
          <div className="jelly-t" style={{ height: 18, background: "linear-gradient(180deg, rgba(168,85,247,0.18), transparent)", animationDelay: "0.3s" }} />
          <div className="jelly-t" style={{ height: 22, background: "linear-gradient(180deg, rgba(168,85,247,0.12), transparent)", animationDelay: "0.6s" }} />
          <div className="jelly-t" style={{ height: 15, background: "linear-gradient(180deg, rgba(168,85,247,0.18), transparent)", animationDelay: "0.9s" }} />
        </div>
      </div>

      {/* Jellyfish — large cyan, upper center-left */}
      <div className="jellyfish jf6" style={{ top: "15%", left: "28%", opacity: 0.35 }}>
        <div className="jelly-body" style={{ width: 38, height: 28, background: "radial-gradient(ellipse at 40% 30%, rgba(76,224,210,0.2), rgba(76,224,210,0.05) 50%, transparent)", boxShadow: "0 0 22px rgba(76,224,210,0.1)" }} />
        <div className="jelly-tentacles">
          <div className="jelly-t" style={{ height: 32, background: "linear-gradient(180deg, rgba(76,224,210,0.15), transparent)" }} />
          <div className="jelly-t" style={{ height: 40, background: "linear-gradient(180deg, rgba(76,224,210,0.1), transparent)", animationDelay: "0.3s" }} />
          <div className="jelly-t" style={{ height: 28, background: "linear-gradient(180deg, rgba(76,224,210,0.15), transparent)", animationDelay: "0.6s" }} />
          <div className="jelly-t" style={{ height: 36, background: "linear-gradient(180deg, rgba(76,224,210,0.08), transparent)", animationDelay: "0.9s" }} />
          <div className="jelly-t" style={{ height: 24, background: "linear-gradient(180deg, rgba(76,224,210,0.12), transparent)", animationDelay: "1.2s" }} />
        </div>
      </div>

      {/* Jellyfish — tiny pink, far right */}
      <div className="jellyfish jf3" style={{ top: "42%", right: "4%", opacity: 0.4 }}>
        <div className="jelly-body" style={{ width: 14, height: 10, background: "radial-gradient(ellipse at 40% 30%, rgba(255,77,142,0.2), rgba(255,77,142,0.04))", boxShadow: "0 0 10px rgba(255,77,142,0.1)" }} />
        <div className="jelly-tentacles">
          <div className="jelly-t" style={{ height: 12, background: "linear-gradient(180deg, rgba(255,77,142,0.15), transparent)", animationDelay: "0.2s" }} />
          <div className="jelly-t" style={{ height: 16, background: "linear-gradient(180deg, rgba(255,77,142,0.1), transparent)", animationDelay: "0.5s" }} />
        </div>
      </div>

      {/* Fish school — original */}
      <div className="fish-school" style={{ top: "30%", animation: "school-swim 30s linear infinite", animationDelay: "3s" }}>
        <div className="fish" style={{ left: 0, top: 0 }}><div className="fish-body"><div className="fish-tail" /></div></div>
        <div className="fish" style={{ left: 18, top: 10 }}><div className="fish-body"><div className="fish-tail" /></div></div>
        <div className="fish" style={{ left: 8, top: -7 }}><div className="fish-body"><div className="fish-tail" /></div></div>
        <div className="fish" style={{ left: 30, top: 4 }}><div className="fish-body"><div className="fish-tail" /></div></div>
      </div>

      {/* Fish school 2 — higher, reversed */}
      <div className="fish-school fish-school-reverse" style={{ top: "18%", animation: "school-swim-reverse 35s linear infinite", animationDelay: "8s" }}>
        <div className="fish fish-reverse" style={{ left: 0, top: 0 }}><div className="fish-body"><div className="fish-tail" /></div></div>
        <div className="fish fish-reverse" style={{ left: 20, top: 8 }}><div className="fish-body"><div className="fish-tail" /></div></div>
        <div className="fish fish-reverse" style={{ left: 10, top: -5 }}><div className="fish-body"><div className="fish-tail" /></div></div>
        <div className="fish fish-reverse" style={{ left: 35, top: 3 }}><div className="fish-body"><div className="fish-tail" /></div></div>
        <div className="fish fish-reverse" style={{ left: 25, top: -10 }}><div className="fish-body"><div className="fish-tail" /></div></div>
      </div>

      {/* Fish school 3 — lower, small group */}
      <div className="fish-school" style={{ top: "55%", animation: "school-swim 25s linear infinite", animationDelay: "15s" }}>
        <div className="fish" style={{ left: 0, top: 0 }}><div className="fish-body fish-body-purple"><div className="fish-tail fish-tail-purple" /></div></div>
        <div className="fish" style={{ left: 15, top: 6 }}><div className="fish-body fish-body-purple"><div className="fish-tail fish-tail-purple" /></div></div>
        <div className="fish" style={{ left: 8, top: -4 }}><div className="fish-body fish-body-purple"><div className="fish-tail fish-tail-purple" /></div></div>
      </div>

      {/* Ocean floor */}
      <div className="ocean-floor">
        {/* Left kelp */}
        <div className="kelp" style={{ left: 30, height: 130, width: 5, background: "linear-gradient(0deg, rgba(42,255,160,0.35), rgba(42,255,160,0.04))", animationDuration: "8s" }} />
        <div className="kelp" style={{ left: 45, height: 95, width: 4, background: "linear-gradient(0deg, rgba(42,255,160,0.25), rgba(42,255,160,0.03))", animationDuration: "7s", animationDelay: "1s" }} />
        <div className="kelp" style={{ left: 22, height: 70, width: 4, background: "linear-gradient(0deg, rgba(76,224,210,0.3), rgba(76,224,210,0.04))", animationDuration: "9s", animationDelay: "0.5s" }} />

        {/* Right kelp */}
        <div className="kelp" style={{ right: 25, height: 110, width: 5, background: "linear-gradient(0deg, rgba(76,224,210,0.3), rgba(76,224,210,0.03))", animationDuration: "9s", animationDelay: "2s" }} />
        <div className="kelp" style={{ right: 40, height: 80, width: 4, background: "linear-gradient(0deg, rgba(42,255,160,0.2), rgba(42,255,160,0.03))", animationDuration: "7.5s", animationDelay: "3s" }} />

        {/* Brain coral */}
        <div className="brain-coral" style={{ left: 70, width: 40, height: 28, background: "radial-gradient(ellipse at 40% 35%, rgba(168,85,247,0.2), rgba(168,85,247,0.05) 60%, rgba(10,26,48,0.4))" }} />
        <div className="brain-coral" style={{ right: 60, width: 45, height: 30, background: "radial-gradient(ellipse at 40% 35%, rgba(76,224,210,0.18), rgba(76,224,210,0.04) 60%, rgba(10,26,48,0.4))" }} />

        {/* Anemone clusters */}
        <div className="anemone-cluster" style={{ left: 120 }}>
          <div className="an-t" style={{ height: 16, background: "linear-gradient(0deg, rgba(255,77,142,0.35), rgba(255,77,142,0.08))", transform: "rotate(-18deg)" }} />
          <div className="an-t" style={{ height: 20, background: "linear-gradient(0deg, rgba(255,77,142,0.4), rgba(255,77,142,0.1))" }} />
          <div className="an-t" style={{ height: 22, background: "linear-gradient(0deg, rgba(255,77,142,0.4), rgba(255,77,142,0.08))" }} />
          <div className="an-t" style={{ height: 20, background: "linear-gradient(0deg, rgba(255,77,142,0.4), rgba(255,77,142,0.1))" }} />
          <div className="an-t" style={{ height: 16, background: "linear-gradient(0deg, rgba(255,77,142,0.35), rgba(255,77,142,0.08))", transform: "rotate(18deg)" }} />
        </div>
        <div className="anemone-cluster" style={{ right: 100, animationDelay: "1s" }}>
          <div className="an-t" style={{ height: 14, background: "linear-gradient(0deg, rgba(255,107,53,0.35), rgba(255,107,53,0.06))", transform: "rotate(-12deg)" }} />
          <div className="an-t" style={{ height: 17, background: "linear-gradient(0deg, rgba(255,107,53,0.4), rgba(255,107,53,0.08))" }} />
          <div className="an-t" style={{ height: 19, background: "linear-gradient(0deg, rgba(255,107,53,0.4), rgba(255,107,53,0.08))" }} />
          <div className="an-t" style={{ height: 17, background: "linear-gradient(0deg, rgba(255,107,53,0.4), rgba(255,107,53,0.08))" }} />
          <div className="an-t" style={{ height: 14, background: "linear-gradient(0deg, rgba(255,107,53,0.35), rgba(255,107,53,0.06))", transform: "rotate(12deg)" }} />
        </div>

        {/* Hydrothermal vent — left */}
        <div className="hydro-vent" style={{ left: "20%" }}>
          <div className="vent-chimney" />
          <div className="vent-smoke">
            <div className="smoke-particle sp1" />
            <div className="smoke-particle sp2" />
            <div className="smoke-particle sp3" />
            <div className="smoke-particle sp4" />
            <div className="smoke-particle sp5" />
          </div>
          <div className="vent-glow" />
        </div>

        {/* Hydrothermal vent — right */}
        <div className="hydro-vent" style={{ right: "15%" }}>
          <div className="vent-chimney vent-chimney-tall" />
          <div className="vent-smoke">
            <div className="smoke-particle sp1" style={{ animationDelay: "0.3s" }} />
            <div className="smoke-particle sp2" style={{ animationDelay: "0.6s" }} />
            <div className="smoke-particle sp3" style={{ animationDelay: "0.1s" }} />
            <div className="smoke-particle sp4" style={{ animationDelay: "0.8s" }} />
            <div className="smoke-particle sp5" style={{ animationDelay: "0.5s" }} />
            <div className="smoke-particle sp6" />
          </div>
          <div className="vent-glow" />
        </div>

        {/* Hydrothermal vent — center small */}
        <div className="hydro-vent" style={{ left: "52%" }}>
          <div className="vent-chimney vent-chimney-small" />
          <div className="vent-smoke">
            <div className="smoke-particle sp1" style={{ animationDelay: "0.5s" }} />
            <div className="smoke-particle sp2" style={{ animationDelay: "0.2s" }} />
            <div className="smoke-particle sp3" style={{ animationDelay: "0.9s" }} />
          </div>
          <div className="vent-glow vent-glow-small" />
        </div>
      </div>
    </>
  );
}
