#!/bin/bash
# Start development services for meet project

# Start Docker services
docker compose -f /home/vopenia/dev/meet/compose.yml up -d \
  app-dev \
  redis \
  postgresql \
  keycloak \
  kc_postgresql \
  minio \
  nginx \
  nginx-lan \
  livekit \
  livekit-egress \
  livekit-sip \
  kamailio \
  mailcatcher

# Start frontend dev server in background
cd /home/vopenia/dev/meet/src/frontend
nohup npm run dev -- --host 0.0.0.0 > /tmp/meet-frontend.log 2>&1 &
echo "Frontend started in background (PID: $!)"
echo "Logs: /tmp/meet-frontend.log"
