# Building the MSSQL FastAPI + Ansible Service From Scratch

> A from-zero build guide for the service that's actually running right now:
> FastAPI (`python-fastapi-mssql/`) driving its own embedded Ansible tree to
> install MSSQL 2019 on two VMs, restore AdventureWorks, stripe a backup from
> vm1 to vm2, and wire them into an Always On Availability Group. Every code
> block below is the real, current, working content — already carrying the
> fixes from [`mssql-ag-build-history-and-lessons.md`](mssql-ag-build-history-and-lessons.md)
> (correct directory ownership, `GO` terminators, `@@SERVERNAME`-based replica
> identity, etc.), so following this guide builds it correctly the first time
> instead of repeating that debugging.
>
> This guide only covers code that's actually used. The Appendix at the end
> lists what else lives in the repo and why you can ignore it.

## What you're building

```
curl -> FastAPI (uvicorn) -> AnsibleRunner (subprocess) -> ansible-playbook -> vm1 + vm2
```

One FastAPI process, running on `devops_VM1` itself (VM1 doubles as the
Ansible controller in this lab — see below), shells out to
`ansible-playbook` against an embedded `ansible/` tree. No AWX, no GitLab CI —
that's a separate, parallel system (`ansible-mssql-deploy/`) this guide
doesn't touch.

## Prerequisites & lab topology

| VM | Role | Hostname | IP |
|---|---|---|---|
| SQL VM 1 | Primary + Ansible controller | `devops_VM1` | `192.168.70.129` |
| SQL VM 2 | Secondary | `devops_VM2` | `192.168.70.130` |

- Both VMs: CentOS 8, reachable by SSH as user `devops` with passwordless sudo.
- Controller (VM1): Python 3.9+, `pip`, and `ansible-core` (installed via
  `requirements.txt` below — no separate system Ansible install needed).
- `ansible-playbook` needs a POSIX control node. Don't try to run this from a
  native Windows shell — run it from VM1 itself, WSL, or another Linux box
  (see the build-history doc's Phase 1/2 for why this matters).

## Part 1 — SSH access

Generate a key on the controller (VM1) if you don't have one, and authorize
it on **both** VMs — including VM1 itself, since it's both the controller and
a deployment target:

```bash
ssh-keygen -t rsa -b 4096 -C "mssql-lab"
ssh-copy-id -i ~/.ssh/id_rsa.pub devops@192.168.70.129   # vm1 -- yes, even though you're running from here
ssh-copy-id -i ~/.ssh/id_rsa.pub devops@192.168.70.130   # vm2
```

Verify both:
```bash
ssh -i ~/.ssh/id_rsa devops@192.168.70.129 'hostname'
ssh -i ~/.ssh/id_rsa devops@192.168.70.130 'hostname'
```

Skipping the vm1 `ssh-copy-id` is the single most common failure the first
time through this — Ansible will report `Permission denied` on vm1 only,
which looks like a config bug but is just a missing `authorized_keys` entry.

## Part 2 — Project skeleton

```bash
mkdir -p python-fastapi-mssql/{app/routes,ansible/inventory,ansible/playbooks,ansible/roles/mssql/{tasks,defaults,handlers},tests,logs,backups}
cd python-fastapi-mssql
```

## Part 3 — The Ansible role: `ansible/roles/mssql/`

### `defaults/main.yml`

```yaml
---
# Default variables for embedded MSSQL Ansible role

sa_password: "YourStr0ng!Passw0rd"
mssql_edition: "Developer"
mssql_version: "2019"
backup_dir: "/backup"
data_dir: "/var/opt/mssql/data"
log_dir: "/var/opt/mssql/log"
mssql_port: 1433
mssql_tools_path: "/opt/mssql-tools/bin"
restore_replace: true
restore_recovery: "RECOVERY"
backup_compression: true
backup_format: "FORMAT"
ag_name: "AG1"
ag_listener: "ag-listener"
ag_port: 5022
ag_replica_mode: "SYNCHRONOUS_COMMIT"
ag_databases:
  - AdventureWorks
ag_endpoint_name: "Hadr_endpoint"
ag_cluster_type: "NONE"
ag_failover_mode: "MANUAL"
ag_cert_name: "dbm_certificate"
ag_cert_password: "{{ sa_password }}"
local_backup_dir: "./backups/vm1_striped"
local_cert_relay_dir: "./backups/ag_certs"
```

`ag_cluster_type: NONE` / `ag_failover_mode: MANUAL` is Microsoft's documented
pattern for a 2-node AG with no external cluster manager (Pacemaker/WSFC) —
correct for this lab, since neither VM runs one.

### `tasks/install.yml`

```yaml
---
# Install MSSQL Server on Linux

- name: Install required dependencies
  yum:
    name:
      - curl
      - wget
      - gnupg
      - libsodium
      - rsync
    state: present
  tags:
    - install
    - dependencies

- name: Add Microsoft SQL Server repository key
  rpm_key:
    key: https://packages.microsoft.com/keys/microsoft.asc
    state: present
  tags:
    - install
    - repo

- name: Add Microsoft SQL Server repository
  yum_repository:
    name: mssql-server
    description: Microsoft SQL Server Repository
    baseurl: https://packages.microsoft.com/rhel/8/mssql-server-{{ mssql_version }}/
    gpgcheck: yes
    gpgkey: https://packages.microsoft.com/keys/microsoft.asc
    enabled: yes
  tags:
    - install
    - repo

- name: Add Microsoft MSSQL-Tools repository
  yum_repository:
    name: mssql-tools
    description: Microsoft MSSQL-Tools Repository
    baseurl: https://packages.microsoft.com/rhel/8/prod/
    gpgcheck: yes
    gpgkey: https://packages.microsoft.com/keys/microsoft.asc
    enabled: yes
  tags:
    - install
    - repo

- name: Install MSSQL Server
  yum:
    name: mssql-server
    state: present
  tags:
    - install
    - mssql

- name: Install MSSQL Tools (sqlcmd)
  yum:
    name: mssql-tools
    state: present
  environment:
    ACCEPT_EULA: "Y"
  tags:
    - install
    - tools

- name: Check whether MSSQL has already been configured
  stat:
    path: /var/opt/mssql/mssql.conf
  register: mssql_config
  tags:
    - install
    - setup

- name: Run MSSQL setup/configuration
  shell: |
    MSSQL_SA_PASSWORD='{{ sa_password }}' \
    MSSQL_PID='{{ mssql_edition }}' \
    /opt/mssql/bin/mssql-conf -n setup accept-eula
  environment:
    ACCEPT_EULA: "Y"
    MSSQL_SA_PASSWORD: "{{ sa_password }}"
    MSSQL_PID: "{{ mssql_edition }}"
  when: not mssql_config.stat.exists
  tags:
    - install
    - setup

- name: Enable MSSQL Server service
  systemd:
    name: mssql-server
    enabled: yes
    state: started
  tags:
    - install
    - service

- name: Wait for SQL Server to start
  wait_for:
    port: "{{ mssql_port }}"
    delay: 10
    timeout: 60
  tags:
    - install
    - service

- name: Verify MSSQL installation
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "SELECT @@VERSION"
  register: version_check
  changed_when: false
  tags:
    - install
    - verify

- name: Display MSSQL version
  debug:
    var: version_check.stdout
  tags:
    - install
    - verify
```

### `tasks/configure.yml`

```yaml
---
# Configure MSSQL Server directories and settings

- name: Create backup directory
  file:
    path: "{{ backup_dir }}"
    state: directory
    mode: '0755'
    owner: mssql
    group: mssql
  tags:
    - configure
    - directories

- name: Create data directory
  file:
    path: "{{ data_dir }}"
    state: directory
    mode: '0755'
    owner: mssql
    group: mssql
  tags:
    - configure
    - directories

- name: Create log directory
  file:
    path: "{{ log_dir }}"
    state: directory
    mode: '0755'
    owner: mssql
    group: mssql
  tags:
    - configure
    - directories

- name: Set MSSQL default data directory path
  shell: |
    /opt/mssql/bin/mssql-conf set filelocation.defaultdatadir {{ data_dir }}
  notify: restart mssql service
  tags:
    - configure
    - paths

- name: Set MSSQL default log directory path
  shell: |
    /opt/mssql/bin/mssql-conf set filelocation.defaultlogdir {{ log_dir }}
  notify: restart mssql service
  tags:
    - configure
    - paths

- name: Set MSSQL network port
  shell: |
    /opt/mssql/bin/mssql-conf set network.tcpport {{ mssql_port }}
  notify: restart mssql service
  tags:
    - configure
    - network

- name: Enable SQL Server Agent
  shell: |
    /opt/mssql/bin/mssql-conf set sqlagent.enabled true
  notify: restart mssql service
  tags:
    - configure
    - agent

- name: Flush handlers to apply configuration changes
  meta: flush_handlers
  tags:
    - configure
```

`owner: mssql, group: mssql` on all three directories matters — this is the
fix for bug #1 in the build-history doc (root-owned directories blocked the
`mssql` service account with a non-obvious "OS error 5" on every
backup/restore).

### `tasks/adventureworks.yml`

```yaml
---
# Download and restore AdventureWorks database

- name: Create AdventureWorks backup directory
  file:
    path: "{{ data_dir }}/backups"
    state: directory
    mode: '0755'
  tags:
    - adventureworks
    - database

- name: Download AdventureWorks 2019 backup file
  get_url:
    url: "https://github.com/microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks2019.bak"
    dest: "{{ data_dir }}/AdventureWorks2019.bak"
    timeout: 300
  register: download_result
  retries: 3
  delay: 5
  until: download_result is succeeded
  tags:
    - adventureworks
    - database
    - download

- name: Wait for MSSQL to be ready
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "SELECT 1"
  register: connectivity_check
  retries: 10
  delay: 5
  until: connectivity_check.rc == 0
  changed_when: false
  tags:
    - adventureworks
    - database
    - verify

- name: Restore AdventureWorks database
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    RESTORE DATABASE AdventureWorks
    FROM DISK = '{{ data_dir }}/AdventureWorks2019.bak'
    WITH MOVE 'AdventureWorks2019' TO '{{ data_dir }}/AdventureWorks.mdf',
    MOVE 'AdventureWorks2019_log' TO '{{ data_dir }}/AdventureWorks.ldf',
    REPLACE
    "
  register: restore_output
  changed_when: "'restored' in restore_output.stdout or 'Processed' in restore_output.stdout"
  tags:
    - adventureworks
    - database
    - restore

- name: Display restore result
  debug:
    msg: "AdventureWorks restore output: {{ restore_output.stdout }}"
  tags:
    - adventureworks
    - database
    - verify

- name: Verify AdventureWorks database exists
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -h -1 -W -Q "SET NOCOUNT ON; SELECT DB_ID('AdventureWorks')"
  register: db_check
  changed_when: false
  failed_when: "'NULL' in db_check.stdout or db_check.stdout | trim == ''"
  tags:
    - adventureworks
    - database
    - verify

- name: Display database verification
  debug:
    msg: "AdventureWorks database check: {{ db_check.stdout }}"
  tags:
    - adventureworks
    - database
    - verify
```

### `tasks/backup.yml`

```yaml
---
# Create 10-stripe backup on VM1 only

- name: Create striped backup directory on VM1
  file:
    path: "{{ backup_dir }}/striped"
    state: directory
    mode: '0755'
    owner: mssql
    group: mssql
  when: inventory_hostname == "vm1"
  tags:
    - backup
    - vm1-only

- name: Create 10-striped backup of AdventureWorks (VM1 only)
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" << 'EOF'
    BACKUP DATABASE AdventureWorks
    TO
      DISK='{{ backup_dir }}/striped/adv_stripe_01.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_02.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_03.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_04.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_05.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_06.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_07.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_08.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_09.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_10.bak'
    WITH FORMAT, COMPRESSION
    GO
    EOF
  when: inventory_hostname == "vm1"
  register: backup_result
  changed_when: "'completed' in backup_result.stdout or 'Processed' in backup_result.stdout"
  tags:
    - backup
    - vm1-only

- name: Verify backup files created on VM1
  find:
    path: "{{ backup_dir }}/striped"
    patterns: "adv_stripe_*.bak"
  register: backup_files
  when: inventory_hostname == "vm1"
  tags:
    - backup
    - vm1-only
    - verify

- name: Display backup file count
  debug:
    msg: "Backup files created: {{ backup_files.matched }}"
  when: inventory_hostname == "vm1"
  tags:
    - backup
    - vm1-only
    - verify

- name: Assert all striped backup files were created
  assert:
    that:
      - backup_files.matched | int == 10
    fail_msg: "Expected 10 striped backup files on VM1, found {{ backup_files.matched | default(0) }}"
  when: inventory_hostname == "vm1"
  tags:
    - backup
    - vm1-only
    - verify
```

Note the `GO` at the end of the heredoc — without it, `sqlcmd` accepts the
input and silently runs nothing (exit code 0, no error, no backup files).
That's bug #2 from the build-history doc.

### `tasks/restore.yml`

```yaml
---
# Copy backup from VM1 to VM2 and restore

- name: Ensure local relay directory exists on controller
  file:
    path: "{{ local_backup_dir }}"
    state: directory
    mode: '0755'
  delegate_to: localhost
  become: false
  when: inventory_hostname == "vm1"
  tags:
    - restore
    - transfer
    - vm1-only

- name: Fetch backup files from VM1
  synchronize:
    src: "{{ backup_dir }}/striped/"
    dest: "{{ local_backup_dir }}/"
    mode: pull
  when: inventory_hostname == "vm1"
  tags:
    - restore
    - transfer
    - vm1-only

- name: Create backup directory on VM2
  file:
    path: "{{ backup_dir }}/striped"
    state: directory
    mode: '0755'
    owner: mssql
    group: mssql
  when: inventory_hostname == "vm2"
  tags:
    - restore
    - transfer
    - vm2-only

- name: Copy backup files to VM2
  copy:
    src: "{{ local_backup_dir }}/"
    dest: "{{ backup_dir }}/striped/"
    mode: '0644'
  when: inventory_hostname == "vm2"
  tags:
    - restore
    - transfer
    - vm2-only

- name: Verify backup files on VM2
  find:
    path: "{{ backup_dir }}/striped"
    patterns: "adv_stripe_*.bak"
  register: backup_files_vm2
  when: inventory_hostname == "vm2"
  tags:
    - restore
    - verify
    - vm2-only

- name: Display backup files on VM2
  debug:
    msg: "Backup files found on VM2: {{ backup_files_vm2.matched }}"
  when: inventory_hostname == "vm2"
  tags:
    - restore
    - verify
    - vm2-only

- name: Assert all striped backup files exist on VM2
  assert:
    that:
      - backup_files_vm2.matched | int == 10
    fail_msg: "Expected 10 striped backup files on VM2, found {{ backup_files_vm2.matched | default(0) }}"
  when: inventory_hostname == "vm2"
  tags:
    - restore
    - verify
    - vm2-only

- name: Restore 10-striped backup on VM2
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" << 'EOF'
    RESTORE DATABASE AdventureWorks
    FROM
      DISK='{{ backup_dir }}/striped/adv_stripe_01.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_02.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_03.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_04.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_05.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_06.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_07.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_08.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_09.bak',
      DISK='{{ backup_dir }}/striped/adv_stripe_10.bak'
    WITH REPLACE
    GO
    EOF
  when: inventory_hostname == "vm2"
  register: restore_result
  changed_when: "'restored' in restore_result.stdout or 'Processed' in restore_result.stdout"
  tags:
    - restore
    - vm2-only

- name: Display restore result on VM2
  debug:
    msg: "Restore output: {{ restore_result.stdout }}"
  when: inventory_hostname == "vm2"
  tags:
    - restore
    - verify
    - vm2-only

- name: Verify database on VM2
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -h -1 -W -Q "SET NOCOUNT ON; SELECT DB_ID('AdventureWorks')"
  when: inventory_hostname == "vm2"
  register: db_verify_vm2
  changed_when: false
  failed_when: "'NULL' in db_verify_vm2.stdout or db_verify_vm2.stdout | trim == ''"
  tags:
    - restore
    - verify
    - vm2-only

- name: Display database verification on VM2
  debug:
    msg: "AdventureWorks database verification on VM2: {{ db_verify_vm2.stdout }}"
  when: inventory_hostname == "vm2"
  tags:
    - restore
    - verify
    - vm2-only
```

### `tasks/alwayson.yml`

```yaml
---
# Always On Availability Group configuration
# Builds a CLUSTER_TYPE=NONE (no external cluster manager), manual-failover
# AG between vm1 (primary) and vm2 (secondary), using certificate-based
# endpoint authentication since there is no AD/Kerberos in this lab.

- name: Check current HADR setting
  command: grep -c "hadrenabled = 1" /var/opt/mssql/mssql.conf
  register: hadr_enabled_check
  failed_when: false
  changed_when: false
  tags:
    - alwayson

- name: Enable HADR on MSSQL
  shell: /opt/mssql/bin/mssql-conf set hadr.hadrenabled 1
  when: hadr_enabled_check.stdout | trim == '0'
  notify: restart mssql service
  tags:
    - alwayson

- name: Flush handlers to apply HADR setting
  meta: flush_handlers
  tags:
    - alwayson

- name: Wait for SQL Server port after HADR enable
  wait_for:
    port: "{{ mssql_port }}"
    delay: 5
    timeout: 120
  tags:
    - alwayson

- name: Wait for sqlcmd connectivity after HADR enable
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "SELECT 1"
  register: post_hadr_check
  retries: 10
  delay: 5
  until: post_hadr_check.rc == 0
  changed_when: false
  tags:
    - alwayson

- name: Check firewalld status
  command: systemctl is-active firewalld
  register: firewalld_status
  failed_when: false
  changed_when: false
  tags:
    - alwayson

- name: Open AG endpoint port in firewalld
  firewalld:
    port: "{{ ag_port }}/tcp"
    permanent: yes
    immediate: yes
    state: enabled
  when: firewalld_status.stdout | trim == 'active'
  tags:
    - alwayson

- name: Create master key and certificate on primary replica (vm1)
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF NOT EXISTS (SELECT * FROM sys.symmetric_keys WHERE name = '##MS_DatabaseMasterKey##')
      CREATE MASTER KEY ENCRYPTION BY PASSWORD = '{{ ag_cert_password }}';
    IF NOT EXISTS (SELECT * FROM sys.certificates WHERE name = '{{ ag_cert_name }}')
      CREATE CERTIFICATE {{ ag_cert_name }} WITH SUBJECT = '{{ ag_cert_name }}';
    "
  when: inventory_hostname == 'vm1'
  changed_when: false
  tags:
    - alwayson

- name: Check if certificate backup files already exist on vm1
  stat:
    path: "{{ data_dir }}/{{ ag_cert_name }}.cer"
  register: cert_file_stat
  when: inventory_hostname == 'vm1'
  tags:
    - alwayson

- name: Backup certificate to file on vm1
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    BACKUP CERTIFICATE {{ ag_cert_name }}
    TO FILE = '{{ data_dir }}/{{ ag_cert_name }}.cer'
    WITH PRIVATE KEY (
      FILE = '{{ data_dir }}/{{ ag_cert_name }}.pvk',
      ENCRYPTION BY PASSWORD = '{{ ag_cert_password }}'
    )
    "
  when: inventory_hostname == 'vm1' and not cert_file_stat.stat.exists
  changed_when: true
  tags:
    - alwayson

- name: Fetch certificate files from vm1 to controller
  fetch:
    src: "{{ data_dir }}/{{ ag_cert_name }}.{{ item }}"
    dest: "{{ local_cert_relay_dir }}/"
    flat: yes
  loop:
    - cer
    - pvk
  when: inventory_hostname == 'vm1'
  tags:
    - alwayson

- name: Create master key on secondary replica (vm2)
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF NOT EXISTS (SELECT * FROM sys.symmetric_keys WHERE name = '##MS_DatabaseMasterKey##')
      CREATE MASTER KEY ENCRYPTION BY PASSWORD = '{{ ag_cert_password }}';
    "
  when: inventory_hostname == 'vm2'
  changed_when: false
  tags:
    - alwayson

- name: Copy certificate files to vm2
  copy:
    src: "{{ local_cert_relay_dir }}/{{ ag_cert_name }}.{{ item }}"
    dest: "{{ data_dir }}/{{ ag_cert_name }}.{{ item }}"
    owner: mssql
    group: mssql
    mode: '0600'
  loop:
    - cer
    - pvk
  when: inventory_hostname == 'vm2'
  tags:
    - alwayson

- name: Import certificate on vm2
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF NOT EXISTS (SELECT * FROM sys.certificates WHERE name = '{{ ag_cert_name }}')
    CREATE CERTIFICATE {{ ag_cert_name }}
    FROM FILE = '{{ data_dir }}/{{ ag_cert_name }}.cer'
    WITH PRIVATE KEY (
      FILE = '{{ data_dir }}/{{ ag_cert_name }}.pvk',
      DECRYPTION BY PASSWORD = '{{ ag_cert_password }}'
    )
    "
  when: inventory_hostname == 'vm2'
  changed_when: false
  tags:
    - alwayson

- name: Create Always On endpoint on each replica
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF NOT EXISTS (SELECT * FROM sys.database_mirroring_endpoints WHERE name = '{{ ag_endpoint_name }}')
    CREATE ENDPOINT [{{ ag_endpoint_name }}]
    STATE=STARTED
    AS TCP (LISTENER_PORT = {{ ag_port }})
    FOR DATA_MIRRORING (ROLE = ALL, AUTHENTICATION = CERTIFICATE {{ ag_cert_name }})
    "
  register: endpoint_result
  changed_when: "'created' in endpoint_result.stdout or 'already exists' in endpoint_result.stdout"
  tags:
    - alwayson

- name: Set AdventureWorks recovery model to FULL on vm1
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "ALTER DATABASE AdventureWorks SET RECOVERY FULL"
  when: inventory_hostname == 'vm1'
  changed_when: false
  tags:
    - alwayson

- name: Seed full + log backup for AdventureWorks on vm1 (required for AG log chain)
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    BACKUP DATABASE AdventureWorks TO DISK = '{{ backup_dir }}/aw_full_seed.bak' WITH INIT;
    BACKUP LOG AdventureWorks TO DISK = '{{ backup_dir }}/aw_log_seed.bak' WITH INIT;
    "
  when: inventory_hostname == 'vm1'
  changed_when: true
  tags:
    - alwayson

- name: Check whether AdventureWorks on vm2 is already part of an AG
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.dm_hadr_database_replica_states drs JOIN sys.databases d ON d.database_id = drs.database_id WHERE d.name = 'AdventureWorks'"
  when: inventory_hostname == 'vm2'
  register: vm2_ag_db_check
  changed_when: false
  tags:
    - alwayson

- name: Drop pre-seeded AdventureWorks on vm2 before AG join
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF EXISTS (SELECT * FROM sys.databases WHERE name = 'AdventureWorks')
    BEGIN
      ALTER DATABASE AdventureWorks SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
      DROP DATABASE AdventureWorks;
    END
    "
  when: inventory_hostname == 'vm2' and (vm2_ag_db_check.stdout | trim) == '0'
  changed_when: true
  tags:
    - alwayson

- name: Create Availability Group on primary replica
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF NOT EXISTS (SELECT * FROM sys.availability_groups WHERE name = '{{ ag_name }}')
    BEGIN
      CREATE AVAILABILITY GROUP [{{ ag_name }}]
      WITH (CLUSTER_TYPE = {{ ag_cluster_type }})
      FOR DATABASE {{ ag_databases | join(', ') }}
      REPLICA ON
      {% for host in groups['mssql_servers'] %}
        N'{{ hostvars[host].vmware_name }}' WITH (ENDPOINT_URL = N'tcp://{{ hostvars[host].ansible_host }}:{{ ag_port }}', FAILOVER_MODE = {{ ag_failover_mode }}, AVAILABILITY_MODE = {{ ag_replica_mode }}, SEEDING_MODE = AUTOMATIC){{ ',' if not loop.last else '' }}
      {% endfor %}
    END
    "
  register: ag_result
  changed_when: "'created' in ag_result.stdout or 'already exists' in ag_result.stdout"
  when: inventory_hostname == 'vm1'
  tags:
    - alwayson

- name: Join secondary replica to Availability Group
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF NOT EXISTS (SELECT * FROM sys.dm_hadr_availability_replica_states ars JOIN sys.availability_replicas ar ON ar.replica_id = ars.replica_id WHERE ar.replica_server_name = '{{ vmware_name }}' AND ars.role_desc = 'SECONDARY')
    ALTER AVAILABILITY GROUP [{{ ag_name }}] JOIN WITH (CLUSTER_TYPE = {{ ag_cluster_type }})
    "
  when: inventory_hostname == 'vm2'
  register: join_result
  changed_when: "'joined' in join_result.stdout or 'already exists' in join_result.stdout"
  tags:
    - alwayson

- name: Grant automatic seeding permission on secondary
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "ALTER AVAILABILITY GROUP [{{ ag_name }}] GRANT CREATE ANY DATABASE"
  when: inventory_hostname == 'vm2'
  changed_when: true
  tags:
    - alwayson

- name: Wait for AdventureWorks to reach SYNCHRONIZED state on all replicas
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.dm_hadr_database_replica_states drs JOIN sys.databases d ON d.database_id = drs.database_id WHERE d.name = 'AdventureWorks' AND drs.synchronization_state_desc != 'SYNCHRONIZED'"
  register: sync_wait
  retries: 30
  delay: 10
  until: sync_wait.stdout | trim == '0'
  when: inventory_hostname == 'vm1'
  changed_when: false
  tags:
    - alwayson

- name: Verify Availability Group state
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -h -1 -W -Q "SET NOCOUNT ON; SELECT ar.replica_server_name, ars.role_desc, ars.synchronization_health_desc FROM sys.dm_hadr_availability_replica_states ars JOIN sys.availability_replicas ar ON ar.replica_id = ars.replica_id"
  register: verify_ag
  changed_when: false
  tags:
    - alwayson

- name: Display Availability Group verification
  debug:
    msg: "AG state: {{ verify_ag.stdout }}"
  tags:
    - alwayson
```

Two things worth calling out because they're easy to get wrong from first
principles: `REPLICA ON` uses `hostvars[host].vmware_name` (`devops_VM1`/
`devops_VM2`), **not** the Ansible inventory hostname (`vm1`/`vm2`) — SQL
Server matches replicas by `@@SERVERNAME`, and using the inventory name looks
correct right up until the AG silently fails to recognize its own replica
(bug #8). And the full+log backup pair before the AG join exists because
`ALTER DATABASE ... SET RECOVERY FULL` needs a fresh full backup before a log
backup will succeed (bug #6).

### `tasks/main.yml`

```yaml
---
# Main task file for embedded MSSQL role

- name: Include install tasks
  include_tasks: install.yml
  tags:
    - always

- name: Include configure tasks
  include_tasks: configure.yml
  tags:
    - always

- name: Include AdventureWorks install tasks
  include_tasks: adventureworks.yml
  tags:
    - always

- name: Include backup tasks
  include_tasks: backup.yml
  tags:
    - always

- name: Include restore tasks
  include_tasks: restore.yml
  tags:
    - always
```

### `handlers/main.yml`

```yaml
---
# MSSQL service handlers

- name: restart mssql service
  systemd:
    name: mssql-server
    state: restarted
```

## Part 4 — Playbooks, inventory, and `ansible.cfg`

### `ansible/inventory/hosts.ini`

```ini
[mssql_servers]
vm1 ansible_host=192.168.70.129 instance_name=instance1 vmware_name=devops_VM1
vm2 ansible_host=192.168.70.130 instance_name=instance2 vmware_name=devops_VM2

[mssql_servers:vars]
ansible_user=devops
ansible_ssh_private_key_file=/home/devops/.ssh/id_rsa
ansible_connection=ssh
ansible_port=22
```

Use a real Linux path for `ansible_ssh_private_key_file` — a Windows
Git-Bash-style path (`/c/Users/.../id_rsa`) left over from a different dev
machine is a real mistake this build made once (see build-history Phase 6).

### `ansible/playbooks/site.yml`

```yaml
---
- name: Deploy MSSQL Server and AdventureWorks Database
  hosts: mssql_servers
  become: yes
  gather_facts: yes

  pre_tasks:
    - name: Display deployment information
      debug:
        msg: |
          Deploying MSSQL Server to {{ inventory_hostname }}
          Instance: {{ instance_name }}
          IP Address: {{ ansible_host }}
          OS: {{ ansible_os_family }}
      tags:
        - always

    - name: Validate system requirements
      assert:
        that:
          - ansible_os_family == "RedHat"
          - ansible_distribution_major_version == "8"
        fail_msg: "This role requires CentOS 8 or compatible"
      tags:
        - always

  roles:
    - role: mssql
      tags:
        - mssql
        - install
        - configure
        - database

  post_tasks:
    - name: Display final status
      debug:
        msg: |
          ✓ MSSQL Server deployment completed successfully!
          Instance: {{ instance_name }}
          Hostname: {{ inventory_hostname }}
          Port: {{ mssql_port }}
          Database: AdventureWorks installed
      tags:
        - always

    - name: Create summary report
      copy:
        content: |
          MSSQL Server Deployment Report
          ================================
          Deployment Date: {{ ansible_date_time.iso8601 }}
          Host: {{ inventory_hostname }}
          Instance: {{ instance_name }}
          MSSQL Version: {{ mssql_version }}
          Edition: {{ mssql_edition }}
          Status: SUCCESS
        dest: /tmp/mssql_deployment_{{ inventory_hostname }}.txt
      tags:
        - always
```

### `ansible/playbooks/backup.yml`

```yaml
---
- name: Create and transfer backups
  hosts: mssql_servers
  become: yes
  gather_facts: yes

  tasks:
    - name: Show backup status
      debug:
        msg: "Processing {{ inventory_hostname }} for backups"

    - name: Include backup tasks from role
      include_role:
        name: mssql
        tasks_from: backup.yml
      when: inventory_hostname == "vm1"

    - name: Include restore tasks from role
      include_role:
        name: mssql
        tasks_from: restore.yml
      when: inventory_hostname == "vm2"
```

### `ansible/playbooks/alwayson.yml`

```yaml
---
- name: Configure Always-On Availability Group for AdventureWorks
  hosts: mssql_servers
  become: yes
  gather_facts: yes

  pre_tasks:
    - name: Verify MSSQL connectivity on each replica
      shell: |
        {{ mssql_tools_path | default('/opt/mssql-tools/bin') }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "SELECT 1"
      register: connectivity_check
      retries: 10
      delay: 5
      until: connectivity_check.rc == 0
      changed_when: false
      tags:
        - alwayson

  tasks:
    - name: Configure Always On endpoints and availability group
      include_role:
        name: mssql
        tasks_from: alwayson.yml
      tags:
        - alwayson
```

### `ansible.cfg` (in `python-fastapi-mssql/`, next to `app/`)

```ini
[defaults]
log_path = ./logs/ansible.log
host_key_checking = False
```

This persists every `ansible-playbook` run's full output to
`logs/ansible.log`, independent of the FastAPI process restarting. Without
it, output only lives in FastAPI's in-memory task history — gone on restart.
`log_path` resolves relative to whatever directory `uvicorn` is started from,
so always launch it from `python-fastapi-mssql/`.

## Part 5 — The FastAPI service

### `requirements.txt`

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
paramiko==3.4.0
psutil==5.9.6
python-multipart==0.0.6
ansible-core==2.13.13
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2
```

### `app/__init__.py` / `app/routes/__init__.py`

```python
"""App package initialization"""
```
```python
"""Routes package initialization"""
```

### `app/config.py`

```python
"""Configuration module"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)
    
    # Application
    APP_NAME: str = "MSSQL Deployment API"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # MSSQL Configuration
    MSSQL_SA_PASSWORD: str = os.getenv("MSSQL_SA_PASSWORD", "YourStr0ng!Passw0rd")
    MSSQL_VERSION: str = os.getenv("MSSQL_VERSION", "2019")
    MSSQL_EDITION: str = os.getenv("MSSQL_EDITION", "Developer")
    MSSQL_PORT: int = int(os.getenv("MSSQL_PORT", "1433"))
    
    # VMware NAT target addresses.
    VM1_HOST: str = os.getenv("VM1_HOST", os.getenv("VM1_IP", "192.168.70.129"))
    VM2_HOST: str = os.getenv("VM2_HOST", os.getenv("VM2_IP", "192.168.70.130"))
    VM1_USER: str = os.getenv("VM1_USER", "root")
    VM2_USER: str = os.getenv("VM2_USER", "root")

    # SSH Configuration
    SSH_PORT: int = int(os.getenv("SSH_PORT", "22"))
    SSH_KEY_PATH: str = os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa")
    SSH_PASSWORD: str = os.getenv("SSH_PASSWORD", "")
    SSH_TIMEOUT: int = int(os.getenv("SSH_TIMEOUT", "30"))
    
    # Backup Configuration
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "/backup")
    BACKUP_STRIPES: int = int(os.getenv("BACKUP_STRIPES", "10"))
    LOCAL_BACKUP_DIR: str = os.getenv("LOCAL_BACKUP_DIR", "./backups/vm1_striped")
    LOCAL_CERT_RELAY_DIR: str = os.getenv("LOCAL_CERT_RELAY_DIR", "./backups/ag_certs")
    DATA_DIR: str = os.getenv("DATA_DIR", "/var/opt/mssql/data")
    MSSQL_LOG_DIR: str = os.getenv("MSSQL_LOG_DIR", "/var/opt/mssql/log")

    # Ansible Configuration
    ANSIBLE_INVENTORY: str = os.getenv("ANSIBLE_INVENTORY", "./ansible/inventory/hosts.ini")
    ANSIBLE_PLAYBOOK_DIR: str = os.getenv("ANSIBLE_PLAYBOOK_DIR", "./ansible/playbooks")
    ANSIBLE_CMD: str = os.getenv("ANSIBLE_CMD", "ansible-playbook")
    ANSIBLE_VERBOSE: int = int(os.getenv("ANSIBLE_VERBOSE", "1"))
    ANSIBLE_PRIVATE_KEY_FILE: str = os.getenv("ANSIBLE_PRIVATE_KEY_FILE", "~/.ssh/id_rsa")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")
    
    # API
    API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "3600"))  # 1 hour

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        """Handle common non-boolean DEBUG values from host environments."""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).lower() in {"1", "true", "yes", "on", "debug", "development"}

settings = Settings()
```

### `app/ansible_runner.py`

```python
"""Ansible integration helper for FastAPI deployment."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.config import settings


class AnsibleRunner:
    """Execute Ansible playbooks from the FastAPI application."""

    def __init__(self) -> None:
        self.inventory = Path(settings.ANSIBLE_INVENTORY)
        self.playbook_dir = Path(settings.ANSIBLE_PLAYBOOK_DIR)
        self.command = settings.ANSIBLE_CMD

    def _resolve_command(self) -> str:
        """Resolve the Ansible executable from PATH or the active Python environment."""
        if os.path.isabs(self.command) or os.sep in self.command or (os.altsep and os.altsep in self.command):
            return self.command

        resolved = shutil.which(self.command)
        if resolved:
            return resolved

        if os.name == "nt":
            scripts_dir = Path(sys.prefix) / "Scripts"
            candidate = scripts_dir / f"{self.command}.exe"
            if candidate.exists():
                return str(candidate)
            fallback = scripts_dir / self.command
            if fallback.exists():
                return str(fallback)

        return self.command

    def run_playbook(
        self,
        playbook_name: str,
        tags: Optional[Iterable[str]] = None,
        limit: Optional[str] = None,
        extra_vars: Optional[Dict[str, object]] = None,
        skip_tags: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        """Run an Ansible playbook and return structured execution details."""
        playbook_path = self.playbook_dir / playbook_name
        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")

        command = [self._resolve_command(), "-i", str(self.inventory), str(playbook_path)]
        if tags:
            command.extend(["-t", ",".join(tags)])
        if skip_tags:
            command.extend(["--skip-tags", ",".join(skip_tags)])
        if limit:
            command.extend(["-l", limit])
        if settings.ANSIBLE_PRIVATE_KEY_FILE:
            command.extend(["--private-key", os.path.expanduser(settings.ANSIBLE_PRIVATE_KEY_FILE)])
        if extra_vars:
            command.extend(["-e", json.dumps(extra_vars)])
        if settings.ANSIBLE_VERBOSE and settings.ANSIBLE_VERBOSE > 0:
            command.append("-" + "v" * settings.ANSIBLE_VERBOSE)

        env = os.environ.copy()
        env["ANSIBLE_FORCE_COLOR"] = "false"
        env["ANSIBLE_HOST_KEY_CHECKING"] = "false"
        env["ANSIBLE_DEPRECATION_WARNINGS"] = "False"
        if settings.ANSIBLE_PRIVATE_KEY_FILE:
            env["ANSIBLE_PRIVATE_KEY_FILE"] = os.path.expanduser(settings.ANSIBLE_PRIVATE_KEY_FILE)

        start_time = datetime.utcnow()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=env,
                timeout=settings.API_TIMEOUT,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Ansible executable not found: {self._resolve_command()}") from exc
        except OSError as exc:
            raise RuntimeError(f"Unable to launch Ansible: {exc}") from exc
        end_time = datetime.utcnow()

        return {
            "playbook": str(playbook_path),
            "command": " ".join(shlex.quote(part) for part in command),
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "started_at": start_time.isoformat() + "Z",
            "completed_at": end_time.isoformat() + "Z",
            "duration_seconds": (end_time - start_time).total_seconds(),
            "success": result.returncode == 0,
        }

    def validate_inventory(self) -> Dict[str, object]:
        """Validate the configured inventory file exists."""
        return {
            "inventory_path": str(self.inventory),
            "exists": self.inventory.exists(),
            "playbook_dir": str(self.playbook_dir),
            "playbook_dir_exists": self.playbook_dir.exists(),
        }
```

### `app/deployer.py`

```python
"""Deployment orchestration wrapper for FastAPI."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from app.ansible_runner import AnsibleRunner
from app.config import settings


logger = logging.getLogger(__name__)


class SequenceStepError(RuntimeError):
    """Raised when one step of a multi-playbook sequence fails, carrying the partial results."""

    def __init__(self, message: str, results: Dict[str, object]) -> None:
        super().__init__(message)
        self.results = results


class AnsibleMssqlDeployer:
    """Deploy MSSQL using Ansible playbooks."""

    def __init__(self) -> None:
        self.ansible = AnsibleRunner()
        self._history: List[Dict] = []
        self._lock = threading.Lock()

    def start_task(self, operation: str) -> str:
        task_id = str(uuid.uuid4())
        self._record(
            {
                "task_id": task_id,
                "operation": operation,
                "status": "queued",
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "results": None,
                "error": None,
            }
        )
        return task_id

    def get_history(self) -> List[Dict]:
        with self._lock:
            return list(self._history)

    def _record(self, record: Dict) -> None:
        with self._lock:
            self._history.insert(0, record)

    def _update(self, task_id: str, **changes) -> None:
        with self._lock:
            task = next(item for item in self._history if item["task_id"] == task_id)
            task.update(changes)

    def _run_task(self, task_id: str, action) -> None:
        self._update(task_id, status="running")
        try:
            result = action()
            self._update(
                task_id,
                status="success",
                completed_at=datetime.now().isoformat(),
                results=result,
            )
        except Exception as exc:
            logger.exception("Deployment task failed")
            self._update(
                task_id,
                status="failed",
                completed_at=datetime.now().isoformat(),
                error=str(exc),
                results=getattr(exc, "results", None),
            )

    def deploy_install(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self.ansible.run_playbook("site.yml", extra_vars=self._build_extra_vars()))

    def deploy_backup_restore(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self.ansible.run_playbook("backup.yml", extra_vars=self._build_extra_vars()))

    def deploy_alwayson(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self.ansible.run_playbook("alwayson.yml", extra_vars=self._build_extra_vars()))

    def deploy_full_ag(self, task_id: str) -> None:
        self._run_task(task_id, self._run_full_ag_sequence)

    def _run_full_ag_sequence(self) -> Dict[str, object]:
        results: Dict[str, object] = {}
        results["restore_vm1"] = self.ansible.run_playbook(
            "site.yml",
            limit="vm1",
            extra_vars=self._build_extra_vars(),
        )
        if not results["restore_vm1"]["success"]:
            raise SequenceStepError("restore_vm1 step failed; see results.restore_vm1 for details", results)

        results["backup_restore_vm2"] = self.ansible.run_playbook(
            "backup.yml",
            extra_vars=self._build_extra_vars(),
        )
        if not results["backup_restore_vm2"]["success"]:
            raise SequenceStepError("backup_restore_vm2 step failed; see results.backup_restore_vm2 for details", results)

        results["alwayson"] = self.ansible.run_playbook(
            "alwayson.yml",
            extra_vars=self._build_extra_vars(),
        )
        if not results["alwayson"]["success"]:
            raise SequenceStepError("alwayson step failed; see results.alwayson for details", results)

        return results

    def deploy_build(self, task_id: str) -> None:
        """Run the MSSQL build playbook which prepares hosts and runs the mssql_build role."""
        self._run_task(task_id, lambda: self.ansible.run_playbook("build.yml", extra_vars=self._build_extra_vars()))

    def get_hosts(self) -> Dict:
        return {
            "hosts": [
                {"name": "vm1", "host": settings.VM1_HOST, "user": settings.VM1_USER, "port": settings.SSH_PORT},
                {"name": "vm2", "host": settings.VM2_HOST, "user": settings.VM2_USER, "port": settings.SSH_PORT},
            ]
        }

    def resolve_hosts(self) -> Dict:
        import socket

        results = {}
        for hostname in [settings.VM1_HOST, settings.VM2_HOST]:
            try:
                results[hostname] = {
                    "address": socket.gethostbyname(hostname),
                    "resolved": True,
                }
            except OSError as exc:
                results[hostname] = {
                    "resolved": False,
                    "error": str(exc),
                }
        return results

    def ping_hosts(self) -> Dict:
        import socket

        results = []
        for host in [settings.VM1_HOST, settings.VM2_HOST]:
            try:
                with socket.create_connection((host, settings.SSH_PORT), timeout=settings.SSH_TIMEOUT):
                    results.append({"host": host, "status": "reachable"})
            except Exception as exc:
                results.append({"host": host, "status": "unreachable", "error": str(exc)})
        return {
            "status": "success" if all(r["status"] == "reachable" for r in results) else "failed",
            "results": results,
        }

    def install_tools(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self.ansible.run_playbook("site.yml", tags=["install", "tools"], extra_vars=self._build_extra_vars()))

    def restore_adventureworks(self, task_id: str) -> None:
        self._run_task(
            task_id,
            lambda: self.ansible.run_playbook(
                "site.yml",
                limit="vm1",
                extra_vars=self._build_extra_vars(),
            ),
        )

    def _build_extra_vars(self) -> Dict[str, object]:
        return {
            "sa_password": settings.MSSQL_SA_PASSWORD,
            "mssql_version": settings.MSSQL_VERSION,
            "mssql_edition": settings.MSSQL_EDITION,
            "backup_dir": settings.BACKUP_DIR,
            "data_dir": settings.DATA_DIR,
            "log_dir": settings.MSSQL_LOG_DIR,
            "mssql_port": settings.MSSQL_PORT,
            "ansible_private_key_file": settings.ANSIBLE_PRIVATE_KEY_FILE,
            "local_backup_dir": settings.LOCAL_BACKUP_DIR,
            "local_cert_relay_dir": settings.LOCAL_CERT_RELAY_DIR,
        }
```

`SequenceStepError` is what makes `full-ag` trustworthy — without it (bug #4
in the build-history doc), the deployer used to march on to the next playbook
even after a prior one failed, and still report the whole thing as
`"success"`.

`deploy_build`/`get_hosts` reference `build.yml` and the `mssql_build` role —
you don't need to create those for this build to work; see the Appendix.

### `app/routes/deploy.py`

```python
"""Deployment routes"""
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
import logging
from app.config import settings
from app.deployer import AnsibleMssqlDeployer

router = APIRouter()
logger = logging.getLogger(__name__)

deployer = AnsibleMssqlDeployer()


@router.get("/status")
async def get_deployment_status():
    """Get current deployment status"""
    history = deployer.get_history()
    latest = history[0] if history else None
    return {
        "status": latest["status"] if latest else "ready",
        "latest_task": latest,
        "engine": "ansible",
        "mssql_version": settings.MSSQL_VERSION,
        "mssql_edition": settings.MSSQL_EDITION,
        "vm1": settings.VM1_HOST,
        "vm2": settings.VM2_HOST
    }


@router.post("/install")
async def deploy_install(background_tasks: BackgroundTasks):
    """Deploy and install MSSQL on all servers

    This is a long-running operation (30-60 minutes).
    Returns immediately with a status ID.
    """

    logger.info("Received deployment request - Install MSSQL")

    try:
        task_id = deployer.start_task("install")
        background_tasks.add_task(deployer.deploy_install, task_id)

        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "MSSQL installation started",
            "engine": "ansible",
            "playbook": "site.yml",
            "estimated_duration_minutes": 45,
            "instructions": "Check /api/v1/deploy/status or /api/v1/deploy/history for progress"
        }

    except Exception as e:
        logger.error(f"Error initiating deployment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate deployment: {str(e)}"
        )


@router.post("/backup")
async def deploy_backup(background_tasks: BackgroundTasks):
    """Create 10-stripe backup on VM1 and transfer to VM2

    Prerequisites: MSSQL must be installed and AdventureWorks DB must exist
    This operation takes 10-20 minutes depending on database size.
    """

    logger.info("Received deployment request - Backup and Restore")

    try:
        task_id = deployer.start_task("backup-restore")
        background_tasks.add_task(deployer.deploy_backup_restore, task_id)

        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "Backup and restore process started",
            "engine": "ansible",
            "playbook": "backup.yml",
            "operations": [
                "Create 10-stripe backup on VM1",
                "Transfer backup files to VM2",
                "Restore AdventureWorks on VM2"
            ],
            "estimated_duration_minutes": 15
        }

    except Exception as e:
        logger.error(f"Error initiating backup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate backup: {str(e)}"
        )


@router.post("/alwayson")
async def deploy_alwayson(background_tasks: BackgroundTasks):
    """Configure Always-On Availability Group across VM1 and VM2"""
    logger.info("Received deployment request - Configure Always On")
    try:
        task_id = deployer.start_task("alwayson")
        background_tasks.add_task(deployer.deploy_alwayson, task_id)

        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "Always On availability group deployment started",
            "engine": "ansible",
            "playbook": "alwayson.yml",
            "estimated_duration_minutes": 30,
            "operations": [
                "Verify MSSQL connectivity",
                "Create AG endpoints",
                "Create and join availability group",
                "Verify AG health"
            ]
        }
    except Exception as e:
        logger.error(f"Error initiating Always-On deployment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate Always-On deployment: {str(e)}"
        )


@router.post("/full-ag")
async def deploy_full_ag(background_tasks: BackgroundTasks):
    """Restore AdventureWorks to VM1, create a striped backup, copy to VM2, restore there, and configure AG."""
    logger.info("Received deployment request - Full AG workflow")
    try:
        task_id = deployer.start_task("full-ag")
        background_tasks.add_task(deployer.deploy_full_ag, task_id)

        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "Full AdventureWorks backup/restore and Always On workflow started",
            "engine": "ansible",
            "playbooks": ["site.yml", "backup.yml", "alwayson.yml"],
            "operations": [
                "Restore AdventureWorks on VM1",
                "Create 10-stripe backup on VM1",
                "Transfer backup to VM2 and restore",
                "Configure Always On availability group"
            ],
            "estimated_duration_minutes": 90,
        }
    except Exception as e:
        logger.error(f"Error initiating full AG workflow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate full AG workflow: {str(e)}"
        )


@router.get("/history")
async def get_deployment_history():
    """Get deployment execution history"""
    try:
        history = deployer.get_history()
        return {
            "total_executions": len(history),
            "executions": history
        }
    except Exception as e:
        logger.error(f"Error retrieving history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve history: {str(e)}"
        )


@router.get("/hosts")
async def get_target_hosts():
    """Get target host information"""
    try:
        inventory = deployer.get_hosts()
        return {
            "status": "success",
            "inventory": inventory,
            "dns": deployer.resolve_hosts(),
            "ansible_inventory": settings.ANSIBLE_INVENTORY,
            "ansible_playbooks": settings.ANSIBLE_PLAYBOOK_DIR,
        }
    except Exception as e:
        logger.error(f"Error retrieving hosts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve hosts: {str(e)}"
        )


@router.post("/ping")
async def ping_hosts():
    """Ping all target hosts to verify connectivity"""
    try:
        result = deployer.ping_hosts()
        return result
    except Exception as e:
        logger.error(f"Error pinging hosts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ping hosts: {str(e)}"
        )
```

The real file also has `POST /install-tools`, `POST /build`, and
`POST /restore-db` routes. `install-tools`/`restore-db` are thin wrappers
around `site.yml` (fine to add, not needed for this walkthrough); `build`
wires to `mssql_build`/`build.yml`, which is in the Appendix, not this guide.

### `app/routes/health.py`

```python
"""Health check routes"""
from fastapi import APIRouter, status
from datetime import datetime
import psutil
import os
from pathlib import Path

router = APIRouter()


@router.get("/check")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "MSSQL Deployment API",
        "version": "1.0.0"
    }


@router.get("/ready")
async def readiness_check():
    """Readiness check - verifies all dependencies"""
    
    checks = {
        "python_ssh": verify_python_ssh(),
        "ssh_key": verify_ssh_credentials(),
        "vmware_dns": verify_vmware_dns(),
        "disk_space": check_disk_space(),
        "system_resources": check_system_resources()
    }
    
    all_ready = all(check.get("ready", False) for check in checks.values())
    
    return {
        "ready": all_ready,
        "timestamp": datetime.now().isoformat(),
        "checks": checks
    }


@router.get("/live")
async def liveness_check():
    """Liveness check - verifies API is running"""
    return {
        "alive": True,
        "timestamp": datetime.now().isoformat()
    }


def verify_python_ssh() -> dict:
    """Verify Paramiko is installed for Python SSH execution."""
    try:
        import paramiko
        return {
            "ready": True,
            "component": "Python SSH",
            "library": "paramiko",
            "version": paramiko.__version__
        }
    except ImportError:
        return {
            "ready": False,
            "component": "Python SSH",
            "error": "paramiko not found"
        }


def verify_ssh_credentials() -> dict:
    """Verify either an SSH key or password is configured."""
    from app.config import settings

    if settings.SSH_PASSWORD:
        return {
            "ready": True,
            "component": "SSH credentials",
            "method": "password"
        }

    key_path = Path(os.path.expanduser(settings.SSH_KEY_PATH))
    if key_path.exists():
        return {
            "ready": True,
            "component": "SSH credentials",
            "method": "key",
            "path": str(key_path)
        }

    return {
        "ready": False,
        "component": "SSH credentials",
        "error": f"SSH key not found at {key_path}; set SSH_KEY_PATH or SSH_PASSWORD"
    }


def verify_vmware_dns() -> dict:
    """Verify VMware hostnames resolve from this API runtime."""
    from app.routes.deploy import deployer

    results = deployer.resolve_hosts()
    return {
        "ready": all(item["resolved"] for item in results.values()),
        "component": "VMware DNS",
        "hosts": results
    }


def check_disk_space() -> dict:
    """Check available disk space"""
    try:
        disk = psutil.disk_usage("/")
        available_gb = disk.free / (1024 ** 3)
        
        return {
            "ready": available_gb > 5,  # Need at least 5GB
            "component": "Disk Space",
            "available_gb": round(available_gb, 2),
            "total_gb": round(disk.total / (1024 ** 3), 2),
            "used_percent": disk.percent
        }
    except Exception as e:
        return {
            "ready": False,
            "component": "Disk Space",
            "error": str(e)
        }


def check_system_resources() -> dict:
    """Check system resources"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        return {
            "ready": cpu_percent < 90 and memory.percent < 90,
            "component": "System Resources",
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "available_memory_gb": round(memory.available / (1024 ** 3), 2)
        }
    except Exception as e:
        return {
            "ready": False,
            "component": "System Resources",
            "error": str(e)
        }
```

> **Heads up while reading this file:** `verify_python_ssh`/`verify_ssh_credentials`
> are named after the Paramiko-SSH architecture from before this service was
> refactored to Ansible (see the build-history doc's Phase 2). They still run
> and don't error, but they don't actually check anything about Ansible or
> `ansible-playbook` — `/health/ready` reporting `"ready": true` doesn't mean
> the Ansible side is actually usable. If you want a real readiness signal,
> check `GET /api/v1/deploy/hosts` instead.

### `app/routes/logs.py`

```python
"""Logging and output routes"""
from fastapi import APIRouter, HTTPException, status
from datetime import datetime, timedelta
import os
import logging
from pathlib import Path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/latest")
async def get_latest_logs(lines: int = 100):
    """Get latest log entries
    
    Args:
        lines: Number of lines to return (default 100)
    """
    from app.config import settings
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if not os.path.exists(log_file):
            return {
                "status": "no logs",
                "message": "No log file found yet",
                "log_path": log_file
            }
        
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        
        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return {
            "status": "success",
            "total_lines": len(all_lines),
            "returned_lines": len(recent_lines),
            "log_path": log_file,
            "logs": "".join(recent_lines)
        }
    
    except Exception as e:
        logger.error(f"Error retrieving logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve logs: {str(e)}"
        )


@router.get("/level/{level}")
async def get_logs_by_level(level: str = "ERROR", lines: int = 50):
    """Get logs filtered by level"""
    from app.config import settings
    
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    
    if level.upper() not in valid_levels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid log level. Must be one of: {', '.join(valid_levels)}"
        )
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if not os.path.exists(log_file):
            return {"status": "no logs", "message": "No log file found yet"}
        
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        
        filtered_lines = [line for line in all_lines if level.upper() in line]
        recent_lines = filtered_lines[-lines:] if len(filtered_lines) > lines else filtered_lines
        
        return {
            "status": "success",
            "level": level.upper(),
            "total_entries": len(filtered_lines),
            "returned_entries": len(recent_lines),
            "logs": "".join(recent_lines)
        }
    
    except Exception as e:
        logger.error(f"Error retrieving logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve logs: {str(e)}"
        )


@router.get("/since")
async def get_logs_since(minutes: int = 30):
    """Get logs from the last N minutes"""
    from app.config import settings
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if not os.path.exists(log_file):
            return {"status": "no logs", "message": "No log file found yet"}
        
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        
        recent_lines = []
        for line in all_lines:
            try:
                timestamp = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                if timestamp >= cutoff_time:
                    recent_lines.append(line)
            except ValueError:
                if recent_lines:
                    recent_lines.append(line)
        
        return {
            "status": "success",
            "minutes_back": minutes,
            "cutoff_time": cutoff_time.isoformat(),
            "entries": len(recent_lines),
            "logs": "".join(recent_lines[-100:])
        }
    
    except Exception as e:
        logger.error(f"Error retrieving logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve logs: {str(e)}"
        )


@router.post("/clear")
async def clear_logs():
    """Clear all log files (use with caution)"""
    from app.config import settings
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if os.path.exists(log_file):
            with open(log_file, "w") as f:
                f.write("")
            
            return {
                "status": "success",
                "message": "Logs cleared",
                "log_path": log_file
            }
        else:
            return {
                "status": "info",
                "message": "No log file to clear"
            }
    
    except Exception as e:
        logger.error(f"Error clearing logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear logs: {str(e)}"
        )


@router.get("/info")
async def get_log_info():
    """Get log file information"""
    from app.config import settings
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if os.path.exists(log_file):
            stat_info = os.stat(log_file)
            
            return {
                "status": "success",
                "log_path": log_file,
                "size_bytes": stat_info.st_size,
                "size_mb": round(stat_info.st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                "accessible": True
            }
        else:
            return {
                "status": "no logs",
                "log_path": log_file,
                "message": "No log file exists yet"
            }
    
    except Exception as e:
        logger.error(f"Error getting log info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get log info: {str(e)}"
        )
```

Note: this file reads `logs/app.log` (FastAPI's own request/error log), not
`logs/ansible.log` (the full `ansible-playbook` output from `ansible.cfg`).
For watching an actual deployment run, `tail -f logs/ansible.log` directly —
these `/logs/*` endpoints won't show you Ansible's output.

### `app/main.py`

```python
"""
MSSQL FastAPI Deployment Service
Main application entry point
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.responses import JSONResponse
import logging
from pathlib import Path

# Import routers
from app.routes import deploy, health, logs
from app.config import settings

# Logging configuration
Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(Path(settings.LOG_DIR) / "app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="MSSQL Deployment API",
    description="FastAPI service for MSSQL deployment automation using embedded Ansible playbooks",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Include routers
app.include_router(deploy.router, prefix="/api/v1/deploy", tags=["deployment"])
app.include_router(health.router, prefix="/api/v1/health", tags=["health"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["logs"])


@app.get("/", tags=["root"])
async def root():
    """Root endpoint - API information"""
    return {
        "service": "MSSQL Deployment API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/api/docs",
        "endpoints": {
            "deploy": "/api/v1/deploy",
            "health": "/api/v1/health",
            "logs": "/api/v1/logs",
        }
    }


@app.get("/api/v1/", tags=["api"])
async def api_root():
    """API v1 root"""
    return {
        "version": "1.0.0",
        "endpoints": {
            "deploy": "/api/v1/deploy",
            "health": "/api/v1/health",
            "logs": "/api/v1/logs",
        }
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
```

`docs_url="/api/docs"` is what puts the Swagger UI at `/api/docs` — used in
Part 8 below.

### `.env`

```bash
DEBUG=False
LOG_LEVEL=INFO

MSSQL_SA_PASSWORD=YourStr0ng!Passw0rd
MSSQL_VERSION=2019
MSSQL_EDITION=Developer
MSSQL_PORT=1433

VM1_HOST=192.168.70.129
VM2_HOST=192.168.70.130
VM1_USER=devops
VM2_USER=devops

SSH_PORT=22
SSH_KEY_PATH=/home/devops/.ssh/id_rsa
SSH_PASSWORD=
SSH_TIMEOUT=30

ANSIBLE_INVENTORY=./ansible/inventory/hosts.ini
ANSIBLE_PLAYBOOK_DIR=./ansible/playbooks
ANSIBLE_CMD=ansible-playbook
ANSIBLE_PRIVATE_KEY_FILE=/home/devops/.ssh/id_rsa
ANSIBLE_VERBOSE=1

BACKUP_DIR=/backup
BACKUP_STRIPES=10
LOCAL_BACKUP_DIR=./backups/vm1_striped
DATA_DIR=/var/opt/mssql/data
MSSQL_LOG_DIR=/var/opt/mssql/log

API_TIMEOUT=3600
```

Change `MSSQL_SA_PASSWORD` before any real use.

## Part 6 — Install and run

```bash
cd python-fastapi-mssql
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Confirm it's up:
```bash
curl http://localhost:8000/api/v1/health/check
```

## Part 7 — Build it: the CLI way

**1. Confirm both VMs are reachable:**
```bash
curl -X POST http://localhost:8000/api/v1/deploy/ping
curl http://localhost:8000/api/v1/deploy/hosts | jq
```

**2. Run the whole build in one call** — restores AdventureWorks on vm1,
stripes+transfers+restores the backup to vm2, then wires up the AG:
```bash
curl -X POST http://localhost:8000/api/v1/deploy/full-ag
```
This takes roughly 60–90 minutes end to end (AdventureWorks download +
install + AG sync). Watch it live:
```bash
tail -f logs/ansible.log
```

**3. Or run it step by step**, if you want to see each stage individually:
```bash
curl -X POST http://localhost:8000/api/v1/deploy/install    # site.yml, both VMs
curl -X POST http://localhost:8000/api/v1/deploy/backup     # backup.yml: stripe vm1 -> restore vm2
curl -X POST http://localhost:8000/api/v1/deploy/alwayson   # alwayson.yml: wire up the AG
```

**4. Check progress/result at any point:**
```bash
curl http://localhost:8000/api/v1/deploy/status | jq
curl http://localhost:8000/api/v1/deploy/history | jq '.executions[0]'
```

**5. Verify independently** — don't just trust the playbook's own `debug`
output:
```bash
/opt/mssql-tools/bin/sqlcmd -S localhost -U SA -P '<sa_password>' -h -1 -W -Q \
  "SELECT ar.replica_server_name, ars.role_desc, ars.synchronization_health_desc FROM sys.dm_hadr_availability_replica_states ars JOIN sys.availability_replicas ar ON ar.replica_id = ars.replica_id"
```
Expect `devops_VM1 PRIMARY HEALTHY` and `devops_VM2 SECONDARY HEALTHY`.

## Part 8 — Build it: the Swagger UI way

1. Open `http://<vm1-ip>:8000/api/docs` in a browser (or
   `http://localhost:8000/api/docs` if you're on VM1 itself).
2. Expand **deployment → POST /api/v1/deploy/ping**, click **Try it out**,
   then **Execute**. Confirm both hosts come back `"reachable"`.
3. Expand **POST /api/v1/deploy/full-ag**, **Try it out**, **Execute** with an
   empty body. The response body shows `"status": "initiated"` and a
   `task_id` immediately — the actual Ansible run continues in the
   background, it hasn't finished yet.
4. Poll progress the same way: expand **GET /api/v1/deploy/status** or
   **GET /api/v1/deploy/history**, **Try it out**, **Execute**, re-run
   **Execute** again every so often. `status` moves from `"running"` to
   `"success"` (or `"failed"`, with `error` and partial `results` from
   `SequenceStepError` if a step broke).
5. Everything under **health** and **logs** in the same Swagger page is safe
   to click at any time — they're all read-only `GET`s (except
   `POST /logs/clear`, which does exactly what it says).

Swagger UI is just a browser front-end for the same HTTP calls `curl` makes
— nothing here is Swagger-specific state; `GET /history` from `curl` and from
the browser show the same in-memory task list.

## Part 9 — Rerun it

**If the VMs are still bare** (nothing installed, or you've torn it down —
see below), rerunning is identical to Part 7/8: `POST /deploy/full-ag` again.

**If the AG is already built and healthy**, calling `full-ag` again will
**not** cleanly rebuild it — `site.yml`'s AdventureWorks restore step tries
`RESTORE DATABASE ... WITH REPLACE`, which SQL Server refuses while that
database is part of an Availability Group. You'll see the `restore_vm1` step
fail in `/deploy/history`. `alwayson.yml`'s own steps are individually
guarded (`IF NOT EXISTS`), so re-running *only* `POST /deploy/alwayson` on an
already-healthy AG is harmless — it's specifically `full-ag`'s restore step
that conflicts with an existing AG.

To do a real clean rerun on top of an existing build, tear it down first —
that workflow (`POST /deploy/teardown`, `/rewind`, `/reset-baseline`) is
covered in
[`mssql-rewind-and-teardown-implementation.md`](mssql-rewind-and-teardown-implementation.md).
Once that's in place, the clean-rerun sequence is:
```bash
curl -X POST http://localhost:8000/api/v1/deploy/reset-baseline   # wipe both VMs
curl -X POST http://localhost:8000/api/v1/deploy/full-ag           # rebuild from bare
```
or the equivalent clicks in Swagger UI, same endpoints.

## Appendix — code in this repo you can ignore

**Dead code — nothing imports or calls it:**

| Path | What it is | Why it's dead |
|---|---|---|
| `python-fastapi-mssql/app/python_deployer.py` | A full Paramiko SSH/SFTP implementation (`PythonMssqlDeployer`) | Retired when the service moved back to Ansible (build-history Phase 2 → 4). `routes/deploy.py` imports `AnsibleMssqlDeployer` from `deployer.py`, never this file. |

**Not dead, but not part of this build — a separate/parallel system:**

| Path | What it is | Why it's not this guide |
|---|---|---|
| `ansible-mssql-deploy/` (repo root) | A second, independent Ansible tree meant for AWX/GitLab-driven deployment | Diverged from `python-fastapi-mssql/ansible/` on purpose (build-history Phase 4) — different playbooks, different inventory, no AG support at all. Editing it has zero effect on the FastAPI service you just built. |
| `python-fastapi-mssql/ansible/roles/mssql_build/` + `playbooks/build.yml` + `deploy_build()`/`POST /deploy/build` | A second, redundant "prepare + install" flow | Real and working, but duplicates what `site.yml`'s `install.yml`/`configure.yml` already do. Not required for `full-ag`, and not covered in Part 3/4 above. |
| Top-level docs: `ARCHITECTURE.md`, `INDEX.md`, `PROJECT_INDEX.md`, `DELIVERY_SUMMARY.md`, `COMPLETION_SUMMARY.txt`, `IMPLEMENTATION_HANDOFF.md` | Early generated project docs | Not reliably kept in sync with the code (`ARCHITECTURE.md` still diagrams the retired Paramiko/SSH design). Trust `RUNBOOK.md`, `CHANGELOG.md`, and the actual code over these. |

**Live code with a misleading name — not dead, but don't be fooled by it:**

`app/routes/health.py`'s `GET /api/v1/health/ready` calls
`verify_python_ssh()`/`verify_ssh_credentials()`, checking for Paramiko and
an SSH key — leftover naming from the Phase-2 architecture. It still runs
today (harmless), but a `"ready": true` from this endpoint says nothing about
whether Ansible/`ansible-playbook` is actually usable. Use
`GET /api/v1/deploy/hosts` (DNS resolution) plus `POST /api/v1/deploy/ping`
(TCP reachability) for a real signal instead.
