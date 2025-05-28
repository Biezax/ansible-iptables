# ansible-iptables роль

Роль для настройки iptables/ip6tables на серверах Ubuntu, обеспечивающая гибкую конфигурацию межсетевого экрана с автоматическим определением интерфейсов и инкрементальным применением правил.

## Возможности

* Использует iptables/ip6tables с пользовательской цепочкой CUSTOM_FILTERS
* Поддерживает как IPv4, так и IPv6 (конфигурируется отдельно)
* **Управляет только собственными правилами** - не изменяет и не удаляет правила, созданные другими сервисами (Docker, fail2ban и т.д.)
* Автоматически определяет внешние сетевые интерфейсы (исключая lo и docker*)
* Опциональная интеграция с Docker через цепочку DOCKER-USER
* Реализует иерархическую структуру `/etc/firewall/rules.d/4/<table>/<chain>/*.rules` для IPv4 и `/etc/firewall/rules.d/6/<table>/<chain>/*.rules` для IPv6
* Инкрементальное применение правил с возможностью отката при ошибках
* Использует NOTRACK для оптимизации входящего трафика на порты 22, 80, 443, 53
* Поддерживает приоритизацию правил через префиксы файлов
* Создает systemd сервис firewall для автоматического применения правил при загрузке
* Включает пользовательский модуль Ansible для генерации структуры правил

## Переменные по умолчанию

### Основные настройки
* `iptables_enabled: true` - Включить сервис iptables
* `ip6tables_enabled: true` - Включить правила IPv6
* `iptables_rules_dir: /etc/firewall/rules.d/4` - Директория правил IPv4
* `ip6tables_rules_dir: /etc/firewall/rules.d/6` - Директория правил IPv6
* `iptables_state_dir: /var/lib/iptables-ng/state` - Директория состояния для отслеживания изменений
* `external_interfaces: []` - Список внешних интерфейсов (если пуст, определяется автоматически)

### Структура правил
Правила задаются в формате:
```yaml
iptables_rules:
  <table>:
    <chain>:
      - rule: "<iptables rule without chain>"
        comment: "Optional comment"
        priority: 10  # Numeric priority (default: 50)
        interfaces: ["eth0", "eth1"]  # Optional: apply rule per interface
```

### Правила по умолчанию для IPv4
Переменные `iptables_rules` и `ip6tables_rules` используются только для настройки правил по умолчанию самой роли:
```yaml
iptables_rules:
  filter:
    INPUT:
      - rule: "-j CUSTOM_FILTERS"
        comment: "Jump to CUSTOM_FILTERS chain for all filtering"
        priority: 0
    CUSTOM_FILTERS:
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
        priority: 20
      - rule: "-j DROP"
        comment: "Drop everything else"
        priority: 30
    DOCKER-USER:
      - rule: "-j CUSTOM_FILTERS"
        comment: "Jump to common CUSTOM_FILTERS chain for Docker rules"
        priority: 0
      - rule: "-j RETURN"
        comment: "Return to calling chain for unmatched packets"
        priority: 10
  raw:
    PREROUTING:
      - rule: "-p tcp --dport 22 -j NOTRACK"
        comment: "NOTRACK for SSH"
        priority: 20
        interfaces: "{{ external_interfaces }}"
      # ... similar NOTRACK rules for other ports
```

### Правила по умолчанию для IPv6
Аналогичная структура `ip6tables_rules` с добавлением:
```yaml
ip6tables_rules:
  filter:
    CUSTOM_FILTERS:
      - rule: "-p ipv6-icmp -j ACCEPT"
        comment: "Accept all ICMPv6 messages"
        priority: 10
```

## Структура каталога правил

Правила организованы в иерархической структуре:

```
/etc/firewall/rules.d/
├── 4/                         # IPv4 правила
│   ├── filter/                # Таблица filter
│   │   ├── INPUT/             # Цепочка INPUT
│   │   │   └── 00-default.rules    # Правила по умолчанию (priority=0, name=default)
│   │   ├── CUSTOM_FILTERS/    # Пользовательская цепочка
│   │   │   ├── 10-default.rules    # Правила по умолчанию (priority=10)
│   │   │   ├── 20-default.rules    # LOG и DROP (priority=20,30)
│   │   │   └── 50-custom.rules     # Кастомные правила (priority=50)
│   │   └── DOCKER-USER/       # Docker интеграция
│   │       └── 00-default.rules
│   └── raw/                   # Таблица raw
│       └── PREROUTING/        # NOTRACK оптимизации
│           └── 20-default.rules
└── 6/                         # IPv6 правила (аналогичная структура)
    ├── filter/
    └── raw/
```

Файлы правил называются по шаблону: `{priority:02d}-{name}.rules`

## Использование

### Базовое использование
Роль автоматически применяет правила по умолчанию при включении:

```yaml
- hosts: firewalls
  roles:
    - iptables-ng
```

### Добавление кастомных правил
```yaml
- hosts: web_servers
  roles:
    - iptables-ng
  tasks:
    - name: Add custom web service rules
      iptables_rules:
        rules:
          filter:
            CUSTOM_FILTERS:
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

### Управление внешними интерфейсами
```yaml
- hosts: edge_servers
  vars:
    external_interfaces: ["eth0", "eth1"]  # Переопределить автоопределение
  roles:
    - iptables-ng
```

### Отключение IPv6
```yaml
- hosts: ipv4_only
  vars:
    ip6tables_enabled: false
  roles:
    - iptables-ng
```

## Пользовательский модуль iptables_rules

Роль включает модуль `iptables_rules` для добавления кастомных правил в директорию правил. Это основной способ добавления дополнительных правил:

### Параметры модуля:
* `rules` (dict, required) - Структура правил в формате table->chain->list
* `dest` (path) - Путь к директории правил (по умолчанию: '/etc/firewall/rules.d')  
* `name` (str, required) - Имя для генерируемых файлов правил
* `owner`, `group`, `mode` - Владелец и права доступа к файлам

### Пример использования:
```yaml
- name: Generate custom application rules
  iptables_rules:
    rules:
      filter:
        CUSTOM_FILTERS:
          - rule: "-p tcp --dport 9000 -j ACCEPT"
            comment: "Allow application port"
            priority: 40
      raw:
        PREROUTING:
          - rule: "-p tcp --dport 9000 -j NOTRACK"
            comment: "NOTRACK for application"
            priority: 25
    dest: "/etc/firewall/rules.d/4"  # Для IPv4
    name: "myapp"
  notify: restart firewall

# Для IPv6 используйте dest: "/etc/firewall/rules.d/6"
```

## Systemd сервис

Роль создает сервис `firewall.service`, который:
* Запускается после network.target (и docker.service если Docker установлен)
* Выполняет `/etc/firewall/apply_rules.sh` при старте
* Поддерживает команды:
  * `systemctl start firewall` - Применить правила
  * `systemctl restart firewall` - Перезапустить правила

## Скрипт применения правил

`/etc/firewall/apply_rules.sh` поддерживает:
* `--flush` - Очистить все правила перед применением
* `--debug` - Включить отладочный вывод
* Инкрементальное применение с автоматическим откатом при ошибках
* Селективное управление правилами - удаляет только ранее созданные собственные правила
* Отслеживание состояния через файлы в `{{ iptables_state_dir }}`

## Обработчики

* `restart firewall` - Перезапускает systemd сервис firewall
* `reload systemd` - Перезагружает конфигурацию systemd

## Требования

* Ubuntu/Debian с пакетом iptables
* Права root для выполнения команд iptables
* systemd для управления сервисом
* Docker (опционально, для интеграции через DOCKER-USER цепочку)

## Примечания

* **Кастомные правила добавляются только через модуль `iptables_rules`**, а не через переопределение переменных роли
* Переменные `iptables_rules` и `ip6tables_rules` предназначены только для настройки правил по умолчанию роли
* **Принцип работы с правилами**: роль отслеживает и управляет только теми правилами, которые создала сама. При обновлении удаляются только ранее созданные роли правила, а правила других сервисов (Docker, fail2ban, ufw и др.) остаются нетронутыми
* Правила для цепочки DOCKER-USER применяются только если Docker установлен
* Роль использует `--noflush` для инкрементального применения правил
* Состояние отслеживается для возможности отката при ошибках
* Автоматическое определение внешних интерфейсов исключает lo и docker*
* Поддерживается приоритизация правил через числовые префиксы файлов
