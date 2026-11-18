<?php
/**
 * recover_step2_firewall_audit_fix.php
 * ====================================
 * Autonomous Recovery Step 2:
 * 1. Fixes firewall rule tracker 1794928789 ("IOT - Block other internal networks")
 *    on opt5 (VLAN 50), which was misconfigured with <type>pass</type> instead of <type>block</type>.
 * 2. Appends 192.168.50.0/24 (IoT VLAN 50) to INTERNAL_NETWORKS, LAB_BLOCKED_NETWORKS,
 *    SERVERS_BLOCKED_NETWORKS, and GUEST_BLOCKED_NETWORKS so inter-VLAN isolation
 *    covers VLAN 50 while preserving explicit Home Assistant (192.168.30.5) pass rules.
 */

require_once("/etc/inc/config.inc");
require_once("/etc/inc/filter.inc");

global $config;

if (isset($config['filter']['rule']) && is_array($config['filter']['rule'])) {
    foreach ($config['filter']['rule'] as &$rule) {
        if (isset($rule['tracker']) && $rule['tracker'] == '1794928789') {
            $rule['type'] = 'block';
            echo "Fixed rule 1794928789 (" . $rule['descr'] . ") -> type=block\n";
        }
    }
    unset($rule);
}

$target_aliases = array(
    'INTERNAL_NETWORKS' => 'IoT',
    'LAB_BLOCKED_NETWORKS' => 'IoT',
    'SERVERS_BLOCKED_NETWORKS' => 'IoT',
    'GUEST_BLOCKED_NETWORKS' => 'IoT'
);

if (isset($config['aliases']['alias']) && is_array($config['aliases']['alias'])) {
    foreach ($config['aliases']['alias'] as &$alias) {
        if (isset($target_aliases[$alias['name']])) {
            $addrs = preg_split('/\s+/', trim($alias['address']));
            if (!in_array('192.168.50.0/24', $addrs)) {
                $addrs[] = '192.168.50.0/24';
                $alias['address'] = implode(' ', $addrs);
                $alias['detail'] = rtrim($alias['detail'], '|') . '||' . $target_aliases[$alias['name']];
                echo "Added 192.168.50.0/24 to alias " . $alias['name'] . "\n";
            }
        }
    }
    unset($alias);
}

write_config("Autonomous Recovery Step 2: Fix IoT block rule (pass->block) and add VLAN 50 to inter-VLAN block aliases");
filter_configure();
echo "Step 2 complete.\n";
?>
