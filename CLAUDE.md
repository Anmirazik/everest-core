# EVerest Core — Project Context for Claude

## What This Repo Is

EVerest is an open-source EV charging software stack. This repo (`everest-core`) contains:
- C++ charge point implementation (OCPP 1.6 and 2.0.1)
- ISO 15118 stack (PyEvJosev, Josev PKI)
- SIL (Software-in-the-Loop) simulation configs
- Module configs for OCPP device model

Anna's work here is **configuration and setup**, not source code development.

## What Anna Works On

- SIL YAML configs: `config/config-sil-*.yaml`
- OCPP 2.0.1 component configs: `lib/everest/ocpp/config/v2/component_config/standardized/`
- PKI cert generation configs: `lib/everest/iso15118/test/iso15118/io/pki/configs/`
- Documentation: `docs/`
- The build output directory: `/home/annasdzik/build/dist/`

## Build Output

The built distribution is at `/home/annasdzik/build/dist/`. Many runtime config files live there
and need to match the source. Key paths in build:
- OCPP201 component config: `build/dist/share/everest/modules/OCPP201/component_config/standardized/`
- Josev PKI: `build/dist/libexec/everest/3rd_party/josev/iso15118/shared/pki/`
- EVerest certs: `build/dist/etc/everest/certs/`

**When Anna changes a source config file, also apply the change to the corresponding build path.**

## CSMS (Backend)

CitrineOS is used as the CSMS, running in Docker at:
- OCPP WebSocket: `ws://localhost:8081`
- Source: `/home/annasdzik/citrineos-core/`

**Anna does NOT modify CitrineOS source code.**

## OCPP 2.0.1 Device Model (Important!)

Unlike OCPP 1.6 (flat JSON key-value config), OCPP 2.0.1 uses a **SQLite database**
built from JSON schema files in `component_config/standardized/`. The DB is regenerated
from migrations in `core_migrations/` at startup. See `docs/ocpp201-vs-ocpp16-config.md`.

## PnC (Plug and Charge) Work

Active area of work. Anna is setting up ISO 15118 PnC in a local SIL test environment.
See `docs/ocpp201-pnc-setup.md` for full context, problems found, and fixes applied.

Key issues resolved:
- Missing `InternalCtrlr.json` and `core_migrations/` in build → copied from source
- CertificateInstallation → set `is_cert_install_needed: false` (no CPS locally)
- eMAID format violation → fixed `contractLeafCert.cnf` CN to `UKSWIC123456791`

**Current blocker:** CitrineOS does live OCSP validation to `https://www.example.com/`
(the OCSP URL embedded in test certs), which fails in a local environment.
A local OCSP responder is the planned fix — see `docs/ocpp201-pnc-setup.md`.

## Do Not

- Modify CitrineOS source (`/home/annasdzik/citrineos-core/`) — it's in production
- Suggest changes to EVerest C++ or Python source code
- Create new config files without asking first
