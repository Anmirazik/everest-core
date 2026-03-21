#!/usr/bin/env python3
"""
Local OCSP responder for EVerest PnC SIL testing.

Listens on http://localhost:2560/ and responds to OCSP requests from CitrineOS
with a signed "good" status for all MO certificate chain certs.

Usage:
    python3 scripts/ocsp_responder.py [--install-prefix /path/to/build/dist] [--port 2560]

Requires: cryptography (available in build venv)
Run with: /home/annasdzik/build/venv/bin/python3 scripts/ocsp_responder.py
"""

import argparse
import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import ocsp


def load_cert(path):
    with open(path, "rb") as f:
        return x509.load_pem_x509_certificate(f.read())


def load_key(path, password=b"123456"):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=password)


def compute_key_hash(cert, algorithm):
    """
    Compute the OCSP issuerKeyHash: hash of the issuer's public key BIT STRING value.
    For EC keys this is the uncompressed point bytes (04 || x || y).
    """
    pub_key = cert.public_key()
    pub_key_bytes = pub_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    digest = hashes.Hash(algorithm, default_backend())
    digest.update(pub_key_bytes)
    return digest.finalize()


def make_dummy_cert(serial_number, issuer_cert):
    """
    Build a minimal certificate with the given serial number and the correct issuer name.
    OCSPResponseBuilder.add_response() computes issuerNameHash from cert.issuer,
    so it must match issuer_cert.subject exactly.
    """
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "dummy")]))
        .issuer_name(issuer_cert.subject)
        .public_key(key.public_key())
        .serial_number(serial_number)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )


class OCSPHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            req = ocsp.load_der_ocsp_request(body)
            serial = req.serial_number
            algorithm = req.hash_algorithm

            print(f"  OCSP request: serial={serial:#x}, alg={algorithm.name}")

            issuer_cert, issuer_key = self._find_issuer(req)
            if issuer_cert is None:
                print("  No matching issuer — sending UNAUTHORIZED")
                resp_bytes = ocsp.OCSPResponseBuilder.build_unsuccessful(
                    ocsp.OCSPResponseStatus.UNAUTHORIZED
                ).public_bytes(serialization.Encoding.DER)
            else:
                cn = issuer_cert.subject.get_attributes_for_oid(
                    x509.oid.NameOID.COMMON_NAME
                )[0].value
                now = datetime.datetime.now(datetime.timezone.utc)
                dummy_cert = make_dummy_cert(serial, issuer_cert)
                response = (
                    ocsp.OCSPResponseBuilder()
                    .add_response(
                        cert=dummy_cert,
                        issuer=issuer_cert,
                        algorithm=algorithm,
                        cert_status=ocsp.OCSPCertStatus.GOOD,
                        this_update=now,
                        next_update=now + datetime.timedelta(days=7),
                        revocation_time=None,
                        revocation_reason=None,
                    )
                    .responder_id(ocsp.OCSPResponderEncoding.HASH, issuer_cert)
                    .sign(issuer_key, hashes.SHA256())
                )
                resp_bytes = response.public_bytes(serialization.Encoding.DER)
                print(f"  Signed GOOD response (issuer: {cn})")

        except Exception as e:
            print(f"  Error: {e}")
            resp_bytes = ocsp.OCSPResponseBuilder.build_unsuccessful(
                ocsp.OCSPResponseStatus.INTERNAL_ERROR
            ).public_bytes(serialization.Encoding.DER)

        self.send_response(200)
        self.send_header("Content-Type", "application/ocsp-response")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)

    def _find_issuer(self, req):
        """Match request's issuerKeyHash against known issuer certs."""
        for issuer_cert, issuer_key in self.server.issuers:
            try:
                computed = compute_key_hash(issuer_cert, req.hash_algorithm)
                if computed == req.issuer_key_hash:
                    return issuer_cert, issuer_key
            except Exception:
                continue
        return None, None

    def log_message(self, format, *args):
        pass  # suppress default HTTP log, we print our own


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-prefix", default="/home/annasdzik/build/dist")
    parser.add_argument("--port", type=int, default=2560)
    args = parser.parse_args()

    pki = f"{args.install_prefix}/libexec/everest/3rd_party/josev/iso15118/shared/pki/iso15118_2/certs"
    ca_mo     = f"{pki}/ca/mo"
    client_mo = f"{pki}/client/mo"

    issuers = [
        (load_cert(f"{ca_mo}/MO_SUB_CA2.pem"), load_key(f"{client_mo}/MO_SUB_CA2.key")),
        (load_cert(f"{ca_mo}/MO_SUB_CA1.pem"), load_key(f"{client_mo}/MO_SUB_CA1.key")),
        (load_cert(f"{ca_mo}/MO_ROOT_CA.pem"), load_key(f"{client_mo}/MO_ROOT_CA.key")),
    ]

    server = HTTPServer(("0.0.0.0", args.port), OCSPHandler)
    server.issuers = issuers

    print(f"OCSP responder listening on http://0.0.0.0:{args.port}/ (also reachable from Docker)")
    for cert, _ in issuers:
        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        print(f"  Issuer: {cn}")
    print("Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
