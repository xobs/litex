import os

from migen import *

from litex.soc.interconnect import wishbone
from litex.soc.interconnect.csr import AutoCSR, CSRStatus, CSRStorage

class VexRiscv(Module, AutoCSR):
    def __init__(self, platform, cpu_reset_address, variant=None):
        assert variant in (None, "debug"), "Unsupported variant %s" % variant
        self.ibus = i = wishbone.Interface()
        self.dbus = d = wishbone.Interface()

        self.interrupt = Signal(32)

        # Output reset signal -- set to 1 when CPU reset is asserted
        self.debug_reset = Signal()

        if variant == None:
            cpu_reset = ResetSignal()
            cpu_args = {}
            cpu_filename = "VexRiscv.v"
        elif variant == "debug":
            cpu_reset = Signal()
            cpu_args = {}
            cpu_filename = "VexRiscv-Debug.v"


            self.i_cmd_valid = Signal()
            self.i_cmd_payload_wr = Signal()
            self.i_cmd_payload_address = Signal(8)
            self.i_cmd_payload_data = Signal(32)
            self.o_cmd_ready = Signal()
            self.o_rsp_data = Signal(32)
            self.o_resetOut = Signal()

            self.transfer_complete = Signal()
            self.transfer_in_progress = Signal()
            self.transfer_wait_for_ack = Signal()

            self.debug_bus = wishbone.Interface()

            self.sync += [
                # CYC is held high for the duration of the transfer.
                # STB is kept high when the transfer finishes (write)
                # or the master is waiting for data (read), and stays
                # there until ACK, ERR, or RTY are asserted.

                self.debug_bus.dat_r.eq(self.o_rsp_data),
            ]

            # Fill in i_cmd_payload_data based on self.debug_bus.sel
            # Once 
            # Acknowledge the packet that just arrived (if any)
            # by flipping ACK HIGH for one cycle.
            self.sync += [
                If((self.debug_bus.stb & self.debug_bus.cyc) & (~self.transfer_in_progress) & (~self.transfer_complete) & (~self.transfer_wait_for_ack),
                    self.i_cmd_payload_data.eq(self.debug_bus.dat_w),
                    self.i_cmd_payload_address.eq((self.debug_bus.adr[0:6] << 2) | 0),
                    self.i_cmd_payload_wr.eq(self.debug_bus.we),
                    self.i_cmd_valid.eq(1),
                    self.transfer_in_progress.eq(1),
                    self.transfer_complete.eq(0),
                    self.debug_bus.ack.eq(0)
                ).Elif(self.transfer_in_progress,
                    If(self.o_cmd_ready,
                        self.i_cmd_valid.eq(0),
                        self.i_cmd_payload_wr.eq(0),
                        self.transfer_complete.eq(1),
                        self.transfer_in_progress.eq(0)
                    )
                ).Elif(self.transfer_complete,
                    self.transfer_complete.eq(0),
                    self.debug_bus.ack.eq(1),
                    self.transfer_wait_for_ack.eq(1)
                ).Elif(self.transfer_wait_for_ack & ~(self.debug_bus.stb & self.debug_bus.cyc),
                    self.transfer_wait_for_ack.eq(0),
                    self.debug_bus.ack.eq(0)
                )
            ]

            cpu_reset.eq((~i.cyc & ~d.cyc & ~d.stb & ~i.stb &
                            self.o_resetOut) | ResetSignal()),

            cpu_args.update({
                "i_debugReset": ResetSignal(),
                "i_debug_bus_cmd_valid": self.i_cmd_valid,
                "i_debug_bus_cmd_payload_wr": self.i_cmd_payload_wr,
                "i_debug_bus_cmd_payload_address": self.i_cmd_payload_address,
                "i_debug_bus_cmd_payload_data": self.i_cmd_payload_data,
                "o_debug_bus_cmd_ready": self.o_cmd_ready,
                "o_debug_bus_rsp_data": self.o_rsp_data,
                "o_debug_resetOut": self.o_resetOut
            })

        self.specials += Instance("VexRiscv",
                **cpu_args,

                i_clk=ClockSignal(),
                i_reset=cpu_reset,

                i_externalResetVector=cpu_reset_address,
                i_externalInterruptArray=self.interrupt,
                i_timerInterrupt=0,

                o_iBusWishbone_ADR=i.adr,
                o_iBusWishbone_DAT_MOSI=i.dat_w,
                o_iBusWishbone_SEL=i.sel,
                o_iBusWishbone_CYC=i.cyc,
                o_iBusWishbone_STB=i.stb,
                o_iBusWishbone_WE=i.we,
                o_iBusWishbone_CTI=i.cti,
                o_iBusWishbone_BTE=i.bte,
                i_iBusWishbone_DAT_MISO=i.dat_r,
                i_iBusWishbone_ACK=i.ack,
                i_iBusWishbone_ERR=i.err,

                o_dBusWishbone_ADR=d.adr,
                o_dBusWishbone_DAT_MOSI=d.dat_w,
                o_dBusWishbone_SEL=d.sel,
                o_dBusWishbone_CYC=d.cyc,
                o_dBusWishbone_STB=d.stb,
                o_dBusWishbone_WE=d.we,
                o_dBusWishbone_CTI=d.cti,
                o_dBusWishbone_BTE=d.bte,
                i_dBusWishbone_DAT_MISO=d.dat_r,
                i_dBusWishbone_ACK=d.ack,
                i_dBusWishbone_ERR=d.err)

        # add verilog sources
        self.add_sources(platform, cpu_filename)

    @staticmethod
    def add_sources(platform, cpu_filename):
        vdir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "verilog")
        platform.add_sources(os.path.join(vdir), cpu_filename)
        platform.add_verilog_include_path(vdir)
