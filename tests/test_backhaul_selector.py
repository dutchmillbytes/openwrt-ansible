import os
from pathlib import Path
import subprocess
import tempfile
import unittest

os.environ.setdefault("ANSIBLE_LOCAL_TEMP", "/tmp/ansible-tests")
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

try:
    from ansible.template import trust_as_template
except ImportError:  # ansible-core 2.18
    trust_as_template = lambda value: value


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "roles/backhaul_selector/templates/backhaul-select.sh.j2"


class BackhaulSelectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sysnet = self.root / "sys/class/net"
        self.bridge = self.sysnet / "br-lan"
        self.mesh = self.sysnet / "phy1-mesh0"
        self.bridge.mkdir(parents=True)
        self.mesh.mkdir()
        for device in ("lan", "wan"):
            path = self.sysnet / device
            path.mkdir()
            (path / "carrier").write_text("0\n")
        self.state = self.root / "state"
        self.ubus = self.root / "ubus"
        self.ubus.write_text(
            "#!/bin/sh\n"
            "[ \"$5\" = '{\"name\":\"phy1-mesh0\"}' ] || {\n"
            "  echo \"invalid payload: $5\" >&2\n"
            "  exit 2\n"
            "}\n"
            "case \"$4\" in\n"
            "  add_device) ln -sfn \"$BACKHAUL_TEST_BRIDGE\" \"$BACKHAUL_TEST_MESH/master\";;\n"
            "  remove_device) rm -f \"$BACKHAUL_TEST_MESH/master\";;\n"
            "  *) exit 1;;\n"
            "esac\n"
        )
        self.ubus.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    def render(self, failover=2):
        variables = {
            "backhaul_selector_mesh_device": "phy1-mesh0",
            "backhaul_selector_lan_interface": "lan",
            "backhaul_selector_bridge_device": "br-lan",
            "backhaul_selector_wired_devices": ["lan", "wan"],
            "backhaul_selector_poll_interval": 1,
            "backhaul_selector_failover_delay": failover,
        }
        script = Templar(loader=DataLoader(), variables=variables).template(
            trust_as_template(TEMPLATE.read_text())
        )
        path = self.root / "backhaul-select"
        path.write_text(script)
        path.chmod(0o700)
        return path

    def run_selector(self, *, polls=1, failover=2):
        script = self.render(failover=failover)
        env = dict(
            os.environ,
            BACKHAUL_SYS_CLASS_NET=str(self.sysnet),
            BACKHAUL_STATE_FILE=str(self.state),
            BACKHAUL_UBUS=str(self.ubus),
            BACKHAUL_LOGGER="/bin/true",
            BACKHAUL_SLEEP="/bin/true",
            BACKHAUL_MAX_POLLS=str(polls),
            BACKHAUL_TEST_BRIDGE=str(self.bridge),
            BACKHAUL_TEST_MESH=str(self.mesh),
        )
        return subprocess.run(["/bin/sh", str(script)], env=env, capture_output=True, text=True)

    def attach_mesh(self):
        (self.mesh / "master").symlink_to(self.bridge)

    def test_wired_carrier_immediately_detaches_mesh(self):
        self.attach_mesh()
        (self.sysnet / "lan/carrier").write_text("1\n")
        result = self.run_selector(polls=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.mesh / "master").exists())
        self.assertEqual(self.state.read_text().strip(), "wired")

    def test_wireless_failover_waits_for_configured_delay(self):
        result = self.run_selector(polls=2, failover=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.mesh / "master").is_symlink())
        self.assertEqual(self.state.read_text().strip(), "wireless")

if __name__ == "__main__":
    unittest.main()
