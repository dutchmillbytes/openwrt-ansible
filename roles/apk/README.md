# APK packages

Install/remove packages on OpenWrt 25.12+ using `community.openwrt.apk`. The role
keeps the existing public variable interface and depends on `community.openwrt.init`.

| Variable | Default | Meaning |
|---|---|---|
| `apk_packages` | `[]` | Packages to install |
| `apk_packages_absent` | `[]` | Packages to remove |
| `apk_update_cache` | `true` | Refresh package metadata when installing missing packages |

The native module checks installed packages, reports predicted changes in check
mode, and performs no package installation/removal during check mode. Package
names are joined with commas for the module's string argument.

Install the collection with `ansible-galaxy collection install -r requirements.yml`.
The provided controller requirements use Ansible-core 2.20 with Python 3.12+.
