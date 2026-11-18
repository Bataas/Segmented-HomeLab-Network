# Part 3: Complete Engineering Log of Mistakes, Unexpected Behaviors & Lessons Learned

Rather than hiding failed attempts, this log documents every mistake and unexpected behavior encountered across both the initial segmented network build and the subsequent VirtIO migration—whether made by me or by an AI assistant—and the engineering lesson learned from each.

---

## 1. Switch, Hardware & Physical Layer Mistakes

| # | Source | What Happened | How It Was Caught | Fix & Engineering Lesson |
|---|---|---|---|---|
| **1** | AI Assistant | Claimed Huawei S5320 ports `9`–`12` were all copper/fiber combo ports. | Port 12 reported `Port Mode: COMMON FIBER`, logged SFP warnings, and rejected `combo-port copper`. | **Know your switch panel:** On S5320-12TP-LI-AC, only ports `9`–`10` are combo; `11`–`12` are SFP-only. Remapped trunks to copper ports `3`–`5` and wiped `10`–`12`. |
| **2** | AI Assistant | Suggested `stp edge-port enable` for access ports. | Rejected by Huawei VRP CLI syntax parser. | Use `stp edged-port enable` (with a `d`) on Huawei VRP firmware. |
| **3** | Human | Pasted batch commands at `<CORE-SW>` user-view prompt instead of `[CORE-SW]` system-view, including prompt strings, and answered `n` to `clear configuration` prompts. | Wall of `Unrecognized command` errors and unchanged port config. | **Prompt discipline:** Always enter `system-view` first, verify the `[CORE-SW]` prompt, and paste pure commands without prompt prefixes. |
| **4** | Human | Requested a 4096-bit local RSA key on the Huawei switch. | Switch refused 4096 bits and fell back to 2048 bits. | Check hardware crypto limits on older switch firmware; 2048-bit RSA is the ceiling on this model. |
| **5** | Human | Switch clock reset to year `2000` after moving power cables. | Checked `display clock` after physical relocation. | The S5320 has no battery-backed RTC; always configure `clock timezone` and point NTP at pfSense (`192.168.99.1`). |
| **6** | Human | Plugged the light-blue flat console rollover cable into Huawei Port 3 instead of a standard Ethernet patch cable for the modem link. | `display interface brief` showed Port 3 physically down. | Replaced with a standard Cat6 patch cable; Port 3 (`VLAN 2`) came up immediately. |
| **7** | Human | UniFi AP on Huawei Port 6 showed no link on first power-up. | `display interface brief` showed Port 6 down. | Always verify PoE injector mains power and LAN vs. PoE port orientation before debugging trunk VLAN tags. |

---

## 2. IP Addressing, Proxmox & Cutover Mistakes

| # | Source | What Happened | How It Was Caught | Fix & Engineering Lesson |
|---|---|---|---|---|
| **8** | AI Assistant | Planned `VLAN 10 (HOME)` as `192.168.10.0/24` without checking the upstream modem's live subnet. | Inspected live pfSense WAN lease (`192.168.10.16/26` on modem subnet `192.168.10.0/26`). pfSense forbids overlapping subnets across interfaces. | **Inspect live addressing before finalizing a subnet plan.** Renumbered `VLAN 10` to `192.168.110.0/24` instead of touching the ISP modem. |
| **9** | AI Assistant | Warned that editing pfSense VM NICs during pre-cutover prep would take home internet down. | Verified actual packet path: pfSense wasn't routing client traffic yet (clients were still on the modem). | Trace the active default gateway before assuming a VM change is service-impacting. |
| **10** | Human | First attempt at staging Proxmox `vmbr0` / `vmbr0.99` edits in the Web UI did not save. | Reviewed the Proxmox pending changes pane before clicking Apply—no diff was listed. | Always verify the pending diff in Proxmox `/etc/network/interfaces.new` before applying bridge changes. |
| **11** | Human | After cutover, DHCP on `VLAN 99` worked and Proxmox (`192.168.99.3`) responded to ping, but pinging pfSense (`192.168.99.1`) timed out. | Checked pfSense console: `LAN` (`em1.99`) had reverted to DHCP (`192.168.99.100`) instead of static `192.168.99.1`. | Re-applied static `192.168.99.1/24` on `LAN`. Layer 2 working does not guarantee Layer 3 static addressing persisted. |
| **12** | Human | Admin PC stayed connected to ISP modem Wi-Fi (`192.168.10.36`) while plugged into Management Ethernet (`192.168.99.101`). | Dual default gateways (`192.168.99.1` and `192.168.10.1`) caused asymmetric routing ambiguity during testing. | Disable Wi-Fi on the management workstation when wired into `VLAN 99`. |

---

## 3. Services, Containers & Firewall Policy Mistakes

| # | Source | What Happened | How It Was Caught | Fix & Engineering Lesson |
|---|---|---|---|---|
| **13** | Human | Unbound DNS Resolver refused to save its interface bindings in pfSense. | WebGUI validation error when selecting only VLAN interfaces. | Always include **Localhost (`lo0`)** in Unbound's active interfaces so the firewall itself can resolve via `127.0.0.1`. |
| **14** | AI Assistant | Assumed Ubiquiti's official Debian `apt` repository works for installing the UniFi controller. | `apt install unifi` failed; the `amd64` `Packages` index in Ubiquiti's repo was `0 bytes`. | Official vendor install docs go stale. Download the `.deb` release directly and inspect dependencies with `apt install -s`. |
| **15** | AI Assistant | Assumed UniFi Network Server `10.6.109` needed Java 17 or Java 21. | `dpkg`/`apt` reported an unmet dependency on **Java 25**. | UniFi `10.6.x` requires Java 25 (`temurin-25-jre` via Eclipse Adoptium) plus `mongodb-org-server` 7.0. |
| **16** | Human | Forgot the root password of the newly created Debian 12 LXC container. | Console login failed inside Proxmox. | No rebuild needed: run `pct enter <ctid>` from the Proxmox host shell and run `passwd`. |
| **17** | Human | Feared `pfctl -d` had been run in the pfSense shell (which disables both firewalling and NAT). | Checked `pfctl -s info`, which confirmed `Status: Enabled`. | Never run `pfctl -d` to test connectivity; use `pfctl -sr`, firewall logs, and targeted client tests instead. |
| **18** | Human | `LAB_BLOCKED_NETWORKS` alias originally included `192.168.20.0/24` (LAB itself) instead of `192.168.110.0/24` (HOME). | Discovered during XML alias review (`config-pfSense.home.arpa-20261117134307.xml`). | Replaced `192.168.20.0/24` with `192.168.110.0/24` and added `192.168.10.0/26` (Modem LAN) to all user VLAN block aliases. |
| **19** | Human | Rule `1794928789` on `opt5` (`IOT - Block other internal networks`) was accidentally created with Action = **`Pass`** instead of **`Block`**, and `192.168.50.0/24` (`IoT`) was omitted from the other 4 VLAN block aliases. | Caught automatically during the Phase A XML security audit ([`pfsense_xml_auditor.py`](../scripts/pfsense_xml_auditor.py)). | Fixed programmatically via [`recover_step2_firewall_audit_fix.php`](../scripts/recover_step2_firewall_audit_fix.php) and verified in `pfctl -sr`. Always audit compiled `pfctl -sr` rules, not just rule descriptions! |

---

## 4. VirtIO Migration & Console Reassignment Mistakes

| # | Source | What Happened | How It Was Caught | Fix & Engineering Lesson |
|---|---|---|---|---|
| **20** | Human | Provisioned pfSense with `Intel E1000` virtual NICs (`em0`/`em1`) on a 500 Mbps connection. | Throughput capped at `92 Mbps` (1 vCPU) and `143 Mbps @ 57% CPU` (4 vCPUs). | Always use paravirtualized **VirtIO (`vtnet`)** NICs for pfSense on Proxmox KVM; VirtIO immediately unlocked **538.08 Mbps at 20% CPU**. |
| **21** | Human | Changed Proxmox NICs from E1000 to VirtIO while VLANs were still bound to `em1`. | On boot, pfSense forced console interface assignment because `em0`/`em1` no longer existed. | Either update `<if>` parent names in `config.xml` before rebooting or reassign all `OPT` interfaces during the console prompt. |
| **22** | Human | Pressed **Enter** (`nothing if finished`) at the `Enter the Optional 1 interface name` prompt during console interface assignment (`revision 1794936514`). | Re-adding `OPT1`–`OPT5` in the WebGUI resulted in blank, disabled interfaces with no IPv4 addresses. | Pressing Enter at `Optional 1` in pfSense's console assignment deletes `<opt1>`–`<opt5>` from `<interfaces>` (though `<dhcpd>`, `<filter>`, and `<unbound>` remain intact in `config.xml` and `/cf/conf/backup/`). |
| **23** | Human | Both old `em1.*` and new `vtnet1.*` VLAN definitions coexisted in `Interfaces -> VLANs`, leaving 6 dummy `em1.*` interfaces with `ether 00:00:00:00:00:00` in the kernel. | Inspected `ifconfig -a` and `<vlans>` in `config.xml`. | After restoring and validating `vtnet1.*` interfaces, remove obsolete `em1.*` entries from `<vlans>` and run `ifconfig em1.X destroy`. |
