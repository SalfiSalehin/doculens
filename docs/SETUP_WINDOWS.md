# Windows setup (PowerShell, no WSL)

Project folder: `E:\DocuLens` (not on OneDrive). Run everything from the project root.

## 0. One-time prerequisites

```powershell
# Python 3.11 (the py launcher currently finds no installed Python, so install it)
winget install -e --id Python.Python.3.11
# Close and reopen PowerShell, then check:
py -3.11 --version          # expect: Python 3.11.x

# Allow local scripts such as .venv\Scripts\Activate.ps1 (current user only)
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
# Answer Y. Check:
Get-ExecutionPolicy -Scope CurrentUser   # expect: RemoteSigned

git --version               # any recent version
```

## 1. Virtual environment and install

```powershell
cd E:\DocuLens
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version            # expect: Python 3.11.x
# venv ships an old setuptools (65.x) that pip-audit flags; upgrade both
python -m pip install --upgrade pip setuptools
pip install -e ".[dev]"
```

## 2. Create `.env`

```powershell
python scripts\make_env.py
# expect: Wrote E:\DocuLens\.env (secret generated, not printed).
```

## 3. Quality checks

```powershell
ruff check .                # expect: All checks passed!
ruff format --check .       # expect: N files already formatted
pytest                      # expect: all tests passed, 0 failed
bandit -c pyproject.toml -r doculens scripts -ll   # expect: No issues identified.
pip-audit                   # expect: No known vulnerabilities found
```

## 4. Run the API

```powershell
uvicorn doculens.api.main:create_app --factory --reload
```

In a **second** PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
# expect:
# status version
# ------ -------
# ok     0.1.0

(Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing).Headers["X-Content-Type-Options"]
# expect: nosniff
```

Interactive docs (development only): http://127.0.0.1:8000/docs. Stop the server with `Ctrl+C`.

## 5. GPU check (PyTorch is installed in Week 3)

```powershell
python scripts\check_gpu.py
# expect now: "PyTorch : not installed (expected until Week 3)."
```

When we get to Week 3, install the CUDA build of PyTorch with the command that
https://pytorch.org/get-started/locally/ shows for *Windows / Pip / Python / CUDA*.
Then run `check_gpu.py` again and look for `available=True` and `NVIDIA GeForce RTX 3060`.

## 6. Gitleaks (secret scan)

```powershell
winget install -e --id Gitleaks.Gitleaks
# reopen PowerShell
gitleaks detect --source . -v       # expect: no leaks found
```

## 7. First commit

```powershell
git init
git add .
git status                  # make sure .env and .venv are NOT listed
git commit -m "Phase 1: secure FastAPI foundation, upload validation, rules, metrics"
```

## Common errors

| Error | Fix |
|---|---|
| `py : No installed Pythons found` | Do step 0, then reopen PowerShell. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ModuleNotFoundError: doculens` | The venv is not active, or you skipped `pip install -e ".[dev]"`. |
| `ValidationError ... CORS` on startup | `DOCULENS_CORS_ORIGINS` must list exact origins without a trailing `/` or `*`. |
| Port 8000 busy | `uvicorn ... --port 8001` |
