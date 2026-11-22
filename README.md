# Tool Planner

Tool Planner is a mobile-first elevator checkout and reservation application.
The backend is Python/FastAPI with PostgreSQL; the frontend is React/TypeScript.
See [the product analysis](docs/analysis/README.md) and [solution design](docs/analysis/solution-design.md).

## Local development

Requirements: Python 3.12+, `uv`, Node.js 22+, npm, Docker, and `docker-compose`.

1. Start Docker Desktop.
2. Start PostgreSQL in Docker and the API/frontend as local processes:

   ```sh
   ./scripts/start-local.sh
   ```

   The script copies `.env.example` to `.env` only when needed, starts only the
   PostgreSQL container, syncs locked Python/Node dependencies, applies
   migrations, and launches Uvicorn and Vite locally. It waits for the API and
   frontend to be ready. Uvicorn reloads the API when backend source files
   change. PostgreSQL is published on `127.0.0.1:5433` by
   default; change `LOCAL_POSTGRES_PORT` in `.env` if that port is in use. The
   included database password is only for local development.
3. Create two administrator accounts interactively. Password prompts do not
   echo; both accounts must change their initial password on first login:

   ```sh
   ./scripts/create-local-admins.sh
   ```

4. Open `http://127.0.0.1:5173`. The initial location is `Geel`, department is
   `Sites & Facilities`, and the first elevator is `LIFT-001`.
5. To stop the local API, frontend, and PostgreSQL without removing database
   data:

   ```sh
   ./scripts/stop-local.sh
   ```

The Compose file retains API/web container definitions for image and deployment
smoke tests; the local start script does not build or run those images. The
local database password is only a development default. Do not use it for a
deployed environment. Production secrets and the PostgreSQL URL are supplied
through the Helm secret reference.

## Backend tests

```sh
cd backend
uv sync --frozen --extra dev
uv run --frozen pytest
```

The suite currently uses SQLite for fast API/domain checks. PostgreSQL remains
the production datastore; run PostgreSQL migration and deployment checks
separately before release.

## Frontend build

```sh
cd web
npm ci --registry=https://registry.npmjs.org
npm run build
```

## Database migrations and maintenance

The local start script runs Alembic migrations before starting the API. For a
manually run migration while the local stack is up:

```sh
cd backend
TOOLPLANNER_DATABASE_URL="$(cat ../.local/database-url)" uv run --frozen alembic upgrade head
```

The three-year retention job runs daily in Helm. After restoring a backup, run
retention cleanup before making the application available (with the local
stack running):

```sh
cd backend
TOOLPLANNER_DATABASE_URL="$(cat ../.local/database-url)" uv run --frozen python -m toolplanner.retention
```

No default admin credentials are included in source or container images.

## Kubernetes deployment

The GitHub Actions workflow builds both images for `linux/arm64` on pull
requests without publishing. A `vMAJOR.MINOR.PATCH` tag publishes the API and
web images to GHCR with version and commit-specific tags; the workflow summary
and the `tool-planner-release-metadata` artifact record their digests. Deploy
using those digest references, create the database URL secret, and provide
environment-specific settings through Helm.
For private GHCR packages, create a Kubernetes image-pull secret and pass it
through `imagePullSecrets`. The chart does not install PostgreSQL or
infrastructure services:

```sh
helm lint deploy/helm/tool-planner
helm template tool-planner deploy/helm/tool-planner \
  --set image.api.repository=ghcr.io/OWNER/toolplanner-api \
  --set-string image.api.digest=sha256:API_IMAGE_DIGEST \
  --set image.web.repository=ghcr.io/OWNER/toolplanner-web \
  --set-string image.web.digest=sha256:WEB_IMAGE_DIGEST \
  --set imagePullSecrets[0].name=ghcr-pull-secret \
  --set ingress.host=YOUR_HOST
```

Omit `imagePullSecrets` for public images. Review the rendered chart, secret
references, ingress/TLS configuration, backup/restore process, and operational
limits before deployment. Confirm that the selected GHCR package visibility
and credentials allow the cluster to pull the images.

The web pod proxies API requests using the API Service's fully qualified
in-cluster DNS name. If the cluster uses a DNS domain other than
`cluster.local`, set `web.clusterDomain` to that domain; `web.dnsResolver`
may be set to the cluster DNS resolver address when it cannot be inferred from
the pod's `/etc/resolv.conf`. When an external Gateway API route targets the
web Service, its `backendRef.name` must match the chart's rendered Service
name (for a `tool-planner` release, `tool-planner-web`).

The RK1 cluster's Argo CD configuration is maintained in the
[cluster-template2 repository](https://github.com/enicky/cluster-template2).
It consumes this chart at a release tag and keeps cluster-specific PostgreSQL,
GHCR credentials, and HTTPRoute configuration in the cluster repository.

### Manually publishing a release's images

Run the release script from a clean, up-to-date `main` checkout. It requires
confirmation before pushing a version tag; pushing the tag starts the GitHub
Actions build and GHCR publication. The initial release uses the current Helm
`appVersion`; later releases increment the latest version tag:

```sh
./scripts/release-images.sh initial
./scripts/release-images.sh patch
./scripts/release-images.sh minor
./scripts/release-images.sh major
```

Choose one command per release. The script only creates and pushes the Git tag;
it does not edit application or chart version files.
