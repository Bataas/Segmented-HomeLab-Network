# Segmented Home Lab Network: Huawei S5320 + Proxmox VE + pfSense + UniFi + Home Assistant

**Project Type:** Network Engineering · VLAN Segmentation · Cybersecurity · Proxmox Virtualisation · Infrastructure Automation  
**Status:** Production Active — Core Network, 6 VLANs, Wi-Fi, Active Directory & Home Assistant Working (`538.08 Mbps` Line-Rate via VirtIO)  
**Last Updated:** 2026-11-18

This repository documents how I rebuilt a flat consumer home network (`192.168.10.0/26`) into a **segmented, 6-VLAN enterprise-style network** with **pfSense CE 2.8.1** (virtualised on **Proxmox VE 9.1**) as the sole router and stateful firewall, a **Huawei S5320-12TP-LI-AC** managed core switch handling Layer 2 VLAN distribution, **UniFi** providing VLAN-tagged multi-SSID Wi-Fi, and dedicated server/smart-home segments running **Windows Server Active Directory (`dc01`)** and **Home Assistant**.

It is written as an **honest engineering build log**: what I planned, what I built phase by phase, what went wrong (including mistakes made by both me and AI assistants), how I diagnosed a **92 Mbps throughput bottleneck** on a **500 Mbps** internet connection, and how I used an **autonomous AI recovery workflow** over SSH to recover my VLAN interfaces and audit firewall rules after migrating pfSense from Intel E1000 to VirtIO network adapters.

---

## Table of Contents

1. [Project Goals & Objectives](#1-project-goals--objectives)
2. [Final Network Architecture & Topology](#2-final-network-architecture--topology)
3. [Hardware & Software Inventory](#3-hardware--software-inventory)
4. [VLAN Addressing Plan & Switch Port Map](#4-vlan-addressing-plan--switch-port-map)
5. [Complete Build Log by Phase (Phases 1–12)](#5-complete-build-log-by-phase-phases-112)
   - [Phase 1: Planning & Architectural Decisions](#phase-1-planning--architectural-decisions)
   - [Phase 2: Huawei S5320 Core Switch Configuration & Hardening](#phase-2-huawei-s5320-core-switch-configuration--hardening)
   - [Phase 3: Linking the ISP Modem Router (WAN VLAN 2)](#phase-3-linking-the-isp-modem-router-wan-vlan-2)
   - [Phase 4: Discovering & Fixing the VLAN 10 Subnet Overlap](#phase-4-discovering--fixing-the-vlan-10-subnet-overlap)
   - [Phase 5: Staged Proxmox & pfSense Preparation (`vmbr0` & `vmbr0.99`)](#phase-5-staged-proxmox--pfsense-preparation-vmbr0--vmbr099)
   - [Phase 6: Physical Cutover & Management Recovery](#phase-6-physical-cutover--management-recovery)
   - [Phase 7: pfSense VLAN Services, Unbound DNS & Firewall Policy](#phase-7-pfsense-vlan-services-unbound-dns--firewall-policy)
   - [Phase 8: High-Availability Design Review (CARP Failover)](#phase-8-high-availability-design-review-carp-failover)
   - [Phase 9: UniFi Network Server 10.6.109 in a Debian 12 LXC](#phase-9-unifi-network-server-106109-in-a-debian-12-lxc)
   - [Phase 10: Trunking the UniFi AP & VLAN-Tagged Wi-Fi SSIDs](#phase-10-trunking-the-unifi-ap--vlan-tagged-wi-fi-ssids)
   - [Phase 11: Expanding to VLAN 50 (IoT), Active Directory (`dc01`) & Home Assistant](#phase-11-expanding-to-vlan-50-iot-active-directory-dc01--home-assistant)
   - [Phase 12: Solving the 500 Mbps Bottleneck, VirtIO Migration & Autonomous AI Recovery](#phase-12-solving-the-500-mbps-bottleneck-virtio-migration--autonomous-ai-recovery)
6. [Firewall, DHCP & DNS Design Specification](#6-firewall-dhcp--dns-design-specification)
7. [Performance Benchmarking (E1000 vs. VirtIO)](#7-performance-benchmarking-e1000-vs-virtio)
8. [Complete Mistakes, Unexpected Behaviour & Corrections Log](#8-complete-mistakes-unexpected-behaviour--corrections-log)
9. [Verification & Validation Matrix](#9-verification--validation-matrix)
10. [Design Rationale: Why I Chose What I Chose](#10-design-rationale-why-i-chose-what-i-chose)
11. [Engineering Lessons Learned](#11-engineering-lessons-learned)
12. [Known Gaps & Future Roadmap](#12-known-gaps--future-roadmap)
13. [Repository Structure & Sanitized Artifacts](#13-repository-structure--sanitized-artifacts)
14. [Appendix: Troubleshooting Commands That Helped](#14-appendix-troubleshooting-commands-that-helped)

---

## 1. Project Goals & Objectives

- **End-to-End VLAN Segmentation:** Separate `HOME` (VLAN 10), `LAB` (VLAN 20), `SERVERS` (VLAN 30), `GUEST` (VLAN 40), `IoT` (VLAN 50), and `MANAGEMENT` (VLAN 99) networks, each with its own subnet, DHCP scope, DNS interface, and least-privilege firewall policy.
- **Single Router & Firewall (`pfSense`):** pfSense (VM 104 on Proxmox) performs all inter-VLAN routing and stateful packet filtering. The Huawei S5320 switch operates strictly at Layer 2.
- **Isolated Management Control Plane (`VLAN 99`):** Administrative interfaces for pfSense (`192.168.99.1`), the Huawei switch (`192.168.99.2`), Proxmox (`192.168.99.3`), and the UniFi Controller (`192.168.99.4`) are reachable **only** from `VLAN 99` and explicitly blocked from all user/IoT/guest VLANs via `(self)` and alias rules.
- **Controlled Smart Home & Server Pinholes:** Allow `HOME` and `IoT` clients to reach **Home Assistant (`192.168.30.5`)** on `SERVERS`, and allow Home Assistant to reach `IoT` devices (`192.168.50.0/24`), while blocking `IoT` from initiating connections to any other internal subnet.
- **Multi-SSID VLAN-Tagged Wi-Fi:** Broadcast separate SSIDs (`ConnectMe` on VLAN 10 and `Stark_Industries` on VLAN 50) from a single UniFi UAP-AC-Pro over an 802.1Q trunk.
- **High-Availability Readiness (CARP):** Architect the WAN (`VLAN 2`) and trunk ports so a physical standby pfSense box on Huawei Port 5 can take over automatically via CARP.
- **Full Line-Rate Throughput (500/50 Mbps):** Identify and eliminate virtual NIC bottlenecks to deliver the full 500+ Mbps ISP speed through the firewall.

---

## 2. Final Network Architecture & Topology

![Home Network Architecture](./diagrams/home_network_current_and_planned.svg)

### Logical & Physical Topology

```text
                                 INTERNET (TPG 500/50 Mbps)
                                             |
                              ISP Modem Router 192.168.10.1/26
                                             |  (Huawei Port 3, Access VLAN 2 = "WAN")
   +-----------------------------------------+-----------------------------------------+
   |  Huawei S5320-12TP-LI-AC Core Switch (Layer 2 Only)                               |
   |  Management: 192.168.99.2/24 on Vlanif99 (SSH only, restricted by ACL 2099)       |
   +---+-------------+-----------------+------------------+----------------+-----------+
       |             |                 |                  |                |
    Port 1        Port 2            Port 4             Port 5           Port 6
   Dell PC       Printer           Proxmox VE        Standby FW        UniFi AP
   Access        Access            802.1Q Trunk      802.1Q Trunk      802.1Q Trunk
   VLAN 99       VLAN 10           VLANs 2,10,20,    (Reserved for     Native (PVID) 99,
  (.99.101)     (Planned)          30,40,50,99       CARP Failover)    Tagged 10,40,50

   Proxmox VE 9.1 Host (192.168.99.3/24 on vmbr0.99, VLAN-aware vmbr0 on nic0)
     |-- pfSense CE 2.8.1 (VM 104: 4 vCPU, 4 GB RAM, Q35)
     |     |-- WAN (net0 -> vtnet0): vmbr0, VLAN tag 2 (DHCP: 192.168.10.16/26)
     |     |-- LAN Trunk (net1 -> vtnet1): vmbr0, untagged trunk carrying:
     |           |-- vtnet1.99 (LAN / MGMT):   192.168.99.1/24
     |           |-- vtnet1.10 (OPT1 / HOME):  192.168.110.1/24
     |           |-- vtnet1.20 (OPT2 / LAB):   192.168.20.1/24
     |           |-- vtnet1.30 (OPT3 / SRV):   192.168.30.1/24
     |           |-- vtnet1.40 (OPT4 / GUEST): 192.168.40.1/24
     |           +-- vtnet1.50 (OPT5 / IoT):   192.168.50.1/24
     |-- UniFi Network Server 10.6.109 (Debian 12 LXC): 192.168.99.4 (VLAN 99)
     |-- Windows Server Domain Controller (dc01 VM):    192.168.30.4 (VLAN 30)
     +-- Home Assistant OS (homeassistant VM):          192.168.30.5 (VLAN 30)
```

---

## 3. Hardware & Software Inventory

| Component | Specifications & Notes |
|---|---|
| **Huawei S5320-12TP-LI-AC** | Core Layer 2 switch. 8 copper GbE ports (`1`–`8`), 2 copper/SFP combo ports (`9`–`10`), 2 SFP-only fiber cages (`11`–`12`). Configured via serial console (`9600` baud), subsequently managed via SSH on `192.168.99.2`. |
| **Cisco WS-C2960-8TC-L** | 8 Fast Ethernet (`100 Mbps`) ports + 1 dual-purpose GbE uplink, Layer 2, no PoE. Intentionally left out of the topology to avoid a 100 Mbps bottleneck and unnecessary device sprawl. |
| **Proxmox VE 9.1.x Host** | Intel Core i5-7400T (`4C/4T @ 2.40 GHz`), `15.5 GiB` RAM, single physical GbE NIC (`nic0`). |
| **pfSense CE 2.8.1 (VM 104)** | Started with `1 vCPU / 2 GB RAM` and two `Intel E1000` (`em0`/`em1`) NICs; upgraded during Phase 12 to **`4 vCPUs (host) / 4 GB RAM`** and two **`VirtIO` (`vtnet0`/`vtnet1`)** NICs on `32 GB` VirtIO-SCSI storage. |
| **Spare x86 Appliance** | `4 GB` RAM, `16 GB` SSD, 1 onboard NIC (+ USB GbE adapter planned). Reserved for the future CARP standby pfSense node on Huawei Port 5. |
| **ISP Modem Router** | Remains untouched at `192.168.10.1/26` on a 500/50 Mbps TPG NBN connection; LAN port connected to Huawei Port 3 (`VLAN 2`). |
| **UniFi UAP-AC-Pro** | Dual-band 802.11ac Access Point (`192.168.99.102`), powered via PoE injector on Huawei Port 6. |
| **UniFi Network Server 10.6.109** | Hosted in an unprivileged Debian 12 LXC (`192.168.99.4`, `2 vCPU, 2 GB RAM, 16 GB disk`) with MongoDB 7.0 and Eclipse Temurin Java 25. |
| **Home Assistant & Active Directory** | Home Assistant VM (`192.168.30.5`) and Windows Server Domain Controller `dc01` (`192.168.30.4`) on `VLAN 30 (SERVERS)`. |
| **Raspberry Pi 4** | Wyoming protocol voice assistant satellite. |
| **MikroTik wAP ac** | Spare AP running RouterOS (not managed by UniFi; parked for future lab testing). |

---

## 4. VLAN Addressing Plan & Switch Port Map

### VLAN & Subnet Table

| VLAN | pfSense Interface | Network Name | Subnet | pfSense Gateway | DHCP Scope | Static Reservations / Key Hosts |
|---:|---|---|---|---|---|---|
| **2** | `WAN` (`vtnet0`) | `WAN` | `192.168.10.0/26` | `192.168.10.1` *(Modem)* | Modem DHCP | pfSense WAN (`192.168.10.16/26`), ISP Modem (`192.168.10.1`) |
| **10** | `OPT1` (`vtnet1.10`) | `HOME` | `192.168.110.0/24` | `192.168.110.1` | `.110.100` – `.110.199` | Personal devices, `ConnectMe` Wi-Fi (e.g., iPhone `.110.100`), Printer |
| **20** | `OPT2` (`vtnet1.20`) | `LAB` | `192.168.20.0/24` | `192.168.20.1` | `.20.100` – `.20.199` | Lab VMs, Windows client, Remote Syslog Server (`192.168.20.9:5514`) |
| **30** | `OPT3` (`vtnet1.30`) | `SERVERS` | `192.168.30.0/24` | `192.168.30.1` | `.30.100` – `.30.149` | `dc01` (`192.168.30.4` / `bc:24:11:bb:ed:9f`), `homeassistant` (`192.168.30.5` / `02:b6:e9:c6:7d:91`) |
| **40** | `OPT4` (`vtnet1.40`) | `GUEST` | `192.168.40.0/24` | `192.168.40.1` | `.40.100` – `.40.200` | Isolated guest Wi-Fi |
| **50** | `OPT5` (`vtnet1.50`) | `IoT` | `192.168.50.0/24` | `192.168.50.1` | `.50.100` – `.50.200` | `Stark_Industries` 2.4 GHz IoT SSID (e.g., `lwip0` `.50.100`, Tuya, TP-Link) |
| **99** | `LAN` (`vtnet1.99`) | `MGMT` | `192.168.99.0/24` | `192.168.99.1` | `.99.100` – `.99.199` | pfSense (`.99.1`), Huawei Switch (`.99.2`), Proxmox (`.99.3`), UniFi LXC (`.99.4`), Admin PC (`.99.101`), UniFi AP (`.99.102`) |

### Huawei S5320-12TP-LI-AC Physical Port Map

*Physical panel note:* Ports `1`–`8` are two rows of four RJ45 sockets (top row `1, 3, 5, 7`; bottom row `2, 4, 6, 8`). Ports `9`–`10` are dual-media combo ports (RJ45 + SFP sharing each port number). Cages `11`–`12` are SFP-only (`COMMON FIBER`).

| Huawei Port | Connected Device | Mode | VLAN Configuration |
|---|---|---|---|
| `GigabitEthernet0/0/1` | Admin Dell PC (`192.168.99.101`) | `access` | Default `VLAN 99`, `stp edged-port enable` |
| `GigabitEthernet0/0/2` | Printer *(not plugged in yet)* | `access` | Default `VLAN 10`, `stp edged-port enable` |
| `GigabitEthernet0/0/3` | ISP Modem Router LAN Port (`192.168.10.1`) | `access` | Default `VLAN 2` (WAN transit) |
| `GigabitEthernet0/0/4` | Proxmox VE Host (`nic0`) | `trunk` | `allow-pass vlan 2 10 20 30 40 50 99` |
| `GigabitEthernet0/0/5` | Standby pfSense *(future CARP)* | `trunk` | `allow-pass vlan 2 10 20 30 40 50 99` |
| `GigabitEthernet0/0/6` | UniFi UAP-AC-Pro *(via PoE injector)* | `trunk` | Native (`pvid`) `VLAN 99`, tagged `10 40 50 99`, `undo allow-pass vlan 1`, `stp edged-port enable` |
| `GigabitEthernet0/0/7`–`12` | Unused | `shutdown` | Administratively shut down in port-group so nobody can plug into a live VLAN |

### Virtual Network Adapter Mapping (Proxmox VM 104 $\leftrightarrow$ pfSense)

| Proxmox Adapter | MAC Address | Proxmox Bridge Config | Old NIC (`E1000`) | New NIC (`VirtIO`) | Role |
|---|---|---|---|---|---|
| `net0` | `BC:24:11:8C:64:78` | `bridge=vmbr0, tag=2, firewall=0` | `em0` | `vtnet0` | WAN (`VLAN 2`) |
| `net1` | `BC:24:11:48:B9:91` | `bridge=vmbr0, untagged, firewall=0` | `em1` | `vtnet1` | LAN 802.1Q Trunk (`VLANs 10, 20, 30, 40, 50, 99`) |

---

## 5. Complete Build Log by Phase (Phases 1–12)

### Phase 1: Planning & Architectural Decisions

**Starting Point:**
- A flat network on the ISP modem router (`192.168.10.0/26`), Proxmox host at `192.168.10.6/26` on `vmbr0`, and pfSense VM 104 with WAN on `vmbr0` (`192.168.10.16/26`) and LAN on `vmbr1` (an internal bridge with no physical NIC). At that stage, pfSense wasn't routing anything—all home devices went straight through the ISP modem.
- A factory-reset Huawei S5320-12TP-LI-AC switch and an unused Cisco Catalyst 2960.

**Key Decisions:**
- **Simplified 2-Tier Physical Design:** Dropped the idea of using the Cisco 2960 as an access switch because it is limited to Fast Ethernet (`100 Mbps`) with no PoE, and the Huawei S5320 has enough gigabit copper ports for every wired device.
- **Layer 3 Exclusively on pfSense:** The Huawei switch performs pure Layer 2 VLAN switching.
- **Management Hardening:** Admin interfaces live only on `VLAN 99`, Telnet and the switch HTTP/HTTPS server are disabled, SSH is restricted by an inbound ACL (`2099`), and nothing is exposed to the WAN.
- **Learn by Doing:** Proxmox network changes were intentionally staged in the Proxmox Web UI so every bridge/VLAN state change could be visually inspected before applying.

---

### Phase 2: Huawei S5320 Core Switch Configuration & Hardening

Configured step-by-step over the serial console (PuTTY, `COM1`, `9600` baud):
1. Created VLANs (`2, 10, 20, 30, 40, 99`, later adding `50`) and verified with `display vlan`.
2. Created `VLAN 2` as the dedicated WAN transit VLAN so the ISP modem and both primary/standby pfSense instances share an isolated Layer 2 broadcast domain.
3. Configured access and trunk ports, `Vlanif99` (`192.168.99.2/24`), and default route `0.0.0.0/0` via `192.168.99.1`.
4. Hardened the switch: generated a local RSA key pair, enabled `stelnet` (SSH), disabled Telnet and HTTP/HTTPS, restricted VTY `0 4` to `192.168.99.0/24` via `acl 2099 inbound`, and set a 5-minute idle timeout.

**Challenges & Lessons in Phase 2:**
- **Port 12 is Fiber-Only (`COMMON FIBER`):** I had assumed ports `9`–`12` were all copper combo ports. Port 12 logged optical transceiver warnings and rejected `combo-port copper`. Only ports `9`–`10` are combo ports (`11`–`12` are SFP-only). I wiped ports `10`–`12` with `clear configuration interface` and remapped the modem, Proxmox trunk, and standby trunk to copper ports `3`, `4`, and `5`.
- **STP Syntax:** On this Huawei VRP firmware, the edge-port command is `stp edged-port enable` (with a `d`); `stp edge-port enable` was rejected.
- **RSA Key Ceiling:** Requesting a 4096-bit RSA key was refused by firmware; it fell back to the maximum supported `2048` bits.
- **Prompt Discipline:** One batch of pasted commands failed because it was pasted at the `<CORE-SW>` user-view prompt instead of `[CORE-SW]` system-view, included prompt text, and answered `n` to `clear configuration` confirmations. Fix: always enter `system-view` first and paste clean commands only.
- **Volatile Clock:** The switch has no battery-backed RTC and reset to year `2000` after a power move.

*(Sanitized switch configuration: [`configs/huawei-s5320-switch.cfg`](./configs/huawei-s5320-switch.cfg))*

---

### Phase 3: Linking the ISP Modem Router (WAN VLAN 2)

- Connected a LAN port of the ISP modem router (`192.168.10.1/26`) to **Huawei Port 3** (access port in `VLAN 2`).
- *Gotcha:* On the first check, no port came up because I had grabbed the light-blue flat console rollover cable instead of an Ethernet patch cable. Swapping to a standard Cat6 cable brought Port 3 up immediately.
- `display mac-address vlan 2` learned four MAC addresses on Port 3—expected behaviour because the modem bridges its internal switch and Wi-Fi clients onto its LAN ports.

---

### Phase 4: Discovering & Fixing the VLAN 10 Subnet Overlap

- Before touching pfSense, I checked live addressing: the ISP modem's LAN was `192.168.10.0/26` (`.1` gateway) and pfSense WAN had leased `192.168.10.16/26`.
- My original plan had `VLAN 10 (HOME)` as `192.168.10.0/24`, which overlaps `192.168.10.0/26`. pfSense strictly refuses overlapping subnets across two interfaces.
- **Decision:** Rather than renumbering the ISP modem (which would have knocked Proxmox and my PC offline simultaneously), I moved **`VLAN 10 (HOME)` to `192.168.110.0/24`**.

---

### Phase 5: Staged Proxmox & pfSense Preparation (`vmbr0` & `vmbr0.99`)

Executed in the Proxmox Web UI in low-risk stages so I would never lose remote management access:
1. Ticked **VLAN aware** on `vmbr0` and clicked Apply.
2. In the pfSense console, created VLAN `99` on `em1` (`em1.99`), assigned it as `LAN` (`192.168.99.1/24`), and enabled DHCP (`192.168.99.100`–`.199`).
3. Created Linux VLAN interface `vmbr0.99` in Proxmox with `192.168.99.3/24` (no gateway yet) and applied, while leaving `192.168.10.6/26` on `vmbr0` so my current browser session stayed connected.
4. Configured pfSense VM 104 NICs: `net0` (`vmbr0`, `tag=2`, `firewall=0`) and `net1` (`vmbr0`, untagged trunk, `firewall=0`).
5. Staged the final Proxmox cutover edit: removed `192.168.10.6/26` from `vmbr0` and set gateway `192.168.99.1` on `vmbr0.99`. Verified the pending diff in the UI before clicking Apply.

*(Sanitized Proxmox configuration: [`configs/proxmox-network-and-vm104.conf`](./configs/proxmox-network-and-vm104.conf))*

---

### Phase 6: Physical Cutover & Management Recovery

**Cutover Sequence:** Clicked Apply in Proxmox $\rightarrow$ moved the Proxmox cable from the modem to **Huawei Port 4** $\rightarrow$ plugged the Dell Admin PC into **Huawei Port 1** (with Wi-Fi off).

**Results & Troubleshooting:**
- The Dell PC immediately leased `192.168.99.101` from pfSense with gateway `192.168.99.1`—proving the entire Layer 2 path (Dell PC $\rightarrow$ Huawei Port 1 $\rightarrow$ Port 4 Trunk $\rightarrow$ Proxmox `vmbr0` $\rightarrow$ pfSense VLAN 99).
- Pinging Proxmox (`192.168.99.3`) succeeded in `<1 ms`, but pinging pfSense (`192.168.99.1`) initially timed out.
- **Root Cause:** Checking the pfSense console revealed the management interface had briefly used a dynamic address (`192.168.99.100`) instead of static `192.168.99.1`. Reapplying static `192.168.99.1/24` stopped the DHCP client on LAN and brought the pfSense HTTPS WebGUI (`https://192.168.99.1`) online immediately.

---

### Phase 7: pfSense VLAN Services, Unbound DNS & Firewall Policy

In the pfSense WebGUI:
- Created VLAN interfaces on the trunk NIC (`99 MGMT`, `10 HOME`, `20 LAB`, `30 SERVERS`, `40 GUEST`, and later `50 IoT`), leaving the parent trunk NIC unassigned.
- Configured static `/24` gateway IPs and DHCP pools on every VLAN.
- Enabled **Unbound DNS Resolver** with DNSSEC, DHCP lease registration, and static mapping registration, listening on all internal VLAN interfaces **plus `Localhost (`lo0`)`** (Unbound refused to save until `Localhost` was selected because pfSense uses itself as resolver).
- Disabled *"Block private networks and loopback addresses"* on `WAN` because the WAN subnet (`192.168.10.0/26`) sits behind the ISP modem's RFC1918 NAT.
- *Side note — The "Firewall Off" Scare:* During rule testing, I worried I had run `pfctl -d` in the shell (which disables both packet filtering and NAT). Checking `pfctl -s info` confirmed `Status: Enabled`. Lesson: never use `pfctl -d` to test a rule; inspect `pfctl -sr | grep USER_RULE` and firewall logs instead.

---

### Phase 8: High-Availability Design Review (CARP Failover)

Reviewed the architecture required to deploy the spare x86 box as a CARP standby firewall on **Huawei Port 5**:
- **CARP Addressing Scheme:** Each firewall needs its own real IP on every VLAN (`.253` primary, `.254` secondary) plus a shared Virtual IP (`.1` VIP) used by clients as their default gateway.
- **WAN Requirement:** CARP requires static WAN IPs (plus a shared WAN VIP) inside `192.168.10.0/26` outside the ISP modem's DHCP pool. Putting the modem on **Huawei Port 3 (`VLAN 2`)** makes this possible without adding a second physical WAN switch.

---

### Phase 9: UniFi Network Server 10.6.109 in a Debian 12 LXC

Rather than running the controller on a separate physical machine or heavy VM, I deployed an unprivileged **Debian 12 LXC** (`2 vCPU, 2 GB RAM, 512 MB swap, 16 GB disk`) on `VLAN 99` (`192.168.99.4/24`).

**Three Real-World Issues Solved:**
1. **Forgotten Container Root Password:** Recovered in 10 seconds from the Proxmox host shell using `pct enter <ctid>` and `passwd` without rebuilding the container.
2. **Broken Ubiquiti APT Repository:** Ubiquiti's official `apt` repo returned a `0-byte` `Packages` index on `amd64` (`Unable to locate package unifi`). Worked around by downloading the `10.6.109` `.deb` package directly.
3. **Why Legacy UniFi Server vs. UniFi OS Server + Java 25 Dependency:**
   - Ubiquiti's newer *UniFi OS Server* requires Podman and 4+ GB RAM / 20 GB disk, which did not fit comfortably on the Proxmox host (`4.7 GiB` free RAM, `10 GiB` free disk).
   - While older UniFi 9.x releases used Java 17/21, **UniFi Network Server 10.6.109 depends on Java 25**, which Debian 12 does not ship.
   - **Solution:** Added the official **MongoDB 7.0** repository (`mongodb-org-server`, disabling standalone `mongod` since UniFi spawns its own instance on port `27117`) and the **Eclipse Adoptium** repository (`temurin-25-jre`), then installed the `.deb`. Controller UI came up at `https://192.168.99.4:8443`.

*(Reproducible installation script: [`configs/unifi-lxc-install.sh`](./configs/unifi-lxc-install.sh))*

---

### Phase 10: Trunking the UniFi AP & VLAN-Tagged Wi-Fi SSIDs

1. Configured **Huawei Port 6** as a hybrid/trunk port with **native (`pvid`) `VLAN 99`** (so the AP leases `192.168.99.102` and reaches `192.168.99.4:8443` untagged) and tagged VLANs `10, 40, 50` (`undo port trunk allow-pass vlan 1`).
2. Defined **Third-Party Gateway** (VLAN-only) networks in the UniFi Controller for `HOME (VLAN 10)` and `IoT (VLAN 50)` so pfSense remains the sole DHCP server and router.
3. Broadcasted two SSIDs across the UAP-AC-Pro ([screenshot](./screenshots/06-unifi-vlan-ssids.png)):
   - **`ConnectMe` (`VLAN 10 – HOME`):** 2.4 GHz & 5 GHz, WPA2/WPA3.
   - **`Stark_Industries` (`VLAN 50 – IoT`):** 2.4 GHz only, WPA2.
4. *Gotcha:* Always bind the SSID explicitly to the VLAN network (`HOME (10)` or `IoT (50)`), never `Default`, otherwise wireless clients drop into management `VLAN 99`.

---

### Phase 11: Expanding to VLAN 50 (IoT), Active Directory (`dc01`) & Home Assistant

With the core network and Wi-Fi working, I completed the server, smart-home, and security hardening tasks:
- **Moved Server VMs to `VLAN 30 (SERVERS - 192.168.30.0/24)`:**
  - Assigned static DHCP reservation **`192.168.30.4`** (`bc:24:11:bb:ed:9f`) to **`dc01`** (Windows Server Domain Controller).
  - Assigned static DHCP reservation **`192.168.30.5`** (`02:b6:e9:c6:7d:91`) to **`homeassistant`** (Home Assistant OS VM running Tuya, TP-Link Smart Home, ESPHome, Music Assistant, Wyoming Protocol, and HomeKit Bridges on `:21064` & `:21065` — [screenshot](./screenshots/07-home-assistant-integrations.png)).
- **Hardened User VLAN Firewall Rules (`opt1`–`opt5`):**
  - Added **`Block access to pfSense (self)`** rules immediately below the DNS (`:53`) and DHCP (`:67`) pass rules on every non-management VLAN so users/IoT/guests cannot access the pfSense WebGUI (`:443`) or SSH (`:22`) ([verification screenshot](./screenshots/08-dns-and-firewall-isolation-test.png)).
  - Added the upstream modem subnet (`192.168.10.0/26`) to every VLAN's blocked-network alias so internal clients cannot access the ISP modem's admin page (`192.168.10.1`).
  - Added granular Home Assistant rules allowing `HOME (VLAN 10)` $\rightarrow$ `192.168.30.5`, `IoT (VLAN 50)` $\rightarrow$ `192.168.30.5`, and `192.168.30.5` $\rightarrow$ `IoT (192.168.50.0/24)`.

---

### Phase 12: Solving the 500 Mbps Bottleneck, VirtIO Migration & Autonomous AI Recovery

#### 1. Diagnosing the 92 Mbps $\rightarrow$ 143 Mbps Bottleneck
- **Symptom:** My internet plan is **500/50 Mbps** (and speed tests directly on the ISP modem's Wi-Fi hit **539 Mbps**), but wired and wireless clients behind pfSense were getting only **~91.6–93 Mbps**.
- **Step 1 — VM CPU/RAM Upgrade (`1 vCPU / 2 GB` $\rightarrow$ `4 vCPU / 4 GB`):** Upgrading VM 104 to 4 vCPUs (`host`) and 4 GB RAM increased download speeds from **92 Mbps to 143 Mbps** (upload **52 Mbps**), with pfSense CPU peaking at **57%**.
- **Root Cause:** Emulated **Intel E1000 (`em0`/`em1`)** virtual NICs in QEMU/KVM incur high per-packet MMIO exit overhead and single-queue interrupt serialization on the i5-7400T host. Achieving full 500+ Mbps required migrating `net0` and `net1` to paravirtualized **VirtIO (`vtnet0`/`vtnet1`)** adapters.

#### 2. The VirtIO Migration & Console Assignment Pitfall
1. Took Proxmox snapshot **`Before_VirtIO_Migration`** (`TASK OK`) and switched `net0` and `net1` from `Intel E1000` to `VirtIO` ([screenshot](./screenshots/01-proxmox-vm104-nic-migration.png)).
2. When pfSense booted, the NIC driver names changed from `em0`/`em1` to `vtnet0`/`vtnet1`, stranding the existing `em1.*` VLAN definitions and triggering the console `1) Assign Interfaces` wizard ([screenshot](./screenshots/03-pfsense-console-assign-pitfall.png)).
3. After creating `vtnet1` VLANs (`99, 10, 20, 30, 40, 50`) and assigning `WAN -> vtnet0` and `LAN -> vtnet1.99`, pressing **Enter** (`nothing if finished`) at `Enter the Optional 1 interface name` caused pfSense (`revision 1794936514`) to **wipe `<opt1>` through `<opt5>` from `<interfaces>` in `/cf/conf/config.xml`**.
4. Re-adding `OPT1`–`OPT5` in the WebGUI created blank, unconfigured interfaces on `vtnet1.10`–`vtnet1.50` missing all IPv4 gateway addresses and descriptions ([screenshot](./screenshots/05-pfsense-blank-opt-interfaces.png)), while both old `em1.*` and new `vtnet1.*` VLANs appeared side-by-side ([screenshot](./screenshots/04-pfsense-duplicate-em1-vtnet1-vlans.png)).

#### 3. Autonomous AI Recovery via SSH & pfSense PHP Subsystem
Rather than manually re-entering every VLAN IP, description, and rule—or overwriting the configuration blindly—an autonomous recovery workflow was executed over SSH (`root@192.168.99.1`):
- **Configuration Diff & Discovery:** Diffing `/cf/conf/backup/config-1794935923.xml` against live `/cf/conf/config.xml` proved that while `<interfaces><opt1..opt5>` had been cleared, **100% of `<dhcpd>`, `<filter>`, `<aliases>`, and `<unbound>` were still intact** in `config.xml`.
- **Two Hidden Firewall Bugs Caught During Audit ([`scripts/pfsense_xml_auditor.py`](./scripts/pfsense_xml_auditor.py)):**
  1. **Critical IoT Rule Bug:** Rule tracker `1794928789` on `opt5` (`IOT - Block other internal networks` $\rightarrow$ `IoT_BLOCKED_NETWORKS`) had accidentally been saved with **`<type>pass</type>`** instead of **`<type>block</type>`**, leaving internal networks exposed to IoT!
  2. **Missing IoT Subnet in Block Aliases:** `192.168.50.0/24` (`IoT`) was missing from `INTERNAL_NETWORKS`, `LAB_BLOCKED_NETWORKS`, `SERVERS_BLOCKED_NETWORKS`, and `GUEST_BLOCKED_NETWORKS`.
- **Surgical Live Restoration:**
  1. Executed [`scripts/recover_step1_interfaces.php`](./scripts/recover_step1_interfaces.php) to restore `OPT1`–`OPT5` IPv4 addresses, subnets, descriptions, and `vtnet1` VLAN descriptions, calling `interface_configure('opt1'..'opt5')`, `services_dhcpd_configure()`, `services_unbound_configure()`, and `filter_configure()` without dropping the active management SSH session on `vtnet1.99`.
  2. Executed [`scripts/recover_step2_firewall_audit_fix.php`](./scripts/recover_step2_firewall_audit_fix.php) to change rule `1794928789` to `block` and add `192.168.50.0/24` to all 4 inter-VLAN block aliases.
  3. Executed [`scripts/cleanup_phase_c_obsolete_vlans.php`](./scripts/cleanup_phase_c_obsolete_vlans.php) after validation to remove the 6 obsolete `em1.*` VLAN definitions from `config.xml` and destroy the orphaned kernel VLAN interfaces.

---

## 6. Firewall, DHCP & DNS Design Specification

### Inter-VLAN Policy Matrix

| Source $\downarrow$ / Destination $\rightarrow$ | `MGMT (99)` | `HOME (10)` | `LAB (20)` | `SERVERS (30)` | `GUEST (40)` | `IoT (50)` | `pfSense (self)` | `Modem (10.0/26)` | `Internet` |
|---|---|---|---|---|---|---|---|---|---|
| **`MGMT (VLAN 99)`** | Allow | Allow | Allow | Allow | Allow | Allow | **Allow (Admin)** | Allow | Allow |
| **`HOME (VLAN 10)`** | Block | Own VLAN | Block | **Allow `.30.5` (HA) only** | Block | Block | **Allow `:53`/`:67` only** | Block | Allow |
| **`LAB (VLAN 20)`** | Block | Block | Own VLAN | **Allow (Stateful)** | Block | Block | **Allow `:53`/`:67` only** | Block | Allow |
| **`SERVERS (VLAN 30)`** | Block | Block | Block new | Own VLAN | Block | **Allow `.30.5` $\rightarrow$ `IoT` only** | **Allow `:53`/`:67` only** | Block | Allow |
| **`GUEST (VLAN 40)`** | Block | Block | Block | Block | Own VLAN | Block | **Allow `:53`/`:67` only** | Block | Allow |
| **`IoT (VLAN 50)`** | Block | Block | Block | **Allow `.30.5` (HA) only** | Block | Own VLAN | **Allow `:53`/`:67` only** | Block | Allow |

### Firewall Aliases (`<aliases>`)

| Alias Name | Used On | Included Subnets |
|---|---|---|
| `INTERNAL_NETWORKS` | `HOME (opt1)` | `192.168.99.0/24`, `192.168.20.0/24`, `192.168.30.0/24`, `192.168.40.0/24`, `192.168.10.0/26`, `192.168.50.0/24` |
| `LAB_BLOCKED_NETWORKS` | `LAB (opt2)` | `192.168.99.0/24`, `192.168.40.0/24`, `192.168.110.0/24`, `192.168.10.0/26`, `192.168.50.0/24` *(omits `.30.0/24` by design)* |
| `SERVERS_BLOCKED_NETWORKS` | `SERVERS (opt3)` | `192.168.99.0/24`, `192.168.110.0/24`, `192.168.20.0/24`, `192.168.40.0/24`, `192.168.10.0/26`, `192.168.50.0/24` |
| `GUEST_BLOCKED_NETWORKS` | `GUEST (opt4)` | `192.168.99.0/24`, `192.168.110.0/24`, `192.168.20.0/24`, `192.168.30.0/24`, `192.168.10.0/26`, `192.168.50.0/24` |
| `IoT_BLOCKED_NETWORKS` | `IoT (opt5)` | `192.168.99.0/24`, `192.168.110.0/24`, `192.168.20.0/24`, `192.168.30.0/24`, `192.168.40.0/24`, `192.168.10.0/26` |

---

## 7. Performance Benchmarking (E1000 vs. VirtIO)

Measured using the official **Ookla Speedtest CLI** (`Server: Launtel - Sydney, id: 61743`) from the wired Dell Workstation (`192.168.99.101` $\rightarrow$ Huawei Switch $\rightarrow$ Proxmox `vmbr0` $\rightarrow$ pfSense `vtnet1.99` $\rightarrow$ `vtnet0` $\rightarrow$ ISP Modem) while sampling 1-second `vmstat` CPU telemetry on pfSense:

| Configuration Stage | Virtual NIC | vCPU / RAM | Download Speed | Upload Speed | Packet Loss | pfSense Peak CPU |
|---|---|---|---:|---:|---:|---:|
| **ISP Modem Wi-Fi** *(Baseline)* | N/A | N/A | 539.00 Mbps | ~50.00 Mbps | 0.0% | N/A |
| **Stage 1 — Initial VM** | Intel E1000 (`em`) | 1 vCPU / 2 GB | 91.62 Mbps | ~45.00 Mbps | — | 100% |
| **Stage 2 — Resource Upgrade** | Intel E1000 (`em`) | 4 vCPU / 4 GB | 143.00 Mbps | 52.00 Mbps | — | 57% |
| **Stage 3 — VirtIO Migration** | **VirtIO (`vtnet`)** | **4 vCPU / 4 GB** | **538.08 Mbps** | **53.94 Mbps** | **0.0%** | **20%** *(80% idle)* |

- **Official Ookla Speedtest Result URL:** https://www.speedtest.net/result/c/35308725-f831-4f1a-a8be-147c626867a7

---

## 8. Complete Mistakes, Unexpected Behaviour & Corrections Log

| # | Who | What Happened | How It Was Found | Fix & Lesson |
|---:|---|---|---|---|
| **1** | AI Assistant | Claimed Huawei ports `9`–`12` were all copper combo ports. | Port 12 reported `Port Mode: COMMON FIBER` and rejected `combo-port copper`. | Only `9`–`10` are combo; `11`–`12` are SFP-only. Remapped trunks to copper ports `3`–`5` and wiped `10`–`12`. |
| **2** | AI Assistant | Suggested `stp edge-port enable` on Huawei switch. | Command rejected by Huawei VRP parser. | Correct syntax on this firmware is `stp edged-port enable` (with a `d`). |
| **3** | Me | Pasted commands at `<CORE-SW>` user-view prompt instead of `[CORE-SW]` system-view, including prompt text, and answered `n` to confirmations. | Wall of `Unrecognized command` errors; config unchanged. | Enter `system-view` first, verify the prompt, and paste commands only. |
| **4** | AI Assistant | Planned `VLAN 10 (HOME)` as `192.168.10.0/24` without checking live WAN addressing. | Modem LAN was `192.168.10.0/26` (pfSense WAN `.10.16/26`); pfSense forbids overlapping subnets. | Renumbered `VLAN 10` to `192.168.110.0/24` instead of touching the ISP modem. |
| **5** | AI Assistant | Claimed editing pfSense VM NICs before cutover would take home internet down. | Checked actual routing path: pfSense wasn't routing client traffic yet. | Verify the active default gateway before assuming a change is service-impacting. |
| **6** | Me | First Proxmox network edits did not save (no pending changes listed). | Checked screenshot before clicking Apply. | Always verify the pending diff in Proxmox UI before applying bridge changes. |
| **7** | AI Assistant | Assumed Ubiquiti's official `apt` repository works for Debian 12. | `Unable to locate package unifi`; `amd64` package index was `0 bytes`. | Bypassed repo and installed the downloaded `.deb` (`10.6.109`) directly. |
| **8** | AI Assistant | Assumed UniFi `10.6.109` needed Java 17 or Java 21. | `apt` reported an unmet dependency on **Java 25**. | Installed `temurin-25-jre` from Eclipse Adoptium + `mongodb-org-server` 7.0. |
| **9** | Me | Pinging pfSense (`192.168.99.1`) timed out right after cutover even though DHCP and Proxmox ping worked. | Inspected pfSense console: `LAN` had fallen back to DHCP (`.99.100`). | Reapplied static `192.168.99.1/24` on `LAN`. |
| **10** | Me | Worried I had disabled `pf` (`pfctl -d`) during testing. | Checked `pfctl -s info` (`Enabled`). | Never run `pfctl -d` to test rules; it disables NAT too. Use `pfctl -sr` and logs. |
| **11** | Me | Forgot root password of the new Debian 12 UniFi LXC container. | Console login failed. | Used `pct enter <ctid>` from the Proxmox host shell and ran `passwd`. |
| **12** | Me | Mistook the light-blue flat console cable for an Ethernet patch cable on Port 3. | Port 3 showed no link on `display interface brief`. | Swapped to a standard Cat6 patch cable. |
| **13** | Both | Transient DNS lookup failure when fetching the MongoDB GPG key. | `Could not resolve host` on first run. | Tested DNS against pfSense and `8.8.8.8`, retried, succeeded. |
| **14** | Me | UniFi AP port (Port 6) showed no link on first connection. | `display interface brief` showed Port 6 down. | Fixed physical PoE injector power/cabling; Port 6 came up and AP adopted. |
| **15** | Me | Unbound DNS Resolver refused to save interface settings. | WebGUI validation error. | Added `Localhost (lo0)` to Unbound's listening interfaces. |
| **16** | Me | `LAB_BLOCKED_NETWORKS` originally contained `192.168.20.0/24` (LAB itself) instead of `192.168.110.0/24` (HOME). | Caught during XML review. | Replaced `.20.0/24` with `.110.0/24` and added Modem LAN `.10.0/26` to all block aliases. |
| **17** | Me | Provisioned pfSense with Intel E1000 NICs on a 500 Mbps link. | Speeds capped at `92 Mbps` (1 vCPU) and `143 Mbps @ 57% CPU` (4 vCPU). | Migrated to VirtIO (`vtnet`), achieving `538.08 Mbps @ 20% CPU`. |
| **18** | Me | Pressed Enter at `Optional 1` during pfSense console interface reassignment (`revision 1794936514`). | Re-added GUI `OPT1`–`OPT5` interfaces were blank and missing IPs. | Pressing Enter at `Optional 1` deletes `<opt1>`–`<opt5>` from `<interfaces>`. Restored programmatically via [`recover_step1_interfaces.php`](./scripts/recover_step1_interfaces.php). |
| **19** | Me | Rule `1794928789` (`IOT - Block other internal networks`) was saved as `Pass` instead of `Block`, and `VLAN 50` was missing from the other 4 block aliases. | Caught by automated XML audit ([`pfsense_xml_auditor.py`](./scripts/pfsense_xml_auditor.py)). | Fixed via [`recover_step2_firewall_audit_fix.php`](./scripts/recover_step2_firewall_audit_fix.php) and verified in `pfctl -sr`. |

---

## 9. Verification & Validation Matrix

| Component / Check | State | How It Was Verified |
|---|---|---|
| **Huawei S5320 VLANs, Trunks & Access Ports** | **Verified** | `display vlan`, `display interface brief`, saved startup config |
| **Huawei S5320 SSH & ACL `2099` Hardening** | **Verified** | `display ssh server status`, Telnet/HTTP disabled, port `22` reachable from `.99.0/24` (`1.17 ms`) |
| **Proxmox VLAN-Aware `vmbr0` & `vmbr0.99`** | **Verified** | `ip -br addr show vmbr0.99`, Web UI reachable at `https://192.168.99.3:8006` (`0.23 ms`) |
| **pfSense Interfaces (`vtnet0` & `vtnet1.*`)** | **Verified** | All 6 VLANs (`10, 20, 30, 40, 50, 99`) UP; obsolete `em1.*` VLANs removed and destroyed |
| **WAN & Per-VLAN Outbound NAT** | **Verified** | `ping 192.168.10.1` (`0.90 ms`), `ping 1.1.1.1` (`10.30 ms`), all 6 subnets in `<tonatsubnets>` |
| **DHCP Server (`isc-dhcpd`) Across All VLANs** | **Verified** | Active `DHCPACK` leases on VLAN 99 (`.99.101`, `.99.102`), VLAN 10 (`.110.100`), VLAN 30 (`.30.4`, `.30.5`), VLAN 50 (`.50.100`) |
| **Unbound DNS Resolver (All 6 Gateways)** | **Verified** | `Resolve-DnsName google.com` against `.99.1`, `.110.1`, `.20.1`, `.30.1`, `.40.1`, `.50.1` $\rightarrow$ all returned `142.250.195.238` |
| **Firewall `(self)` & Inter-VLAN Isolation** | **Verified** | `pfctl -sr`, `pfctl -t <alias> -T show`, and PowerShell port `443` block test from non-mgmt VLAN ([screenshot](./screenshots/08-dns-and-firewall-isolation-test.png)) |
| **Active Directory (`dc01`) & Home Assistant** | **Verified** | `192.168.30.4:53` OPEN; Home Assistant `192.168.30.5:80`, `:4357` (`Connected / Supported / Healthy`), HomeKit `:21064` & `:21065` OPEN |
| **UniFi Controller, AP & SSID VLAN Mapping** | **Verified** | Controller `192.168.99.4:8443` OPEN; `ConnectMe` $\rightarrow$ VLAN 10 (`iPhone` `.110.100`); `Stark_Industries` $\rightarrow$ VLAN 50 (`lwip0` `.50.100`) |
| **500/50 Mbps Throughput via VirtIO** | **Verified** | Ookla Speedtest CLI: **538.08 Mbps down / 53.94 Mbps up (`0.0%` loss, `20%` peak CPU)** |

---

## 10. Design Rationale: Why I Chose What I Chose

- **Why a dedicated WAN VLAN (`VLAN 2`) on the switch?** Both the primary pfSense VM (on Port 4) and the planned standby pfSense appliance (on Port 5) need Layer 2 adjacency to the ISP modem (on Port 3) for CARP failover.
- **Why `192.168.110.0/24` for `HOME (VLAN 10)`?** The ISP modem uses `192.168.10.0/26`, and pfSense forbids overlapping subnets. Leaving the modem untouched and moving `VLAN 10` to `.110.0/24` eliminated cutover risk.
- **Why a single untagged trunk (`vtnet1`) into pfSense instead of 6 separate virtual NICs?** Tagging VLANs inside pfSense on one `vtnet1` trunk keeps the Proxmox VM configuration simple and allows adding new VLANs without hot-plugging virtual hardware.
- **Why Linux VLAN `vmbr0.99` for the Proxmox host?** It isolates Proxmox management traffic onto `VLAN 99` (`192.168.99.3`) while `vmbr0` itself remains an untagged VLAN-aware trunk for VMs and containers.
- **Why a Debian 12 LXC for the UniFi Controller?** It uses minimal RAM and snapshots in seconds. Even if the container stops, the UniFi AP continues forwarding traffic across tagged SSIDs.
- **Why leave the Cisco 2960 out?** Its ports are limited to `100 Mbps` Fast Ethernet with no PoE, and the Huawei S5320 has enough gigabit ports for all wired devices.

---

## 11. Engineering Lessons Learned

1. **Always use VirtIO (`vtnet`) for high-throughput Proxmox firewalls:** Switching from Intel E1000 (`em`) to VirtIO (`vtnet`) increased throughput from `143 Mbps @ 57% CPU` to **`538.08 Mbps @ 20% CPU`**.
2. **Check live addressing before finalizing a subnet plan** to avoid RFC1918 overlaps with upstream ISP equipment.
3. **Stage network cutovers with a fallback path** (dual-homing `vmbr0` and `vmbr0.99` before moving physical cables, and keeping serial console access ready).
4. **Never disable the packet filter (`pfctl -d`) to test a rule**, as doing so disables NAT and breaks internet across all VLANs.
5. **Know your switch's physical port media types** (`RJ45 copper` vs. `combo` vs. `SFP-only`).
6. **Beware the pfSense console `Assign Interfaces` OPT wipe:** Pressing Enter at `Optional 1` clears `<opt1>`–`<optN>` from `<interfaces>`, though `<dhcpd>`, `<filter>`, and `<unbound>` remain intact in `config.xml`.
7. **Always audit compiled `pfctl -sr` rules and alias tables**, not just GUI rule descriptions—automated XML auditing caught an IoT block rule that was accidentally set to `pass`.
8. **Update all existing VLAN block aliases whenever introducing a new VLAN** (such as `VLAN 50 IoT`).
9. **Official vendor documentation goes out of date:** Verify repository indexes and Java/MongoDB runtime dependencies directly (`apt-cache policy`, `apt install -s`).
10. **Plan for high availability (CARP) early** so switch trunks and WAN segments don't have to be re-cabled later.

---

## 12. Known Gaps & Future Roadmap

- [ ] **Remove Proxmox Snapshot (`Before_VirtIO_Migration`):** Delete the migration snapshot on VM 104 after a 48-hour stability burn-in.
- [ ] **Active Directory DNS Hand-off:** Configure `LAB (VLAN 20)` and `SERVERS (VLAN 30)` DHCP scopes to hand out `192.168.30.4` (`dc01`) as primary DNS, forwarding external queries to pfSense (`192.168.30.1`).
- [ ] **Guest Wi-Fi SSID (`VLAN 40`):** Broadcast the Guest SSID on the UniFi AP with client isolation enabled.
- [ ] **Switch NTP Synchronization:** Point the Huawei S5320 at pfSense (`192.168.99.1`) so its clock persists across power loss.
- [ ] **Standby pfSense Hardware Appliance (CARP):** Deploy the secondary x86 box on **Huawei Port 5** using `.253`/`.254` real interface IPs and `.1` shared CARP VIPs.
- [ ] **ISC DHCP $\rightarrow$ Kea Migration:** Transition pfSense DHCP backend from ISC DHCPd to Kea once CARP addressing is finalized.

---

## 13. Repository Structure & Sanitized Artifacts

```text
Segmented-HomeLab-Network/
├── README.md                                       # Complete end-to-end project documentation & build log
├── docs/
│   ├── 01-foundation-build-log.md                  # Deep-dive notes on Phases 1–10 (Switch, Proxmox, Cutover, UniFi LXC)
│   ├── 02-virtio-migration-and-recovery.md         # Deep-dive notes on Phase 12 (VirtIO migration, SSH/PHP recovery, benchmarks)
│   ├── 03-mistakes-and-lessons-learned.md          # Categorized log of all 23 human & AI mistakes and lessons
│   └── 04-troubleshooting-and-validation.md        # 10-point validation matrix & change log (CHG-001..017)
├── configs/
│   ├── pfsense-config-sanitized.xml                # Production pfSense 2.8.1 VirtIO config.xml (passwords/keys redacted)
│   ├── huawei-s5320-switch.cfg                     # Sanitized Huawei S5320-12TP-LI-AC switch configuration
│   ├── proxmox-network-and-vm104.conf              # Proxmox /etc/network/interfaces (vmbr0/vmbr0.99) & VM 104 config
│   └── unifi-lxc-install.sh                        # Reproducible Debian 12 LXC installer for UniFi 10.6.109 (MongoDB 7 + Java 25)
├── scripts/
│   ├── pfsense_xml_auditor.py                      # Standalone Python 3 pfSense config.xml dependency & security auditor
│   ├── recover_step1_interfaces.php                # Live pfSense PHP script to restore OPT1-OPT5 IPv4/descriptions & services
│   ├── recover_step2_firewall_audit_fix.php        # Live pfSense PHP script to fix IoT pass->block rule & block aliases
│   ├── cleanup_phase_c_obsolete_vlans.php          # Live pfSense PHP script to remove obsolete em1 VLANs & kernel interfaces
│   └── speedtest_multistream.py                    # Multi-stream Python HTTPS download/upload throughput benchmark
├── diagrams/
│   └── home_network_current_and_planned.svg        # Architecture diagram (active vs. planned links, ports, VLANs)
└── screenshots/
    └── README.md                                   # 8 annotated screenshots from Proxmox, pfSense, UniFi, Home Assistant & PowerShell
```

---

## 14. Appendix: Troubleshooting Commands That Helped

### Huawei S5320 Switch
- `display vlan` — shows which ports are tagged (`TG`) or untagged (`UT`) in each VLAN.
- `display interface brief` — shows physical link states (`up`, `down`, and `*down` for administratively shut).
- `display mac-address vlan 99` — shows which MAC address is learned on which switch port.
- `display interface GigabitEthernet0/0/12` — shows port media mode (`COMMON COPPER` vs. `COMMON FIBER`).
- `compare configuration` — checks whether unsaved running-config changes exist before power-off.

### Proxmox VE & Containers
- `ip -br addr show vmbr0.99` — confirms IPv4 address and UP state on the host management VLAN interface.
- `qm config 104` / `qm listsnapshot 104` — inspects VM 104 hardware and rollback snapshots.
- `pct list` / `pct enter <ctid>` — enters a container shell directly from the Proxmox host without needing its root password.

### pfSense CE (Read-Only Verification)
- `pfctl -s info | head -n 5` — confirms the packet filter is `Enabled`.
- `pfctl -sr | grep USER_RULE` — lists compiled user firewall rules in exact evaluation order.
- `pfctl -t INTERNAL_NETWORKS -T show` — displays exact CIDRs loaded into a firewall alias table.
- `ifconfig -g vlan` — lists all active kernel VLAN interfaces.
- `diff -u /cf/conf/backup/config-<ts>.xml /cf/conf/config.xml` — diffs a historical backup against live `config.xml`.

### Linux / Debian LXC
- `apt-cache policy <pkg>` & `apt install -s <pkg>` — simulates package installation and reveals dependency versions before committing.
- `getent hosts <name>` & `nslookup <name> <server>` — separates local resolver issues from upstream DNS server issues.
