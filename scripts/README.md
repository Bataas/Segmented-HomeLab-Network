# Automation, Auditing & Recovery Scripts

This directory contains the Python and pfSense PHP automation scripts used to audit, recover, clean up, and benchmark the pfSense VirtIO migration.

## Script Inventory

| Script | Language | Purpose |
|---|---|---|
| [`pfsense_xml_auditor.py`](./pfsense_xml_auditor.py) | Python 3 | Standalone CLI utility that parses one or two pfSense `config.xml` exports, audits interface/VLAN parent mappings, detects orphaned VLAN definitions, checks for unconfigured OPT interfaces referenced by DHCP/Unbound/firewall rules, and flags security bugs (such as `pass` rules with `"Block"` in their description or missing internal subnets in block aliases). |
| [`recover_step1_interfaces.php`](./recover_step1_interfaces.php) | PHP (pfSense API) | Uses pfSense's native `/etc/inc/config.inc`, `interfaces.inc`, `services.inc`, `unbound.inc`, and `filter.inc` subsystems to programmatically restore `OPT1`–`OPT5` IPv4 gateways, subnets, descriptions, and `vtnet1` VLAN descriptions without dropping the active management SSH session on `vtnet1.99`. |
| [`recover_step2_firewall_audit_fix.php`](./recover_step2_firewall_audit_fix.php) | PHP (pfSense API) | Fixes rule tracker `1794928789` (`IOT - Block other internal networks`) from `pass` to `block`, appends `192.168.50.0/24` (`IoT`) to `INTERNAL_NETWORKS`, `LAB_BLOCKED_NETWORKS`, `SERVERS_BLOCKED_NETWORKS`, and `GUEST_BLOCKED_NETWORKS`, and reloads `pf`. |
| [`cleanup_phase_c_obsolete_vlans.php`](./cleanup_phase_c_obsolete_vlans.php) | PHP (pfSense API) | Safely removes the 6 obsolete `em1.*` VLAN definitions from `config.xml` and destroys the orphaned FreeBSD kernel VLAN interfaces after dependency verification. |
| [`speedtest_multistream.py`](./speedtest_multistream.py) | Python 3 | 8-stream parallel HTTPS download/upload throughput benchmark utility. |

## Usage Examples

### 1. Audit a pfSense `config.xml` Export
```bash
python scripts/pfsense_xml_auditor.py configs/pfsense-config-sanitized.xml
```

### 2. Compare Pre-Migration vs. Post-Migration `config.xml` Exports
```bash
python scripts/pfsense_xml_auditor.py --compare before-virtio.xml after-virtio.xml
```

### 3. Execute Live Recovery Step on pfSense via SSH
```bash
scp scripts/recover_step1_interfaces.php root@192.168.99.1:/tmp/
ssh root@192.168.99.1 "cp /cf/conf/config.xml /cf/conf/backup/pre-recovery.xml && php -f /tmp/recover_step1_interfaces.php"
```
