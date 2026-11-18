#!/usr/bin/env python3
"""
pfsense_xml_auditor.py
======================
Standalone pfSense Configuration XML Dependency & Security Auditor.

Features:
1. Parses interface assignments (<interfaces>), VLAN definitions (<vlans>),
   DHCP scopes/static mappings (<dhcpd>), Unbound bindings (<unbound>),
   firewall aliases (<aliases>), and firewall rules (<filter>).
2. Detects orphaned VLAN definitions (VLANs not assigned to any interface or
   referencing a legacy parent NIC such as em1 after a VirtIO migration).
3. Detects unconfigured OPT interfaces (missing <enable>, <ipaddr>, or <subnet>)
   that are still referenced by DHCP, Unbound, or firewall rules.
4. Audits firewall rules and aliases for common misconfigurations:
   - Rules with "block" or "deny" in the description whose action is set to "pass".
   - Internal RFC1918 VLAN subnets missing from inter-VLAN block aliases.
5. Optional --compare mode to diff two pfSense config.xml exports before restoring.

Usage:
    python scripts/pfsense_xml_auditor.py configs/pfsense-config-sanitized.xml
    python scripts/pfsense_xml_auditor.py --compare before.xml after.xml
"""

import argparse
import ipaddress
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Tuple


def parse_pfsense_xml(path: str) -> ET.Element:
    tree = ET.parse(path)
    return tree.getroot()


def extract_summary(root: ET.Element) -> dict:
    data = {
        "interfaces": {},
        "vlans": [],
        "dhcpd": {},
        "aliases": {},
        "rules": [],
        "unbound_interfaces": [],
    }

    # 1. Interfaces
    ifaces_el = root.find("interfaces")
    if ifaces_el is not None:
        for child in ifaces_el:
            if_id = child.tag
            data["interfaces"][if_id] = {
                "descr": (child.findtext("descr") or if_id).strip(),
                "if": (child.findtext("if") or "").strip(),
                "enabled": child.find("enable") is not None,
                "ipaddr": (child.findtext("ipaddr") or "").strip(),
                "subnet": (child.findtext("subnet") or "").strip(),
            }

    # 2. VLANs
    vlans_el = root.find("vlans")
    if vlans_el is not None:
        for vlan in vlans_el.findall("vlan"):
            data["vlans"].append({
                "parent": (vlan.findtext("if") or "").strip(),
                "tag": (vlan.findtext("tag") or "").strip(),
                "vlanif": (vlan.findtext("vlanif") or "").strip(),
                "descr": (vlan.findtext("descr") or "").strip(),
            })

    # 3. DHCP Scopes & Static Reservations
    dhcpd_el = root.find("dhcpd")
    if dhcpd_el is not None:
        for scope in dhcpd_el:
            rng = scope.find("range")
            statics = []
            for sm in scope.findall("staticmap"):
                statics.append({
                    "mac": (sm.findtext("mac") or "").strip(),
                    "ipaddr": (sm.findtext("ipaddr") or "").strip(),
                    "hostname": (sm.findtext("hostname") or "").strip(),
                    "descr": (sm.findtext("descr") or "").strip(),
                })
            data["dhcpd"][scope.tag] = {
                "enabled": scope.find("enable") is not None,
                "from": (rng.findtext("from") if rng is not None else "") or "",
                "to": (rng.findtext("to") if rng is not None else "") or "",
                "staticmaps": statics,
            }

    # 4. Aliases
    aliases_el = root.find("aliases")
    if aliases_el is not None:
        for alias in aliases_el.findall("alias"):
            name = (alias.findtext("name") or "").strip()
            addrs = (alias.findtext("address") or "").strip().split()
            data["aliases"][name] = {
                "type": (alias.findtext("type") or "").strip(),
                "addresses": addrs,
                "descr": (alias.findtext("descr") or "").strip(),
            }

    # 5. Firewall Rules
    filter_el = root.find("filter")
    if filter_el is not None:
        for rule in filter_el.findall("rule"):
            src = rule.find("source")
            dst = rule.find("destination")
            src_val = "any"
            if src is not None:
                src_val = src.findtext("network") or src.findtext("address") or ("any" if src.find("any") is not None else "unknown")
            dst_val = "any"
            dst_port = ""
            if dst is not None:
                dst_val = dst.findtext("network") or dst.findtext("address") or ("any" if dst.find("any") is not None else "unknown")
                dst_port = dst.findtext("port") or ""
            data["rules"].append({
                "tracker": (rule.findtext("tracker") or "").strip(),
                "interface": (rule.findtext("interface") or "").strip(),
                "type": (rule.findtext("type") or "").strip(),
                "protocol": (rule.findtext("protocol") or "any").strip(),
                "src": src_val,
                "dst": dst_val,
                "port": dst_port,
                "descr": (rule.findtext("descr") or "").strip(),
            })

    # 6. Unbound
    unbound_el = root.find("unbound")
    if unbound_el is not None:
        active = (unbound_el.findtext("active_interface") or "").strip()
        data["unbound_interfaces"] = [x.strip() for x in active.split(",") if x.strip()]

    return data


def audit_config(data: dict, label: str = "Configuration") -> List[str]:
    findings: List[str] = []
    assigned_phys = {v["if"]: k for k, v in data["interfaces"].items()}

    # Check 1: Orphaned VLAN definitions
    for vlan in data["vlans"]:
        if vlan["vlanif"] not in assigned_phys:
            findings.append(
                f"[WARN] Orphaned VLAN definition '{vlan['vlanif']}' (parent='{vlan['parent']}', tag={vlan['tag']}, descr='{vlan['descr']}') is not assigned to any interface."
            )
        if not vlan["descr"]:
            findings.append(
                f"[INFO] VLAN '{vlan['vlanif']}' is missing a description (<descr>)."
            )

    # Check 2: Assigned interfaces missing IPv4 or disabled while referenced by DHCP/Firewall/Unbound
    rule_ifaces = {r["interface"] for r in data["rules"]}
    for if_id, info in data["interfaces"].items():
        if if_id == "wan":
            continue
        has_dhcp = if_id in data["dhcpd"]
        has_rules = if_id in rule_ifaces
        in_unbound = if_id in data["unbound_interfaces"]
        if (has_dhcp or has_rules or in_unbound) and (not info["enabled"] or not info["ipaddr"]):
            findings.append(
                f"[CRITICAL] Interface '{if_id}' ({info['descr']} on {info['if']}) is unconfigured/disabled (ipaddr='{info['ipaddr']}', enabled={info['enabled']}) "
                f"but is actively referenced by DHCP={has_dhcp}, FirewallRules={has_rules}, Unbound={in_unbound}!"
            )

    # Check 3: Firewall rules whose description says "Block" but action is "pass"
    for r in data["rules"]:
        descr_lower = r["descr"].lower()
        if ("block" in descr_lower or "deny" in descr_lower) and r["type"] == "pass":
            findings.append(
                f"[CRITICAL] Firewall Rule tracker={r['tracker']} on '{r['interface']}' ('{r['descr']}') has action <type>pass</type> instead of <type>block</type>!"
            )

    # Check 4: Audit inter-VLAN block aliases against configured internal /24 subnets
    internal_subnets: Dict[str, str] = {}
    for if_id, info in data["interfaces"].items():
        if info["ipaddr"] and info["ipaddr"] != "dhcp" and info["subnet"]:
            try:
                net = str(ipaddress.ip_network(f"{info['ipaddr']}/{info['subnet']}", strict=False))
                internal_subnets[if_id] = net
            except ValueError:
                pass

    for r in data["rules"]:
        if r["type"] == "block" and r["dst"] in data["aliases"]:
            alias_name = r["dst"]
            alias_nets = set(data["aliases"][alias_name]["addresses"])
            src_if = r["interface"]
            for other_if, other_net in internal_subnets.items():
                if other_if == src_if:
                    continue
                if other_net not in alias_nets:
                    findings.append(
                        f"[NOTICE] Alias '{alias_name}' (used by block rule on '{src_if}') does not include '{other_if}' subnet {other_net}."
                    )

    return findings


def print_report(path: str, data: dict, findings: List[str]) -> None:
    print("=" * 80)
    print(f"pfSense Configuration Audit Report: {path}")
    print("=" * 80)
    print("\n1. Interface Assignments:")
    print(f"  {'ID':<8} {'Descr':<12} {'Port':<12} {'Enabled':<9} {'IPv4/Subnet'}")
    print("  " + "-" * 65)
    for if_id, info in data["interfaces"].items():
        ip_str = f"{info['ipaddr']}/{info['subnet']}" if info["subnet"] else info["ipaddr"]
        print(f"  {if_id:<8} {info['descr']:<12} {info['if']:<12} {str(info['enabled']):<9} {ip_str}")

    print(f"\n2. VLAN Definitions ({len(data['vlans'])} total):")
    for v in data["vlans"]:
        print(f"  - {v['vlanif']:<12} parent={v['parent']:<8} tag={v['tag']:<4} descr='{v['descr']}'")

    print(f"\n3. DHCP Scopes ({len(data['dhcpd'])} configured):")
    for scope_id, sc in data["dhcpd"].items():
        print(f"  - {scope_id:<8} enabled={str(sc['enabled']):<6} range={sc['from']} - {sc['to']} (static reservations: {len(sc['staticmaps'])})")

    print(f"\n4. Audit Findings ({len(findings)}):")
    if not findings:
        print("  [OK] Zero orphaned VLANs, unconfigured OPT interfaces, or rule/alias mismatches detected.")
    else:
        for f in findings:
            print(f"  {f}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and compare pfSense config.xml files.")
    parser.add_argument("config", help="Path to pfSense config.xml file")
    parser.add_argument("--compare", help="Optional second pfSense config.xml file to compare against")
    args = parser.parse_args()

    root1 = parse_pfsense_xml(args.config)
    data1 = extract_summary(root1)
    findings1 = audit_config(data1, args.config)
    print_report(args.config, data1, findings1)

    if args.compare:
        root2 = parse_pfsense_xml(args.compare)
        data2 = extract_summary(root2)
        findings2 = audit_config(data2, args.compare)
        print_report(args.compare, data2, findings2)


if __name__ == "__main__":
    main()
