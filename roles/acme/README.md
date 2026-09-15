# `flyoverhead.openwrt.acme`

OpenWRT `acme` configuration
- configure acme settings
- configure certificate sections

## Role Variables

| Variable | Descritpion | Status | Type | Example |
| :--- | :--- | :--- | :--- | :--- |
| `acme` | ACME client settings | | `dictionary` | |
| &emsp;`account_email` | Account e-mail registered with the CA | `required` | `string` | `admin@example.org` |
| &emsp;`debug` | Enable verbose logging | `optional` | `boolean` | `0` |
| `acme_certs` | Certificates to issue and renew | | `list` | |
| &emsp;`id` | UCI section name | `required` | `string` | `device` |
| &emsp;`state` | Section state | `optional` | `string` | `present` |
| &emsp;`enabled` | Issue and renew this certificate | `required` | `boolean` | `1` |
| &emsp;`domains` | Domains to request; the first is the main domain | `required` | `list` | `["host.example.org"]` |
| &emsp;`validation_method` | `webroot`, `standalone` or `dns` | `required` | `string` | `webroot` |
| &emsp;`webroot` | Directory served on port 80, for `webroot` validation | `optional` | `string` | `/www` |
| &emsp;`standalone` | Bind port 80 directly instead of using a webroot | `optional` | `boolean` | `0` |
| &emsp;`listen_port` | Port for `standalone` validation | `optional` | `integer` | `80` |
| &emsp;`key_type` | Key type | `optional` | `string` | `ec256` |
| &emsp;`keylength` | Key length (deprecated in favour of `key_type`) | `optional` | `string` | `2048` |
| &emsp;`days` | Renew when fewer than this many days remain | `optional` | `integer` | `10` |
| &emsp;`acme_server` | ACME directory URL | `optional` | `string` | `https://ca.example.org/acme/provisioner/directory` |
| &emsp;`staging` | Use the CA's staging environment | `optional` | `boolean` | `0` |
| &emsp;`use_staging` | Deprecated alias of `staging` | `optional` | `boolean` | `0` |
| &emsp;`cert_profile` | Certificate profile requested from the CA | `optional` | `string` | |
| &emsp;`calias` | Challenge alias domain | `optional` | `string` | `example.com` |
| &emsp;`dalias` | Domain alias | `optional` | `string` | `alias.example.com` |
| &emsp;`dns` | acme.sh DNS API, for `dns` validation | `optional` | `string` | `dns_cf` |
| &emsp;`dns_wait` | Seconds to wait for DNS propagation | `optional` | `integer` | `30` |
| &emsp;`credentials` | Environment assignments for the DNS API | `optional` | `list` | `['CF_Token="..."']` |

> Note: `domains` and `credentials` are UCI **lists**. Pass them as lists — do
> not join them into a string. `credentials` is read with
> `config_list_foreach`, which ignores an `option` outright.

### uhttpd integration

| Variable | Descritpion | Status | Type | Example |
| :--- | :--- | :--- | :--- | :--- |
| `acme_issue_now` | Obtain certificates during the play instead of waiting for the nightly cron | `optional` | `boolean` | `true` |
| `acme_issue_timeout` | Seconds to wait for issuance before failing | `optional` | `integer` | `120` |
| `acme_main_domain` | Domain this role waits for and serves; defaults to the first domain of the first cert | `optional` | `string` | |
| `acme_uhttpd_enabled` | Point uhttpd at the issued certificate and reload it on renewal | `optional` | `boolean` | `false` |
| `acme_uhttpd_section` | UCI section in `/etc/config/uhttpd` to update | `optional` | `string` | `main` |
| `acme_uhttpd_redirect_https` | Force HTTPS: redirect plain-HTTP requests to TLS (`redirect_https`) | `optional` | `boolean` | `true` |

## Notes

- Certificates are written to **`/etc/ssl/acme/`**. The `state_dir` option is
  deprecated and is not exposed by this role.
- There is **no `update_uhttpd` option** in this package, despite what some
  documentation suggests. `acme_uhttpd_enabled` is this role's own
  implementation of it: it points uhttpd at the issued certificate and installs
  `/etc/hotplug.d/acme/50-uhttpd` so uhttpd reloads on every renewal.
- **`/usr/lib/acme/hook` is a file, not a directory.** The extension point is
  hotplug: `/usr/lib/acme/notify` runs `hotplug-call acme` with `ACTION` set to
  `issued` or `renewed`, so scripts belong in `/etc/hotplug.d/acme/`.
- uhttpd is pointed at **`.fullchain.crt`**, not `.crt`. The latter is the leaf
  alone; the fullchain carries the intermediate, so a client that trusts only
  the root can still build a path.
- Wiring uhttpd is **guarded on the certificate existing**. Pointing uhttpd at
  a missing file stops it serving HTTPS entirely, and on a device's first run
  the certificate does not exist until issuance completes.
- **Forcing HTTPS is part of the same step.** `acme_uhttpd_redirect_https`
  writes uhttpd's `redirect_https`, in the same commit that points uhttpd at
  the certificate — so plain HTTP is only redirected once there is a valid
  certificate to redirect it to. The role refuses to enable it when the uhttpd
  section has no `listen_https`, since that combination redirects every request
  to a closed port and takes the web UI away.
- Forcing HTTPS does **not** break renewal. http-01 challenges are answered on
  port 80 and ACME servers follow the redirect to HTTPS without verifying the
  certificate presented on the way.
- **Restarting the acme service does not issue anything.** It registers the
  nightly cron and prints "Nightly certificate renewal enabled". Obtaining a
  certificate needs `/etc/init.d/acme renew`, which returns immediately and
  works in the background — hence `acme_issue_now` and its wait loop.
- Renewal scheduling is handled by the package itself: enabling the service
  appends `0 0 * * * /etc/init.d/acme renew` to `/etc/crontabs/root`.
- The `Reload acme` handler restarts the service, which enables the nightly
  cron but does **not** issue anything — see the point above.
- Install the client with the `apk` role (OpenWrt 24.10+); `acme-acmesh`
  provides the virtual name `acme`.

## Dependencies

- `community.openwrt.init`
