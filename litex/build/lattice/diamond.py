# This file is Copyright (c) 2015 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

import os
import sys
import subprocess
import shutil

from migen.fhdl.structure import _Fragment

from litex.gen.fhdl.verilog import DummyAttrTranslate

from litex.build.generic_platform import *
from litex.build import tools
from litex.build.lattice import common


def _produces_jedec(device):
    return device.startswith("LCMX")


def _format_constraint(c):
    if isinstance(c, Pins):
        return ("LOCATE COMP ", " SITE " + "\"" + c.identifiers[0] + "\"")
    elif isinstance(c, IOStandard):
        return ("IOBUF PORT ", " IO_TYPE=" + c.name)
    elif isinstance(c, Misc):
        return ("IOBUF PORT ", " " + c.misc)


def _format_lpf(signame, pin, others, resname):
    fmt_c = [_format_constraint(c) for c in ([Pins(pin)] + others)]
    r = ""
    for pre, suf in fmt_c:
        r += pre + "\"" + signame + "\"" + suf + ";\n"
    return r


def _build_lpf(named_sc, named_pc):
    r = "BLOCK RESETPATHS;\n"
    r += "BLOCK ASYNCPATHS;\n"
    for sig, pins, others, resname in named_sc:
        if len(pins) > 1:
            for i, p in enumerate(pins):
                r += _format_lpf(sig + "[" + str(i) + "]", p, others, resname)
        else:
            r += _format_lpf(sig, pins[0], others, resname)
    if named_pc:
        r += "\n" + "\n\n".join(named_pc)
    return r


def _build_files(device, sources, vincpaths, build_name):
    tcl = []
    tcl.append("prj_project new -name \"{}\" -impl \"impl\" -dev {} -synthesis \"synplify\"".format(build_name, device))
    for path in vincpaths:
        tcl.append("prj_impl option {include path} {\"" + path + "\"}")
    for filename, language, library in sources:
        tcl.append("prj_src add \"" + filename + "\" -work " + library)
    tcl.append("prj_impl option top \"{}\"".format(build_name))
    tcl.append("prj_project save")
    tcl.append("prj_run Synthesis -impl impl -forceOne")
    tcl.append("prj_run Translate -impl impl")
    tcl.append("prj_run Map -impl impl")
    tcl.append("prj_run PAR -impl impl")
    tcl.append("prj_run Export -impl impl -task Bitgen")
    if _produces_jedec(device):
        tcl.append("prj_run Export -impl impl -task Jedecgen")
    tools.write_to_file(build_name + ".tcl", "\n".join(tcl))


def _build_script(build_name, device, toolchain_path, ver=None):
    if sys.platform in ("win32", "cygwin"):
        script_ext = ".bat"
        build_script_contents = "@echo off\nrem Autogenerated by Migen\n\n"
        copy_stmt = "copy"
        fail_stmt = " || exit /b"
    else:
        script_ext = ".sh"
        build_script_contents = "# Autogenerated by Migen\nset -e\n\n"
        copy_stmt = "cp"
        fail_stmt = ""

    if sys.platform not in ("win32", "cygwin"):
        build_script_contents += "bindir={}\n".format(toolchain_path)
        build_script_contents += ". ${{bindir}}/diamond_env{fail_stmt}\n".format(
            fail_stmt=fail_stmt)
    build_script_contents += "{pnmainc} {tcl_script}{fail_stmt}\n".format(
        pnmainc=os.path.join(toolchain_path, "pnmainc"),
        tcl_script=build_name + ".tcl",
        fail_stmt=fail_stmt)
    for ext in (".bit", ".jed"):
        if ext == ".jed" and not _produces_jedec(device):
            continue
        build_script_contents += "{copy_stmt} {diamond_product} {migen_product}" \
                                 "{fail_stmt}\n".format(
            copy_stmt=copy_stmt,
            fail_stmt=fail_stmt,
            diamond_product=os.path.join("impl", build_name + "_impl" + ext),
            migen_product=build_name + ext)

    build_script_file = "build_" + build_name + script_ext
    tools.write_to_file(build_script_file, build_script_contents,
                        force_unix=False)
    return build_script_file


def _run_script(script):
    if sys.platform in ("win32", "cygwin"):
        shell = ["cmd", "/c"]
    else:
        shell = ["bash"]

    if subprocess.call(shell + [script]) != 0:
        raise OSError("Subprocess failed")


class LatticeDiamondToolchain:
    attr_translate = {
        # FIXME: document
        "keep": ("syn_keep", "true"),
        "no_retiming": ("syn_no_retiming", "true"),
        "async_reg": None,
        "mr_ff": None,
        "mr_false_path": None,
        "ars_ff1": None,
        "ars_ff2": None,
        "ars_false_path": None,
        "no_shreg_extract": None
    }

    special_overrides = common.lattice_ecpx_special_overrides

    def build(self, platform, fragment, build_dir="build", build_name="top",
              toolchain_path=None, run=True, **kwargs):
        if toolchain_path is None:
            toolchain_path = "/opt/Diamond"
        os.makedirs(build_dir, exist_ok=True)
        cwd = os.getcwd()
        os.chdir(build_dir)

        if not isinstance(fragment, _Fragment):
            fragment = fragment.get_fragment()
        platform.finalize(fragment)

        v_output = platform.get_verilog(fragment, name=build_name, **kwargs)
        named_sc, named_pc = platform.resolve_signals(v_output.ns)
        v_file = build_name + ".v"
        v_output.write(v_file)
        sources = platform.sources | {(v_file, "verilog", "work")}
        _build_files(platform.device, sources, platform.verilog_include_paths, build_name)

        tools.write_to_file(build_name + ".lpf", _build_lpf(named_sc, named_pc))

        script = _build_script(build_name, platform.device, toolchain_path)
        if run:
            _run_script(script)

        os.chdir(cwd)

        return v_output.ns

    def add_period_constraint(self, platform, clk, period):
        # TODO: handle differential clk
        platform.add_platform_command("""FREQUENCY PORT "{clk}" {freq} MHz;""".format(freq=str(float(1/period)*1000), clk="{clk}"), clk=clk)
