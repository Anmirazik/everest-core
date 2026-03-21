#!/bin/bash
# Regenerates ISO 15118 MO certificates and copies them to the EVerest build dist directory.
# Run this after: cmake ../everest-core/ && make -j1 install
#
# Usage: ./scripts/regen_mo_certs.sh [INSTALL_PREFIX]
# Default INSTALL_PREFIX: /home/annasdzik/build/dist

set -e

INSTALL_PREFIX="${1:-/home/annasdzik/build/dist}"
PKI="$INSTALL_PREFIX/libexec/everest/3rd_party/josev/iso15118/shared/pki"
CLIENT_MO="$PKI/iso15118_2/certs/client/mo"
CA_MO="$PKI/iso15118_2/certs/ca/mo"
CERTS_CLIENT="$INSTALL_PREFIX/etc/everest/certs/client/mo"
CERTS_CA="$INSTALL_PREFIX/etc/everest/certs/ca/mo"

echo "=== Regenerating MO certificates ==="
echo "PKI dir:    $PKI"
echo "Certs dir:  $INSTALL_PREFIX/etc/everest/certs"
echo ""

if [ ! -f "$PKI/create_certs.sh" ]; then
    echo "ERROR: create_certs.sh not found at $PKI"
    echo "Make sure you have run: make -j1 install"
    exit 1
fi

cd "$PKI"
bash create_certs.sh -v iso-2

echo ""
echo "=== Copying client certs ==="
cp "$CLIENT_MO/MO_LEAF.pem"       "$CERTS_CLIENT/"
cp "$CLIENT_MO/MO_LEAF.der"       "$CERTS_CLIENT/"
cp "$CLIENT_MO/MO_LEAF.key"       "$CERTS_CLIENT/"
cp "$CLIENT_MO/MO_CERT_CHAIN.p12" "$CERTS_CLIENT/"
echo "Done: $CERTS_CLIENT"

echo ""
echo "=== Copying CA chain ==="
cp "$CA_MO/MO_ROOT_CA.pem"              "$CERTS_CA/"
cp "$CA_MO/MO_ROOT_CA.der"              "$CERTS_CA/"
cp "$CA_MO/MO_SUB_CA1.pem"             "$CERTS_CA/"
cp "$CA_MO/MO_SUB_CA1.der"             "$CERTS_CA/"
cp "$CA_MO/MO_SUB_CA2.pem"             "$CERTS_CA/"
cp "$CA_MO/MO_SUB_CA2.der"             "$CERTS_CA/"
cp "$CA_MO/INTERMEDIATE_MO_CA_CERTS.pem" "$CERTS_CA/"
echo "Done: $CERTS_CA"

echo ""
echo "=== Verifying ==="
LEAF_CN=$(openssl x509 -in "$CERTS_CLIENT/MO_LEAF.pem" -noout -subject 2>/dev/null | sed 's/.*CN = //')
KEY_PUB=$(openssl pkey -in "$CERTS_CLIENT/MO_LEAF.key" -passin pass:123456 -pubout 2>/dev/null | openssl dgst -sha256)
CERT_PUB=$(openssl x509 -in "$CERTS_CLIENT/MO_LEAF.pem" -noout -pubkey 2>/dev/null | openssl dgst -sha256)
CA_SKID=$(openssl x509 -in "$CERTS_CA/MO_SUB_CA2.pem" -noout -text 2>/dev/null | grep -A1 "Subject Key Identifier" | tail -1 | tr -d ' ')
LEAF_AKID=$(openssl x509 -in "$CERTS_CLIENT/MO_LEAF.pem" -noout -text 2>/dev/null | grep -A1 "Authority Key Identifier" | tail -1 | tr -d ' ')

echo "Leaf CN:          $LEAF_CN"

if [ "$KEY_PUB" = "$CERT_PUB" ]; then
    echo "Key/cert match:   OK"
else
    echo "Key/cert match:   MISMATCH (EVP_PKEY_verify will fail)"
fi

if [ "$CA_SKID" = "$LEAF_AKID" ]; then
    echo "AKID/SKID match:  OK"
else
    echo "AKID/SKID match:  MISMATCH (cert chain validation will fail)"
    echo "  MO_SUB_CA2 SKID: $CA_SKID"
    echo "  MO_LEAF AKID:    $LEAF_AKID"
fi

echo ""
echo "=== Done ==="
