# Tool Planner

Tool Planner is a mobile-first elevator checkout and reservation application.
The backend is Python/FastAPI with PostgreSQL; the frontend is React/TypeScript.
See [the product analysis](docs/analysis/README.md) and [solution design](docs/analysis/solution-design.md).

## Local development

Requirements: Python 3.12+, Node.js 22+, Docker, and `docker-compose`.

1. Copy `.env.example` to `.env` and use a local-only development password.
2. Start the stack:

   ```sh
   docker-compose up --build -d
   ```

3. Create two administrator accounts interactively. Password prompts do not
   echo; both accounts must change their initial password on first login:

   ```sh
   docker-compose run --rm api python -m toolplanner.bootstrap_admin --count 2
   ```

4. Open `http://localhost:8080`. The initial location is `Geel`, department is
   `Sites & Facilities`, and the first elevator is `LIFT-001`.
5. To stop the local services without removing the persistent database volume:

   ```sh
   docker-compose down
   ```

The local database password is only a development default. Do not use it for a
deployed environment. Production secrets and the PostgreSQL URL are supplied
through the environment/Helm secret reference.

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

The API container runs Alembic migrations during local startup. For a manually
run migration:

```sh
docker-compose run --rm api alembic upgrade head
```

The three-year retention job runs daily in Helm. After restoring a backup, run
retention cleanup before making the application available:

```sh
docker-compose run --rm api python -m toolplanner.retention
```

No default admin credentials are included in source or container images.

## Kubernetes deployment

Build and publish the API and web images, create the database URL secret, then
provide environment-specific ingress, image, and secret settings through Helm.
The chart does not install PostgreSQL or infrastructure services:

```sh
helm lint deploy/helm/tool-planner
helm template tool-planner deploy/helm/tool-planner \
  --set image.api.repository=YOUR_REGISTRY/tool-planner-api \
  --set image.api.tag=YOUR_TAG \
  --set image.web.repository=YOUR_REGISTRY/tool-planner-web \
  --set image.web.tag=YOUR_TAG \
  --set ingress.host=YOUR_HOST
```

Review the rendered chart, secret references, ingress/TLS configuration,
backup/restore process, and operational limits before deployment.
