"""Desk monitors for vpin_of — read vpin_day / panel Pass 1 + Pass 2 artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BOOK = Path(__file__).resolve().parents[1]
OUT_DAY = BOOK / "out" / "vpin_day"
OUT_PANEL = BOOK / "out" / "vpin_panel"
OUT_PASS2 = BOOK / "out" / "pass2"


def latest_vpin_day_snapshot() -> dict[str, Any]:
    """Newest JSON in out/vpin_day/ by mtime."""
    if not OUT_DAY.is_dir():
        return {"ok": False, "reason": "no_out_vpin_day"}
    files = sorted(OUT_DAY.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"ok": False, "reason": "empty_out_vpin_day"}
    data = json.loads(files[0].read_text())
    return {"ok": True, "path": str(files[0].relative_to(BOOK)), "data": data}


def panel_summary() -> dict[str, Any]:
    p = OUT_PANEL / "summary.json"
    if not p.is_file():
        return {"ok": False, "reason": "run exp_vpin_panel first"}
    return {"ok": True, "data": json.loads(p.read_text())}


def _decisions_from(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "reason": f"missing {path.name}"}
    data = json.loads(path.read_text())
    table = data.get("decision_table", [])
    promote = [t["id"] for t in table if t.get("decision") == "Promote"]
    hold = [t["id"] for t in table if t.get("decision") == "Hold"]
    return {
        "ok": True,
        "path": str(path.relative_to(BOOK)),
        "n_ok": data.get("n_ok"),
        "decision_counts": data.get("decision_counts"),
        "promote_ids": promote,
        "hold_ids": hold,
        "falsifiers": data.get("falsifiers"),
        "data_provenance": data.get("data_provenance"),
        "pass2_block": data.get("pass2"),
    }


def panel_decisions() -> dict[str, Any]:
    return _decisions_from(OUT_PANEL / "decisions.json")


def pass2_decisions() -> dict[str, Any]:
    p = OUT_PASS2 / "decisions_pass2.json"
    out = _decisions_from(p)
    if out.get("ok"):
        summary_path = OUT_PASS2 / "pass2_summary.json"
        if summary_path.is_file():
            out["summary"] = json.loads(summary_path.read_text())
    return out


def write_monitor_snapshot(dest: Path | None = None) -> Path:
    dest = dest or (BOOK / "applications" / "out" / "monitor_snapshot.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    p1 = panel_decisions()
    p2 = pass2_decisions()
    payload = {
        "vpin_day": latest_vpin_day_snapshot(),
        "panel": panel_summary(),
        "decisions_pass1": p1,
        "decisions_pass2": p2,
        "pass1_complete": p1.get("ok") and p1.get("n_ok", 0) >= 30,
        "pass2_complete": p2.get("ok") and bool(p2.get("pass2_block")),
    }
    dest.write_text(json.dumps(payload, indent=2) + "\n")
    return dest


if __name__ == "__main__":
    print(write_monitor_snapshot())
