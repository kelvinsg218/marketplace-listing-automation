"""Delegate cheap text tasks to a local Ollama model.

Stdlib only. Every call appends real metrics returned by the Ollama API
(prompt/eval token counts, durations) to tools/.metrics/ollama_usage.jsonl.

Usage:
    python tools/ollama_assist.py summarize <file|->      # resumo de log/texto
    python tools/ollama_assist.py triage <file|->         # classifica um erro/traceback
    python tools/ollama_assist.py explain <file|->        # explica um trecho de código
    python tools/ollama_assist.py ask "pergunta"           # pergunta livre curta
    python tools/ollama_assist.py stats                   # resume as métricas registradas
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("MLA_LOCAL_MODEL", "qwen2.5-coder:1.5b")
METRICS = Path(__file__).resolve().parent / ".metrics" / "ollama_usage.jsonl"
MAX_INPUT_CHARS = 12_000  # ~3k tokens; keeps CPU prompt-eval time bounded

PROMPTS = {
    "summarize": (
        "Summarize the following log or text for a developer. Output at most 8 bullet "
        "points in Portuguese. Keep exact error messages, file names and line numbers. "
        "Do not invent anything that is not in the text.\n\n{text}"
    ),
    "triage": (
        "Classify the following error. Answer in Portuguese with exactly these lines:\n"
        "TIPO: <syntax|import|type|value|io|db|network|timeout|selector|assertion|other>\n"
        "ARQUIVO: <file:line of the most relevant frame or 'desconhecido'>\n"
        "CAUSA_PROVAVEL: <one sentence>\n"
        "PROXIMO_PASSO: <one sentence>\n\n{text}"
    ),
    "explain": (
        "Explain what the following code does in Portuguese, in at most 6 short bullet "
        "points. Mention inputs, outputs and side effects.\n\n{text}"
    ),
    "ask": "{text}",
}


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_INPUT_CHARS:
        return text, False
    half = MAX_INPUT_CHARS // 2
    return text[:half] + "\n...[trecho omitido]...\n" + text[-half:], True


def _read_input(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8", errors="replace")


def generate(task: str, text: str, model: str = MODEL, num_ctx: int = 4096) -> dict:
    text, clipped = _clip(text)
    payload = {
        "model": model,
        "prompt": PROMPTS[task].format(text=text),
        "stream": False,
        "keep_alive": "2m",  # free RAM soon after use on low-memory machines
        "options": {"temperature": 0.1, "num_ctx": num_ctx, "num_predict": 400},
    }
    req = urllib.request.Request(
        f"{HOST}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.load(resp)
    wall = time.perf_counter() - started
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "task": task,
        "model": model,
        "input_chars": len(text),
        "clipped": clipped,
        "prompt_tokens": data.get("prompt_eval_count"),
        "output_tokens": data.get("eval_count"),
        "load_s": round(data.get("load_duration", 0) / 1e9, 2),
        "total_s": round(data.get("total_duration", 0) / 1e9, 2),
        "wall_s": round(wall, 2),
    }
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    with METRICS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return {"response": data.get("response", "").strip(), "metrics": record}


def stats() -> str:
    if not METRICS.exists():
        return "Nenhuma métrica registrada ainda."
    rows = [json.loads(line) for line in METRICS.read_text(encoding="utf-8").splitlines() if line]
    by_task: dict[str, list[dict]] = {}
    for r in rows:
        by_task.setdefault(r["task"], []).append(r)
    lines = [f"{len(rows)} chamadas locais registradas"]
    for task, items in sorted(by_task.items()):
        prompt = sum(i.get("prompt_tokens") or 0 for i in items)
        out = sum(i.get("output_tokens") or 0 for i in items)
        avg = sum(i["wall_s"] for i in items) / len(items)
        lines.append(f"  {task:10} n={len(items):3}  tokens_in={prompt:6}  tokens_out={out:5}  média={avg:.1f}s")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=[*PROMPTS, "stats"])
    parser.add_argument("source", nargs="?", default="-", help="arquivo, '-' para stdin, ou texto (ask)")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--quiet-metrics", action="store_true")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")

    if args.task == "stats":
        print(stats())
        return 0
    text = args.source if args.task == "ask" else _read_input(args.source)
    try:
        result = generate(args.task, text, model=args.model)
    except urllib.error.URLError as exc:
        print(f"Ollama indisponível em {HOST}: {exc}", file=sys.stderr)
        return 2
    print(result["response"])
    if not args.quiet_metrics:
        m = result["metrics"]
        print(
            f"\n[local {m['model']}: {m['prompt_tokens']} in / {m['output_tokens']} out, "
            f"{m['wall_s']}s{', entrada truncada' if m['clipped'] else ''}]",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
