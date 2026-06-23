#!/usr/bin/env bash
cd "$(dirname "$0")"

echo ""
echo " ================================================"
echo "  Smart AI Attendance System - Stopping"
echo " ================================================"
echo ""

docker compose -f docker-compose.dev.yml down

echo ""
echo " Stopped. All data is preserved in Docker volumes."
echo " Run ./start.sh to start again."
echo ""
