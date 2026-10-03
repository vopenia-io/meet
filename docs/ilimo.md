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

## Not covered

Recording and transcription (`livekit-egress`, LiveKit agents) and SIP are
not available with Ilimo yet: `compose.ilimo.yml` does not start them and
turns telephony off.
