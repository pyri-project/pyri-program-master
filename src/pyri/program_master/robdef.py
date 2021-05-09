from typing import List
from RobotRaconteurCompanion.Util import RobDef as robdef_util
from pyri.plugins.robdef import PyriRobDefPluginFactory

class ProgramMasterRobDefPluginFactory(PyriRobDefPluginFactory):
    def __init__(self):
        super().__init__()

    def get_plugin_name(self):
        return "pyri-program-master"

    def get_robdef_names(self) -> List[str]:
        return ["tech.pyri.program_master"]

    def  get_robdefs(self) -> List[str]:
        return get_program_master_robdef()

def get_robdef_factory():
    return ProgramMasterRobDefPluginFactory()

def get_program_master_robdef():
    return robdef_util.get_service_types_from_resources(__package__,["tech.pyri.program_master.robdef"])