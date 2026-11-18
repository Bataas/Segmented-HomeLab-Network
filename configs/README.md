# Sanitized Infrastructure Configurations

This directory contains the sanitized, production-verified configurations from the homelab environment.

## Files Included

| File | Component | Description |
|---|---|---|
| [`pfsense-config-sanitized.xml`](./pfsense-config-sanitized.xml) | **pfSense CE 2.8.1 (VM 104)** | The final recovered `config.xml` running on `vtnet0` (WAN) and `vtnet1` (LAN trunk, VLANs `10, 20, 30, 40, 50, 99`), including all DHCP scopes, static reservations (`dc01` & `homeassistant`), Unbound DNS Resolver settings, inter-VLAN aliases, and 28 firewall rules. |
| [`huawei-s5320-switch.cfg`](./huawei-s5320-switch.cfg) | **Huawei S5320-12TP-LI-AC** | Layer 2 VLAN segmentation (`2, 10, 20, 30, 40, 50, 99`), access & trunk port assignments (`GigabitEthernet0/0/1`–`0/0/6`), unused port shutdown (`0/0/7`–`0/0/12`), `Vlanif99` management interface (`192.168.99.2/24`), and SSH/ACL `2099` hardening. |
| [`proxmox-network-and-vm104.conf`](./proxmox-network-and-vm104.conf) | **Proxmox VE 9.1 Host & VM 104** | Host `/etc/network/interfaces` showing the VLAN-aware `vmbr0` bridge and `vmbr0.99` (`192.168.99.3/24`) management interface, alongside the VM 104 (`104.conf`) hardware definition before (`e1000`) and after (`virtio`) migration. |
| [`unifi-lxc-install.sh`](./unifi-lxc-install.sh) | **UniFi Network Server 10.6.109 (Debian 12 LXC)** | Reproducible installation script resolving the broken Ubiquiti APT repository and Java 25 dependency using MongoDB 7.0 and Eclipse Temurin 25 JRE. |

## Sanitization Notice

Before committing [`pfsense-config-sanitized.xml`](./pfsense-config-sanitized.xml), the following sensitive fields were replaced with placeholders:
- `<bcrypt-hash>` $\rightarrow$ `[REDACTED_BCRYPT_HASH]`
- `<authorizedkeys>` $\rightarrow$ `[REDACTED_SSH_PUBLIC_KEY]`
- `<crt>` / `<prv>` $\rightarrow$ `[REDACTED_TLS_CERTIFICATE]` / `[REDACTED_TLS_PRIVATE_KEY]`
- `<sshdata><sshkeyfile><xmldata>` $\rightarrow$ `[REDACTED_SSH_HOST_KEY]`

> **Warning:** Do not import `pfsense-config-sanitized.xml` directly into a live firewall without replacing the redacted certificate/password fields or restoring only specific config sections.
