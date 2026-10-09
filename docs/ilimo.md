# Running Meet with the Ilimo SFU

[Ilimo](https://github.com/vopenia-io/ilimo) is an SFU that speaks the
LiveKit protocol. This branch runs Meet's development stack against it
instead of `livekit-server`.

## Start

Ilimo runs on the host, built from a checkout of its repository
(`../../ilimo/repos/ilimo` by default, set `ILIMO_REPO` otherwise):

```sh
make create-env-files   # once
make build-backend build-frontend   # once, or after changes
make run-ilimo
make migrate            # once
```

`make run-ilimo` starts the backend, Keycloak, nginx and the frontend
without `livekit-server`, then builds and starts Ilimo with
`docker/ilimo/ilimo.yaml`. Meet is on http://localhost:3000. Ilimo listens
where `livekit-server` did, `127.0.0.1.nip.io:7880` for signaling and UDP
7882-7883 for media, uses the same API key, and sends its webhooks to the
backend on `127.0.0.1:8071`. Its log is `data/ilimo.log`.

Media goes to this machine's network address (`en0` on macOS, set
`ILIMO_PUBLIC_IP` otherwise): Chrome gathers no ICE candidate on the
loopback interface.

`make stop-ilimo` stops Ilimo; `make stop` stops the containers.

## Kubernetes (Helm)

`MEET_SFU=ilimo` makes the Helm environments (`src/helm/helmfile.yaml.gotmpl`,
used by Tilt) install Ilimo's chart instead of `livekit-server` and
`livekit-egress`. Ilimo takes livekit-server's host
(`livekit.127.0.0.1.nip.io`), API key and webhook URL, so Meet's own values
do not change. Its values are `src/helm/env.d/<env>/values.ilimo.yaml.gotmpl`.

```sh
MEET_SFU=ilimo make start-tilt-keycloak
```

The chart comes from `vopenia-io/ilimo-deploy` (`charts/ilimo`); set
`ILIMO_CHART` to use a local checkout, `ILIMO_IMAGE` and `ILIMO_TAG` for
another image.

Ilimo runs with `hostNetwork` and announces the Kubernetes node's address
to clients: browsers must reach that address on UDP 7882. In kind, they
cannot: livekit-server gets through with its TURN server on port 443, which
Ilimo does not have yet. Media therefore needs a cluster whose nodes the
browsers can reach (staging); in kind, use `make run-ilimo` instead.

## Not covered

Recording and transcription (`livekit-egress`, LiveKit agents) and SIP are
not available with Ilimo yet: `compose.ilimo.yml` does not start them and
turns telephony off.
