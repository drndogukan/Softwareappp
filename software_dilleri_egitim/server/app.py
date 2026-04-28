from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="software_dilleri_egitim runner")


class RunRequest(BaseModel):
    languageId: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)
    stdin: Optional[str] = None
    timeLimitMs: int = 3000
    memoryLimitMb: int = 256


class RunResponse(BaseModel):
    stdout: str
    stderr: str
    exitCode: int
    durationMs: int
    didTimeout: bool
    hint: Optional[str] = None


@dataclass(frozen=True)
class LangSpec:
    image: str
    filename: str
    compile_cmd: Optional[list[str]]
    run_cmd: list[str]


LANGS: dict[str, LangSpec] = {
    "python": LangSpec("python:3.12-alpine", "main.py", None, ["python", "main.py"]),
    "javascript": LangSpec("node:20-alpine", "main.js", None, ["node", "main.js"]),
    # Typescript: uses npx each run (MVP). Slower but ok.
    "typescript": LangSpec(
        "node:20-alpine",
        "main.ts",
        None,
        ["sh", "-lc", "npx -y ts-node main.ts"],
    ),
    "c": LangSpec(
        "gcc:13",
        "main.c",
        ["sh", "-lc", "gcc main.c -O2 -pipe -static -s -o main"],
        ["./main"],
    ),
    "cpp": LangSpec(
        "gcc:13",
        "main.cpp",
        ["sh", "-lc", "g++ main.cpp -O2 -pipe -static -s -o main"],
        ["./main"],
    ),
    "java": LangSpec(
        "eclipse-temurin:21-jdk",
        "Main.java",
        ["sh", "-lc", "javac Main.java"],
        ["sh", "-lc", "java Main"],
    ),
    "dart": LangSpec(
        "dart:stable",
        "main.dart",
        None,
        ["dart", "run", "main.dart"],
    ),
    "go": LangSpec(
        "golang:1.22-alpine",
        "main.go",
        ["sh", "-lc", "go build -o main main.go"],
        ["./main"],
    ),
    "rust": LangSpec(
        "rust:1.77-alpine",
        "main.rs",
        ["sh", "-lc", "rustc main.rs -O -o main"],
        ["./main"],
    ),
    "php": LangSpec("php:8.3-cli-alpine", "main.php", None, ["php", "main.php"]),
    "ruby": LangSpec("ruby:3.3-alpine", "main.rb", None, ["ruby", "main.rb"]),
    "r": LangSpec("r-base:4.4.1", "main.R", None, ["Rscript", "main.R"]),
    # MATLAB -> Octave
    "matlab": LangSpec("gnuoctave/octave:latest", "main.m", None, ["octave-cli", "--quiet", "main.m"]),
    "kotlin": LangSpec(
        "zenika/kotlin:latest",
        "Main.kt",
        ["sh", "-lc", "kotlinc Main.kt -include-runtime -d main.jar"],
        ["sh", "-lc", "java -jar main.jar"],
    ),
    "swift": LangSpec(
        "swift:5.10",
        "main.swift",
        ["sh", "-lc", "swiftc main.swift -o main"],
        ["./main"],
    ),
    # SQL: just echo + no real DB in MVP.
    "sql": LangSpec(
        "alpine:3.20",
        "main.sql",
        None,
        ["sh", "-lc", "echo 'SQL çalıştırma MVP değil. Sorgun:' && cat main.sql"],
    ),
}


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _make_hint(language_id: str, stderr: str) -> Optional[str]:
    s = stderr.strip()
    if not s:
        return None

    # Generic patterns
    if "syntax error" in s.lower():
        return "Syntax error görünüyor. Eksik parantez/tırnak/sonlandırma olabilir. Hata satırını kontrol et."
    if "NameError" in s or "is not defined" in s:
        return "Tanımsız isim kullanılmış. Değişken adını yazdığından ve daha önce tanımladığından emin ol."
    if "Segmentation fault" in s:
        return "Segmentation fault: C/C++ tarafında hatalı pointer/bellek erişimi olabilir."
    if "cannot find symbol" in s and language_id == "java":
        return "Java: Bulunamayan bir sınıf/metot/alan var. İsimleri ve Main sınıfını kontrol et."
    if "error:" in s.lower() and language_id in ("c", "cpp", "rust", "go", "swift", "kotlin"):
        return "Derleyici hatası var. Hata mesajındaki satır numarasına git ve önce ilk hatayı düzelt."
    return None


def _run_in_docker(spec: LangSpec, code: str, stdin: Optional[str], time_limit_ms: int) -> RunResponse:
    with tempfile.TemporaryDirectory(prefix="runner_") as td:
        src_path = os.path.join(td, spec.filename)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Mount at /work
        mount = f"{td}:/work"
        base = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-m",
            "256m",
            "--cpus",
            "1",
            "-v",
            mount,
            "-w",
            "/work",
            spec.image,
        ]

        start = time.perf_counter()
        stdout_all = ""
        stderr_all = ""
        did_timeout = False
        exit_code = 0

        def run_step(cmd: list[str]) -> subprocess.CompletedProcess:
            nonlocal did_timeout
            try:
                return subprocess.run(
                    base + cmd,
                    input=(stdin.encode("utf-8") if stdin is not None else None),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=max(0.2, time_limit_ms / 1000.0),
                )
            except subprocess.TimeoutExpired as e:
                did_timeout = True
                out = (e.stdout or b"").decode("utf-8", errors="replace")
                err = (e.stderr or b"").decode("utf-8", errors="replace")
                return subprocess.CompletedProcess(base + cmd, 124, out.encode("utf-8"), err.encode("utf-8"))

        if spec.compile_cmd is not None:
            cp = run_step(spec.compile_cmd)
            stdout_all += cp.stdout.decode("utf-8", errors="replace")
            stderr_all += cp.stderr.decode("utf-8", errors="replace")
            exit_code = cp.returncode
            if exit_code != 0 or did_timeout:
                dur = int((time.perf_counter() - start) * 1000)
                return RunResponse(
                    stdout=stdout_all,
                    stderr=stderr_all,
                    exitCode=exit_code,
                    durationMs=dur,
                    didTimeout=did_timeout,
                    hint=_make_hint(_lang_id_for(spec), stderr_all),
                )

        rp = run_step(spec.run_cmd)
        stdout_all += rp.stdout.decode("utf-8", errors="replace")
        stderr_all += rp.stderr.decode("utf-8", errors="replace")
        exit_code = rp.returncode
        dur = int((time.perf_counter() - start) * 1000)

        return RunResponse(
            stdout=stdout_all,
            stderr=stderr_all,
            exitCode=exit_code,
            durationMs=dur,
            didTimeout=did_timeout,
            hint=_make_hint(_lang_id_for(spec), stderr_all),
        )


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run_local(lang: str, spec: LangSpec, code: str, stdin: Optional[str], time_limit_ms: int) -> RunResponse:
    """
    Local fallback runner (for development without Docker).
    Only works if required runtime/compiler exists on PATH.
    """
    with tempfile.TemporaryDirectory(prefix="runner_local_") as td:
        src_path = os.path.join(td, spec.filename)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        start = time.perf_counter()
        stdout_all = ""
        stderr_all = ""
        did_timeout = False

        def run_step(cmd: list[str]) -> subprocess.CompletedProcess:
            nonlocal did_timeout
            exe = shutil.which(cmd[0]) if os.path.sep not in cmd[0] else cmd[0]
            if exe is None:
                raise FileNotFoundError(f"Executable not found on PATH: {cmd[0]}")
            cmd2 = [exe, *cmd[1:]]
            try:
                return subprocess.run(
                    cmd2,
                    cwd=td,
                    input=(stdin.encode("utf-8") if stdin is not None else None),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=max(0.2, time_limit_ms / 1000.0),
                )
            except subprocess.TimeoutExpired as e:
                did_timeout = True
                out = (e.stdout or b"")
                err = (e.stderr or b"")
                return subprocess.CompletedProcess(cmd2, 124, out, err)

        if spec.compile_cmd is not None:
            cp = run_step(spec.compile_cmd)
            stdout_all += cp.stdout.decode("utf-8", errors="replace")
            stderr_all += cp.stderr.decode("utf-8", errors="replace")
            if cp.returncode != 0 or did_timeout:
                dur = int((time.perf_counter() - start) * 1000)
                return RunResponse(
                    stdout=stdout_all,
                    stderr=stderr_all,
                    exitCode=cp.returncode,
                    durationMs=dur,
                    didTimeout=did_timeout,
                    hint=_make_hint(lang, stderr_all),
                )

        rp = run_step(spec.run_cmd)
        stdout_all += rp.stdout.decode("utf-8", errors="replace")
        stderr_all += rp.stderr.decode("utf-8", errors="replace")
        dur = int((time.perf_counter() - start) * 1000)
        return RunResponse(
            stdout=stdout_all,
            stderr=stderr_all,
            exitCode=rp.returncode,
            durationMs=dur,
            didTimeout=did_timeout,
            hint=_make_hint(lang, stderr_all),
        )


def _lang_id_for(spec: LangSpec) -> str:
    # Small reverse lookup for hint routing.
    for k, v in LANGS.items():
        if v == spec:
            return k
    return "unknown"


@app.post("/run", response_model=RunResponse)
def run(req: RunRequest) -> RunResponse:
    lang = req.languageId.strip().lower()
    spec = LANGS.get(lang)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"Unsupported languageId: {lang}")

    # Basic size limit
    if len(req.code) > 200_000:
        raise HTTPException(status_code=413, detail="Code too large.")

    if _docker_available():
        return _run_in_docker(spec, req.code, req.stdin, req.timeLimitMs)

    # Local fallback (development). Limited set.
    local_supported = {
        "python": ("python",),
        "javascript": ("node",),
        "typescript": ("node",),
    }
    if lang in local_supported:
        needed = local_supported[lang]
        missing = [c for c in needed if not _which(c)]
        if missing:
            raise HTTPException(
                status_code=503,
                detail=f"Docker yok ve local runtime eksik: {', '.join(missing)}",
            )

        # Use a local-friendly spec for ts (avoid npx installing each time if possible).
        if lang == "typescript":
            # Requires ts-node installed globally if using local mode.
            if not _which("ts-node"):
                raise HTTPException(
                    status_code=503,
                    detail="Docker yok. TypeScript için local modda ts-node gerekli (PATH).",
                )
            local_spec = LangSpec(spec.image, spec.filename, None, ["ts-node", spec.filename])
            return _run_local(lang, local_spec, req.code, req.stdin, req.timeLimitMs)

        try:
            return _run_local(lang, spec, req.code, req.stdin, req.timeLimitMs)
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail=str(e))

    raise HTTPException(
        status_code=503,
        detail="Docker bulunamadı. Bu dil için güvenli sandbox çalıştırma Docker gerektirir.",
    )

