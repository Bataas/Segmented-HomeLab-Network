# Part 1: Foundation Build Log — From Flat Network to Segmented 6-VLAN Homelab

This document records the ground-up engineering build that transformed a flat consumer router network (`192.168.10.0/26`) into a segmented, VLAN-isolated enterprise-style homelab using a **Huawei S5320-12TP-LI-AC** managed switch, **Proxmox VE 9.1**, **pfSense CE 2.8.1**, **UniFi Wireless**, **Windows Server Active Directory (`dc01`)**, and **Home Assistant**.

---

## Phase 1: Starting Point & Architectural Decisions

### Starting State
- **Flat LAN:** All devices sat on the ISP modem/router's subnet (`192.168.10.0/26`, gateway `192.168.10.1`).
- **Proxmox Host:** `192.168.10.6/26` on `vmbr0`.
- **pfSense VM 104:** Originally provisioned with 1 vCPU and 2 GB RAM; WAN (`em0`) had a DHCP lease on `vmbr0` (`192.168.10.16/26`) and LAN (`em1`) sat on an isolated internal bridge (`vmbr1`) with no physical port—meaning pfSense was not actually routing traffic for the home network.
- **Unused Hardware:** A factory-reset Huawei S5320-12TP-LI-AC gigabit switch and a Cisco Catalyst WS-C2960-8TC-L sitting on the shelf.

### Core Design Principles
1. **Router-on-a-Stick via pfSense:** pfSense is the sole Layer 3 router and stateful firewall. The Huawei S5320 operates strictly at Layer 2 (VLAN switching).
2. **Leave the Cisco 2960 Out:** The Cisco 2960 only has Fast Ethernet (100 Mbps) ports and no PoE, while the Huawei S5320 has more than enough gigabit copper ports (`1`–`10`) for all wired hosts. Fewer switches mean fewer points of failure and less power draw.
3. **Dedicated WAN VLAN (VLAN 2):** Placing the ISP modem LAN port into an untagged access port on `VLAN 2` allows both the primary pfSense VM (over the Proxmox trunk) and a future physical standby pfSense box (over port 5) to share the upstream WAN segment cleanly for CARP high availability.
4. **Strict Management Isolation (VLAN 99):** All infrastructure control planes—pfSense (`192.168.99.1`), Huawei switch (`192.168.99.2`), Proxmox (`192.168.99.3`), and UniFi Controller (`192.168.99.4`)—live exclusively on `VLAN 99`.

---

## Phase 2: Huawei S5320-12TP-LI-AC Switch Configuration

Configured incrementally over a serial console cable (PuTTY, `COM1`, `9600` baud):

1. **Created VLANs:** `2` (`WAN`), `10` (`HOME`), `20` (`LAB`), `30` (`SERVERS`), `40` (`GUEST`), `50` (`IoT`), and `99` (`MGMT`). Verified with `display vlan`.
2. **Discovered Port Panel Quirks:**
   - I initially assumed ports `9`–`12` were all copper/SFP combo ports. When configuring port 12, it reported `Port Mode: COMMON FIBER` and rejected `combo-port copper`.
   - **Reality on S5320-12TP-LI-AC:** Ports `1`–`8` are RJ45 copper, ports `9`–`10` are dual-media combo ports (appearing as both RJ45 and SFP), and ports `11`–`12` are **SFP-only**.
   - **Fix:** Wiped ports `10`–`12` with `clear configuration interface`, remapped the modem, Proxmox trunk, and standby trunk to copper ports `3`, `4`, and `5`, put the UniFi AP on port `6`, and administratively shut down unused ports `7`–`12`.
3. **Syntax & Firmware Nuances:**
   - Spanning-tree edge port syntax on Huawei VRP is `stp edged-port enable` (with a `d`), not `stp edge-port enable`.
   - The switch firmware caps local RSA keys at `2048` bits (requesting `4096` falls back to `2048`).
4. **Control Plane Hardening:**
   - Configured `Vlanif99` (`192.168.99.2/24`) and static default route via `192.168.99.1`.
   - Enabled `stelnet` (SSH), disabled Telnet (`undo telnet server enable`) and HTTP/HTTPS (`undo http server enable`, `undo http secure-server enable`).
   - Restricted VTY lines `0 4` with `acl 2099 inbound` (`permit source 192.168.99.0 0.0.0.255`) and a 5-minute idle timeout.

*(Full sanitized configuration: [`configs/huawei-s5320-switch.cfg`](../configs/huawei-s5320-switch.cfg))*

---

## Phase 3: Linking the Upstream Modem Router (VLAN 2)

- Connected a LAN port of the ISP modem router (`192.168.10.1/26`) to **Huawei Port 3** (access port in `VLAN 2`).
- *Troubleshooting note:* On the first attempt, port 3 stayed down because the light-blue flat console rollover cable was accidentally used instead of a patch cable. Swapping to a standard Cat6 cable brought port 3 up immediately.
- Verified with `display mac-address vlan 2`, which learned the modem and its active Wi-Fi clients on port 3 while keeping `VLAN 2` completely isolated from internal VLANs.

---

## Phase 4: Resolving the VLAN 10 Subnet Overlap

- **Initial Plan:** `VLAN 10 (HOME)` was originally planned as `192.168.10.0/24`.
- **Conflict Discovered:** Checking live addressing revealed the ISP modem LAN was `192.168.10.0/26` and pfSense WAN (`em0`) had leased `192.168.10.16/26`. pfSense strictly rejects overlapping subnets across WAN and LAN/OPT interfaces.
- **Decision:** Rather than renumbering the ISP modem (which would simultaneously sever fallback Wi-Fi and management access during cutover), I renumbered **VLAN 10 (`HOME`) to `192.168.110.0/24`**.

---

## Phase 5 & 6: Staged Proxmox Cutover (`vmbr0` & `vmbr0.99`)

To avoid locking myself out of the single-NIC Proxmox host during the transition to VLAN trunking:

1. **Made `vmbr0` VLAN-Aware:** Enabled the `VLAN aware` checkbox on `vmbr0` in the Proxmox Web UI and applied.
2. **Prepared pfSense LAN on VLAN 99:** From the pfSense console inside Proxmox, created VLAN tag `99` on `em1` (`em1.99`), assigned it as `LAN` with static IPv4 `192.168.99.1/24`, and enabled DHCP (`192.168.99.100`–`.199`).
3. **Dual-Homed Proxmox Temporarily:** Created Linux VLAN interface `vmbr0.99` (`192.168.99.3/24`, no gateway yet) while keeping `192.168.10.6/26` active on `vmbr0` so the Web UI session remained alive.
4. **Configured pfSense VM 104 NICs:**
   - `net0` (WAN): `bridge=vmbr0, tag=2, firewall=0`
   - `net1` (LAN trunk): `bridge=vmbr0, untagged, firewall=0` (Proxmox firewall disabled so pfSense handles all filtering).
5. **Final Cutover:** Removed the legacy `192.168.10.6/26` IP from `vmbr0`, set gateway `192.168.99.1` on `vmbr0.99`, applied changes, moved the Proxmox physical ethernet cable to **Huawei Port 4 (Trunk)**, and plugged the Dell Admin PC into **Huawei Port 1 (Access VLAN 99)**.
6. **Verification & Fix:** The Admin PC immediately leased `192.168.99.101` and pinged Proxmox (`192.168.99.3`) in `<1 ms`. When pinging `192.168.99.1` initially timed out, inspection revealed `em1.99` had briefly fallen back to DHCP (`192.168.99.100`); re-applying static `192.168.99.1/24` brought the pfSense HTTPS WebGUI up immediately.

---

## Phase 7: Multi-VLAN Services, Active Directory & Home Assistant

With management stable on `VLAN 99`, the remaining internal segments were built out:
- **`VLAN 10 (HOME - 192.168.110.0/24)`:** Primary user Wi-Fi and personal devices.
- **`VLAN 20 (LAB - 192.168.20.0/24)`:** Security testing VMs and remote syslog collector (`192.168.20.9:5514`).
- **`VLAN 30 (SERVERS - 192.168.30.0/24)`:**
  - **Windows Server Domain Controller (`dc01`):** Static DHCP reservation `192.168.30.4` (`bc:24:11:bb:ed:9f`).
  - **Home Assistant VM (`homeassistant`):** Static DHCP reservation `192.168.30.5` (`02:b6:e9:c6:7d:91`).
- **`VLAN 40 (GUEST - 192.168.40.0/24)`:** Isolated guest network.
- **`VLAN 50 (IoT - 192.168.50.0/24)`:** Smart home & IoT devices (Tuya, TP-Link, ESPHome, HomeKit Bridge).
- **DNS Resolver (Unbound):** Configured with DNSSEC, listening on all 6 internal VLAN interfaces **plus `Localhost (`lo0`)`** (required because pfSense queries itself), forwarding/resolving out `WAN`.

---

## Phase 8: CARP High-Availability Design Review

Before expanding static rules further, I reviewed what would be required to add a physical standby pfSense appliance on **Huawei Port 5**:
- **CARP Addressing Requirement:** CARP requires a shared Virtual IP (VIP) per VLAN (`.1`) plus two dedicated real interface IPs (`.253` primary, `.254` secondary) and a static WAN IP outside the ISP modem's DHCP pool.
- **Why Port 3 (VLAN 2) Matters:** Putting the ISP modem on Huawei Port 3 (`VLAN 2`) rather than cabled directly to the Proxmox host means both the virtual primary firewall (Port 4) and physical standby firewall (Port 5) have Layer 2 adjacency to the WAN subnet.

---

## Phase 9 & 10: UniFi Network Server LXC & VLAN-Tagged Wi-Fi

### Deploying UniFi 10.6.109 in a Debian 12 LXC (`192.168.99.4`)
- **Resource Constraint:** The Proxmox host (`15.5 GiB` RAM, ~4.7 GiB free, 85% disk used) did not have the overhead for Ubiquiti's heavy Podman-based *UniFi OS Server*. Instead, I deployed a lightweight unprivileged **Debian 12 LXC** (`2 vCPU, 2 GB RAM, 16 GB disk`) on `VLAN 99` (`192.168.99.4/24`).
- **Two Dependency Roadblocks Solved:**
  1. **Empty Ubiquiti APT Index:** Ubiquiti's official `apt` repository returned a `0-byte` `Packages` index on `amd64`. Solved by downloading the `.deb` package (`10.6.109`) directly.
  2. **MongoDB & Java 25 Requirement:** Debian 12 omits MongoDB and Java 25. While UniFi 9.x used Java 17/21, **UniFi 10.6.109 strictly requires `temurin-25-jre`**. Added the official MongoDB 7.0 repository (`mongodb-org-server`, with standalone `mongod` disabled since UniFi runs its own instance on port `27117`) and the Eclipse Adoptium repository (`temurin-25-jre`).

*(Reproducible installation script: [`configs/unifi-lxc-install.sh`](../configs/unifi-lxc-install.sh))*

### Trunking the UniFi UAP-AC-Pro (`Huawei Port 6`)
- Configured **Huawei Port 6** with `port trunk pvid vlan 99` (untagged native management so the AP leases `192.168.99.102` and talks to the controller at `192.168.99.4:8443`) and `port trunk allow-pass vlan 10 40 50 99` (`undo port trunk allow-pass vlan 1`).
- Configured two VLAN-tagged SSIDs in UniFi (using **Third-Party Gateway** networks so pfSense handles all routing and DHCP):
  - **`ConnectMe` (VLAN 10 – `HOME`):** 2.4 GHz & 5 GHz, WPA2/WPA3.
  - **`Stark_Industries` (VLAN 50 – `IoT`):** 2.4 GHz only, WPA2.
