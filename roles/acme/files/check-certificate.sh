#!/bin/sh
# Read-only. Exit 0: desired SANs and enough lifetime; 1: needs issuance;
# 2: openssl unavailable. Parameters: certificate, minimum seconds, DNS SANs.
set -eu
cert=$1
seconds=$2
shift 2
command -v openssl >/dev/null 2>&1 || exit 2
[ -f "$cert" ] || exit 1
openssl x509 -in "$cert" -noout -checkend "$seconds" >/dev/null 2>&1 || exit 1
actual=$(openssl x509 -in "$cert" -noout -ext subjectAltName 2>/dev/null |
    sed '1d' | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | LC_ALL=C sort)
expected=$(printf 'DNS:%s\n' "$@" | LC_ALL=C sort)
[ "$actual" = "$expected" ]
