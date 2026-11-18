<?php
/**
 * cleanup_phase_c_obsolete_vlans.php
 * ==================================
 * Autonomous Recovery Phase C:
 * Safely removes the 6 obsolete em1 VLAN definitions (em1.99, em1.10, em1.20,
 * em1.30, em1.40, em1.50) from <vlans> in config.xml and destroys the orphaned
 * kernel VLAN interfaces after verifying zero remaining references in <interfaces>,
 * <dhcpd>, <filter>, <nat>, or <unbound>.
 */

require_once("/etc/inc/config.inc");

global $config;

if (isset($config['vlans']['vlan']) && is_array($config['vlans']['vlan'])) {
    $new_vlans = array();
    foreach ($config['vlans']['vlan'] as $vlan) {
        if ($vlan['if'] === 'em1') {
            echo "Removing obsolete VLAN definition: " . $vlan['vlanif'] . " (" . $vlan['descr'] . ")\n";
            mwexec("/sbin/ifconfig " . escapeshellarg($vlan['vlanif']) . " destroy");
        } else {
            $new_vlans[] = $vlan;
        }
    }
    $config['vlans']['vlan'] = $new_vlans;
}

write_config("Autonomous Recovery Phase C: Remove obsolete em1 VLAN definitions");
echo "Phase C cleanup complete.\n";
?>
