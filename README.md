# SIDA Registration Automation

A Python automation tool for processing preschool preregistration records in SIDA from an Excel workbook. It validates each row, completes the repetitive browser steps, and stores the run status in the same workbook.

## Human in the Loop

The user signs in to SIDA, solves the CAPTCHA, and clicks Search for each record. The bot does not read or solve CAPTCHA, handle credentials, or bypass security controls.

## Requirements

- Python 3.10 or later
- Google Chrome
- Access to SIDA
- The included Excel workbook

## Usage

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Open `data/students.xlsx`, replace the fictional sample rows with your own data, then double-click `Run_SIDA_Bot.cmd`. The workbook's `راهنمای ورود` sheet lists the allowed education and job values and the fields that need extra care. The launcher opens a dedicated Chrome profile when needed and asks you to sign in. For each record, enter the CAPTCHA and click Search; the bot completes the remaining workflow.

The included workbook contains fictional records. Do not publish a completed workbook containing real data.

The bot writes status, selected grade, last error, and last attempt time to the source workbook. The JSON recovery journal and logs are kept local and excluded from Git.

## AI-Assisted Development

This project was developed with AI-assisted coding workflows. The author reviewed the implementation, validated the workflow, and maintained the test suite.
