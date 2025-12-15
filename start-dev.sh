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

# Start frontend dev server in foreground (Ctrl+C to stop)
cd /home/vopenia/dev/meet/src/frontend
npm run dev -- --host 0.0.0.0
