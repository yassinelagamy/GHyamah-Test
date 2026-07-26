# Ghaymah Cloud Technical Assessment

This repository contains the five deliverables for the Ghaymah cloud platform assessment.

## Deliverables

| Question | Deliverable | Status |
|---|---|---|
| Q1 — Deploy and monitor an API | [Application, monitor, dashboard, and deployment guide](q1-deploy-monitor/README.md) | Implementation complete; live Ghaymah deployment evidence pending |
| Q2 — OOMKilled postmortem | [POSTMORTEM.md](q2-postmortem/POSTMORTEM.md) | Complete |
| Q3 — CI/CD pipeline | [Workflow](.github/workflows/deploy.yml) and [CICD.md](q3-cicd/CICD.md) | Build/push and approval gate complete; automated Ghaymah image update awaiting a documented non-interactive command |
| Q4 — Scalability | [SCALABILITY.md](q4-scalability/SCALABILITY.md) | Complete |
| Q5 — mithal.space monitoring | [Collector and dashboard](q5-mithal-dashboard/) | Implementation present; live deployment evidence pending |

## Current verified Ghaymah information

The current public Ghaymah documentation establishes the following:

- The official CLI is installed with `curl -sSL https://cli.ghaymah.systems/install.sh | bash`.
- The executable is named `gy`; the current binary reports its release with `gy version`.
- Authentication uses `gy auth login`. The current CLI exposes `--email` and `--password` flags, but does not expose an API-token flag.
- `gy resource app init --project-id <PROJECT_ID> --name <APP_NAME>` creates `.ghaymah.json`.
- `gy resource app launch [PATH]` builds and deploys the application described by the local Dockerfile and `.ghaymah.json`.
- `gy resource app logs` retrieves application logs.
- `gy resource app update <APP_ID>` accepts JSON input or dot-notation updates, but the public help does not identify a supported external-image field.
- The documented `.ghaymah.json` example includes the application ID/name, project ID, exposed port, public access, resource tier, and Dockerfile name.
- Ghaymah lists a container registry, CI/CD, monitoring, autoscaling, APIs, and Block Storage as products or capabilities, but the public pages reviewed for this submission do not expose enough operational syntax or limits to use their hard specifics safely.
- The authenticated deployment form supports either a Git repository or container image URL, an optional registry pull secret, instance size, application name, port, public access, custom domain, environment variables, and attached storage volumes.
- The authenticated volume form displays a supported size range of 50 MiB to 10 GiB.
- The authenticated External Integrations page exposes Docker Hub connection fields; no Ghaymah-hosted registry endpoint or push instructions were visible.

Official references:

- [Ghaymah CLI documentation](https://ghaymah.systems/docs)
- [Ghaymah CLI overview](https://ghaymah.systems/cli)
- [Ghaymah products](https://ghaymah.systems/products)
- [Ghaymah changelog](https://ghaymah.systems/changelog)

## Local quick checks

### Q1 API

```bash
python -m pip install -r q1-deploy-monitor/app/requirements.txt
python -m uvicorn main:app --app-dir q1-deploy-monitor/app --host 0.0.0.0 --port 8080
```

Then open:

- `http://localhost:8080/health`
- `http://localhost:8080/metrics`
- `http://localhost:8080/docs`

### Q1 monitor and dashboard

```bash
APP_URL=http://localhost:8080 python q1-deploy-monitor/monitor/monitor.py --once
python -m http.server 8000 --directory q1-deploy-monitor
```

Open `http://localhost:8000/dashboard/index.html`.

### Q5 collector

```bash
python -m pip install -r q5-mithal-dashboard/collector/requirements.txt
python q5-mithal-dashboard/collector/collect.py --once
```

## Work that requires account access

The following cannot be completed safely from source code alone:

1. Create the Ghaymah projects/applications and obtain their IDs and public URLs.
2. Push the Docker images using the owner's registry credentials.
3. Deploy Q1 and Q5 and capture the required screenshots.
4. Configure GitHub secrets and the `production` Environment with required reviewers.
5. Confirm the supported non-interactive Ghaymah authentication mechanism for GitHub Actions.
6. Confirm the command/API that updates an existing Ghaymah application to a specific external image tag.
7. Run the workflow, approve production, and capture the approval evidence.
8. Confirm monitoring/autoscaling controls and Block Storage limits in the authenticated dashboard before removing remaining `VERIFY` markers.

No credentials should be committed to this repository. Use GitHub Secrets and Ghaymah's secret-management controls for sensitive values.
