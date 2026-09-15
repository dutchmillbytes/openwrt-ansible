# Local validation

Run pure planner, certificate and template/rollback tests:

```sh
ANSIBLE_LOCAL_TEMP=/tmp/ansible-tests python3 -m unittest discover -s tests -v
```

For migration integration tests, supply a locally built OpenWrt UCI executable:

```sh
UCI_TEST_BIN=/absolute/path/to/uci ANSIBLE_LOCAL_TEMP=/tmp/ansible-tests \
  python3 -m unittest discover -s tests -v
```

The test harness uses private temporary configuration, override and delta paths.
It never accesses a device. It exercises the action against the actual UCI parser
and commit implementation; `fw4` is a controlled failure fixture for rollback,
not a validation of a real router's firewall rules. Tests without UCI_TEST_BIN
explicitly skip these integration cases.

Validated on 2026-09-12 against OpenWrt UCI commit
`74f6277aabffc943d026f406df57c22595134c42`. A controller-only CLI can be built from
that official source with GCC, without installing anything globally:

```sh
git clone https://github.com/openwrt/uci.git /tmp/uci-test-src
cd /tmp/uci-test-src
git checkout 74f6277aabffc943d026f406df57c22595134c42
# Debug flags are disabled; the CLI does not require the blob conversion layer.
touch uci_config.h
gcc -O2 -DUCI_PREFIX='"/usr"' -I. \
  cli.c libuci.c file.c util.c delta.c parse.c -ldl -o /tmp/uci-test
```

Certificate tests use local self-signed fixtures and stub the ACME client for
failure/rollback tests. They never contact a CA. Fleet-specific resolved-variable
checks live in `../openwrt-ansible-config/tests/validate.py`.

## Native community.openwrt integration

Use the supported controller environment and install the optional Docker test
connection collection with `tests/requirements.yml`. Production needs only the
collection in the root `requirements.yml`.

```sh
ansible-galaxy collection install -r requirements.yml -p .collections
ansible-galaxy collection install -r tests/requirements.yml -p .collections
export ANSIBLE_COLLECTIONS_PATH="$PWD/.collections"
export ANSIBLE_ACTION_PLUGINS="$PWD/plugins/action"
docker run --detach --rm --name community-openwrt-test --network none \
  --entrypoint /bin/sh ghcr.io/openwrt/rootfs:x86_64-25.12.0 \
  -c 'while :; do sleep 300; done'
printf '[openwrt_test]\ncommunity-openwrt-test\n' > /tmp/community-openwrt-test.ini
ansible-playbook -i /tmp/community-openwrt-test.ini tests/community-openwrt-smoke.yml \
  -e smoke_manifest_dir=/tmp/community-openwrt-test-manifests
docker rm --force community-openwrt-test
```

The container has no network access. The playbook deliberately sets
`ansible_python_interpreter: /python-must-not-be-used` and uses only native
collection modules for device operations. Always remove the disposable container
after testing, including after a failed playbook run. The fixture service is a
small test script; this test does not validate a real firewall or CA service.
