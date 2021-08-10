import sys
import RobotRaconteur as RR
RRN = RR.RobotRaconteurNode.s
import RobotRaconteurCompanion as RRC
from .pyri_program_master import PyriProgramMaster
import argparse
from RobotRaconteurCompanion.Util.InfoFileLoader import InfoFileLoader
from RobotRaconteurCompanion.Util.AttributesUtil import AttributesUtil
from pyri.plugins import robdef as robdef_plugins
from pyri.util.service_setup import PyriServiceNodeSetup

def main():
   
    with PyriServiceNodeSetup("tech.pyri.program_master",59906, \
        display_description="PyRI Program Master Service", \
        default_info=(__package__,"pyri_program_master_default_info.yml"), \
        register_plugin_robdef=True, device_manager_autoconnect=False, \
        distribution_name="pyri-program-master") as service_node_setup:

        extra_imports = RRN.GetRegisteredServiceTypes()

        program_master = PyriProgramMaster(service_node_setup.device_manager, device_info=service_node_setup.device_info_struct, node = RRN) 

        service_ctx = service_node_setup.register_service("program_master","tech.pyri.program_master.PyriProgramMaster",program_master)

        for e in extra_imports:
            service_ctx.AddExtraImport(e)
       
        service_node_setup.wait_exit()

        program_master.close()

if __name__ == "__main__":
    sys.exit(main() or 0)