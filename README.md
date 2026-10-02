# Python Automation Portfolio

[![Testes](https://github.com/Fe262/python-automation-portfolio/actions/workflows/testes.yml/badge.svg)](https://github.com/Fe262/python-automation-portfolio/actions/workflows/testes.yml)
**🌐 Portfolio site:** https://fe262.github.io/python-automation-portfolio/

Web apps, optimization tools and payment integrations for real business problems. Every project has automated tests, and the two newest have a recorded demo video.

| Project | What it does |
|---|---|
| ⭐ [Shift Scheduler (OR-Tools solver)](projeto8-escala-turnos/) | Builds a fair weekly rota under hard rules (coverage, availability, rest, weekly max) and explains why when a request is impossible. Streamlit UI, 13 tests. [Demo video](projeto8-escala-turnos/video/shift-scheduler-demo-web.mp4) |
| ⭐ [Subscription Billing Backend (Stripe webhooks)](projeto9-cobranca-stripe/) | Verifies signed webhooks, handles duplicate / forged / replayed / out-of-order events, and answers "does this customer have access?". Flask + SQLite, 18 tests. [Demo video](projeto9-cobranca-stripe/video/billing-backend-demo-web.mp4) |
| ⭐ [Agenda Fácil — Booking Web App](projeto4-agendamento/) | Full web app: customers book online from their phone, the owner manages the agenda in a password-protected dashboard. Flask + SQLite, 15 automated tests. |
| [Spreadsheet Reconciliation](projeto6-conciliacao/) | Compares company vs employee spreadsheets and shows mismatched amounts, missing and duplicated orders, with a per-employee summary. 8 automated tests. |
| [PDF Invoice Data Extractor](projeto2-extrator-pdf/) | Reads a folder of PDF invoices and builds an Excel sheet with the data, flagging anything that needs checking. Runs 100% locally. |

The demo videos are recorded by scripts in the repo (`make_video.py` in each project, built on [`tools/video`](tools/video/)). They drive the real apps, not mock-ups.

All sample data in this repository is fake and generated for demonstration.
