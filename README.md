# ansible-iptables role

Role for configuring iptables/ip6tables on Ubuntu servers, providing flexible firewall configuration with automatic interface detection and incremental rule application.

## Features

* Uses iptables/ip6tables with ephemeral INPUT_DOCKER chain for simplified configuration
* Supports both IPv4 and IPv6 (configured separately)
* **Manages only its own rules** - does not modify or delete rules created by other services (Docker, fail2ban, etc.)
* Automatically detects external network interfaces (excluding lo and docker*)
* Automatic Docker integration: rules from INPUT_DOCKER are duplicated to INPUT and DOCKER-USER chains with Docker adaptations
* Implements hierarchical structure `/etc/firewall/rules.d/4/<table>/<chain>/*.rules` for IPv4 and `/etc/firewall/rules.d/6/<table>/<chain>/*.rules` for IPv6
* Incremental rule application with rollback capability on errors
* Uses NOTRACK for optimizing incoming traffic on ports 22, 80, 443, 53
* Supports rule prioritization through file prefixes
* Creates systemd firewall service for automatic rule application on boot
* Includes custom Ansible module for generating rule structure

## Default Variables

### Basic Settings
* `iptables_enabled: true` - Enable iptables service
* `ip6tables_enabled: true` - Enable IPv6 rules
* `iptables_rules_dir: /etc/firewall/rules.d/4` - IPv4 rules directory
* `ip6tables_rules_dir: /etc/firewall/rules.d/6` - IPv6 rules directory
* `iptables_state_dir: /var/lib/iptables-ng/state` - State directory for tracking changes
* `external_interfaces: []` - List of external interfaces (if empty, determined automatically)

### Rule Structure
Rules are defined in the format:
```yaml
iptables_rules:
  <table>:
    <chain>:
      - rule: "<iptables rule without chain>"
        comment: "Optional comment"
        priority: 10  # Numeric priority (default: 50)
        interfaces: ["eth0", "eth1"]  # Optional: apply rule per interface
```

### Ephemeral INPUT_DOCKER Chain
The new logic uses a special ephemeral `INPUT_DOCKER` chain that:
* **Automatically duplicates rules to INPUT chain** - rules are applied as-is
* **Automatically duplicates rules to DOCKER-USER chain** with modifications:
  - `-j ACCEPT` is replaced with `-j RETURN`
  - `--dport` is replaced with `-m conntrack --ctorigdstport` for conntrack
  - `-d` is replaced with `-m conntrack --ctorigdst` for conntrack
  - Rules with `-i lo` are skipped for DOCKER-USER (not relevant)
* Simplifies configuration - one set of rules applies to both chains

### Default IPv4 Rules
Variables `iptables_rules` and `ip6tables_rules` are used only for configuring the role's default rules:
```yaml
iptables_rules:
  filter:
    INPUT_DOCKER:
      - rule: "-m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT"
        comment: "Accept established/related connections"
        priority: 10
      - rule: "-i lo -j ACCEPT"
        comment: "Accept traffic from loopback"
        priority: 10
      - rule: "-p tcp --dport 22 -j ACCEPT"
        comment: "Accept SSH (22/tcp)"
        priority: 10
      - rule: "-p tcp --dport 80 -j ACCEPT"
        comment: "Accept HTTP (80/tcp)"
        priority: 10
      - rule: "-p tcp --dport 443 -j ACCEPT"
        comment: "Accept HTTPS (443/tcp)"
        priority: 10
      - rule: "-p tcp --dport 53 -j ACCEPT"
        comment: "Accept DNS TCP (53/tcp)"
        priority: 10
      - rule: "-p udp --dport 53 -j ACCEPT"
        comment: "Accept DNS UDP (53/udp)"
        priority: 10
      - rule: "-j LOG --log-prefix \"iptables-drop: \""
        comment: "Log dropped packets"
        priority: 98
      - rule: "-j DROP"
        comment: "Drop everything else"
        priority: 99
  raw:
    PREROUTING:
      - rule: "-p tcp --dport 22 -j NOTRACK"
        comment: "NOTRACK for SSH"
        priority: 20
        interfaces: "{{ external_interfaces }}"
      - rule: "-p tcp --dport 80 -j NOTRACK"
        comment: "NOTRACK for HTTP"
        priority: 20
        interfaces: "{{ external_interfaces }}"
      - rule: "-p tcp --dport 443 -j NOTRACK"
        comment: "NOTRACK for HTTPS"
        priority: 20
        interfaces: "{{ external_interfaces }}"
      - rule: "-p tcp --dport 53 -j NOTRACK"
        comment: "NOTRACK for DNS TCP"
        priority: 20
        interfaces: "{{ external_interfaces }}"
      - rule: "-p udp --dport 53 -j NOTRACK"
        comment: "NOTRACK for DNS UDP"
        priority: 20
        interfaces: "{{ external_interfaces }}"
```

### Default IPv6 Rules
Similar `ip6tables_rules` structure with addition:
```yaml
ip6tables_rules:
  filter:
    INPUT_DOCKER:
      - rule: "-p ipv6-icmp -j ACCEPT"
        comment: "Accept all ICMPv6 messages"
        priority: 10
```

## Rules Directory Structure

Rules are organized in a hierarchical structure:

```
/etc/firewall/rules.d/
├── 4/                         # IPv4 rules
│   ├── filter/                # filter table
│   │   ├── INPUT_DOCKER/      # Ephemeral chain (automatically duplicated to INPUT and DOCKER-USER)
│   │   │   ├── 10-default.rules    # Main rules (priority=10)
│   │   │   ├── 50-custom.rules     # Custom rules (priority=50)
│   │   │   └── 98-drop.rules       # LOG and DROP (priority=98,99)
│   │   ├── INPUT/             # Direct INPUT rules (optional)
│   │   │   └── 00-custom.rules
│   │   └── DOCKER-USER/       # Direct DOCKER-USER rules (optional)
│   │       └── 00-custom.rules
│   └── raw/                   # raw table
│       └── PREROUTING/        # NOTRACK optimizations
│           └── 20-default.rules
└── 6/                         # IPv6 rules (similar structure)
    ├── filter/
    └── raw/
```

Rule files are named with the pattern: `{priority:02d}-{name}.rules`

## Usage

### Basic Usage
The role automatically applies default rules when enabled:

```yaml
- hosts: firewalls
  roles:
    - iptables-ng
```

### Adding Custom Rules via INPUT_DOCKER
```yaml
- hosts: web_servers
  roles:
    - iptables-ng
  tasks:
    - name: Add custom web service rules
      iptables_rules:
        rules:
          filter:
            INPUT_DOCKER:
              - rule: "-p tcp --dport 8080 -j ACCEPT"
                comment: "Allow custom web service"
                priority: 15
              - rule: "-s 192.168.1.0/24 -p tcp --dport 3306 -j ACCEPT"
                comment: "Allow MySQL from internal network"
                priority: 15
        dest: "/etc/firewall/rules.d/4"
        name: "webapp"
      notify: restart firewall
```

### Adding Rules Directly to INPUT or DOCKER-USER
```yaml
- hosts: special_servers
  roles:
    - iptables-ng
  tasks:
    - name: Add direct INPUT rules (not duplicated to DOCKER-USER)
      iptables_rules:
        rules:
          filter:
            INPUT:
              - rule: "-p tcp --dport 9000 -j ACCEPT"
                comment: "Direct INPUT rule"
                priority: 20
            DOCKER-USER:
              - rule: "-p tcp --dport 9001 -j RETURN"
                comment: "Direct DOCKER-USER rule"
                priority: 20
        dest: "/etc/firewall/rules.d/4"
        name: "direct-rules"
      notify: restart firewall
```

### Managing External Interfaces
```yaml
- hosts: edge_servers
  vars:
    external_interfaces: ["eth0", "eth1"]  # Override auto-detection
  roles:
    - iptables-ng
```

### Disabling IPv6
```yaml
- hosts: ipv4_only
  vars:
    ip6tables_enabled: false
  roles:
    - iptables-ng
```

## Custom iptables_rules Module

The role includes an `iptables_rules` module for adding custom rules to the rules directory. This is the primary way to add additional rules:

### Module Parameters:
* `rules` (dict, required) - Rule structure in table->chain->list format
* `dest` (path) - Path to rules directory (default: '/etc/firewall/rules.d')  
* `name` (str, required) - Name for generated rule files
* `owner`, `group`, `mode` - File owner and permissions

### Usage Example:
```yaml
- name: Generate custom application rules
  iptables_rules:
    rules:
      filter:
        INPUT_DOCKER:
          - rule: "-p tcp --dport 9000 -j ACCEPT"
            comment: "Allow application port"
            priority: 40
      raw:
        PREROUTING:
          - rule: "-p tcp --dport 9000 -j NOTRACK"
            comment: "NOTRACK for application"
            priority: 25
    dest: "/etc/firewall/rules.d/4"  # For IPv4
    name: "myapp"
  notify: restart firewall

# For IPv6 use dest: "/etc/firewall/rules.d/6"
```

## Systemd Service

The role creates a `firewall.service` that:
* Starts after network.target (and docker.service if Docker is installed)
* Executes `/etc/firewall/apply_rules.sh` on start
* Supports commands:
  * `systemctl start firewall` - Apply rules
  * `systemctl restart firewall` - Restart rules

## Rule Application Script

`/etc/firewall/apply_rules.sh` supports:
* `--flush` - Clear all rules before applying
* `--debug` - Enable debug output
* Incremental application with automatic rollback on errors
* Selective rule management - removes only previously created own rules
* State tracking through files in `{{ iptables_state_dir }}`

## Handlers

* `restart firewall` - Restarts systemd firewall service
* `reload systemd` - Reloads systemd configuration

## Requirements

* Ubuntu/Debian with iptables package
* Root privileges for executing iptables commands
* systemd for service management
* Docker (optional, for integration via DOCKER-USER chain)

## Notes

* **Custom rules are added only via the `iptables_rules` module**, not by overriding role variables
* Variables `iptables_rules` and `ip6tables_rules` are intended only for configuring the role's default rules
* **Rule management principle**: the role tracks and manages only the rules it created itself. During updates, only previously created role rules are removed, while rules from other services (Docker, fail2ban, ufw, etc.) remain untouched
* DOCKER-USER chain rules are applied only if Docker is installed
* The role uses `--noflush` for incremental rule application
* State is tracked for rollback capability on errors
* Automatic external interface detection excludes lo and docker*
* Rule prioritization is supported through numeric file prefixes

## INPUT_DOCKER Processing Logic

When using the ephemeral `INPUT_DOCKER` chain, the rule application script performs the following transformations:

### Duplication to INPUT
Rules from INPUT_DOCKER are copied to the INPUT chain without changes:
```bash
# Original rule in INPUT_DOCKER
-p tcp --dport 80 -j ACCEPT

# Becomes in INPUT
-A INPUT -p tcp --dport 80 -j ACCEPT
```

### Duplication to DOCKER-USER with Modifications
Rules are adapted for Docker operation:

1. **ACCEPT → RETURN**: `-j ACCEPT` is replaced with `-j RETURN`
2. **Ports**: `--dport` is replaced with `-m conntrack --ctorigdstport`
3. **IP addresses**: `-d` is replaced with `-m conntrack --ctorigdst`
4. **Loopback**: Rules with `-i lo` are skipped

```bash
# Original rule in INPUT_DOCKER
-p tcp --dport 80 -j ACCEPT

# Becomes in DOCKER-USER
-A DOCKER-USER -p tcp -m conntrack --ctorigdstport 80 -j RETURN
```

### Transformation Examples
```yaml
# In INPUT_DOCKER:
- rule: "-p tcp --dport 80 -j ACCEPT"
# Result in INPUT:
-A INPUT -p tcp --dport 80 -j ACCEPT
# Result in DOCKER-USER:
-A DOCKER-USER -p tcp -m conntrack --ctorigdstport 80 -j RETURN

# In INPUT_DOCKER:
- rule: "-s 192.168.1.0/24 -p tcp --dport 22 -j ACCEPT"
# Result in INPUT:
-A INPUT -s 192.168.1.0/24 -p tcp --dport 22 -j ACCEPT
# Result in DOCKER-USER:
-A DOCKER-USER -m conntrack --ctorigdst 192.168.1.0/24 -p tcp -m conntrack --ctorigdstport 22 -j RETURN

# In INPUT_DOCKER:
- rule: "-i lo -j ACCEPT"
# Result in INPUT:
-A INPUT -i lo -j ACCEPT
# Result in DOCKER-USER:
# (rule is skipped as not relevant for Docker)
```
