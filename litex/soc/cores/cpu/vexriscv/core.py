import os

from migen import *

from litex.soc.interconnect import wishbone
from litex.soc.interconnect.csr import AutoCSR, CSRStatus, CSRStorage

class VexRiscv(Module, AutoCSR):
    def __init__(self, platform, cpu_reset_address, cpu_debugging=False):
        self.ibus = i = wishbone.Interface()
        self.dbus = d = wishbone.Interface()

        self.interrupt = Signal(32)

        i_debug_bus_cmd_payload_wr = Signal()
        i_debug_bus_cmd_payload_address = Signal(8)
        i_debug_bus_cmd_payload_data = Signal(32)
        o_debug_bus_cmd_ready = Signal()
        o_debug_bus_rsp_data = Signal(32)
        debug_start_cmd = Signal()

        if cpu_debugging:
            debug_data_is_ready = Signal()
            self.debug_core_reg = CSRStorage(32, name="debug_core", write_from_dev=True)
            self.debug_data_reg = CSRStorage(32, name="debug_data", write_from_dev=True)
            self.debug_refresh_reg = CSRStorage(8, name="debug_refresh_reg")
            self.debug_packet_counter = CSRStatus(32, name="debug_packet_counter")

            self.sync += [
                If(self.debug_core_reg.re,
                    i_debug_bus_cmd_payload_address.eq(0x00),
                    i_debug_bus_cmd_payload_data.eq(self.debug_core_reg.storage),

                    i_debug_bus_cmd_payload_wr.eq(1),
                    debug_start_cmd.eq(1),
                    self.debug_packet_counter.status.eq(self.debug_packet_counter.status + 1),

                    self.debug_core_reg.we.eq(0),
                    self.debug_data_reg.we.eq(0)
                ).Elif(self.debug_data_reg.re,
                    i_debug_bus_cmd_payload_address.eq(0x04),
                    i_debug_bus_cmd_payload_data.eq(self.debug_data_reg.storage),

                    i_debug_bus_cmd_payload_wr.eq(1),
                    debug_start_cmd.eq(1),
                    self.debug_packet_counter.status.eq(self.debug_packet_counter.status + 1),

                    self.debug_core_reg.we.eq(0),
                    self.debug_data_reg.we.eq(0)
                ).Elif(self.debug_refresh_reg.re,
                    # Python array slices appear to be semi-inclusive, in that they
                    # only include the first element and not the last, unlike Verilog.
                    # They're also backwards compared to Verilog.
                    # Therefore, storage[0:8] in Python will get mapped to storage[7:0]
                    # in Verilog.
                    i_debug_bus_cmd_payload_address.eq(self.debug_refresh_reg.storage),
                    i_debug_bus_cmd_payload_data.eq(0), # Data can be anything, since it's a "read"

                    # Start a "Read" command with the "Write" bit set to 0
                    i_debug_bus_cmd_payload_wr.eq(0),
                    debug_start_cmd.eq(1),

                    # The data will be ready on the next clock cycle
                    debug_data_is_ready.eq(1),

                    self.debug_core_reg.we.eq(0),
                    self.debug_data_reg.we.eq(0)
                ).Elif(debug_data_is_ready == 1,
                    If(o_debug_bus_cmd_ready == 1,
                        i_debug_bus_cmd_payload_wr.eq(0),
                        debug_data_is_ready.eq(0),
                        debug_start_cmd.eq(0),
                        self.debug_packet_counter.status.eq(self.debug_packet_counter.status + 1),
                        If(self.debug_refresh_reg.storage == 0x00,
                            self.debug_core_reg.dat_w.eq(o_debug_bus_rsp_data),
                            self.debug_core_reg.we.eq(1),
                            self.debug_data_reg.we.eq(0)
                        ).Elif(self.debug_refresh_reg.storage == 0x04,
                            self.debug_data_reg.dat_w.eq(o_debug_bus_rsp_data),
                            self.debug_core_reg.we.eq(0),
                            self.debug_data_reg.we.eq(1)
                        ).Else(
                            # Invalid address -- echo it back to the user.
                            self.debug_core_reg.dat_w.eq(0xfeedbeef),
                            self.debug_data_reg.dat_w.eq(self.debug_refresh_reg.storage),
                            self.debug_core_reg.we.eq(1),
                            self.debug_data_reg.we.eq(1)
                        )
                    )
                ).Elif(o_debug_bus_cmd_ready == 1,
                    # Default case: Don't start a new command, leave everything as-is.
                    debug_data_is_ready.eq(0),
                    debug_start_cmd.eq(0),
                    self.debug_data_reg.we.eq(0),
                    self.debug_core_reg.we.eq(0)
                )
            ]

            kwargs = {
                'i_debugReset': ResetSignal(),
                'i_debug_bus_cmd_valid': debug_start_cmd,
                'i_debug_bus_cmd_payload_wr': i_debug_bus_cmd_payload_wr,
                'i_debug_bus_cmd_payload_address': i_debug_bus_cmd_payload_address,
                'i_debug_bus_cmd_payload_data': i_debug_bus_cmd_payload_data,
                'o_debug_bus_cmd_ready': o_debug_bus_cmd_ready,
                'o_debug_bus_rsp_data': o_debug_bus_rsp_data
            }
            source_file = "VexRiscv-Debug.v"
        else:
            kwargs = {}
            source_file = "VexRiscv.v"

        self.specials += Instance("VexRiscv",
                                  i_clk=ClockSignal(),
                                  i_reset=ResetSignal(),

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
                                  i_dBusWishbone_ERR=d.err,
                                  **kwargs)

        # add Verilog sources
        vdir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "verilog")
        platform.add_sources(os.path.join(vdir), source_file)
        platform.add_verilog_include_path(vdir)
