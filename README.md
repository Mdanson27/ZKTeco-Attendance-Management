# AutoMinds Africa — Attendance Command Center

A polished, local-first **ZKTeco F18 attendance integration proof of concept** built with Python, SQLite and vanilla HTML/CSS/JS.

## Important status

**SIMULATOR ONLY.** No physical F18 is connected. Every demo event is labeled `SIMULATED`. The employee names and branches are fictional examples. This is **not** production-ready for real employee records; a production rollout requires authentication, authorization, secure ingestion, audited rules, monitored synchronization, backups, device enrollment, and privacy review.

## Run on Windows

1. Install Python 3.10+.
2. Double-click `START_DEMO.bat` or run `python app.py`.
3. Browse to `http://127.0.0.1:8765/`.
4. Select an employee and click **Simulate Fingerprint Scan**.

The application binds to `127.0.0.1`, deliberately limiting access to the local computer. No extra Python packages are needed. SQLite event data stays on your machine and is excluded from Git.

## Features

- AutoMinds Africa logo and responsive branded dashboard
- Four sample branch performance cards
- Live 2-second polling across open dashboard tabs
- Check-in and check-out simulation with daily state reset
- Employee/branch filters and CSV reports
- A health endpoint at `/api/health`
- Persistent local demo event storage in SQLite

## Physical-device integration roadmap

1. Obtain authorization and back up current ZKTeco settings.
2. Identify F18 firmware, ADMS/TA Push/AC Push or SDK compatibility, IP settings, and network route.
3. Connect one test device on a secured network and validate attendance event format.
4. Build a separate authenticated event-ingestion service with deduplication, offline replay, clock validation, and device registry.
5. Add tenant/branch isolation, roles, audit logs, TLS, retention rules, backups and privacy compliance before production use.

**Logo:** `autominds-logo.jpeg` is copied from the company resource file supplied on the owner's authorized desktop.
