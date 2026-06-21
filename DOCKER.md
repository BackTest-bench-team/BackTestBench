# Docker Setup Guide for BackTestBench

This project is fully configured for Docker deployment with development, testing, and production modes.

## Quick Start

### Build the Docker Image

```bash
docker build -t backtest-bench:latest .
```

### Run the Demo

```bash
docker run --rm backtest-bench:latest
```

This will execute the MA crossover strategy demo and show the results.

## Using Docker Compose

### Run the Main Application

```bash
docker-compose up backtest-app
```

This runs the MA crossover demo strategy.

### Run Tests

```bash
docker-compose run --rm test
```

This executes the full pytest suite (21 tests).

### Interactive Development Shell

```bash
docker-compose --profile dev run --rm dev
```

This launches an interactive bash shell with the application code mounted.

## File Structure

- **Dockerfile** — Multi-stage build optimizing for size and build time
  - Builder stage: installs dependencies
  - Runtime stage: minimal image with only production requirements
  
- **docker-compose.yml** — Orchestration configuration with three services:
  - `backtest-app` — Main application service
  - `test` — Test runner service (profile: test)
  - `dev` — Interactive development environment (profile: dev)

- **.dockerignore** — Excludes unnecessary files from Docker context

- **requirements.txt** — Python package dependencies
  - PyYAML — YAML configuration parsing
  - pytest — Testing framework
  - python-dotenv — Environment variable management

- **pyproject.toml** — Project metadata and build configuration
  - Python 3.10+ requirement
  - Development dependencies (pytest-cov, black, ruff, mypy)
  - Tool configurations

## Environment Variables

Configure via `.env` file (see `.env.example`):

```bash
PYTHONUNBUFFERED=1  # Real-time log output
PYTHONDONTWRITEBYTECODE=1  # No .pyc files
```

## Volume Mounts

Services have volumes mounted for development:

- `./src` — Application source code
- `./config` — Strategy configurations
- `./tests` — Test suite
- `./examples` — Demo scripts

Changes to these directories are reflected in running containers.

## Multi-Stage Build Benefits

The Dockerfile uses multi-stage builds to minimize final image size:

1. **Builder Stage** — Installs all dependencies (larger)
2. **Runtime Stage** — Only copies compiled wheels and app code (minimal)

This results in a lean, production-ready image.

## Common Commands

```bash
# Build image
docker build -t backtest-bench:latest .

# Run demo
docker run --rm backtest-bench:latest

# Run tests with Docker Compose
docker-compose run --rm test

# Interactive shell
docker-compose --profile dev run --rm dev

# Check image size
docker images | grep backtest-bench

# View image layers
docker history backtest-bench:latest

# Clean up
docker-compose down --volumes
docker rmi backtest-bench:latest
```

## Development Workflow

1. Make code changes in your local editor
2. Run tests in container: `docker-compose run --rm test`
3. Test interactively: `docker-compose --profile dev run --rm dev`
4. Run demo: `docker run --rm backtest-bench:latest`

## Production Deployment

The image is ready for production:

```bash
# Build with tag
docker build -t backtest-bench:1.0.0 .

# Push to registry
docker tag backtest-bench:1.0.0 your-registry/backtest-bench:1.0.0
docker push your-registry/backtest-bench:1.0.0

# Run in production
docker run --rm \
  -v /path/to/config:/app/config \
  -v /path/to/reports:/app/reports \
  your-registry/backtest-bench:1.0.0
```

## Testing

All 21 tests pass in Docker:

```bash
docker-compose run --rm test

# Output:
# ============================== 21 passed in 0.05s ==============================
```

## Troubleshooting

### Image Build Fails

```bash
# Check build with verbose output
docker build --progress=plain -t backtest-bench:latest .

# Clean up and rebuild
docker system prune -a
docker build -t backtest-bench:latest .
```

### Container Won't Start

```bash
# Check logs
docker run -it backtest-bench:latest /bin/bash

# Verify dependencies
docker run --rm backtest-bench:latest pip list
```

### Permission Issues with Volumes

```bash
# Run with user ID
docker run --rm --user $(id -u):$(id -g) backtest-bench:latest
```

## Notes

- Python 3.10 is required (specified in Dockerfile and pyproject.toml)
- Tests require pytest (included in requirements.txt)
- YAML configurations are loaded via PyYAML
- All code runs with Python optimizations disabled for debugging
