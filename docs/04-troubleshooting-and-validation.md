# Part 4: Validation Matrix, Change Log & Troubleshooting Cheat Sheet

---

## 1. Post-Recovery Validation Matrix

All 10 validation categories were executed and verified against the live environment on **2026-11-18**:

| # | Test Category | Target / Scope | Verification Command / Method | Result | Status |
|---|---|---|---|---|---|
| **1** | **WAN Connectivity** | `vtnet0` (`192.168.10.16/26` $\rightarrow$ `192.168.10.1`) | `ping -c 2 192.168.10.1` & `ping -c 2 1.1.1.1` from pfSense | `0.90 ms` to modem, `10.30 ms` to `1.1.1.1` (`0.0%` loss) | **PASS** |
| **2** | **Outbound NAT & Internet** | All 6 VLANs (`10, 20, 30, 40, 50, 99`) | `pfctl -sn` & `pfctl -t tonatsubnets -T show` + active state check (`pfctl -ss`) | All 6 `/24` subnets present in `<tonatsubnets>`; active `ESTABLISHED` NAT states confirmed | **PASS** |
| **3** | **DHCP Server (`isc-dhcpd`)** | `lan`, `opt1`, `opt2`, `opt3`, `opt4`, `opt5` | `/var/log/dhcpd.log` & `/var/dhcpd/var/db/dhcpd.leases` | Active `DHCPACK` leases verified on VLAN 99 (`.99.101`, `.99.102`), VLAN 10 (`.110.100`), VLAN 30 (`.30.4`, `.30.5`), VLAN 50 (`.50.100`) | **PASS** |
| **4** | **Unbound DNS Resolver** | All 6 VLAN gateway IPs (`:53` TCP/UDP) | `Resolve-DnsName google.com -Server <gw_ip>` across `.99.1`, `.110.1`, `.20.1`, `.30.1`, `.40.1`, `.50.1` | All 6 VLAN gateways resolved `142.250.195.238` in `<5 ms` | **PASS** |
| **5** | **Inter-VLAN Isolation & `(self)` Protection** | `opt1`–`opt5` firewall rules & aliases | `pfctl -sr` & `pfctl -t <alias> -T show` + PowerShell `Test-NetConnection -Port 443` ([screenshot](../screenshots/08-dns-and-firewall-isolation-test.png)) | `(self)` blocks WebGUI/SSH from non-mgmt VLANs; `<*_BLOCKED_NETWORKS>` blocks unauthorized cross-VLAN traffic | **PASS** |
| **6** | **Proxmox Management** | `192.168.99.3:8006` (`vmbr0.99`) | `ping 192.168.99.3` & TCP connect `:8006` | `0.23 ms` RTT (`0%` loss); HTTPS port `8006` open | **PASS** |
| **7** | **Huawei Switch Management** | `192.168.99.2:22` (`Vlanif99`) | `ping 192.168.99.2` & TCP connect `:22` | `1.17 ms` RTT (`0%` loss); SSH port `22` open (restricted to `192.168.99.0/24` via ACL `2099`) | **PASS** |
| **8** | **Home Assistant & Active Directory (`SERVERS`)** | `192.168.30.5` (`homeassistant`) & `192.168.30.4` (`dc01`) | TCP port check + HTTP health check on `192.168.30.5:4357` | `dc01:53` open; Home Assistant `:80`, `:4357` (`Supervisor: Connected / Supported / Healthy`), HomeKit `:21064` & `:21065` open | **PASS** |
| **9** | **IoT Device Connectivity** | VLAN 50 (`192.168.50.0/24` on `vtnet1.50`) | `arp -an` & `pfctl -ss \| grep 192.168.50.` | `192.168.50.100` (`lwip0`) leased & maintaining `ESTABLISHED` TLS `:8883` cloud connection | **PASS** |
| **10** | **UniFi SSID-to-VLAN Mapping** | Controller `192.168.99.4:8443` & AP `192.168.99.102` | Verified client leases on `ConnectMe` (VLAN 10) and `Stark_Industries` (VLAN 50) | `iPhone` leased `192.168.110.100` on `vtnet1.10`; `lwip0` leased `192.168.50.100` on `vtnet1.50` | **PASS** |

---

## 2. Complete Configuration Change Log

| Change ID | Phase | Description | Status |
|---|---|---|---|
| **CHG-001** | Foundation | Configured Huawei S5320 VLANs (`2, 10, 20, 30, 40, 50, 99`), access/trunk ports, `Vlanif99`, and ACL `2099` SSH hardening | Completed |
| **CHG-002** | Foundation | Renumbered `VLAN 10 (HOME)` from `192.168.10.0/24` to `192.168.110.0/24` to avoid overlap with ISP modem (`192.168.10.0/26`) | Completed |
| **CHG-003** | Foundation | Enabled VLAN-aware `vmbr0` and created `vmbr0.99` (`192.168.99.3/24`) on Proxmox VE host | Completed |
| **CHG-004** | Foundation | Deployed UniFi Network Server `10.6.109` in Debian 12 LXC (`192.168.99.4`) with MongoDB 7.0 & Temurin Java 25 | Completed |
| **CHG-005** | Foundation | Adopted UniFi UAP-AC-Pro (`192.168.99.102`) on Port 6 trunk and mapped SSIDs `ConnectMe` (VLAN 10) & `Stark_Industries` (VLAN 50) | Completed |
| **CHG-006** | Expansion | Added DHCP static reservations on `VLAN 30 (SERVERS)` for `dc01` (`192.168.30.4`) and `homeassistant` (`192.168.30.5`) | Completed |
| **CHG-007** | Hardening | Added `Block access to pfSense (self)` rules on `opt1`–`opt5` and added `192.168.10.0/26` (Modem LAN) to all block aliases | Completed |
| **CHG-008** | Performance | Upgraded pfSense VM 104 from `1 vCPU / 2 GB RAM` to `4 vCPU (host) / 4 GB RAM` (throughput rose from `92 Mbps` to `143 Mbps`) | Completed |
| **CHG-009** | Migration | Created Proxmox snapshot `Before_VirtIO_Migration` on VM 104 | Completed |
| **CHG-010** | Migration | Migrated VM 104 `net0` (WAN) and `net1` (LAN trunk) from `Intel E1000` (`em0`/`em1`) to `VirtIO` (`vtnet0`/`vtnet1`) | Completed |
| **CHG-011** | Migration | Created VLANs `99, 10, 20, 30, 40, 50` on `vtnet1` and restored management access on `vtnet1.99` (`192.168.99.1/24`) | Completed |
| **CHG-012** | AI Recovery | Backed up `/cf/conf/config.xml` and diffed against `/cf/conf/backup/config-1794935923.xml` over SSH | Completed |
| **CHG-013** | AI Recovery | Executed [`recover_step1_interfaces.php`](../scripts/recover_step1_interfaces.php) to restore `OPT1`–`OPT5` IPv4 gateways, descriptions, DHCP, Unbound, and `pf` | Completed |
| **CHG-014** | AI Recovery | Executed [`recover_step2_firewall_audit_fix.php`](../scripts/recover_step2_firewall_audit_fix.php) to fix rule `1794928789` (`pass` $\rightarrow$ `block`) and add `192.168.50.0/24` to block aliases | Completed |
| **CHG-015** | Cleanup | Executed [`cleanup_phase_c_obsolete_vlans.php`](../scripts/cleanup_phase_c_obsolete_vlans.php) to remove obsolete `em1.*` VLANs from `config.xml` and kernel | Completed |
| **CHG-016** | Validation | Verified WAN, NAT, DHCP, Unbound DNS, inter-VLAN isolation, Home Assistant, DC01, and UniFi SSIDs across all 6 VLANs | Completed |
| **CHG-017** | Benchmark | Verified **538.08 Mbps download / 53.94 Mbps upload (`0.0%` loss) at `20%` peak CPU** via Ookla Speedtest CLI | Completed |

---

## 3. Reusable Troubleshooting Commands Cheat Sheet

### Huawei S5320 Switch (VRP CLI)
```text
display vlan                                  # Show VLAN IDs and tagged (TG) vs untagged (UT) member ports
display interface brief                       # Show physical link status (up, down, *down = admin shut)
display mac-address vlan 99                   # Verify which port learned a specific MAC address on VLAN 99
display interface GigabitEthernet0/0/12       # Check physical media mode (COMMON COPPER vs COMMON FIBER)
display ssh server status                     # Verify Stelnet (SSH) server settings and version
compare configuration                         # Check if running-config differs from saved startup config
```

### Proxmox VE Host & LXC Containers
```bash
qm config 104                                 # Inspect VM 104 hardware and NIC bridge/VLAN settings
qm listsnapshot 104                           # List available rollback snapshots for VM 104
ip -br addr show vmbr0.99                     # Verify Proxmox host management IP on VLAN 99
pct list                                      # List LXC containers (e.g., UniFi controller)
pct enter <ctid>                              # Enter LXC container root shell directly without password
```

### pfSense CE (SSH / Shell)
```bash
ifconfig -g vlan                              # List all active kernel VLAN interfaces
pfctl -s info | head -n 5                     # Confirm packet filter is Enabled and check state count
pfctl -sr | grep USER_RULE                    # Inspect compiled user firewall rules in evaluation order
pfctl -t INTERNAL_NETWORKS -T show            # Inspect exact CIDRs loaded into a firewall alias table
pfctl -sn                                     # Inspect compiled outbound NAT and port-forward rules
sockstat -4 -l | grep -E 'unbound|dhcpd'      # Confirm Unbound (:53) and ISC DHCPd (:67) bindings
ls -ltr /cf/conf/backup/                      # List automatic timestamped config.xml backups
diff -u /cf/conf/backup/config-<ts>.xml /cf/conf/config.xml  # Diff a backup against live config.xml
vmstat 1 20                                   # Sample per-second interrupt rate, context switches, and CPU load
```
