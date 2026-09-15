# OpenWrt backhaul selector

This role installs a small procd service for access points that keep an
802.11s interface active alongside Ethernet. It dynamically adds the mesh
device to the LAN only while every configured Ethernet device is down. Wired
failback is immediate; wireless failover is delayed to avoid link flapping.

Set `dynamic_backhaul_enabled: true` for the access-point inventory group.
Set `dynamic_backhaul_main: true` on exactly one node in each Layer 2 mesh.
The main node declares static LAN membership on its mesh interface and does not
run the selector service. It provides the wired path used by selector nodes
during wireless failover. Nodes with `dynamic_backhaul_main: false` use the
wired-preferred selector behavior.

The service uses netifd's `network.interface.<name>.add_device` and
`remove_device` ubus methods. A selector's wireless mesh interface must have
an empty static `network` list so netifd does not independently attach it.
