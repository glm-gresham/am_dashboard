# AM Dashboard Setup Guide

This guide is for getting the AM dashboard working from a normal PowerShell terminal on your laptop.

## 1. Install The Core Tools

Install these first:

- Python 3.12 or newer from the official Python website.
- Git for Windows.
- Visual Studio Code.

During Python installation, tick the option called `Add python.exe to PATH`.

After installing Git and Python, close PowerShell and open a new PowerShell window.

Check the tools:

```powershell
python --version
git --version
```

If either command says it is not recognised, the tool is not installed correctly or is not on your PATH.

## 2. Open The Project

In Visual Studio Code:

1. Open Visual Studio Code.
2. Select `File > Open Folder`.
3. Open the `AM dashboard` folder.
4. Open the built-in terminal with `Terminal > New Terminal`.

The terminal should show that you are inside the project folder.

## 3. Create A Virtual Environment

A virtual environment is a private Python workspace for this project. It keeps dashboard packages separate from the rest of your machine.

Because this project is inside OneDrive, create the virtual environment outside the project folder. Virtual environments contain many small executable files, and OneDrive can interfere with their creation.

Run:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.venvs"
python -m venv "$env:USERPROFILE\.venvs\am-dashboard"
```

Activate it:

```powershell
& "$env:USERPROFILE\.venvs\am-dashboard\Scripts\Activate.ps1"
```

If PowerShell says running scripts is disabled, use the virtual environment's Python directly instead of activating it. This avoids changing your system's execution policy:

```powershell
cd "C:\Users\g.mantinan\OneDrive - Gresham House\Documents\AM dashboard"
& "$env:USERPROFILE\.venvs\am-dashboard\Scripts\python.exe" -m pip install -r requirements.txt
& "$env:USERPROFILE\.venvs\am-dashboard\Scripts\python.exe" sync_sqlite_repository.py --source sample
& "$env:USERPROFILE\.venvs\am-dashboard\Scripts\python.exe" -m streamlit run app.py
```

Alternative for the current PowerShell window only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "$env:USERPROFILE\.venvs\am-dashboard\Scripts\Activate.ps1"
```

Install the dashboard packages:

```powershell
pip install -r requirements.txt
```

## 4. Build The Local SQLite Repository

The dashboard reads from SQLite. For local testing, create the SQLite file with sample data:

```powershell
python sync_sqlite_repository.py --source sample
```

On Windows, the default SQLite location is:

```text
%LOCALAPPDATA%\AM Dashboard\am_dashboard.sqlite
```

The file is outside OneDrive because SQLite database files can behave badly in synced folders.

## 5. Run The Dashboard

Start the app:

```powershell
streamlit run app.py
```

Streamlit will print a local URL, usually:

```text
http://localhost:8501
```

Open that URL in your browser.

## 6. First GitHub Workflow

Use this simple rhythm when changing the project:

```powershell
git status
git add .
git commit -m "Describe the change clearly"
git push
```

What those commands mean:

- `git status` shows what changed.
- `git add .` stages the changed files.
- `git commit` saves a named snapshot on your machine.
- `git push` uploads your commits to GitHub.

Do not commit passwords, `.env` files, `secrets.toml`, virtual environments, or local SQLite databases.

## 7. Snowflake Sync Later

Only do this once the real Snowflake table or view has been agreed.

Install the Snowflake connector:

```powershell
pip install -r requirements-snowflake.txt
```

Set the Snowflake environment variables listed in `README.md`, then run:

```powershell
python sync_sqlite_repository.py --source snowflake
```

That command pulls from Snowflake and refreshes the SQLite repository used by the dashboard.

## Current Setup Notes

In the current workspace check, PowerShell could not find `python` or `git`. That means the first practical setup task is installing those tools properly and reopening PowerShell.
