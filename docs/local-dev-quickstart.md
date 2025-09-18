# Local Development Quickstart

This guide gets you from an empty machine to a running Meet stack on Kubernetes using Tilt. All commands are copy-pastable; adjust only when you know you need something different.

## 1. Install the toolchain

### macOS (Homebrew)
```bash
brew install docker kind kubectl helm helmfile tilt mkcert age
```

### Debian / Ubuntu
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin build-essential curl git
sudo usermod -aG docker "$USER"

# install Homebrew once, then pull the rest of the toolchain with it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
brew install kind kubectl helm helmfile tilt mkcert age
```

After installing Docker, start it and (on Linux) log out/in once so group membership applies. Trust the local CA for mkcert:
```bash
mkcert -install
```

## 2. Clone the repository

```bash
git clone git@github.com:vopenia/meet.git
cd meet
```

## 3. Prepare local secrets (optional)

Everything needed for local dev already ships in `src/helm/env.d/dev`. If you ever need to override secrets, edit `src/helm/env.d/dev/values.secrets.yaml`. No encryption is required for local use.

## 4. Build the local Kubernetes cluster

```bash
make build-k8s-cluster
```

The command provisions a Kind cluster, installs the required CRDs, and sets up an NGINX ingress.

## 5. Start the stack with Tilt

```bash
DEV_ENV=dev make start-tilt-keycloak
```

Tilt performs these steps for you:
- builds backend, frontend, summary, agents, and livekit Docker images
- runs `helmfile -e dev -n meet template` to render manifests
- applies everything into the `meet` namespace
- streams pod logs and health checks at http://localhost:10350/

Keep the Tilt process running while you work. The application is reachable at:
```bash
open https://meet.127.0.0.1.nip.io/
```

### Optional: SIP bridge helpers
- `livekit-sip` listens on `localhost:32062/udp` for SIP and exposes HTTP health on `32080`.
- `opensips` listens on `localhost:32060` and forwards pin-based calls to the LiveKit SIP bridge.
- Check them with:
  ```bash
  kubectl -n meet get pods -l app.kubernetes.io/name=livekit-sip
  kubectl -n meet logs deployment/livekit-sip
  ```

## 6. Common follow-up commands

Check resource status:
```bash
kubectl -n meet get pods
```

Tail backend logs:
```bash
kubectl -n meet logs deployment/meet-backend
```

Run Django migrations inside the running pod:
```bash
kubectl -n meet exec deployment/meet-backend -- python manage.py migrate --no-input
```

Run backend tests (from the repo root):
```bash
bin/pytest
```

## 7. Stop and clean up

Stop Tilt but keep the cluster:
```bash
tilt down
```

Delete the Kind cluster when you no longer need it:
```bash
kind delete cluster --name meet
```

That is all you need for local development. Re-run `DEV_ENV=dev make start-tilt-keycloak` whenever you want the stack back up.
