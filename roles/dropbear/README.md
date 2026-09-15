# `flyoverhead.openwrt.dropbear`

OpenWRT `dropbear` configuration
- configure dropbear settings
- install root's SSH public keys

Together these are the "SSH Access" and "SSH-Keys" halves of LuCI's
**System → Administration** page.

## Role Variables

| Variable | Descritpion | Status | Type | Example |
| :--- | :--- | :--- | :--- | :--- |
| `dropbear` | Dropbear settings configuration |  | `dictionary` |  |
| &emsp;`enable` | Enable starting dropbear at system boot | `required` | `boolean` | `1` |
| &emsp;`verbose` | Enable verbose output by the start scrip | `optional` | `boolean` | `0` |
| &emsp;`BannerFile` | Name of a file to be printed before the user has authenticated successfully | `optional` | `string` | `7` |
| &emsp;`PasswordAuth` | Allow authenticating with passwords | `optional` | `boolean` | `1` |
| &emsp;`Port` | SSH service listening port | `required` | `integer` | `22` |
| &emsp;`RootPasswordAuth` | Allow authenticating as root with passwords | `optional` | `boolean` | `1` |
| &emsp;`RootLogin` | Allow SSH logins as root | `optional` | `boolean` | `1` |
| &emsp;`GatewayPorts` | Allow remote hosts to connect to forwarded port | `optional` | `boolean` | `0` |
| &emsp;`Interface` | Limit connections to specified network interface | `optional` | `string` | `lan` |
| &emsp;`keyfile` | Path to host key file | `optional` | `string` | `/etc/dropbear/authorized_keys` |
| &emsp;`SSHKeepAlive` | Keep alive | `optional` | `integer` | `300` |
| &emsp;`IdleTimeout` | Idle timeout | `optional` | `integer` | `0` |
| &emsp;`mdns` | Enable announcing the service via mDNS | `optional` | `boolean` | `1` |
| &emsp;`MaxAuthTries` | Amount of password entering retries before SSH server closes the connection | `optional` | `integer` | `3` |
| &emsp;`RecvWindowSize` | Per-channel receive window buffer size | `optional` | `integer` | `24576` |

### SSH keys

| Variable | Descritpion | Status | Type | Example |
| :--- | :--- | :--- | :--- | :--- |
| `dropbear_authorized_keys` | Root's SSH public keys, one per entry | `optional` | `list` | `["ssh-ed25519 AAAAC3Nza... me@host"]` |
| `dropbear_authorized_keys_src` | File in this role's `files/` directory to merge in as well; `""` to ignore | `optional` | `string` | `authorized_keys` |
| `dropbear_authorized_keys_path` | Where the keys are written | `optional` | `string` | `/etc/dropbear/authorized_keys` |
| `dropbear_authorized_keys_exclusive` | Make the file *exactly* the configured keys, removing any others | `optional` | `boolean` | `true` |

> Note: keys can also be listed in the `authorized_keys` file in the `files`
> directory. They are merged with `dropbear_authorized_keys`; blank lines and
> `#` comments are ignored. Prefer the variable — a key committed to `files/`
> applies to every device in every inventory.

## Notes

- **An empty key list leaves the device alone.** Configure no keys and the role
  does not touch `/etc/dropbear/authorized_keys` at all, and says so in the play
  output. This is deliberate: the role used to copy `files/authorized_keys` over
  it unconditionally with `force: true`, and since that file ships empty, simply
  including the role truncated the file on every device — breaking key-based SSH,
  and with it Ansible's own access. An empty list means "not managed here", never
  "remove every key".
- `dropbear_authorized_keys_exclusive: true` (the default) makes the file
  declarative: dropping a key from the list removes it from the device, as does
  anything added out of band. **The list must therefore contain the key Ansible
  itself connects with.** Set it to `false` to only append what is missing and
  leave existing lines untouched.
- Keys are validated before anything is written — a line has to look like an SSH
  public key, and a private key is rejected outright. Lines carrying an options
  prefix (`restrict,command="..." ssh-ed25519 AAAA...`) are accepted.
- Keys are installed **before** the dropbear settings, so a settings change that
  costs you password access finds the keys already in place.

## Dependencies

| Name | Description |
| :--- | :--- |
| `community.openwrt` | [community.openwrt collection](https://github.com/ansible-collections/community.openwrt) for managing OpenWRT and derivatives |

## Example Playbook

```yaml
- hosts: openwrt
  roles:
      - role: flyoverhead.openwrt.dropbear
```

## License

[GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.txt)

## Author Information

fly0v3rH34D

## References

- https://openwrt.org/docs/guide-user/base-system/dropbear
