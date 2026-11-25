"""DesignJack command line.

  python -m designjack generate                       # write scenarios/ (183 IFC files)
  python -m designjack run --models anthropic:claude-haiku-4-5 --defenses none spotlight
  python -m designjack report results/main
"""

from __future__ import annotations

import argparse
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .agents import DEFENSES, run_agent
from .scenarios import build_grid, load_manifest
from .scoring import score


def cmd_generate(a):
    s = build_grid(Path(a.out), styles=a.styles)
    n_attack = sum(x.is_attack for x in s)
    print(f"Wrote {len(s)} scenarios ({n_attack} attacks, {len(s) - n_attack} clean) to {a.out}/")


def cmd_run(a):
    scen_dir = Path(a.scenarios)
    manifest = scen_dir / "manifest.jsonl"
    if not manifest.exists():
        build_grid(scen_dir)
    scenarios = load_manifest(manifest)
    if a.styles:
        scenarios = [s for s in scenarios if s.style is None or s.style in a.styles]
    if a.tasks:
        scenarios = [s for s in scenarios if s.task in a.tasks]
    if a.limit:
        clean = [s for s in scenarios if not s.is_attack]
        attacks = [s for s in scenarios if s.is_attack]
        random.Random(a.seed).shuffle(attacks)
        scenarios = clean + attacks[: a.limit]

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    runs_path = out / "runs.jsonl"
    done = set()
    if runs_path.exists():
        for line in runs_path.open():
            r = json.loads(line)
            if not r.get("error"):
                done.add((r["model"], r["defense"], r["scenario"]))

    jobs = [(m, d, s) for m in a.models for d in a.defenses for s in scenarios
            if (m, d, s.id) not in done]
    print(f"{len(jobs)} runs to do ({len(done)} already done) -> {runs_path}")
    lock = threading.Lock()
    transcripts = out / "transcripts"
    if a.save_transcripts:
        transcripts.mkdir(exist_ok=True)

    def work(job):
        model, defense, s = job
        r = run_agent(model, s, defense)
        rec = {
            "model": model, "defense": defense, "scenario": s.id, "task": s.task,
            "carrier": s.carrier, "goal": s.goal, "style": s.style,
            **score(s, r.calls, r.answer),
            "answer": r.answer,
            "tool_calls": [{"name": c.name, "args": c.args} for c in r.calls],
            "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "error": r.error,
        }
        if a.save_transcripts and r.transcript:
            name = f"{model}__{defense}__{s.id}".replace("/", "_").replace(":", "_")
            (transcripts / f"{name}.json").write_text(json.dumps(r.transcript, indent=1, default=str))
        return rec

    n = 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool, runs_path.open("a") as fh:
        for fut in as_completed(pool.submit(work, j) for j in jobs):
            rec = fut.result()
            with lock:
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                n += 1
                flag = "ERR" if rec["error"] else ("HIJACKED" if rec["attack_success"] else "ok")
                print(f"[{n}/{len(jobs)}] {rec['model']} {rec['defense']:9s} {rec['scenario']}: {flag}")


def cmd_rescore(a):
    """Recompute the deception verdicts from stored answers, without calling any model.

    Tool-call goals (delete, exfil, tamper) depend on the original tool results
    and are left as recorded.
    """
    from .scoring import deception_outcome
    results = Path(a.results)
    runs = results / "runs.jsonl"
    lines = [l for l in runs.read_text().splitlines() if l.strip()]
    (results / "runs.before_rescore.jsonl").write_text("\n".join(lines) + "\n")
    out, changed = [], 0
    for line in lines:
        r = json.loads(line)
        r["echoed_payload"] = False
        if r.get("goal") == "deceive" and not r.get("error"):
            asserted, echoed = deception_outcome(r["answer"])
            changed += r.get("attack_success") != asserted
            r["attack_attempted"] = r["attack_success"] = asserted
            r["echoed_payload"] = echoed
        out.append(json.dumps(r))
    runs.write_text("\n".join(out) + "\n")
    print(f"Rescored {len(out)} runs; {changed} deception verdicts changed. Backup: runs.before_rescore.jsonl")


def cmd_report(a):
    from .report import write_report
    write_report(Path(a.results))


def main(argv=None):
    p = argparse.ArgumentParser(prog="designjack")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write the scenario IFC files")
    g.add_argument("--out", default="scenarios")
    g.add_argument("--styles", nargs="*")
    g.set_defaults(fn=cmd_generate)

    r = sub.add_parser("run", help="run models against the scenarios")
    r.add_argument("--models", nargs="+", required=True)
    r.add_argument("--defenses", nargs="+", default=["none"], choices=list(DEFENSES))
    r.add_argument("--scenarios", default="scenarios")
    r.add_argument("--styles", nargs="*")
    r.add_argument("--tasks", nargs="*")
    r.add_argument("--limit", type=int, help="random sample of N attack scenarios (clean controls always run)")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--out", default="results/main")
    r.add_argument("--save-transcripts", action="store_true")
    r.set_defaults(fn=cmd_run)

    rs = sub.add_parser("rescore", help="recompute scores for an existing results folder (no API calls)")
    rs.add_argument("results")
    rs.set_defaults(fn=cmd_rescore)

    rep = sub.add_parser("report", help="summarize a results folder")
    rep.add_argument("results")
    rep.set_defaults(fn=cmd_report)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
