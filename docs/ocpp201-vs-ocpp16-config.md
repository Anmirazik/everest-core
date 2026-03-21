# OCPP 2.0.1 vs 1.6 — Config Files & Database Explained

## What Happened Today (Session Notes)

When running `config-sil-ocpp201-pnc.yaml`, EVerest crashed with:

```
[CRIT] Required value SupportedOcppVersions of component InternalCtrlr could not be retrieved
```

Then after fixing that:

```
[ERRO] Migration files must be in a directory: .../OCPP201/core_migrations
```

### Root Cause

The build at `/home/annasdzik/build/dist/share/everest/modules/OCPP201/` was missing two things that are present in the source tree but weren't installed:

| Missing file/dir | Source location | Installed to |
|---|---|---|
| `InternalCtrlr.json` | `lib/everest/ocpp/config/v2/component_config/standardized/` | `build/dist/.../OCPP201/component_config/standardized/` |
| `core_migrations/` (directory) | `lib/everest/ocpp/config/v2/core_migrations/` | `build/dist/.../OCPP201/core_migrations/` |

Both were manually copied as a workaround. The proper fix long-term is to rebuild/reinstall so the build system puts them there automatically.

---

## OCPP 1.6 Config: How It Works

In OCPP 1.6, all configuration lives in **a single flat JSON file** (e.g. `cp001.json` or `user_config.json`).

```
build/dist/share/everest/modules/OCPP/
├── config/
│   └── cp001.json          ← all settings in one flat file
└── user_config.json        ← overrides on top of cp001.json
```

`cp001.json` contains key-value pairs for everything: heartbeat interval, connection URL, auth settings, etc. It maps directly to the OCPP 1.6 spec's "Configuration Keys".

```json
{
  "Core": {
    "HeartbeatInterval": 60,
    "ConnectionUrl": "ws://localhost:9000/cp001"
  },
  "SmartCharging": {
    "ChargeProfileMaxStackLevel": 10
  }
}
```

**No database involved** — settings are read from and written to that JSON file directly.

---

## OCPP 2.0.1 Config: How It Works

OCPP 2.0.1 introduced the **Device Model** — a structured hierarchy of Components and Variables replacing flat config keys. EVerest implements this with:

1. **Component config JSON files** — define the schema and default values
2. **SQLite databases** — store the live runtime values

### Directory Structure

```
build/dist/share/everest/modules/OCPP201/
├── component_config/
│   └── standardized/
│       ├── InternalCtrlr.json       ← connection URL, logging, certs
│       ├── OCPPCommCtrlr.json       ← heartbeat, message timeout
│       ├── AuthCtrlr.json           ← authorization settings
│       ├── ChargingStation.json     ← charger identity
│       ├── SmartChargingCtrlr.json  ← smart charging
│       └── ... (one file per component)
├── device_model_migrations/
│   ├── 1_up-initial.sql
│   ├── 2_up-variable_source.sql
│   └── 3_up-variable_required.sql
├── core_migrations/
│   ├── 1_up-initial.sql
│   ├── 2_up-auth_cache_management.sql
│   └── ... (transaction/profile history schema)
├── device_model_storage.db          ← generated at runtime
├── everest_device_model_storage.db  ← generated at runtime
└── cp.db  (at /tmp/ocpp201/cp.db)  ← generated at runtime
```

### The Two-Step Process on Startup

1. **EVerest reads all `component_config/*.json` files** and builds the Device Model in memory.
2. **It opens/creates the SQLite databases**, running any pending SQL migration files to set up the schema.
3. Default values from the JSON files are written into the DB. Runtime changes (from CSMS via SetVariables) are persisted there.

### What Each Database Does

| Database | Purpose |
|---|---|
| `device_model_storage.db` | Stores all OCPP 2.x Component/Variable values (the Device Model). This is what the CSMS reads and writes via GetVariables/SetVariables. |
| `everest_device_model_storage.db` | EVerest-specific extensions to the device model (custom variables not in the OCPP spec). |
| `/tmp/ocpp201/cp.db` | Transaction history, auth cache, charging profiles, message queue. Migrated by `core_migrations/`. |

### Why You Delete the DBs When Changing Config

The DBs are generated from the JSON component config files. If you change a JSON file (e.g. update `NetworkConnectionProfiles` in `InternalCtrlr.json`), the DB still has the old value cached. Deleting the DBs forces EVerest to regenerate them from the JSON files on next startup, picking up your changes.

---

## Key Differences Summary

| | OCPP 1.6 | OCPP 2.0.1 |
|---|---|---|
| Config format | Single flat JSON file | Many JSON files, one per Component |
| Config location | One file with all keys | `component_config/standardized/*.json` |
| Runtime storage | JSON file updated in place | SQLite databases |
| Connection URL | Key in `cp001.json` | `NetworkConnectionProfiles` in `InternalCtrlr.json` |
| DB migrations | None | SQL migration files in `device_model_migrations/` and `core_migrations/` |
| CSMS can change settings | No (read-only from CSMS side) | Yes, via GetVariables/SetVariables messages |
| Config concept | Flat key-value list | Hierarchical Component → Variable tree |

---

## Where the CSMS URL Lives (OCPP 2.0.1)

`InternalCtrlr.json` → `NetworkConnectionProfiles` → `ocppCsmsUrl`:

```json
"value": "[{\"configurationSlot\": 1, \"connectionData\": {
    \"ocppCsmsUrl\": \"ws://localhost:8081\",
    \"ocppVersion\": \"OCPP20\",
    \"securityProfile\": 1
}}]"
```

After changing this file, always delete the device model DBs so the new value is loaded.
