# ROCmForge

ROCmForge is a proof-backed multi-agent migration lab for moving CUDA-focused AI code toward AMD/ROCm compatibility.

## Run Locally

```bash
git clone <repo-url>
cd ROCmForge
python -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install dependencies and create a local secrets file:

```powershell
python -m pip install -r requirements.txt
Copy-Item .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

On macOS/Linux:

```bash
python -m pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

## First-Time Setup Notes

- Always install dependencies inside `.venv`, not into global Python. In PowerShell, your prompt should start with `(.venv)` before you run `python -m pip install ...`.
- Prefer `python -m pip ...` over plain `pip ...` so the command uses the active environment.
- On Windows, stop Streamlit with `Ctrl+C` before installing or upgrading packages. Running Streamlit can lock `.pyd` files and cause `WinError 5: Access is denied`.
- If you see warnings like `Ignoring invalid distribution ~ip` from `C:\Python312`, that is a global Python issue. The project can still work as long as `.venv` is active.
