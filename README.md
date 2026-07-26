# Ghaymah Cloud Technical Assessment

Complete implementation of the five Ghaymah cloud assessment tasks: deployment,
monitoring, incident analysis, CI/CD, scalability, and the `mithal.space`
monitoring dashboard.

## Deliverables

| Question | Deliverable | Status |
|---|---|---|
| Q1 — Deploy and monitor an API | [Application, monitor, dashboard, and deployment guide](q1-deploy-monitor/README.md) | Live |
| Q2 — OOMKilled postmortem | [Professional blameless postmortem](q2-postmortem/POSTMORTEM.md) | Complete |
| Q3 — CI/CD pipeline | [Workflow](.github/workflows/deploy.yml) and [documentation](q3-cicd/CICD.md) | Complete |
| Q4 — Scalability | [Architecture, capacity calculation, cold starts, and storage](q4-scalability/SCALABILITY.md) | Complete |
| Q5 — `mithal.space` monitoring | [Collector and dashboard](q5-mithal-dashboard/) | Live |

## Live services

- Q1 API: <https://ghaymah-api-615e99f13665.hosted.ghaymah.systems>
- Q1 health: <https://ghaymah-api-615e99f13665.hosted.ghaymah.systems/health>
- Q1 OpenAPI: <https://ghaymah-api-615e99f13665.hosted.ghaymah.systems/docs>
- Q5 dashboard: <https://mithal-monitor-292f00f076b1.hosted.ghaymah.systems>
- Docker Hub API image: `docker.io/agamy74/ghaymah-api`
- Docker Hub dashboard image: `docker.io/agamy74/mithal-monitor`
- Public repository: <https://github.com/yassinelagamy/GHyamah-Test>
- Successful protected deployment run:
  <https://github.com/yassinelagamy/GHyamah-Test/actions/runs/30215537509>

## Deployment evidence

The curated evidence set is documented in
[docs/evidence/README.md](docs/evidence/README.md).

| Evidence | Screenshot |
|---|---|
| Ghaymah project and applications | [Project](docs/evidence/screenshots/01-ghaymah-project.png) |
| Q1 API service | [Q1 service](docs/evidence/screenshots/02-q1-service.png) |
| Q1 live health response | [Q1 health](docs/evidence/screenshots/03-q1-health.png) |
| Q1 monitoring dashboard | [Q1 dashboard](docs/evidence/screenshots/04-q1-dashboard.png) |
| Q5 Ghaymah service | [Q5 service](docs/evidence/screenshots/05-q5-service.png) |
| Q5 monitoring dashboard | [Q5 dashboard](docs/evidence/screenshots/06-q5-dashboard.png) |
| GitHub production protection | [Approval protection](docs/evidence/screenshots/07-production-approval.png) |
| Successful CI/CD run | [Pipeline](docs/evidence/screenshots/08-pipeline-success.png) |

## CI/CD behavior

The workflow:

1. Builds `q1-deploy-monitor/app`.
2. Embeds the Git commit as `RELEASE_SHA`.
3. Pushes immutable SHA and `latest` tags to Docker Hub.
4. Starts the immutable image in an ephemeral staging container.
5. Requires `status=ok` and the expected SHA from `/health`.
6. Pauses for the required reviewer on the GitHub `production` Environment.
7. Verifies that the live Ghaymah application serves the approved SHA.

Ghaymah CLI `0.0.24` documents interactive email/password login but does not
publish API-token authentication or the external-image field for
`gy resource app update`. Production image promotion therefore uses the
authenticated dashboard and is followed by automated release verification. The
workflow does not report a stale or unverified deployment as successful.

The account's five-resource free-plan limit prevents a third persistent Ghaymah
application, so staging runs as an isolated ephemeral container on the Actions
runner. Production and the Q5 dashboard remain live on Ghaymah.

## Verified platform information

- The authenticated deployment form accepts a Git repository or container image,
  registry pull secret, instance size, application name, port, public access,
  custom domain, environment variables, and storage volumes.
- Docker Hub is available through External Integrations.
- The authenticated volume form displays a range from 50 MiB to 10 GiB.
- The official CLI installs with
  `curl -sSL https://cli.ghaymah.systems/install.sh | bash`.
- CLI `0.0.24` exposes `gy version`, `gy auth login`,
  `gy resource app init`, `gy resource app launch`, logs, and a generic
  `gy resource app update`.

Official references:

- [Ghaymah CLI documentation](https://ghaymah.systems/docs)
- [Ghaymah CLI overview](https://ghaymah.systems/cli)
- [Ghaymah products](https://ghaymah.systems/products)

## Local checks

```bash
docker build --build-arg RELEASE_SHA=local \
  -t ghaymah-api:local q1-deploy-monitor/app
docker run --rm -p 8080:8080 ghaymah-api:local
curl -f http://localhost:8080/health
```

```bash
APP_URL=https://ghaymah-api-615e99f13665.hosted.ghaymah.systems \
  python q1-deploy-monitor/monitor/monitor.py --once
```

```bash
python q5-mithal-dashboard/collector/collect.py --once
```

No credentials are stored in the repository. Docker Hub credentials remain in
GitHub Secrets and Ghaymah registry authentication remains in the platform
integration.
