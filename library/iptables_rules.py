#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Ansible module to write iptables rules into /etc/firewall/rules.d directories
Accepts a dict of tables -> chains -> list of rule strings, creates directories and files accordingly.
"""
try:
    from ansible.module_utils.basic import AnsibleModule
except ImportError:
    # stub for local lint
    class AnsibleModule:
        def __init__(self, *args, **kwargs):
            self.params = kwargs.get('argument_spec', {})
        def run_command(self, *args, **kwargs): return (0, '', '')
        def exit_json(self, **kwargs): print(kwargs)
        def fail_json(self, **kwargs): print(kwargs)
import os

def write_file(path, content, owner, group, mode, module):
    # write only if content changed
    if os.path.exists(path):
        with open(path, 'r') as f:
            if f.read() == content:
                return False
    with open(path, 'w') as f:
        f.write(content)
    module.run_command(['chown', f"{owner}:{group}", path])
    module.run_command(['chmod', mode, path])
    return True


def main():
    module = AnsibleModule(
        argument_spec=dict(
            rules=dict(type='dict', required=True),
            dest=dict(type='path', default='/etc/firewall/rules.d'),
            owner=dict(type='str', default='root'),
            group=dict(type='str', default='root'),
            mode=dict(type='str', default='0644'),
            name=dict(type='str', required=True),
        ),
        supports_check_mode=True
    )
    params = module.params
    rules = params['rules']
    dest = params['dest']
    owner = params['owner']
    group = params['group']
    mode = params['mode']
    name = params['name']
    changed = False

    # группируем правила по table->chain->priority
    from collections import defaultdict
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for table, chains in rules.items():
        for chain, entries in chains.items():
            if not isinstance(entries, list):
                module.fail_json(msg=f"Rules for {table}->{chain} must be a list of dict entries")
            for entry in entries:
                if not isinstance(entry, dict):
                    module.fail_json(msg=f"Each rule entry in {table}->{chain} must be a dict")
                rule_str = entry.get('rule')
                if not rule_str:
                    module.fail_json(msg=f"Missing 'rule' in entry for {table}->{chain}")
                comment = entry.get('comment')
                priority = entry.get('priority', 50)
                interfaces = entry.get('interfaces')
                
                lines = []
                if comment:
                    lines.append(f"# {comment}")
                
                if isinstance(interfaces, list):
                    for iface in interfaces:
                        lines.append(f"-i {iface} {rule_str}")
                else:
                    lines.append(rule_str)
                
                grouped[table][chain][priority].extend(lines)
    
    for table, chains in grouped.items():
        for chain, priorities in chains.items():
            dir_path = os.path.join(dest, table, chain)
            if not os.path.isdir(dir_path):
                if not module.check_mode:
                    os.makedirs(dir_path, exist_ok=True)
                    module.run_command(['chown', f"{owner}:{group}", dir_path])
                    module.run_command(['chmod', '0755', dir_path])
                changed = True
            
            for priority, lines in sorted(priorities.items()):
                filename = f"{priority:02d}-{name}.rules"
                file_path = os.path.join(dir_path, filename)
                content = "\n".join(lines) + "\n"
                if write_file(file_path, content, owner, group, mode, module):
                    changed = True
    
    module.exit_json(changed=changed)

if __name__ == '__main__':
    main()
