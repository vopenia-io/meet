-- ============================================================
-- Kamailio Database Data Insertion Script (DEV / LOCAL)
-- All services on 192.168.0.10
-- Run AFTER 01_create_schema.sql
-- Target: PostgreSQL
-- ============================================================

-- --------------------------------------------------------
-- Version entries
-- --------------------------------------------------------
INSERT INTO version (table_name, table_version) VALUES ('subscriber', 7)
    ON CONFLICT (table_name) DO UPDATE SET table_version = 7;

INSERT INTO version (table_name, table_version) VALUES ('dispatcher', 4)
    ON CONFLICT (table_name) DO UPDATE SET table_version = 4;

INSERT INTO version (table_name, table_version) VALUES ('rtpengine', 1)
    ON CONFLICT (table_name) DO UPDATE SET table_version = 1;

INSERT INTO version (table_name, table_version) VALUES ('address', 6)
    ON CONFLICT (table_name) DO UPDATE SET table_version = 6;

INSERT INTO version (table_name, table_version) VALUES ('trusted', 6)
    ON CONFLICT (table_name) DO UPDATE SET table_version = 6;

INSERT INTO version (table_name, table_version) VALUES ('uacreg', 5)
    ON CONFLICT (table_name) DO UPDATE SET table_version = 5;

-- --------------------------------------------------------
-- Dispatcher destinations (LiveKit-SIP)
-- --------------------------------------------------------
INSERT INTO dispatcher (setid, destination, flags, priority, attrs, description)
    SELECT 1, 'sip:192.168.0.10:5080;transport=tcp', 0, 0, '', 'DEV LiveKit-SIP'
    WHERE NOT EXISTS (SELECT 1 FROM dispatcher WHERE setid = 1 AND destination = 'sip:192.168.0.10:5080;transport=tcp');

-- --------------------------------------------------------
-- RTPEngine instance
-- --------------------------------------------------------
INSERT INTO rtpengine (setid, url, weight, disabled, external_ip)
    SELECT 1, 'udp:192.168.0.10:22222', 1, 0, '192.168.0.10'
    WHERE NOT EXISTS (SELECT 1 FROM rtpengine WHERE setid = 1 AND url = 'udp:192.168.0.10:22222');

-- --------------------------------------------------------
-- Address whitelist (permissions module - IP-based access control)
-- --------------------------------------------------------
-- DEV: allow all local network devices
INSERT INTO address (grp, ip_addr, mask, port, tag)
    SELECT 1, '192.168.0.0', 24, 0, 'DEV local network'
    WHERE NOT EXISTS (SELECT 1 FROM address WHERE grp = 1 AND ip_addr = '192.168.0.0');

-- --------------------------------------------------------
-- OVH SIP trunk registration
-- Set password: UPDATE uacreg SET auth_password='<PASSWORD>' WHERE l_uuid='0033972122011';
-- Then reload: kamcmd uac.reg_reload
-- --------------------------------------------------------
INSERT INTO uacreg (l_uuid, l_username, l_domain, r_username, r_domain,
    realm, auth_username, auth_password, auth_ha1, auth_proxy,
    expires, flags, reg_delay, contact_addr, socket)
SELECT '0033972122011', '0033972122011', 'siptrunk.ovh.net',
    '0033972122011', 'siptrunk.ovh.net', 'siptrunk.ovh.net',
    '0033972122011', '', '', 'sip:siptrunk.ovh.net',
    3600, 0, 0, '', ''
WHERE NOT EXISTS (SELECT 1 FROM uacreg WHERE l_uuid = '0033972122011');