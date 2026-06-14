import os
import shutil
import tempfile
import types
import unittest
import importlib
from importlib.machinery import SourceFileLoader
from pathlib import Path

def load_howdone():
    """
    Load howdone module using importlib because it does not have the .py extension.
    """
    loader = SourceFileLoader("howdone", str(Path(__file__).parent / "howdone"))
    spec = importlib.util.spec_from_loader("howdone", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod

howdone_module = load_howdone()

find_config_file = howdone_module.find_config_file
validate_output_dir_config = howdone_module.validate_output_dir_config
substitute_output_dir = howdone_module.substitute_output_dir
append_output_dir_arg = howdone_module.append_output_dir_arg
format_command_line = howdone_module.format_command_line
run = howdone_module.run


class TestFormatCommandLine(unittest.TestCase):
    def test_string_passthrough(self):
        self.assertEqual(format_command_line("echo hello"), "echo hello")

    def test_list_joined(self):
        self.assertEqual(format_command_line(["echo", "hello", "world"]), "echo hello world")

    def test_empty_list(self):
        self.assertEqual(format_command_line([]), "")


class TestSubstituteOutputDir(unittest.TestCase):
    def test_substitutes_placeholder(self):
        self.assertEqual(
            substitute_output_dir("-o {OUTPUT_DIR}/out.txt", Path("/tmp/mydir")),
            "-o /tmp/mydir/out.txt",
        )

    def test_no_placeholder(self):
        self.assertEqual(substitute_output_dir("--flag", Path("/tmp/mydir")), "--flag")

    def test_multiple_occurrences(self):
        self.assertEqual(
            substitute_output_dir("{OUTPUT_DIR} and {OUTPUT_DIR}", Path("/p")),
            "/p and /p",
        )


class TestAppendOutputDirArg(unittest.TestCase):
    def test_str_command_str_arg(self):
        self.assertEqual(
            append_output_dir_arg("prog", "-o {OUTPUT_DIR}", Path("/tmp/outdir")),
            "prog -o /tmp/outdir",
        )

    def test_str_command_list_arg(self):
        self.assertEqual(
            append_output_dir_arg("prog", ["-o", "{OUTPUT_DIR}"], Path("/tmp/outdir")),
            "prog -o /tmp/outdir",
        )

    def test_list_command_str_arg(self):
        self.assertEqual(
            append_output_dir_arg(["prog"], "-o {OUTPUT_DIR}", Path("/tmp/outdir")),
            ["prog", "-o", "/tmp/outdir"],
        )

    def test_list_command_list_arg(self):
        self.assertEqual(
            append_output_dir_arg(["prog"], ["-o", "{OUTPUT_DIR}"], Path("/tmp/outdir")),
            ["prog", "-o", "/tmp/outdir"],
        )


class TestValidateOutputDirConfig(unittest.TestCase):
    def test_no_output_dir_key(self):
        validate_output_dir_config({})  # must not raise

    def test_empty_output_dir(self):
        validate_output_dir_config({"output_dir": {}})  # must not raise

    def test_valid_variable(self):
        validate_output_dir_config({"output_dir": {"variable": "X"}})  # must not raise

    def test_valid_argument_string(self):
        validate_output_dir_config({"output_dir": {"argument": "-o {OUTPUT_DIR}"}})

    def test_valid_argument_list(self):
        validate_output_dir_config({"output_dir": {"argument": ["-o", "{OUTPUT_DIR}"]}})

    def test_argument_missing_placeholder_raises(self):
        with self.assertRaises(ValueError):
            validate_output_dir_config({"output_dir": {"argument": "-o /hardcoded"}})

    def test_argument_wrong_type_raises(self):
        with self.assertRaises(ValueError):
            validate_output_dir_config({"output_dir": {"argument": 42}})


class TestFindConfigFile(unittest.TestCase):
    def test_finds_in_start_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / ".howdone.yaml"
            cfg.write_text("prefix: test\n")
            self.assertEqual(find_config_file(Path(tmpdir)), cfg)

    def test_finds_in_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / ".howdone.yaml"
            cfg.write_text("prefix: test\n")
            child = Path(tmpdir) / "subdir"
            child.mkdir()
            self.assertEqual(find_config_file(child), cfg)

    def test_returns_none_when_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            child = Path(tmpdir) / "a" / "b"
            child.mkdir(parents=True)
            self.assertIsNone(find_config_file(child))


# ---- Integration tests (converted from test.sh) ----

MINIMAL_COMMANDS = "commands:\n  side.txt: echo sideout\n"


def make_args(**kwargs):
    defaults = dict(config=None, name=None, dir=None, prefix=None, cmd=["echo mainout"])
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


class IntegrationTestBase(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = Path.cwd()
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def write_config(self, name, content):
        p = self._tmpdir / name
        p.write_text(content)
        return p

    def find_output_dir(self, prefix, base=None):
        base = base or self._tmpdir
        matches = list(Path(base).glob(f"{prefix}-*"))
        return matches[0] if matches else None


class TestAutoDiscoverConfig(IntegrationTestBase):
    """Auto-discover .howdone.yaml"""

    def setUp(self):
        super().setUp()
        self.write_config(".howdone.yaml", f"prefix: autorun\noutput_file: output.txt\n{MINIMAL_COMMANDS}")
        os.chdir(self._tmpdir)
        run(make_args())
        self.outdir = self.find_output_dir("autorun")

    def test_output_dir_created(self):
        self.assertIsNotNone(self.outdir)
        self.assertTrue(self.outdir.is_dir())

    def test_meta_yaml_written(self):
        self.assertTrue((self.outdir / "meta.yaml").is_file())

    def test_main_output_file_written(self):
        self.assertTrue((self.outdir / "output.txt").is_file())

    def test_side_command_file_written(self):
        self.assertTrue((self.outdir / "side.txt").is_file())

    def test_main_output_captured(self):
        self.assertIn("mainout", (self.outdir / "output.txt").read_text())


class TestExplicitConfig(IntegrationTestBase):
    """Explicit config file via -c"""

    def setUp(self):
        super().setUp()
        cfg = self.write_config("my.yaml", f"prefix: explicitrun\noutput_file: output.txt\n{MINIMAL_COMMANDS}")
        workdir = self._tmpdir / "workdir"
        workdir.mkdir()
        os.chdir(workdir)
        run(make_args(config=cfg))
        self.outdir = self.find_output_dir("explicitrun", base=workdir)

    def test_output_dir_created(self):
        self.assertIsNotNone(self.outdir)

    def test_side_file_written(self):
        self.assertTrue((self.outdir / "side.txt").is_file())

    def test_main_output_captured(self):
        self.assertIn("mainout", (self.outdir / "output.txt").read_text())


class TestPrefixFromConfig(IntegrationTestBase):
    """Output dir named with prefix from config"""

    def test_dir_named_with_config_prefix(self):
        self.write_config(".howdone.yaml", "prefix: cfgprefix\noutput_file: output.txt\ncommands: {}\n")
        os.chdir(self._tmpdir)
        run(make_args(cmd=["echo hi"]))
        outdir = self.find_output_dir("cfgprefix")
        self.assertIsNotNone(outdir)
        self.assertTrue(outdir.is_dir())


class TestPrefixFlag(IntegrationTestBase):
    """-p flag overrides config prefix"""

    def setUp(self):
        super().setUp()
        self.write_config(".howdone.yaml", "prefix: cfgprefix\noutput_file: output.txt\ncommands: {}\n")
        os.chdir(self._tmpdir)
        run(make_args(prefix="cmdprefix", cmd=["echo hi"]))

    def test_cmd_prefix_dir_created(self):
        self.assertIsNotNone(self.find_output_dir("cmdprefix"))

    def test_config_prefix_not_used(self):
        self.assertIsNone(self.find_output_dir("cfgprefix"))


class TestExactDir(IntegrationTestBase):
    """-d flag creates exact directory"""

    def setUp(self):
        super().setUp()
        self.write_config(".howdone.yaml", "prefix: someprefix\noutput_file: output.txt\ncommands: {}\n")
        self.exact = self._tmpdir / "my_exact_dir"
        os.chdir(self._tmpdir)
        run(make_args(dir=self.exact, cmd=["echo hi"]))

    def test_exact_dir_created(self):
        self.assertTrue(self.exact.is_dir())

    def test_output_file_in_exact_dir(self):
        self.assertTrue((self.exact / "output.txt").is_file())

    def test_meta_yaml_in_exact_dir(self):
        self.assertTrue((self.exact / "meta.yaml").is_file())


class TestOutputDirVariable(IntegrationTestBase):
    """output_dir.variable passes env var to main command"""

    def test_env_var_received_by_main_command(self):
        self.write_config(".howdone.yaml",
            "prefix: vartest\noutput_file: output.txt\n"
            "output_dir:\n  variable: MY_OUTPUT_DIR\ncommands: {}\n")
        os.chdir(self._tmpdir)
        run(make_args(cmd=["echo $MY_OUTPUT_DIR"]))
        outdir = self.find_output_dir("vartest")
        self.assertIn(str(outdir), (outdir / "output.txt").read_text())


class TestOutputDirVariableSideCommands(IntegrationTestBase):
    """output_dir.variable also passed to side commands"""

    def test_env_var_received_by_side_command(self):
        self.write_config(".howdone.yaml",
            "prefix: varside\noutput_file: output.txt\n"
            "output_dir:\n  variable: MY_OUTPUT_DIR\n"
            "commands:\n  sideenv.txt: echo $MY_OUTPUT_DIR\n")
        os.chdir(self._tmpdir)
        run(make_args(cmd=["echo main"]))
        outdir = self.find_output_dir("varside")
        self.assertIn(str(outdir), (outdir / "sideenv.txt").read_text())


class TestOutputDirChangeDirectory(IntegrationTestBase):
    """output_dir.change_directory runs commands in output dir"""

    def test_side_commands_run_in_output_dir(self):
        self.write_config(".howdone.yaml",
            "prefix: cdtest\noutput_file: output.txt\n"
            "output_dir:\n  change_directory: true\n"
            "commands:\n  workdir.txt: pwd\n")
        os.chdir(self._tmpdir)
        run(make_args(cmd=["echo main"]))
        outdir = self.find_output_dir("cdtest")
        self.assertIn(str(outdir), (outdir / "workdir.txt").read_text())


class TestOutputDirArgumentString(IntegrationTestBase):
    """output_dir.argument as string appends to main command"""

    def test_output_dir_appended_as_arg(self):
        self.write_config(".howdone.yaml",
            "prefix: argtest\noutput_file: output.txt\n"
            'output_dir:\n  argument: "-o {OUTPUT_DIR}"\n'
            "commands: {}\n")
        os.chdir(self._tmpdir)
        run(make_args(cmd=["echo"]))
        outdir = self.find_output_dir("argtest")
        self.assertIsNotNone(outdir)
        self.assertIn(f"-o {outdir}", (outdir / "output.txt").read_text())


class TestOutputDirArgumentList(IntegrationTestBase):
    """t10: output_dir.argument as list appends to main command"""

    def test_output_dir_appended_as_list_arg(self):
        self.write_config(".howdone.yaml",
            "prefix: argtest\noutput_file: output.txt\n"
            'output_dir:\n  argument: ["-o", "{OUTPUT_DIR}"]\n'
            "commands: {}\n")
        os.chdir(self._tmpdir)
        run(make_args(cmd=["echo"]))
        outdir = self.find_output_dir("argtest")
        self.assertIsNotNone(outdir)
        self.assertIn(f"-o {outdir}", (outdir / "output.txt").read_text())


if __name__ == "__main__":
    unittest.main()
