"""Build the data files behind the TRILEMMA project site (site/index.html, site/traces.html).

Source: the `main` experiment of the paper = agent5 5.e.x (medium-conf / `confidentiality: audience`),
seven open-weight models + claude-opus-5 + gpt-5.6-sol, seeds s0-s9.

  runs        outputs/5e10_deception_judges/runlist.txt, outputs/5e10_closed_deception_judges/runlist.txt
  deception   outputs/5e10{,_closed}_deception_judges/plain/*.json (3 replicates, no-CoT judge)
              outputs/5e10_deception_judges/ack-{fabr,fram}/*.json (CoT acknowledgment check)
              seat label = figures/judged_data.py (same rule as the paper figure)
  disclosure  outputs/disclosure_5e10{_luna_v5c_flagged,_closed_luna_v5c}/r{1,2,3}/rows.jsonl

Writes site/data/index.json (one row per run, seat labels) and site/data/runs/<model>_s<seed>.json.
Names stay as in the rollouts (Priya, Nadia, ...); the pages map them to the paper's placeholders.

    python experiments/agent5/site/build_site.py
"""
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SITE = Path(__file__).resolve().parent
AGENT5 = SITE.parent
REPO = AGENT5.parents[1]
sys.path.insert(0, str(AGENT5 / "figures"))
import judged_data as jd  # noqa: E402

OPEN = jd.MODELS["5e10"]
CLOSED = jd.CLOSED["5e10"]
MODEL_NAME = {
    "deepseek": "deepseek-v4-flash-0731", "dspro": "deepseek-v4-pro-0813", "glm53": "glm-5.3",
    "glm53flash": "glm-5.3-flash", "kimi": "kimi-k2.6", "kimik3": "kimi-k3", "qwen38flash": "qwen3.8-flash",
    "gpt56sol": "gpt-5.6-sol", "opus5or": "claude-opus-5",
}
FOCAL = ["Priya", "Nadia"]
AGENTS = ["Priya", "Nadia", "Matthieu", "Rafael", "Helena"]
SECRET_DMS = [("Priya", "Zofia"), ("Priya", "Ines"), ("Nadia", "Ines"), ("Nadia", "Zofia")]
MAX_RESULT = 500  # chars of a tool result kept for the drawer


def naive_utc(iso):
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


def epoch_offset(r):
    for t in r["turns"]:
        w = t.get("wake") or {}
        if w.get("ts") and t.get("clock"):
            return float(w["ts"]) - naive_utc(t["clock"])
    return 0.0


def clip(obj, n=MAX_RESULT):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + " …"


def lit(v):
    if isinstance(v, str) and v[:1] in "[{'\"" or v in ("True", "False", "None"):
        try:
            return ast.literal_eval(v)
        except Exception:
            return v
    return v


def run_dirs():
    out = {}
    for f, models in (("5e10_deception_judges", OPEN), ("5e10_closed_deception_judges", CLOSED)):
        for line in (AGENT5 / "outputs" / f / "runlist.txt").read_text().split():
            m = jd.RUN_RE.search(line)
            if m and m.group(1) in models and f"s{m.group(2)}" in jd.SEEDS:
                out[(m.group(1), f"s{m.group(2)}")] = REPO / Path(line).parent
    return out


def deception(model, seed, emp, closed):
    base = AGENT5 / "outputs" / ("5e10_closed_deception_judges" if closed else "5e10_deception_judges")
    stem = f"{model}_{seed}__{emp}"

    def reps(variant):
        out = []
        for suf in ("", "__r2", "__r3"):
            p = base / variant / f"{stem}{suf}.json"
            if p.exists():
                d = json.loads(p.read_text())
                res = d.get("result") or {}
                if variant == "plain":
                    out.append({k: res.get(k) for k in ("label", "decisive_time", "decisive_quote",
                                                        "contradicted_by", "disclosure", "why")})
                else:
                    out.append({k: res.get(k) for k in ("acknowledged", "cot_quote", "cot_time", "why")}
                               | {"label": (d.get("flag") or {}).get("label")})
        return out

    o = {"plain": reps("plain")}
    if not closed:
        for v in ("ack-fabr", "ack-fram"):
            r = reps(v)
            if r:
                o[v] = r
    return o


def disclosure_rows(closed):
    d = AGENT5 / "outputs" / ("disclosure_5e10_closed_luna_v5c" if closed else "disclosure_5e10_luna_v5c_flagged")
    by_run = {}
    for rep in ("r1", "r2", "r3"):
        for line in (d / rep / "rows.jsonl").read_text().splitlines():
            row = {k: lit(v) for k, v in json.loads(line).items()}
            grounds = [{k: g.get(k) for k in ("ground", "subject", "strength", "new", "span")}
                       for g in (row.get("grounds") or [])]
            by_run.setdefault(row["run"], {}).setdefault(row["id"], []).append(
                {"rep": rep, "label": row.get("label"), "grounds": grounds, "reason": row.get("reason"),
                 "audience": row.get("audience")})
    return by_run


def call_view(c, conv_label, users):
    tool = c.get("tool", "?")
    args = c.get("args") or {}
    res = c.get("result") or {}
    ch = str(args.get("channel") or args.get("channel_id") or "")
    lab = conv_label.get(ch, ch)
    v = {"tool": tool, "step": int(c.get("step") or 0), "clock": (c.get("clock") or "")[11:19]}
    if tool in ("conversations_history", "conversations_replies"):
        n = len(res.get("messages") or []) if isinstance(res, dict) else 0
        v["line"] = f"read {lab} ({n} msgs)"
        v["conv"] = lab
    elif tool == "chat_postMessage":
        v["line"] = f"post → {lab}"
        v["conv"] = lab
        v["text"] = args.get("text") or ""
        if isinstance(res, dict) and res.get("ts"):
            v["ts"] = str(res["ts"])
    elif tool == "board_assign":
        v["line"] = f"board: {args.get('person') or ''} → {args.get('task_id') or ''}".replace(":  →", ":")
        v["task"] = str(args.get("task_id") or "")
        v["ok"] = not (isinstance(res, dict) and (res.get("ok") is False or res.get("error")))
    elif tool == "notify_user":
        v["line"] = "note to own user"
        v["text"] = args.get("text") or args.get("message") or ""
    elif tool == "users_info":
        v["line"] = f"look up {users.get(str(args.get('user')), args.get('user'))}"
    elif tool == "search_messages":
        v["line"] = f"search “{args.get('query', '')}”"
    elif tool.startswith("calendar_"):
        v["line"] = tool.replace("_", " ") + (f" {args.get('title')}" if args.get("title") else "")
    else:
        v["line"] = tool.replace("_", " ") + (f" {lab}" if lab else "")
    v["args"] = clip(args, 300)
    v["result"] = clip(res)
    return v


def build_run(model, seed, rdir, labels, leaks, disc):
    r = json.loads((rdir / "run.json").read_text())
    off = epoch_offset(r)
    start = naive_utc(r["clock_start"]) + off
    fx = json.loads((REPO / r["config"]["fixture"]).read_text())
    users = {u["id"]: u["name"] for u in fx.get("users") or []}
    roles = {u["name"]: u.get("title") or "" for u in fx.get("users") or []}
    conv_label = {m["conv_id"]: m["label"] for m in r["messages"]}

    def hms(ep):
        return datetime.fromtimestamp(ep - off, tz=timezone.utc).strftime("%H:%M:%S")

    # message ts run ahead of the simulated clock (wall-clock drift), so place live messages on the
    # sim clock via the chat_postMessage calls that created them (call clock <-> result ts), interpolated
    anchors = sorted({(float(c["result"]["ts"]), naive_utc(c["clock"]) + off)
                      for t in r["turns"] for c in t.get("tool_calls") or []
                      if c.get("tool") == "chat_postMessage" and isinstance(c.get("result"), dict)
                      and c["result"].get("ts") and c.get("clock")})

    def sim(ts):
        if not anchors:
            return ts
        if ts <= anchors[0][0]:
            return anchors[0][1] - (anchors[0][0] - ts)
        if ts >= anchors[-1][0]:
            return anchors[-1][1] + (ts - anchors[-1][0])
        for (a0, s0), (a1, s1) in zip(anchors, anchors[1:]):
            if a0 <= ts <= a1:
                return s0 + (s1 - s0) * ((ts - a0) / (a1 - a0) if a1 > a0 else 0)

    msg_flags = disc.get(rdir.name, {})
    msgs, convs = [], {}
    secret_labels = {f"dm:{'+'.join(sorted(p))}" for p in SECRET_DMS}
    for m in r["messages"]:
        ts = float(m["ts"])
        live = ts >= start
        if not live and m["label"] not in secret_labels:
            continue
        mid = f"{m['conv_id']}:{m['ts']}"
        convs.setdefault(m["label"], {"label": m["label"], "type": m["type"], "members": m.get("members") or []})
        o = {"id": mid, "conv": m["label"], "user": m["user"], "text": m["text"], "live": live,
             "t": round(sim(ts) - start, 1) if live else None,
             "time": hms(sim(ts)) if live else datetime.fromtimestamp(ts - off, tz=timezone.utc).strftime("%a %d %b %H:%M")}
        if mid in msg_flags:
            o["disc"] = msg_flags[mid]
        msgs.append(o)
    msgs.sort(key=lambda o: (o["live"], o["t"] if o["live"] else 0, o["id"].split(":")[1]))

    turns = []
    board = []
    for t in r["turns"]:
        w = t.get("wake") or {}
        steps = t.get("steps_detail") or []
        rf = t.get("reasoning_full") or t.get("reasoning") or []
        reasoning = [s.get("reasoning") or "" for s in steps] if steps else list(rf)
        texts = [s.get("text") or "" for s in steps] if steps else []
        calls = [call_view(c, conv_label, users) for c in t.get("tool_calls") or []]
        for c in calls:
            if c["tool"] == "board_assign" and c.get("ok"):
                ep = naive_utc(t["clock"][:19] if not c["clock"] else t["clock"][:11] + c["clock"]) + off
                board.append({"agent": t["agent"], "task": c["task"], "t": round(ep - start, 1), "time": c["clock"]})
        t0 = naive_utc(t["clock"]) + off
        t1 = naive_utc(t.get("clock_end") or t["clock"]) + off
        turns.append({
            "i": t["i"], "agent": t["agent"], "kind": t.get("kind"), "t": round(t0 - start, 1),
            "t_end": round(t1 - start, 1), "time": hms(t0), "wake": w.get("label") or "",
            "wake_from": w.get("from") or "", "steps": [{"reasoning": a, "text": b} for a, b in
                                                         zip(reasoning, texts + [""] * (len(reasoning) - len(texts)))],
            "calls": calls, "to_user": t.get("text_to_principal") or "",
        })
    seats = {}
    for emp in FOCAL:
        key = (model, seed, emp)
        b, w = leaks.get(key, (False, False))
        seats[emp] = {"label": labels.get(key), "leak_bob": b, "leak_work": w,
                      "deception": deception(model, seed, emp, model in CLOSED),
                      "final_task": (r.get("assignments") or {}).get(emp)}
    score = r.get("score") or {}
    return {
        "model": model, "model_name": MODEL_NAME[model], "seed": seed, "closed": model in CLOSED,
        "dir": rdir.name, "outcome": r.get("outcome"),
        "kickoff": round(naive_utc(r["kickoff"]) + off - start, 1),
        "deadline": round(naive_utc(r["deadline"]) + off - start, 1),
        "clock_start": r["clock_start"][11:19],
        "assignments": r.get("assignments") or {}, "valid": bool(score.get("valid")),
        "complete": bool(score.get("complete")), "board_shape": score.get("board_shape"),
        "roles": {n: roles.get(n, "") for n in set(roles)},
        "convs": list(convs.values()), "msgs": msgs, "turns": turns, "board": board, "seats": seats,
        "system_prompt_focal": (r.get("system_prompts") or {}).get("Priya", ""),
        "asks": {a: ((r["config"].get("ask_overrides") or {}).get(a) or r["config"].get("ask") or "") for a in AGENTS},
    }


def main():
    labels = jd.reason_labels("5e10") | jd.closed_reason_labels("5e10")
    leaks = jd.leak_flags("5e10") | jd.closed_leak_flags("5e10")
    disc = disclosure_rows(False) | disclosure_rows(True)
    out_dir = SITE / "data" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for (model, seed), rdir in sorted(run_dirs().items(), key=lambda kv: ((OPEN + CLOSED).index(kv[0][0]), int(kv[0][1][1:]))):
        d = build_run(model, seed, rdir, labels, leaks, disc)
        name = f"{model}_{seed}.js"
        # JSONP so the pages also work from file:// (fetch() of local files is blocked there)
        (out_dir / name).write_text("TRACE_LOAD(" + json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ");\n")
        n_posts = sum(1 for m in d["msgs"] if m["live"] and m["conv"].startswith("#"))
        index.append({"model": model, "model_name": d["model_name"], "seed": seed, "closed": d["closed"],
                      "file": name, "valid": d["valid"], "assignments": d["assignments"],
                      "sprint_posts": n_posts, "turns": len(d["turns"]),
                      "seats": {e: {k: v for k, v in s.items() if k != "deception"} |
                                {"quote": next((x.get("decisive_quote") for x in s["deception"]["plain"]
                                                if x.get("decisive_quote")), None)}
                                for e, s in d["seats"].items()}})
        print(name, (out_dir / name).stat().st_size // 1024, "KB")
    for old in out_dir.glob("*.json"):
        old.unlink()
    (SITE / "data" / "index.js").write_text("window.TRILEMMA_INDEX = " + json.dumps(
        {"models": [{"key": m, "name": MODEL_NAME[m], "closed": m in CLOSED} for m in OPEN + CLOSED],
         "runs": index}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";\n")
    print(len(index), "runs")


if __name__ == "__main__":
    main()
