# This file is Copyright (c) 2015 Sebastien Bourdeauducq <sb@m-labs.hk>
# This file is Copyright (c) 2015-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

from math import log2

from migen import *
from migen.genlib.record import *

from litex.soc.interconnect import wishbone
from litex.soc.interconnect.csr import AutoCSR
from litex.soc.integration.soc_core import *

from litedram.frontend.wishbone import *
from litedram.frontend.axi import *
from litedram import dfii, core


__all__ = ["SoCSDRAM", "soc_sdram_args", "soc_sdram_argdict"]

# Controller Injector ------------------------------------------------------------------------------

# FIXME: move to LiteDRAM

class ControllerInjector(Module, AutoCSR):
    def __init__(self, phy, geom_settings, timing_settings, clk_freq, **kwargs):
        self.submodules.dfii = dfii.DFIInjector(
            geom_settings.addressbits,
            geom_settings.bankbits,
            phy.settings.nranks,
            phy.settings.dfi_databits,
            phy.settings.nphases)
        self.comb += self.dfii.master.connect(phy.dfi)

        self.submodules.controller = controller = core.LiteDRAMController(
            phy.settings, geom_settings, timing_settings,
            clk_freq, **kwargs)
        self.comb += controller.dfi.connect(self.dfii.slave)

        self.submodules.crossbar = core.LiteDRAMCrossbar(controller.interface)

# SoCSDRAM -----------------------------------------------------------------------------------------

class SoCSDRAM(SoCCore):
    csr_map = {
        "sdram":           8,
        "l2_cache":        9
    }
    csr_map.update(SoCCore.csr_map)

    def __init__(self, platform, clk_freq, l2_size=8192, **kwargs):
        SoCCore.__init__(self, platform, clk_freq, **kwargs)
        if not self.integrated_main_ram_size:
            if self.cpu_type is not None and self.csr_data_width != 8:
                 raise NotImplementedError("BIOS supports SDRAM initialization only for csr_data_width=8")
        self.l2_size = l2_size

        self._sdram_phy    = []
        self._wb_sdram_ifs = []
        self._wb_sdram     = wishbone.Interface()

    def add_wb_sdram_if(self, interface):
        if self.finalized:
            raise FinalizeError
        self._wb_sdram_ifs.append(interface)

    def register_sdram(self, phy, geom_settings, timing_settings, use_axi=False, use_full_memory_we=True, **kwargs):
        assert not self._sdram_phy
        self._sdram_phy.append(phy) # encapsulate in list to prevent CSR scanning

        # LiteDRAM core ----------------------------------------------------------------------------
        self.submodules.sdram = ControllerInjector(
            phy, geom_settings, timing_settings, self.clk_freq, **kwargs)

        # SoC <--> L2 Cache <--> LiteDRAM ----------------------------------------------------------
        if self.with_wishbone:
            # LiteDRAM port ------------------------------------------------------------------------
            port = self.sdram.crossbar.get_port()
            port.data_width = 2**int(log2(port.data_width)) # Round to nearest power of 2

            # Parameters ---------------------------------------------------------------------------
            main_ram_size = 2**(geom_settings.bankbits +
                                geom_settings.rowbits +
                                geom_settings.colbits)*phy.settings.databits//8
            main_ram_size = min(main_ram_size, 0x20000000) # FIXME: limit to 512MB for now

            l2_size = max(self.l2_size, int(2*port.data_width/8)) # L2 has a minimal size, use it if lower
            l2_size = 2**int(log2(l2_size))                       # Round to nearest power of 2

            # SoC <--> L2 Cache Wishbone interface -------------------------------------------------
            wb_sdram = wishbone.Interface()
            self.add_wb_sdram_if(wb_sdram)
            self.register_mem("main_ram", self.mem_map["main_ram"], wb_sdram, main_ram_size)

            # L2 Cache -----------------------------------------------------------------------------
            l2_cache = wishbone.Cache(l2_size//4, self._wb_sdram, wishbone.Interface(port.data_width))
            # XXX Vivado ->2018.2 workaround, Vivado is not able to map correctly our L2 cache.
            # Issue is reported to Xilinx, Remove this if ever fixed by Xilinx...
            from litex.build.xilinx.vivado import XilinxVivadoToolchain
            if isinstance(self.platform.toolchain, XilinxVivadoToolchain) and use_full_memory_we:
                from migen.fhdl.simplify import FullMemoryWE
                self.submodules.l2_cache = FullMemoryWE()(l2_cache)
            else:
                self.submodules.l2_cache = l2_cache
            self.config["L2_SIZE"] = l2_size

            # L2 Cache <--> LiteDRAM bridge --------------------------------------------------------
            if use_axi:
                axi_port = LiteDRAMAXIPort(
                    port.data_width,
                    port.address_width + log2_int(port.data_width//8))
                axi2native = LiteDRAMAXI2Native(axi_port, port)
                self.submodules += axi2native
                self.submodules.wishbone_bridge = LiteDRAMWishbone2AXI(self.l2_cache.slave, axi_port)
            else:
                self.submodules.wishbone_bridge = LiteDRAMWishbone2Native(self.l2_cache.slave, port)

    def do_finalize(self):
        if not self.integrated_main_ram_size:
            if not self._sdram_phy:
                raise FinalizeError("Need to call SoCSDRAM.register_sdram()")

            # Arbitrate wishbone interfaces to the DRAM
            if len(self._wb_sdram_ifs) != 0:
                self.submodules.wb_sdram_con = wishbone.Arbiter(self._wb_sdram_ifs, self._wb_sdram)
        SoCCore.do_finalize(self)


soc_sdram_args = soc_core_args
soc_sdram_argdict = soc_core_argdict
