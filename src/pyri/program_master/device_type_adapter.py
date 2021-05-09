from pyri.plugins.device_type_adapter import PyriDeviceTypeAdapterExtendedState, \
    PyriDeviceTypeAdapter, PyriDeviceTypeAdapterPluginFactory
from typing import List, Dict, Any, NamedTuple
import RobotRaconteur as RR

class ProgramMaster_TypeAdapter(PyriDeviceTypeAdapter):
    """Adapter for tech.pyri.program_master.PyriProgramMaster"""

    def __init__(self, client_subscription, node):
        self._sub: "RobotRaconteur.ServiceSubscription" = client_subscription
        self._state_sub = self._sub.SubscribeWire("program_state")
        self._state_sub.InValueLifespan = 0.5
        self._node = node
        self._program_consts = None

    async def get_extended_device_infos(self, timeout) -> Dict[str,RR.VarValue]:

        return dict()

    async def get_extended_device_states(self, timeout) -> Dict[str,PyriDeviceTypeAdapterExtendedState]:
        res, program_state, _ = self._state_sub.TryGetInValue()
        if not res:
            return dict()

        if self._program_consts is None:
            res, default_client = self._sub.TryGetDefaultClient()
            if res:
                self._program_consts = self._node.GetConstants("tech.pyri.program_master",default_client)

        display_flags = []
        ready = False
        error = True
        

        if self._program_consts is not None:
            state_flags_enum = self._program_consts['PyriProgramStateFlags']
            for flag_name, flag_code in state_flags_enum.items():
                if flag_code & program_state.program_state_flags != 0:
                    display_flags.append(flag_name)
            
            ready = program_state.program_state_flags & self._program_consts['PyriProgramStateFlags']['ready'] != 0
            error = program_state.program_state_flags & self._program_consts['PyriProgramStateFlags']['error'] !=0
        else:
            display_flags ["pyri_internal_error"]

        p_value = PyriDeviceTypeAdapterExtendedState(
            "tech.pyri.program_master.PyriProgramState",
            display_flags,
            RR.VarValue(program_state, 'tech.pyri.program_master.PyriProgramState'), 
            ready, 
            error, 
            program_state.seqno
        )

        return {"tech.pyri.program_master.PyriProgramState": p_value}

class PyriProgramMasterTypeAdapterPluginFactory(PyriDeviceTypeAdapterPluginFactory):
    
    def get_plugin_name(self):
        return "pyri-robotics"

    def get_robotraconteur_types(self) -> List[str]:
        return ["tech.pyri.program_master.PyriProgramMaster"]

    def create_device_type_adapter(self, robotraconteur_type: str, client_subscription: Any, node) -> PyriDeviceTypeAdapter:

        if robotraconteur_type == "tech.pyri.program_master.PyriProgramMaster":
            return ProgramMaster_TypeAdapter(client_subscription,node)
        assert False, "Invalid robotraconteur_type device type adapter requested"

def get_device_type_adapter_factory():
    return PyriProgramMasterTypeAdapterPluginFactory()