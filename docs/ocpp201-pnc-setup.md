# OCPP 2.0.1 Plug and Charge (PnC) — SIL Setup Guide

This document captures everything learned while getting PnC working locally using EVerest + CitrineOS.
It is written for someone who has never set up OCPP 2.0.1 or PnC before.

---

## What is PnC?

Plug and Charge (ISO 15118 / OCPP 2.0.1 use case C07) lets an EV authorize automatically using
a **contract certificate** stored in the vehicle — no RFID card needed.

The flow:
1. EV plugs in → SECC (charge point) and EVCC (car) do ISO 15118 handshake
2. EVCC presents its **contract certificate** (eMAID = electric mobility contract ID)
3. Charge point validates the cert and sends an `AuthorizeRequest` to the CSMS
4. CSMS checks cert status via OCSP → returns `Accepted` or `Invalid`
5. If accepted, charging starts

---

## Stack Used

| Component | Role |
|-----------|------|
| EVerest | Charge point (SECC), runs locally |
| CitrineOS | CSMS (backend), runs in Docker |
| PyEvJosev | EV simulator (EVCC), included in EVerest |
| Josev PKI | Script that generates all test certs |

Config file: `config/config-sil-ocpp201-pnc.yaml`

---

## How OCPP 2.0.1 Config Differs from 1.6

### OCPP 1.6 (flat key-value)
Config is a single flat JSON file, e.g.:
```json
{
  "AuthorizeRemoteStart": true,
  "LocalPreAuthorize": true
}
```

### OCPP 2.0.1 (Component/Variable device model)
Config is a **SQLite database** built from many JSON schema files.
Each setting has a Component, Variable, and Attribute hierarchy:
```
Component: AuthCtrlr
  Variable: AuthorizeRemoteStart
    Attribute: Actual = true
```

The JSON files live in:
```
lib/everest/ocpp/config/v2/component_config/standardized/
```

The SQLite DB is generated at runtime from these JSON files using migration scripts in:
```
lib/everest/ocpp/config/v2/core_migrations/
```

**If either of these directories is missing from the build, EVerest will crash at startup.**

---

## Problems We Hit and How We Fixed Them

### 1. Missing `InternalCtrlr.json` → CRIT error about `SupportedOcppVersions`

**Symptom:** EVerest crashes immediately with a `CRIT` error about `SupportedOcppVersions`.

**Cause:** The build at `build/dist/share/everest/modules/OCPP201/component_config/standardized/`
was missing `InternalCtrlr.json` because the build process didn't copy all files.

**Fix:** Copy `InternalCtrlr.json` from the source:
```bash
cp lib/everest/ocpp/config/v2/component_config/standardized/InternalCtrlr.json \
   build/dist/share/everest/modules/OCPP201/component_config/standardized/
```

Also update the CSMS URL inside the file — look for `NetworkConnectionProfiles` and change
`ocppCsmsUrl` to match your CitrineOS port (e.g., `ws://localhost:8081`).

### 2. Missing `core_migrations/` → DB init failure

**Symptom:** EVerest cannot initialize the device model SQLite database.

**Cause:** The migration SQL files were missing from the build.

**Fix:**
```bash
cp -r lib/everest/ocpp/config/v2/core_migrations/ \
      build/dist/share/everest/modules/OCPP201/core_migrations/
```

### 3. CertificateInstallation timeout

**Symptom:** PnC fails because the EV (PyEvJosev) tries to install a contract certificate
from a CPS (Certificate Provisioning Service) that doesn't exist in a local SIL environment.

**Fix:** In `config/config-sil-ocpp201-pnc.yaml`, set:
```yaml
iso15118_car:
  config_module:
    is_cert_install_needed: false
```

This tells PyEvJosev to use the test contract certificate already on disk instead of
fetching a new one from a CPS.

### 4. `CALLERROR` on AuthorizeRequest — eMAID format violation

**Symptom:** CitrineOS rejects the AuthorizeRequest with a `CALLERROR PropertyConstraintViolation`
because the eMAID in the contract certificate's CN does not match the eMI3 format.

**Background:** The eMI3 eMAID format is exactly 15 characters:
```
CC(2) + Provider(3) + C(type char, 1) + Instance(8) + CheckDigit(1)
```
Example: `UKSWIC123456791`
- `UK` = country code (2 chars)
- `SWI` = provider ID (3 chars)
- `C` = EMAID type character (always `C` for contract, at position 5)
- `12345679` = instance (8 digits)
- `1` = check digit (eMI3 algorithm, see below)

**Fix:** Edit `lib/everest/iso15118/test/iso15118/io/pki/configs/contractLeafCert.cnf`:
```ini
[ca_dn]
commonName = UKSWIC123456791
```

Then regenerate the MO leaf cert (see cert regeneration section below).

**How the check digit works (eMI3 algorithm):**
CitrineOS validates the check digit using a matrix-based calculation over Z2×Z3.
To compute it: use the `emaidCheckDigitCalculator.ts` in CitrineOS, or use an online
eMI3 check digit calculator. The check digit for `UKSWIC12345679` is `1`.

### 5. Stale cert in `etc/everest/certs/` → eMAID format error

**Symptom:** CitrineOS rejects with `ID Type must be 'C' for Contract (found: '1'),
Invalid check digit: expected '5', found 'A'`.

**Cause:** After fixing `contractLeafCert.cnf` and regenerating certs in the PKI dir, the old
cert remained in `build/dist/etc/everest/certs/client/mo/`. The stale cert had CN `UKSWI123456791A`
(no `C` type char, wrong check digit). The cmake install does not update this file automatically
— it must be copied manually.

**Fix:** Copy certs manually (see Certificate Regeneration section below).

### 6. `EVP_PKEY_verify: 0` → Signature Error at Authorization

**Symptom:** ISO 15118 Authorization fails with `Signature Error` immediately after
`PaymentDetailsReq` succeeds.

**Cause:** The private key in `etc/everest/certs/client/mo/MO_LEAF.key` was from a previous
cert generation run. The cert (`MO_LEAF.pem`) had been updated to the new generation but the key
had not — they were mismatched. The EVCC signs the AuthorizationReq with the key; the SECC
verifies against the public key in the cert. Mismatch → signature failure.

**Fix:** Copy `MO_LEAF.key` along with the cert files (see Certificate Regeneration section).
The key was missing from the original copy list.

### 7. `authority and subject key identifier mismatch` → cert chain rejected

**Symptom:** `evse_security` logs `authority and subject key identifier mismatch`. Local
contract validation fails.

**Cause:** The MO CA certs in `etc/everest/certs/ca/mo/` were stale from a previous generation.
The leaf cert's Authority Key Identifier (AKID) pointed to the newly generated `MO_SUB_CA2`
(from PKI dir), but the CA certs dir still had the old `MO_SUB_CA2` with a different Subject Key
Identifier (SKID). Only the leaf/client certs were being copied, not the CA chain.

**Fix:** Also copy all MO CA certs after regeneration (see Certificate Regeneration section).

### 8. `NoCertificateAvailable` — OCSP validation fails

**Symptom:** CitrineOS returns `certificateStatus: NoCertificateAvailable` and
`idTokenInfo.status: Invalid`. Local validation now passes (`Local contract validation result: Valid`)
and EVerest successfully generates OCSP data and sends it to CitrineOS.

**Cause:** CitrineOS does live OCSP validation against the URL in the certificate's
`authorityInfoAccess` extension. The test certs from Josev PKI have:
```
authorityInfoAccess = OCSP;URI:https://www.example.com/
```
This URL is unreachable in a local SIL environment, so OCSP fails.

**Status:** This is the remaining blocker. See the "OCSP Responder" section below.

---

## Build and Install Workflow

Every time you rebuild, run these four commands in order:

```bash
cd /home/annasdzik/build
cmake ../everest-core/
make -j1 install
~/everest-core/scripts/regen_mo_certs.sh
```

### What each step does

**`cmake ../everest-core/`**
Reads all CMakeLists.txt files and regenerates the build system. Required after any source change.

**`make -j1 install`**
Two things happen that affect PnC certs, in this order:
1. Josev dependency installs its entire source tree to `build/dist/libexec/everest/3rd_party/josev/` — this includes the **default** `contractLeafCert.cnf` with the wrong eMAID CN
2. PyEvJosev's cmake install then overwrites that with **our fixed** `contractLeafCert.cnf` (CN = `UKSWIC123456791`) from `lib/everest/iso15118/test/iso15118/io/pki/configs/`

At this point the correct `.cnf` is in place but no certs have been regenerated yet.

**`regen_mo_certs.sh`**
1. Runs `create_certs.sh -v iso-2` from the PKI dir, which reads the now-correct `.cnf` and generates all certs with CN `UKSWIC123456791`
2. Copies client certs (`MO_LEAF.pem`, `.der`, `.key`, `MO_CERT_CHAIN.p12`) → `etc/everest/certs/client/mo/`
3. Copies CA chain (`MO_ROOT_CA`, `MO_SUB_CA1`, `MO_SUB_CA2`, `INTERMEDIATE_MO_CA_CERTS`) → `etc/everest/certs/ca/mo/`
4. Verifies CN, key/cert match, and AKID/SKID consistency

The script lives at `scripts/regen_mo_certs.sh` in the source repo and accepts an optional install prefix argument (default: `/home/annasdzik/build/dist`).

### Why the order matters

```
make install
  ├── josev installs default .cnf  (wrong CN — overwritten next)
  └── PyEvJosev installs fixed .cnf (correct CN = UKSWIC123456791)

regen_mo_certs.sh
  ├── create_certs.sh reads fixed .cnf → all certs generated with correct eMAID
  ├── client certs copied to etc/everest/certs/client/mo/
  ├── CA chain copied to etc/everest/certs/ca/mo/
  └── verification: CN / key-cert match / AKID-SKID match
```

Skipping the script leaves stale certs in place. Skipping `make install` means the fixed `.cnf` never lands in the PKI dir and the script regenerates certs with the wrong CN.

### Notes on `create_certs.sh`

- Valid flags: `-v`, `-p`, `-k`, `-i`, `-h`
- `-t local` is **NOT** a valid flag — it causes the script to exit immediately via `usage()` without generating any certs

---

## Key Config Files Changed

| File | Change | Reason |
|------|--------|--------|
| `config/config-sil-ocpp201-pnc.yaml` | `is_cert_install_needed: false` | No CPS in local test |
| `lib/everest/ocpp/config/v2/component_config/standardized/ISO15118Ctrlr.json` | `CentralContractValidationAllowed: false` | EVerest handles local cert validation |
| `lib/everest/ocpp/config/v2/component_config/standardized/AuthCtrlr.json` | `DisableRemoteAuthorization: true` | Note: does NOT affect PnC flows (see below) |
| `lib/everest/iso15118/test/iso15118/io/pki/configs/contractLeafCert.cnf` | `commonName = UKSWIC123456791` | eMI3-compliant eMAID format |

**Important:** `DisableRemoteAuthorization` does NOT block PnC flows. EVerest's `authorization.cpp`
checks this flag only for non-eMAID token types. For eMAID (PnC), EVerest ALWAYS sends to
the CSMS when online and OCSP data is available.

---

## How EVerest PnC Authorization Works (OCPP 2.0.1)

Source: `lib/everest/ocpp/lib/ocpp/v2/functional_blocks/authorization.cpp`

```
EV plugs in → EVCC presents contract cert (eMAID)
    ↓
EVerest local cert validation
    ↓
is_online?
  YES:
    - Try to generate OCSP hash data from cert chain
    - If OCSP data generated → send AuthorizeRequest with OCSP data (no cert chain)
    - If OCSP data NOT generated:
        - If CentralContractValidationAllowed → send cert chain to CSMS
        - Else → reject (Invalid)
  NO (offline):
    - Use ContractValidationOffline setting
    - Validate locally against local trust store
```

So if the cert has an OCSP URL → EVerest always sends OCSP hash data to CSMS.
CitrineOS then calls that OCSP URL live.

---

## The OCSP Solution — Local Responder

### Why a local OCSP responder is required

CitrineOS's `CertificateAuthority.ts` has two validation paths:

1. **`validateCertificateHashData`** — called when EVerest sends OCSP hash data. Directly calls
   the `responderURL` from the OCSP data. Does NOT call Hubject or check a root CA trust store.
2. **`validateCertificateChainPem`** — called when EVerest sends the cert chain PEM. Calls
   `getRootCertificates()` which goes to **Hubject** (the real V2G PKI). Our local test CA
   will never be in Hubject → always returns `NoCertificateAvailable`. Dead end.

**The only viable path is `validateCertificateHashData`** — which means:
- Certs must have an OCSP URL (so EVerest generates OCSP hash data)
- That URL must point to a local responder CitrineOS can reach
- `CentralContractValidationAllowed` must be `false` (so EVerest sends OCSP hash data, not cert chain)

### OCSP URL in cert configs

All 4 MO cert configs have been updated to use `http://localhost:2560/`:
- `lib/everest/iso15118/test/iso15118/io/pki/configs/contractLeafCert.cnf`
- `lib/everest/iso15118/test/iso15118/io/pki/configs/moRootCACert.cnf`
- `lib/everest/iso15118/test/iso15118/io/pki/configs/moSubCA1Cert.cnf`
- `lib/everest/iso15118/test/iso15118/io/pki/configs/moSubCA2Cert.cnf`

**Important:** `make install` restores the josev default cnf files for the 3 CA configs
(from the josev dependency install). The cmake install rule in
`modules/EV/PyEvJosev/CMakeLists.txt` overwrites all 4 with our fixed versions after josev
installs. This is why `regen_mo_certs.sh` must always be run after `make install`.

### What happens in the authorization flow (OCPP 2.0.1)

```
EVerest sends GetCertificateStatus → CitrineOS
  └── responderURL = http://localhost:2560/  (from cert AIA extension)
  └── CitrineOS calls local OCSP responder → gets "good"
  └── returns status: "OK"

EVerest sends Authorize → CitrineOS
  └── iso15118CertificateHashData (OCSP hash data for full chain)
  └── CitrineOS calls validateCertificateHashData
  └── calls local OCSP responder for each cert in chain → all "good"
  └── returns certificateStatus: Accepted, idTokenInfo: Accepted
```

### Running the local OCSP responder

The responder is at `scripts/ocsp_responder.py`. It:
- Listens on `http://localhost:2560/`
- Receives OCSP POST requests from CitrineOS
- Matches the `issuerKeyHash` against the 3 MO CA certs (SUB_CA2, SUB_CA1, ROOT_CA)
- Signs a "good" response using the matching CA key
- Must be started **before** EVerest

```bash
/home/annasdzik/build/venv/bin/python3 ~/everest-core/scripts/ocsp_responder.py
```

### Problem: `GetCertificateStatus` returning `Failed` with old URL

**Symptom:** CitrineOS logs show `GetCertificateStatus` with `responderURL: https://www.example.com/`
and `status: Failed`, followed by `Authorize` returning `NoCertificateAvailable`.

**Cause:** The 3 MO CA cert configs were not updated before cert regeneration. `make install`
restores josev defaults for `moRootCACert.cnf`, `moSubCA1Cert.cnf`, `moSubCA2Cert.cnf` — only
`contractLeafCert.cnf` gets our fixed version. Running `regen_mo_certs.sh` without fixing the CA
configs first produces CA certs with `https://www.example.com/` and only the leaf cert with
`http://localhost:2560/`.

**Fix:** Always run the full build flow in order:
```bash
cd /home/annasdzik/build
cmake ../everest-core/   # picks up cmake install rules for all 4 cnf files
make -j1 install         # josev installs defaults, then our cmake rule overwrites all 4
~/everest-core/scripts/regen_mo_certs.sh  # regenerates certs using fixed configs
```

### Current status (as of 2026-03-21)

All cert issues are resolved:
- All 4 MO certs have `http://localhost:2560/` OCSP URL
- Key/cert match verified
- AKID/SKID chain verified
- OCSP responder tested and working (`openssl ocsp` returns `good`)

**Next step:** Run EVerest with the OCSP responder and verify `Authorize` returns `Accepted`.

---

## Ports Reference

| Service | Port |
|---------|------|
| CitrineOS OCPP WebSocket | 8081 |
| CitrineOS Operator UI | 4200 (or similar) |
| EVerest admin panel | 8849 |
| Node-RED | 1880 |

---

## Adding a Token to CitrineOS (for the eMAID)

When PnC works and cert validation passes, CitrineOS also needs to know the eMAID token.
In the Operator UI, add an authorization record:
- `idToken`: `UKSWIC123456791`
- `type`: `eMAID`
- `status`: `Accepted`

---

## References

- OCPP 2.0.1 spec, Part 2 Appendix, use case C07: Authorization using Contract Certificates
- eMI3 standard: https://www.emobility-interop.eu/
- EVerest docs: https://everest.github.io/
- CitrineOS: https://citrineos.github.io/
