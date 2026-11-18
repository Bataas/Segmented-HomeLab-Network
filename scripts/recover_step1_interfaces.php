<?php
/**
 * recover_step1_interfaces.php
 * ============================
 * Autonomous Recovery Step 1:
 * Restores OPT1-OPT5 interface IPv4 addresses, subnets, descriptions, and enable
 * flags on vtnet1.10 through vtnet1.50 after pfSense's console interface assignment
 * cleared <opt1>-<opt5> from <interfaces>. Also populates VLAN descriptions on
 * the vtnet1 VLAN entries and reloads interfaces, ISC DHCPd, Unbound DNS, and pf
 * without disrupting the active management SSH session on LAN (vtnet1.99).
 */

require_once("/etc/inc/config.inc");
require_once("/etc/inc/interfaces.inc");
require_once("/etc/inc/services.inc");
require_once("/etc/inc/filter.inc");
require_once("/etc/inc/unbound.inc");

global $config;

$opt_restore = array(
    'opt1' => array(
        'descr' => 'HOME',
        'if' => 'vtnet1.10',
        'enable' => '',
        'ipaddr' => '192.168.110.1',
        'subnet' => '24',
        'spoofmac' => ''
    ),
    'opt2' => array(
        'descr' => 'LAB',
        'if' => 'vtnet1.20',
        'enable' => '',
        'ipaddr' => '192.168.20.1',
        'subnet' => '24',
        'spoofmac' => ''
    ),
    'opt3' => array(
        'descr' => 'SERVERS',
        'if' => 'vtnet1.30',
        'enable' => '',
        'ipaddr' => '192.168.30.1',
        'subnet' => '24',
        'spoofmac' => ''
    ),
    'opt4' => array(
        'descr' => 'GUEST',
        'if' => 'vtnet1.40',
        'enable' => '',
        'ipaddr' => '192.168.40.1',
        'subnet' => '24',
        'spoofmac' => ''
    ),
    'opt5' => array(
        'descr' => 'IoT',
        'if' => 'vtnet1.50',
        'enable' => '',
        'spoofmac' => '',
        'ipaddr' => '192.168.50.1',
        'subnet' => '24'
    )
);

foreach ($opt_restore as $opt => $settings) {
    $config['interfaces'][$opt] = $settings;
}

$vlan_descrs = array(
    '99' => 'MGMT',
    '10' => 'HOME',
    '20' => 'LAB',
    '30' => 'SERVERS',
    '40' => 'GUEST',
    '50' => 'IoT'
);

if (isset($config['vlans']['vlan']) && is_array($config['vlans']['vlan'])) {
    foreach ($config['vlans']['vlan'] as &$vlan) {
        if ($vlan['if'] === 'vtnet1' && isset($vlan_descrs[$vlan['tag']])) {
            $vlan['pcp'] = '';
            $vlan['descr'] = $vlan_descrs[$vlan['tag']];
        }
    }
    unset($vlan);
}

write_config("Autonomous Recovery Step 1: Restore OPT1-OPT5 IPv4, descriptions, and vtnet1 VLAN descriptions");

foreach (array('opt1', 'opt2', 'opt3', 'opt4', 'opt5') as $opt) {
    echo "Configuring $opt...\n";
    interface_configure($opt);
}

echo "Reconfiguring DHCPd...\n";
services_dhcpd_configure();

echo "Reconfiguring Unbound DNS Resolver...\n";
services_unbound_configure();

echo "Reloading packet filter...\n";
filter_configure();

echo "Step 1 complete.\n";
?>
