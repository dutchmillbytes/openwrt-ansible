# `flyoverhead.openwrt.ca-trust`

Install private root CAs into the OpenWrt trust store
- write each certificate to `/etc/ssl/certs/<name>.crt`
- append it to the system trust bundle if not already present
- optionally verify that a given HTTPS URL now validates

## Role Variables

| Variable | Descritpion | Status | Type | Example |
| :--- | :--- | :--- | :--- | :--- |
| `ca_trust_certs` | Root CAs to install | `optional` | `list` | |
| &emsp;`name` | Basename for the installed file, without extension | `required` | `string` | `example-root` |
| &emsp;`content` | PEM certificate body | `required` | `string` | `-----BEGIN CERTIFICATE-----...` |
| `ca_trust_dir` | Directory the certificate files are written to | `optional` | `string` | `/etc/ssl/certs` |
| `ca_trust_bundle` | System trust bundle to append to | `optional` | `string` | `/etc/ssl/certs/ca-certificates.crt` |
| `ca_trust_verify_url` | HTTPS URL fetched to prove the chain validates; skipped when empty | `optional` | `string` | `https://ca.example.com/health` |

> Note: `ca_trust_certs` is empty by default, so including this role without
> configuring it does nothing.

## Why the certificate is a variable

A private CA is site data. This role deliberately does **not** ship a
certificate in its own `files/` directory — pass the content in from the
inventory instead:

```yaml
ca_trust_certs:
  - name: "example-root"
    content: "{{ lookup('file', 'files/example-root.crt') }}"
```

## Notes

- OpenWrt's `ca-bundle` package ships a single concatenated bundle rather than
  a hash-symlink directory (`/etc/ssl/cert.pem` is a symlink to it), so
  trusting a new root means appending to that file.
- That bundle is package-owned and is replaced when `ca-bundle` is upgraded,
  which drops the appended root. This role re-appends whenever its marker is
  missing, so a routine playbook run repairs it.
- Idempotency is checked by grepping for the certificate's first base64 body
  line, not with `openssl` — that binary is not present on all OpenWrt devices.

## Dependencies

- `community.openwrt.init`
