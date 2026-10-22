import { useEffect, useState } from "react";
import { stickers } from "./data";

export default function useMigration(scenario) {
  const [step, setStep] = useState(0);
  const [selected, setSelected] = useState(
    new Set(stickers.map((item) => item.id)),
  );
  const [operation, setOperation] = useState(null);
  const [done, setDone] = useState(0);
  const [paused, setPaused] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState(null);
  const [loggedIn, setLoggedIn] = useState(false);
  const [existing, setExisting] = useState("960");
  const [result, setResult] = useState(null);
  const total = operation === "export" ? stickers.length : selected.size;
  const validCount = /^\d+$/.test(existing) && Number(existing) <= 1000;
  const available = validCount ? 1000 - Number(existing) : null;
  const fits = validCount && selected.size > 0 && selected.size <= available;

  useEffect(() => {
    if (!operation || paused) return;
    const timer = setInterval(
      () => setDone((value) => Math.min(total, value + 1)),
      140,
    );
    return () => clearInterval(timer);
  }, [operation, paused, total]);

  useEffect(() => {
    if (!operation) return;
    if (operation === "export" && scenario === "export-error" && done === 8) {
      setOperation(null);
      setError("export");
      return;
    }
    if (
      operation === "import" &&
      scenario === "import-uncertain" &&
      done === 8 &&
      !uncertain
    ) {
      setPaused(true);
      setUncertain(true);
      return;
    }
    if (done < total) return;
    if (operation === "export") {
      setStep(1);
      setOperation(null);
    } else {
      setResult({ success: total, unknown: 0, remaining: 0 });
      setStep(3);
      setOperation(null);
    }
  }, [operation, done, total, scenario, uncertain]);

  function startExport() {
    setError(null);
    setDone(0);
    setOperation("export");
  }
  function startImport() {
    if (!fits || !loggedIn) return;
    setDone(0);
    setPaused(false);
    setUncertain(false);
    setOperation("import");
  }
  function pause() {
    setPaused(true);
    setUncertain(true);
  }
  function resume() {
    setPaused(false);
  }
  function endImport() {
    setResult({
      success: done,
      unknown: uncertain && done < total ? 1 : 0,
      remaining: Math.max(0, total - done - (uncertain ? 1 : 0)),
    });
    setOperation(null);
    setPaused(false);
    setStep(3);
  }
  function toggle(id) {
    setSelected((previous) => {
      const next = new Set(previous);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  function reset() {
    setStep(0);
    setOperation(null);
    setDone(0);
    setPaused(false);
    setUncertain(false);
    setError(null);
    setLoggedIn(false);
    setExisting("960");
    setSelected(new Set(stickers.map((item) => item.id)));
  }
  return {
    real: false,
    items: stickers,
    step,
    setStep,
    selected,
    setSelected,
    operation,
    done,
    total,
    paused,
    uncertain,
    error,
    setError,
    loggedIn,
    setLoggedIn,
    existing,
    setExisting,
    validCount,
    available,
    fits,
    result,
    startExport,
    startImport,
    pause,
    resume,
    endImport,
    toggle,
    reset,
  };
}
