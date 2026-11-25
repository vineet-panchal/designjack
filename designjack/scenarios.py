"""Builds the scenario grid and writes one IFC file per scenario."""

from __future__ import annotations

import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import ifcopenshell
import ifcopenshell.api as api

from .building import build_base_model
from .payloads import CARRIERS, GOALS, STYLES, TASKS, render_payload


@dataclass(frozen=True)
class Scenario:
    id: str
    task: str
    carrier: Optional[str]  # None for clean controls
    goal: Optional[str]
    style: Optional[str]
    payload: Optional[str]
    ifc_path: str  # file name, relative to the manifest's folder

    @property
    def is_attack(self) -> bool:
        return self.goal is not None


def _find(f: ifcopenshell.file, ifc_class: str, name: str):
    for el in f.by_type(ifc_class):
        if el.Name == name:
            return el
    raise KeyError(f"{ifc_class} {name!r} not in base model")


def inject(f: ifcopenshell.file, task_id: str, carrier: str, payload: str) -> None:
    """Hide `payload` in the model, on the element the task will read."""
    task = TASKS[task_id]
    if carrier == "project_description":
        project = f.by_type("IfcProject")[0]
        project.Description = f"{project.Description} {payload}"
        return
    el = _find(f, task.target_class, task.target_name)
    if carrier == "name":
        el.Name = f"{el.Name} | {payload}"
    elif carrier == "description":
        el.Description = payload
    elif carrier == "object_type":
        el.ObjectType = f"{el.ObjectType} - {payload}"
    elif carrier == "pset_value":
        ps = api.run("pset.add_pset", f, product=el, name="Pset_Annotations")
        api.run("pset.edit_pset", f, pset=ps, properties={"Comment": payload})
    else:
        raise ValueError(f"unknown carrier {carrier}")


def build_grid(out_dir: Path, styles: Optional[list] = None) -> list[Scenario]:
    """Write clean controls + every (task, carrier, goal, style) attack to out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    styles = styles or list(STYLES)
    scenarios: list[Scenario] = []

    for task_id in TASKS:
        sid = f"{task_id}__clean"
        path = out_dir / f"{sid}.ifc"
        build_base_model().write(str(path))
        scenarios.append(Scenario(sid, task_id, None, None, None, None, path.name))

    for task_id, carrier, goal, style in itertools.product(TASKS, CARRIERS, GOALS, styles):
        sid = f"{task_id}__{carrier}__{goal}__{style}"
        payload = render_payload(goal, style)
        f = build_base_model()
        inject(f, task_id, carrier, payload)
        path = out_dir / f"{sid}.ifc"
        f.write(str(path))
        scenarios.append(Scenario(sid, task_id, carrier, goal, style, payload, path.name))

    manifest = out_dir / "manifest.jsonl"
    with manifest.open("w") as fh:
        for s in scenarios:
            fh.write(json.dumps(asdict(s)) + "\n")
    return scenarios


def load_manifest(path: Path) -> list[Scenario]:
    """Load scenarios; ifc_path is resolved against the manifest's folder."""
    path = Path(path)
    out = []
    with path.open() as fh:
        for line in fh:
            if line.strip():
                d = json.loads(line)
                d["ifc_path"] = str(path.parent / d["ifc_path"])
                out.append(Scenario(**d))
    return out
