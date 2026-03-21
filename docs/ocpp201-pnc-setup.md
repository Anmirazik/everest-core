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

### 5. `NoCertificateAvailable` — OCSP validation fails

**Symptom:** CitrineOS returns `certificateStatus: NoCertificateAvailable` and
`idTokenInfo.status: Invalid`.

**Cause:** CitrineOS does live OCSP validation against the URL in the certificate's
`authorityInfoAccess` extension. The test certs from Josev PKI have:
```
authorityInfoAccess = OCSP;URI:https://www.example.com/
```
This URL is unreachable in a local SIL environment, so OCSP fails.

**Status:** This is the remaining blocker. See the "OCSP Responder" section below.

---

## Certificate Regeneration

After editing any `.cnf` file under `pki/configs/`, you must regenerate the certs.

Run from the PKI directory:
```bash
cd build/dist/libexec/everest/3rd_party/josev/iso15118/shared/pki/
./create_certs.sh -v iso-2 -t local
```

This regenerates ALL certs. The generated files land in:
- `iso15118_2/certs/client/mo/MO_LEAF.pem` — contract cert
- `iso15118_2/certs/client/mo/MO_CERT_CHAIN.p12` — PKCS12 bundle for the EV

After regeneration, copy the relevant files to the EVerest cert dirs:
```bash
PKI=build/dist/libexec/everest/3rd_party/josev/iso15118/shared/pki
CERTS=build/dist/etc/everest/certs

cp $PKI/iso15118_2/certs/client/mo/MO_LEAF.pem      $CERTS/client/mo/MO_LEAF.pem
cp $PKI/iso15118_2/certs/client/mo/MO_LEAF.der      $CERTS/client/mo/MO_LEAF.der
cp $PKI/iso15118_2/certs/client/mo/MO_CERT_CHAIN.p12 $CERTS/client/mo/MO_CERT_CHAIN.p12
```

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

## The OCSP Problem (Current Blocker)

CitrineOS's `CertificateAuthority.ts` does live OCSP checks in two places:
1. `validateCertificateHashData` — called when EVerest sends OCSP hash data (our current path)
2. `validateCertificateChainPem` — called when EVerest sends the cert chain PEM

Both try to reach the OCSP URL from the cert's AIA extension (`https://www.example.com/`).
Both fail in a local SIL environment. No environment variable in CitrineOS disables this.

**Option A: Run a local OCSP responder**

Change OCSP URL in all MO cert configs to `http://localhost:2560/`, regenerate certs,
and run a Python OCSP responder:
```bash
python3 pki/ocsp_responder.py --port 2560 \
  --ca pki/iso15118_2/certs/ca/mo/MO_SUB_CA2.pem \
  --ca-key pki/iso15118_2/certs/client/mo/MO_SUB_CA2.key
```

**Option B: CitrineOS source change (user rejected)**
Modify CitrineOS to skip OCSP or return `Accepted` for test environments.

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
