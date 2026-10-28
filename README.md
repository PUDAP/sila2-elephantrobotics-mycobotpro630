# myCobotPro630

A SiLA 2 connector for the myCobot Pro 630 arm, built with the UniteLabs CDK.

`io/` calls `elephant-driver` and does not import SiLA. `features/` is the SiLA face. Simulation is an in-memory arm in `io/simulation.py`. The default is simulation, so starting the server leaves TCP port 5001 closed and does not scan. Cameras and vision are not part of this server.

The client is `scripts/mycobotpro630_client.py`. Run it with the hackathon client environment, separate from this connector's virtual environment.

## Getting Started

### Prerequisites

Install these before cloning:

- Git
- [uv][] 0.6.8 or newer: <https://docs.astral.sh/uv/getting-started/installation/>
- Python 3.10. After uv is installed, run `uv python install 3.10`

`elephant-driver` requires Python 3.10 and does not install on 3.11 or newer. This connector uses that same range.

This server is the process that opens the arm's socket. Stop `elephant-edge` before real mode. Both would connect to the same robot port.

Clone, configure, and start the server with [Run the SiLA server](#run-the-sila-server).

## Usage

To interact with the running connector from another computer, install the [UniteLabs App](https://gitlab.com/unitelabs/sila2/sila-browser) on that computer. Add `<sila-host>` and port `50053` by hand.

### Encryption

To secure communication between the connector and its clients, you can enable TLS encryption. Start by installing the optional `cryptography` package for generating TLS certificates:

```sh
python -m pip install cryptography
```

To generate a pair of public and private keys, use the following command:

```sh
uv run certificate generate
```

Without any arguments this command uses the default config location to get the connector's UUID and host name, required to generate TLS certificates. It will prompt you as to whether or not you want to update your config file to enable TLS encryption on your connector. This prompt can be suppressed with the use of the `--non-interactive` or `-y` flag, which will update the config file with paths to the locally created files without prompting, or with `--embed` or `-e` flag to write the file contents into the config file directly.

You can adjust your config file's host to reflect the machine's hostname, or set it to `localhost` if the connector should only be accessible locally.

If your config file was created at a non-default path, you can provide it with the `--config-path` or `-cfg` option:

```sh
uv run certificate generate -cfg <path to config>
```

By default the generate command creates the `cert.pem` and `key.pem` files in your current working directory. You can customize the output directory with the `--target` argument.

If you choose not to update your config file with the paths to your certificates using `--non-interactive` or `-y` or to have the file contents saved directly in your config file with `--embed` or `-e` flag, you will have to modify the config file yourself to set the following values under `sila_server`:

- `certificate_chain` - the path to the `cert.pem` file
- `private_key` - the path to the `key.pem` file
- `tls` - a boolean that toggles on/off TLS encryption for the SiLA server

With your updated config file you can once again run:

```sh
uv run connector start --app unitelabs.mycobotpro630:create_app -vvv
```

> **Important:** Never share the `key.pem` file with anyone. Only the `cert.pem` is required for clients to connect to encrypted servers.

## Run the SiLA server

The SiLA server runs on the computer that can reach the arm. A client runs on another computer and connects to that server. The arm's own socket stays on port 5001. This server listens on port 50053. Each connector uses port 50053 on its own host. If more than one connector runs on the same host, give each a different `sila_server.port`.

Install Git, [uv][] 0.6.8 or newer, and Python 3.10 (`uv python install 3.10`). Stop `elephant-edge` so only this process opens the arm.

```sh
git clone https://github.com/PUDAP/sila2-elephantrobotics-mycobotpro630.git
cd sila2-elephantrobotics-mycobotpro630
uv python install 3.10
uv sync --frozen --no-default-groups
```

`uv sync` installs the versions in `uv.lock`. That includes `unitelabs-cdk` from PyPI and `elephant-driver` from the `driver/` directory in this repository. The host needs network access to PyPI during this step.

`config.json` stays on the host. It is listed in `.gitignore`. Create it in the repository directory. Give this server its own `sila_server.uuid` and keep that same value across restarts. `uv run config create --app unitelabs.mycobotpro630:create_app` writes a new file and a new UUID; set the remaining fields as in the example below. On Linux, `uuidgen` prints a UUID.

Connecting may enable the servos. It does not scan, reset, or move. `Scan` is a client command. Someone needs to be at the arm for that call.

The six `x_min` through `z_max` fields are the workspace this server enforces. Their meaning, and how to change them, is in [Motion limits](#motion-limits).

```json
{
  "sila_server": {
    "hostname": "<sila-bind-address>",
    "port": 50053,
    "tls": false,
    "require_client_auth": false,
    "root_certificates": null,
    "certificate_chain": null,
    "private_key": null,
    "options": {},
    "uuid": "00000000-0000-4000-8000-000000000002",
    "name": "myCobotPro630",
    "type": "Robot",
    "description": "A SiLA 2 connector for the myCobot Pro 630 arm, built with the UniteLabs CDK.",
    "vendor_url": "https://puda.co/",
    "default_lifetime": 3600.0
  },
  "cloud_servers": {
    "enabled": false,
    "endpoints": []
  },
  "discovery": null,
  "logging": null,
  "simulation_mode": false,
  "robot_ip": "<robot-ip>",
  "robot_port": 5001,
  "default_speed": 800,
  "scan_x": -250.0,
  "scan_y": 280.0,
  "scan_z": 330.0,
  "scan_rx": -179.99,
  "scan_ry": 0.0,
  "scan_rz": 111.0,
  "x_min": -500.0,
  "x_max": -100.0,
  "y_min": -250.0,
  "y_max": 400.0,
  "z_min": -425.0,
  "z_max": 835.0
}
```

`robot_ip` is the arm, not the SiLA bind address. Replace `<robot-ip>` with the arm's address, `<sila-bind-address>` with the interface this server listens on, and `<sila-host>` with the address a client uses to reach this server. `cloud_servers.endpoints` stays empty unless this server should connect to the UniteLabs platform. A machine without the arm uses the same file with `"simulation_mode": true` and `"sila_server.hostname": "<sila-host>"`. TLS certificates are covered in [Encryption](#encryption).

## Motion limits

Two ranges apply to every `MoveAbsolute`, `MoveRelative`, and `Scan`. The driver envelope is the outer range. The bench workspace is a smaller XYZ box inside it. A target is checked against the driver envelope first, then against the bench workspace. A miss on either check raises `InvalidCoordinate` and the arm stays where it is.

### Driver envelope

This range is fixed in `elephant-driver` as `COORD_RANGE`. It is the same range the driver applies before `send_coords`. This connector cannot widen it. A workspace bound outside this table is rejected when the server starts.

| Axis | Minimum | Maximum | Unit |
| --- | --- | --- | --- |
| X | −630 | 630 | mm |
| Y | −630 | 630 | mm |
| Z | −425 | 835 | mm |
| Rx | −180 | 180 | degrees |
| Ry | −180 | 180 | degrees |
| Rz | −180 | 180 | degrees |

Driver speed is an integer from 1 to 3000. The driver default is 800. SiLA move commands do not take a speed argument. They send `default_speed` from `config.json`.

Rx, Ry, and Rz have no workspace fields. They stay at this ±180 degree envelope. The driver may rewrite a rotation by ±360 degrees so the wrist takes the short path, and the rewritten value still has to land inside ±180 degrees.

### Bench workspace

Past Elephant use recorded a tighter XY box and used it to clamp vision targets before motion. The same numbers are in `bears-skills/bears-machines/references/elephant.md` (`ROBOT_X_MIN`, `ROBOT_X_MAX`, `ROBOT_Y_MIN`, `ROBOT_Y_MAX`) and in `elephant/vlm_new.py`. This connector ships those numbers as the default workspace and rejects a command that leaves the box.

| Axis | Config fields | Minimum | Maximum | Unit | Where the number came from |
| --- | --- | --- | --- | --- | --- |
| X | `x_min`, `x_max` | −500 | −100 | mm | Bench workspace from past use |
| Y | `y_min`, `y_max` | −250 | 400 | mm | Bench workspace from past use |
| Z | `z_min`, `z_max` | −425 | 835 | mm | Driver envelope. Past use did not record a separate Z box |

Those workflows also recorded heights. They are poses, and they are already inside the default box:

| Pose | Value |
| --- | --- |
| Scan / clearance | X −250 mm, Y 280 mm, Z 330 mm, Rx −179.99°, Ry 0°, Rz 111° |
| Alignment height | Z 180 mm |
| Pickup height (`z_touch`) | Z 155 mm |
| Default place pose in the blue-vial skill | X −264 mm, Y 175 mm, Z 140 mm, Rx 179.99°, Ry 0°, Rz 113° |

The scan pose in `config.json` matches the scan row. `Scan` moves to that pose, so `scan_x`, `scan_y`, and `scan_z` have to sit inside the workspace. The server checks that at startup.

### What stays configurable

Edit these fields in `config.json`. The server reads them when the process starts.

| Field | Default | Rule |
| --- | --- | --- |
| `x_min`, `x_max` | −500, −100 | Millimeters. `x_min` ≤ `x_max`. Both ends inside −630 to 630 |
| `y_min`, `y_max` | −250, 400 | Millimeters. `y_min` ≤ `y_max`. Both ends inside −630 to 630 |
| `z_min`, `z_max` | −425, 835 | Millimeters. `z_min` ≤ `z_max`. Both ends inside −425 to 835 |
| `scan_x`, `scan_y`, `scan_z` | −250, 280, 330 | Millimeters. The scan pose must sit inside the workspace above |
| `scan_rx`, `scan_ry`, `scan_rz` | −179.99, 0, 111 | Degrees, each inside −180 to 180 |
| `default_speed` | 800 | Integer from 1 to 3000 |

The driver envelope itself is not a config field. Setting `x_min` to −700, or `z_max` to 900, makes the server exit at startup with `InvalidCoordinate`. An inverted pair such as `x_min` −100 and `x_max` −500 does the same. The arm socket stays closed.

### Change the limits

On the computer that runs this server, edit `config.json` in the `mycobotpro630` directory, or the file you pass with `-cfg`. Replace the six workspace lines. This example narrows Z to the place height and the clearance height from past use, and leaves the recorded XY box as it is:

```json
"x_min": -500.0,
"x_max": -100.0,
"y_min": -250.0,
"y_max": 400.0,
"z_min": 140.0,
"z_max": 330.0
```

That box still contains the default scan pose, because scan Z is 330 mm. If you set `z_max` below 330, or move an XY edge past the scan point, change `scan_x`, `scan_y`, and `scan_z` in the same file so the scan pose stays inside the box.

Stop the server and start it again with the command below. A server that is already running keeps the limits it loaded at startup. `config.json` is gitignored, so this change stays on that machine.

Start the server from the repository directory so it reads this `config.json`:

```sh
uv run connector start --app unitelabs.mycobotpro630:create_app -vvv
```

A client connects to `<sila-host>` at port 50053 with TLS off. `scripts/mycobotpro630_client.py` uses `<sila-host>` and port 50053. Set `hostname` in that script to the computer that runs this server when the client runs on another machine. Run the script with the hackathon SiLA client environment, separate from this server's virtual environment. Do not point that script at the real arm until someone is standing next to it.

To use a config file outside the repository directory:

```sh
uv run connector start --app unitelabs.mycobotpro630:create_app -cfg <path to config> -vvv
```

`docker-compose.yml` is optional. It uses host networking and binds `config.json`. It does not mount `/dev` and it is not privileged. The host path above is the one to use. Do not also run `uv run connector start` while a container is up. Both would open the same robot socket.

## Contribute

### Development environment

From the clone above, install the test and development tools and run the suite:

```sh
uv sync --frozen --all-extras
uv run pytest
```

`uv run` syncs dependencies on every call. `uv run --frozen` uses the existing lock. `UV_FROZEN=true` does the same for the session.

Install the hooks:

```sh
uv run pre-commit install
```

Developer mode reloads the server when source files change:

```sh
uv run connector dev --app unitelabs.mycobotpro630:create_app
```

## Contact

If you found a bug, please use the [issue tracker][issue-tracker].

[issue-tracker]: https://github.com/PUDAP/sila2-elephantrobotics-mycobotpro630/issues
[uv]: https://docs.astral.sh/uv/
