# Proxmox VE Host Configuration Backup to PBS

## 1. Overview & Architecture

Automated host configuration backup from Proxmox VE (PVE) nodes to Proxmox Backup Server (PBS) using `proxmox-backup-client`.

* **Backup Scope:**
  * `etc.pxar` (`/etc`): Network (`interfaces`), storage (`storage.cfg`), cluster, and firewall rules (`--include-dev /etc/pve` forces traversal of the FUSE cluster filesystem).
  * `pve-cluster.pxar` (`/var/lib/pve-cluster`): Contains `config.db` (SQLite master cluster state database).
  * `root.pxar` (`/root`): Custom scripts and SSH keys.
  * `cron.pxar` (`/var/spool/cron`): Local scheduled jobs.
* **Security Model:**
  * Dedicated API Token (`root@pam!pve-host-backup`) limited to the **`DatastoreBackup`** role on the `backup-cluster` datastore.
  * Allows creating new snapshots; strictly forbids pruning or modifying existing historical backups (anti-ransomware defense).
  * Secret value isolated in `/etc/pve_pbs_token.secret` (`chmod 600`).

---

## 2. Configuration & Automation

### File Setup

1. **Token Secret** (`/etc/pve_pbs_token.secret`):
   ```bash
   echo -n "YOUR_API_TOKEN_SECRET" > /etc/pve_pbs_token.secret
   chmod 600 /etc/pve_pbs_token.secret
   ```

2. **Backup Script** (`/usr/local/bin/backup-pve-host.sh`, `chmod 700`):
   ```bash
   #!/bin/bash
   export PBS_REPOSITORY='root@pam!pve-host-backup@10.4.111.120:8007:backup-cluster'
   export PBS_PASSWORD="$(cat /etc/pve_pbs_token.secret)"
   export PBS_FINGERPRINT="YOUR_PBS_FINGERPRINT"

   proxmox-backup-client backup \
       etc.pxar:/etc \
       pve-cluster.pxar:/var/lib/pve-cluster \
       root.pxar:/root \
       cron.pxar:/var/spool/cron \
       --include-dev /etc/pve
   ```

3. **Cron Scheduling:**
   Run daily at 02:00 AM (`crontab -e`):
   ```cron
   0 2 * * * /usr/local/bin/backup-pve-host.sh >/dev/null 2>&1
   ```

---

## 3. Retention & Maintenance (PBS Web UI)

Managed centrally on PBS under **Datastore > backup-cluster > Prune & GC Jobs**:

* **Prune Policy:**
  * `Keep Last`: 7 (last 7 daily backups)
  * `Keep Weekly`: 4 (weekly backups for 1 month)
  * `Keep Monthly`: 6 (monthly archives for 6 months)
* **Garbage Collection (GC):** Run weekly (e.g., Sunday at 04:00 AM) to purge unreferenced data chunks.

---

## 4. Disaster Recovery Procedures

### Scenario A: Single File / Config Recovery

1. List available snapshots:
   ```bash
   export PBS_REPOSITORY='root@pam!pve-host-backup@10.4.111.120:8007:backup-cluster'
   export PBS_PASSWORD="$(cat /etc/pve_pbs_token.secret)"
   proxmox-backup-client snapshot list
   ```

2. Restore archive to a temporary location:
   ```bash
   mkdir -p /tmp/restore
   proxmox-backup-client restore host/<node-name>/<timestamp> etc.pxar /tmp/restore
   ```

3. Copy the required file and clean up:
   ```bash
   cp /tmp/restore/network/interfaces /etc/network/interfaces
   rm -rf /tmp/restore
   ```

---

### Scenario B: Full Node Disaster Recovery (Hardware Failure)

> **Warning:** Never extract `etc.pxar` directly over `/` on a fresh installation. This will corrupt disk UUIDs in `/etc/fstab` and machine hardware keys.

1. **Clean Installation:** Reinstall base Proxmox VE using the **exact same hostname and IP address**.
2. **Setup Credentials:**
   ```bash
   echo -n "YOUR_API_TOKEN_SECRET" > /etc/pve_pbs_token.secret
   chmod 600 /etc/pve_pbs_token.secret

   export PBS_REPOSITORY='root@pam!pve-host-backup@10.4.111.120:8007:backup-cluster'
   export PBS_PASSWORD="$(cat /etc/pve_pbs_token.secret)"
   export PBS_FINGERPRINT="YOUR_PBS_FINGERPRINT"
   ```
3. **Download Backup Archives:**
   ```bash
   mkdir -p /tmp/recovery
   proxmox-backup-client restore host/<node-name>/<latest-snapshot> pve-cluster.pxar /tmp/recovery/pve-cluster
   proxmox-backup-client restore host/<node-name>/<latest-snapshot> etc.pxar /tmp/recovery/etc
   ```
4. **Restore Cluster Database (`config.db`):**
   ```bash
   systemctl stop pve-cluster
   cp /tmp/recovery/pve-cluster/config.db /var/lib/pve-cluster/config.db
   systemctl start pve-cluster
   ```
5. **Restore Network and Apply:**
   ```bash
   cp /tmp/recovery/etc/network/interfaces /etc/network/interfaces
   ifreload -a
   ```
6. **Cleanup:**
   ```bash
   rm -rf /tmp/recovery
   ```
   *Reload the PVE Web GUI: all VMs, LXCs, storage pools, and cluster definitions will reappear.*
