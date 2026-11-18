# Migration, Troubleshooting & Validation Screenshots

This folder contains visual evidence captured during the E1000-to-VirtIO migration, troubleshooting, and validation process.

| Screenshot | Description |
|---|---|
| [`01-proxmox-vm104-nic-migration.png`](./01-proxmox-vm104-nic-migration.png) | Proxmox VE hardware view of VM 104 (`pfSense`) showing 4 vCPUs (`host`), 4.00 GiB RAM, `q35` machine type, and the transition from `e1000` to `virtio` on `vmbr0`. |
| [`02-pfsense-pre-migration-em1-vlans.png`](./02-pfsense-pre-migration-em1-vlans.png) | Pre-migration pfSense interface assignments on `em0` (WAN) and `em1` (`MGMT`, `HOME`, `LAB`, `SERVERS`, `GUEST`, `IoT`). |
| [`03-pfsense-console-assign-pitfall.png`](./03-pfsense-console-assign-pitfall.png) | The pfSense console `1) Assign Interfaces` prompt where assigning `vtnet0`/`vtnet1` and pressing Enter at `Optional 1` cleared `<opt1>`–`<opt5>` from `<interfaces>`. |
| [`04-pfsense-duplicate-em1-vtnet1-vlans.png`](./04-pfsense-duplicate-em1-vtnet1-vlans.png) | `Interfaces -> VLANs` during migration showing both the 6 old `em1` VLAN definitions and the 6 newly created `vtnet1` VLAN definitions (missing descriptions). |
| [`05-pfsense-blank-opt-interfaces.png`](./05-pfsense-blank-opt-interfaces.png) | `Interfaces -> Interface Assignments` after re-adding `OPT1`–`OPT5` on `vtnet1`, before running `recover_step1_interfaces.php` to restore descriptions and IPv4 configurations. |
| [`06-unifi-vlan-ssids.png`](./06-unifi-vlan-ssids.png) | UniFi Network Controller Wi-Fi settings mapping `ConnectMe` (2.4/5 GHz, WPA2/WPA3) to `HOME (10)` and `Stark_Industries` (2.4 GHz, WPA2) to `IoT (50)`. |
| [`07-home-assistant-integrations.png`](./07-home-assistant-integrations.png) | Home Assistant (`192.168.30.5`) integrations dashboard showing HomeKit Bridge, ESPHome, TP-Link Smart Home, Tuya, Music Assistant, and Wyoming Protocol. |
| [`08-dns-and-firewall-isolation-test.png`](./08-dns-and-firewall-isolation-test.png) | PowerShell verification from `SERVERS` (`192.168.30.x`) confirming that TCP port `443` to `192.168.20.1` and `192.168.99.1` is blocked by the `(self)` firewall rule while DNS (`nslookup google.com 192.168.30.1`) resolves both `A` and `AAAA` records. |
