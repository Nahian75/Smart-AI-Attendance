#!/usr/bin/env bash
# ================================================================
#  Stops the cloud stack on the GCP VM (postgres, redis, backend,
#  celery, frontend, nginx, mediamtx). Data is preserved in Docker
#  volumes. Run ./start_cloud.sh to start again.
# ================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo " ================================================"
echo "  Smart AI Attendance — Cloud Stopping"
echo " ================================================"
echo ""

docker compose -f docker-compose.cloud.yml down

echo ""
echo " Stopped. All data is preserved in Docker volumes."
echo " Run ./start_cloud.sh to start again."
echo ""
