# PFSense/Kubernetes Network Filtering Charter — Zero Trust Policy

Scope: WAN network, SDN LAN (2× Proxmox), pfSense cluster in high availability (CARP), internal Kubernetes network
Version: 1.0
Status: Deny All by default, opening by documented exception

---

# 1. Guiding Principles

1. **Deny All by default** on all interfaces, all zones, all flow directions (inbound, outbound, inter-zone).

2. **No "any/any" rule**, ever, even temporarily.

3. **Least privilege**: one rule = one identified business need, with precise source, destination, port, and protocol.

4. **Traceability**: every rule carries a comment (Author, implementation date, lifespan if temporary, reason for the rule's implementation).

5. **Strong authentication** on administrative access (pfSense, Proxmox): MFA + access restricted by dedicated IP/segment.

6. **Systematic encryption** of management and synchronization flows (HTTPS, SSH, IPsec for pfSense sync).

7. **Periodic review** of rules: removal of obsolete rules, verification of expired temporary rules.

8. **Centralized logging**: all blocks and sensitive authorizations are logged and exported to an external syslog (outside pfSense) for log integrity.

9. **Versioning of the Firewall Rules file**: The established rules file must be kept up to date, and must reflect the current state of the firewall rules. Versioning is performed and allows tracking of the latest modifications. (See Principle 4)