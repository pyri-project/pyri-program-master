from pyri.plugins.service_node_launch import ServiceNodeLaunch, PyriServiceNodeLaunchFactory


launches = [
    ServiceNodeLaunch("program_master", "pyri.program_master", "pyri.program_master",default_devices=[("pyri_program_master","program_master")])
]

class ProgramMasterLaunchFactory(PyriServiceNodeLaunchFactory):
    def get_plugin_name(self):
        return "pyri.program_master"

    def get_service_node_launch_names(self):
        return ["program_master"]

    def get_service_node_launches(self):
        return launches

def get_service_node_launch_factory():
    return ProgramMasterLaunchFactory()

        
