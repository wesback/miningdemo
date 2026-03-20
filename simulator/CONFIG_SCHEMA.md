# Simulator Configuration Schema

This document describes the complete configuration schema for the Mining RTI Demo simulator. The simulator can be configured via:

1. **YAML configuration file** (passed with `--config`)
2. **Command-line arguments** (override YAML settings)
3. **Environment variables** (fallback for connection details)

---

## YAML Configuration File

### File Location
- Default: Not loaded unless specified
- Specify with: `--config path/to/config.yaml`
- Sample: `config.sample.yaml`

### Complete Schema

```yaml
# Azure Event Hub connection (leave blank for console mode)
connection_string: ""        # Event Hub namespace connection string
eventhub_name: ""            # Event Hub / Eventstream topic name

# Simulation parameters
interval_sec: 10             # Seconds between each batch of events
batch_size: 50               # Not used directly — all fleet sensors emit each cycle
max_iterations: 0            # 0 = run indefinitely; set to e.g. 100 for bounded demo
```

---

## Field Reference

### `connection_string`
- **Type:** String
- **Default:** `""` (empty)
- **Required:** Yes, unless `console_mode` is enabled
- **Description:** Azure Event Hub namespace connection string in the format:
  ```
  Endpoint=sb://<namespace>.servicebus.windows.net/;SharedAccessKeyName=<key-name>;SharedAccessKey=<key>
  ```
- **Overrides:**
  - CLI: `--connection-string <value>`
  - Environment: `EVENT_HUB_CONNECTION_STRING`
- **Validation:** If empty and not in console mode, simulator exits with error
- **Common mistakes:**
  - Using Event Hub entity connection string instead of namespace connection string
  - Forgetting to set when not using `--console` mode
  - Including line breaks or extra whitespace

### `eventhub_name`
- **Type:** String
- **Default:** `""` (empty)
- **Required:** Yes, unless `console_mode` is enabled
- **Description:** Name of the Event Hub entity or Fabric Eventstream custom endpoint
- **Overrides:**
  - CLI: `--eventhub-name <value>`
  - Environment: `EVENT_HUB_NAME`
- **Validation:** Must be a valid Event Hub entity name
- **Common mistakes:**
  - Using the namespace name instead of the entity name
  - Typos in the entity name

### `interval_sec`
- **Type:** Integer or Float
- **Default:** `10`
- **Required:** No
- **Range:** `> 0` and `<= 3600` (1 second to 1 hour)
- **Description:** Number of seconds to wait between sending batches of sensor events
- **Overrides:** CLI: `--interval <seconds>`
- **Validation:** Must be a positive number ≤ 3600. Config loader exits if out of range.
- **Behavior:**
  - At each interval, the simulator generates sensor readings for ALL equipment in the fleet
  - Shorter intervals = higher data volume
  - Longer intervals = more realistic for production monitoring
- **Common mistakes:**
  - Setting to `0` (not allowed)
  - Setting too low (<1 second) causing Event Hub throttling
  - Setting negative values

### `batch_size`
- **Type:** Integer
- **Default:** `50`
- **Required:** No
- **Range:** `> 0` and `<= 10000`
- **Description:** **Note: This field is NOT actively used in current implementation.** The simulator always generates events for all fleet equipment on each cycle. This field exists for backward compatibility and future use.
- **Validation:** Must be a positive integer ≤ 10000. Config loader exits if out of range.
- **Common mistakes:**
  - Expecting this to limit the number of events sent (it doesn't)
  - Setting extremely high values expecting more data (fleet size controls this)

### `max_iterations`
- **Type:** Integer
- **Default:** `0` (infinite)
- **Required:** No
- **Range:** `>= 0`
- **Description:** Number of batches to send before stopping. `0` means run indefinitely until interrupted (Ctrl+C).
- **Overrides:** CLI: `--max-iterations <count>`
- **Validation:** Must be a non-negative integer. Config loader exits if negative.
- **Behavior:**
  - `0`: Runs forever (typical for demos and load testing)
  - `> 0`: Sends exactly N batches then exits cleanly
- **Common mistakes:**
  - Setting to `1` expecting continuous data (only sends one batch)
  - Forgetting it's set when testing, causing early termination

---

## Command-Line Arguments

All CLI arguments override YAML config and environment variables:

| Argument | Type | Description | Default |
|----------|------|-------------|---------|
| `--connection-string <value>` | String | Event Hub connection string | From config/env |
| `--eventhub-name <value>` | String | Event Hub name | From config/env |
| `--config <path>` | String | Path to YAML config file | None |
| `--interval <seconds>` | Integer | Seconds between batches | 10 |
| `--inject-anomaly <scenario>` | Choice | Inject anomaly scenario | None |
| `--console` | Flag | Print to stdout, don't send to Event Hub | False |
| `--max-iterations <count>` | Integer | Stop after N batches (0=infinite) | 0 |

### Anomaly Scenarios

The `--inject-anomaly` flag accepts these predefined scenarios:

- `overheat`: Engine overheating on haul trucks
- `hydraulic`: Low hydraulic pressure on drills
- `vibration`: High vibration on conveyors
- `gas`: Elevated CO/CH4 in environmental sensors
- `conveyor_stop`: Conveyor belt stopped
- `all`: Combines all scenarios above

**Behavior:** When an anomaly is injected, specific equipment emits sensor values outside normal ranges (see `anomaly_value` in sensor profiles).

---

## Environment Variables

The simulator checks these environment variables as fallbacks:

| Variable | Usage | Overridden By |
|----------|-------|---------------|
| `EVENT_HUB_CONNECTION_STRING` | Connection string if not in config/CLI | `--connection-string`, YAML `connection_string` |
| `EVENT_HUB_NAME` | Event Hub name if not in config/CLI | `--eventhub-name`, YAML `eventhub_name` |

---

## Console Mode

**What it is:** A special mode that prints JSON events to stdout instead of sending them to Event Hub.

**When it's enabled:**
- `--console` flag is used, OR
- No `connection_string` is provided (config, CLI, or env)

**Use cases:**
- Local testing without Azure resources
- Inspecting event structure and data quality
- Piping events to other tools
- CI/CD validation

**Example:**
```bash
python simulator.py --console --inject-anomaly gas | jq .
```

---

## Configuration Priority

Settings are resolved in this order (highest priority first):

1. **Command-line arguments** (`--interval`, `--connection-string`, etc.)
2. **YAML config file** (if `--config` is provided)
3. **Environment variables** (`EVENT_HUB_CONNECTION_STRING`, `EVENT_HUB_NAME`)
4. **Built-in defaults** (`interval_sec=10`, `batch_size=50`, `max_iterations=0`)

---

## Validation Rules

The simulator performs these validations on startup:

### YAML Config Validation
- ✅ Valid numeric ranges for `interval_sec`, `batch_size`, `max_iterations`
- ✅ Required fields present when not in console mode
- ❌ **Exits with error** if validation fails

### Runtime Validation
- ✅ Event Hub connection string present (unless console mode)
- ✅ Event Hub name present (unless console mode)
- ❌ **Exits with error** if Event Hub config missing and not in console mode

---

## Example Configurations

### Minimal Console Mode (Local Testing)
```yaml
# config.yaml
connection_string: ""
eventhub_name: ""
interval_sec: 5
max_iterations: 10  # Send 10 batches then stop
```

**Run:**
```bash
python simulator.py --config config.yaml --console
```

---

### Production Event Hub Configuration
```yaml
# config.yaml
connection_string: "Endpoint=sb://mynamespace.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=<key>"
eventhub_name: "mining-sensor-stream"
interval_sec: 10
batch_size: 50
max_iterations: 0  # Run indefinitely
```

**Run:**
```bash
python simulator.py --config config.yaml
```

---

### Demo Mode with Anomalies
```yaml
# config.yaml
connection_string: "Endpoint=sb://..."
eventhub_name: "mining-sensor-stream"
interval_sec: 15
max_iterations: 100  # Run for ~25 minutes (100 batches × 15 sec)
```

**Run with gas anomaly:**
```bash
python simulator.py --config config.yaml --inject-anomaly gas
```

---

### Environment Variable Mode (No Config File)
```bash
export EVENT_HUB_CONNECTION_STRING="Endpoint=sb://..."
export EVENT_HUB_NAME="mining-sensor-stream"

python simulator.py --interval 10
```

---

## Common Mistakes and Fixes

### Mistake: "No Event Hub connection string provided" Error
**Cause:** Missing `connection_string` and not in console mode.

**Fix:**
- Add `--console` for local testing, OR
- Provide `--connection-string <value>`, OR
- Set `EVENT_HUB_CONNECTION_STRING` environment variable, OR
- Add `connection_string: "..."` to config.yaml

---

### Mistake: Config File Not Loading
**Cause:** Forgot to pass `--config` argument.

**Fix:**
```bash
# Wrong
python simulator.py

# Right
python simulator.py --config config.yaml
```

---

### Mistake: Validation Error "interval_sec must be positive"
**Cause:** Invalid value in YAML (e.g., `0`, negative, or non-numeric).

**Fix:**
```yaml
# Wrong
interval_sec: 0

# Right
interval_sec: 10
```

---

### Mistake: Simulator Stops After One Batch
**Cause:** `max_iterations` is set to `1` or another low value.

**Fix:**
```yaml
# For continuous operation
max_iterations: 0
```

---

### Mistake: Expected batch_size to Limit Events
**Cause:** Misunderstanding of `batch_size` behavior.

**Reality:** The simulator sends events for ALL fleet equipment on each cycle, regardless of `batch_size`. This field is not actively enforced in the current implementation.

**Note:** To control event volume, adjust `interval_sec` or modify the fleet definition in `simulator.py` (lines 375-389).

---

## What Happens with Invalid/Missing Config Values?

| Scenario | Behavior |
|----------|----------|
| Missing `connection_string` (not console mode) | ❌ Simulator exits with error |
| Missing `eventhub_name` (not console mode) | ❌ Simulator exits with error |
| `interval_sec` out of range (≤0 or >3600) | ❌ Config loader exits with validation error |
| `batch_size` out of range (≤0 or >10000) | ❌ Config loader exits with validation error |
| `max_iterations` negative | ❌ Config loader exits with validation error |
| YAML file not found (`--config` points to missing file) | ❌ Python raises `FileNotFoundError` |
| Invalid YAML syntax | ❌ PyYAML raises parsing error |
| Missing `--config` argument | ✅ Simulator uses CLI args, env vars, and defaults |
| Extra unknown fields in YAML | ✅ Silently ignored (no validation) |

---

## Dependencies

The simulator requires:
- **Python 3.7+**
- **azure-eventhub** — Event Hub client (not required for `--console` mode)
- **pyyaml** — YAML config parsing (required if using `--config`)

**Install:**
```bash
pip install -r requirements.txt
```

**Console Mode Only (no Azure):**
```bash
# pyyaml still needed if using --config
pip install pyyaml
```

---

## Related Files

- **`config.sample.yaml`** — Template configuration file
- **`simulator.py`** — Main simulator implementation
- **`requirements.txt`** — Python dependencies

---

## Code References

Configuration loading logic: `simulator.py` lines 438-500

- Line 450-474: YAML config loading
- Line 476-490: CLI and env override logic
- Line 397-423: YAML validation function (`_validate_yaml_config`)
- Line 600-633: CLI argument definitions
