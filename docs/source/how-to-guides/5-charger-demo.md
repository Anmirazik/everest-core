# EVerest 5-Charger Demo Guide

## Overview
This demo spins up **5 simulated chargers**, each with **2 EVSEs**, all connected to a single SteVe OCPP central system.

---

## Prerequisites (One-Time Setup)

### 1. Create Docker network
```bash
docker network create --driver bridge --ipv6 --subnet fd00::/80 infranet_network --attachable
```

### 2. Start MQTT broker
```bash
docker run -d --name mqtt-server --network infranet_network -p 1883:1883 -p 9001:9001 ghcr.io/everest/containers/mosquitto:docker-images-v0.1.0
```

### 3. Build EVerest
```bash
cd ~/everest/everest-core/build
source venv/bin/activate
make iso15118_pip_install_dist
cmake .. && make -j$(nproc) && make install
```

### 4. Register chargers in SteVe

Open http://localhost:8180/steve (admin / 1234) and add the following Charge Point IDs:
- `cp001-everest`
- `cp002-everest`
- `cp003-everest`
- `cp004-everest`
- `cp005-everest`

---

## Step 1 — Start the 5 Chargers

Open **5 separate terminals** and run one script per terminal:

```bash
# Terminal 1
~/everest/everest-core/build/run-scripts/run-sil-ocpp-two-evse-load-balance-cp001.sh

# Terminal 2
~/everest/everest-core/build/run-scripts/run-sil-ocpp-two-evse-load-balance-cp002.sh

# Terminal 3
~/everest/everest-core/build/run-scripts/run-sil-ocpp-two-evse-load-balance-cp003.sh

# Terminal 4
~/everest/everest-core/build/run-scripts/run-sil-ocpp-two-evse-load-balance-cp004.sh

# Terminal 5
~/everest/everest-core/build/run-scripts/run-sil-ocpp-two-evse-load-balance-cp005.sh
```

---

## Step 2 — Start Node-RED UI

In a new terminal:

```bash
~/everest/everest-core/build/run-scripts/nodered-sil-two-evse-iso15118.sh
```

The script will print the port it picked, e.g.:
```
Starting Node-RED on port 54321
```

Open: **http://localhost:\<printed port\>/ui**

---

## Pages to Open

| What | URL | Credentials |
|------|-----|-------------|
| SteVe OCPP Management | http://localhost:8180/steve | admin / 1234 |
| Node-RED UI (EV controls) | http://localhost:`<printed port>`/ui | — |

---

## Setting Charging Profiles via SteVe

Go to **http://localhost:8180/steve** → Operations → SetChargingProfile.

### TxProfile (limit a specific connector during an active transaction)

| Field | Value |
|-------|-------|
| ChargePointId | `cp001-everest` (or whichever charger) |
| ConnectorId | `1` or `2` (must match an active transaction) |
| ChargingProfilePurpose | `TxProfile` |
| ChargingProfileKind | `Absolute` |
| StackLevel | `1` |
| startSchedule | any past UTC time e.g. `2026-01-01T00:00:00.000Z` |
| ChargingRateUnit | `A` |
| limit | e.g. `8.0` |

> TxProfile requires an active transaction on the connector. It takes effect immediately.

---

### ChargePointMaxProfile (station-wide max limit)

| Field | Value |
|-------|-------|
| ChargePointId | `cp001-everest` (or whichever charger) |
| ConnectorId | `0` (must be 0 for station-wide) |
| ChargingProfilePurpose | `ChargePointMaxProfile` |
| ChargingProfileKind | `Absolute` |
| StackLevel | `1` |
| startSchedule | any past UTC time e.g. `2026-01-01T00:00:00.000Z` |
| ChargingRateUnit | `A` |
| limit | e.g. `8.0` |

> **Important:** `startSchedule` must be a UTC time that has **already passed**. If set to a future time, the charger will accept the profile but not apply it until that time is reached. Always use a past UTC timestamp (e.g. `2026-01-01T00:00:00.000Z`) to apply the limit immediately.

> `ConnectorId` must be `0` for ChargePointMaxProfile. Sending to connector 1 or 2 will result in a `Rejected` response.

---

## Stopping the Demo

```bash
# Ctrl+C in each charger terminal

# Stop MQTT
docker stop mqtt-server && docker rm mqtt-server
```
